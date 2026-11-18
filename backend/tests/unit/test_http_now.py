"""HTTP 계층 중 뼈대 상태에서도 확인할 수 있는 것 (DB, deps 구현 없이).

- Dockerfile 이 모든 프록시를 믿지 않는다
- 운영(ENV=prod)에서 짧은 관리자 키로는 시작하지 않는다
- 관리자 키 검사(AdminRoute)가 본문 해석보다 먼저, 한 번만 돈다
- Swagger 에 X-Admin-Key 입력칸이 보인다
- Content-Length 를 안전하게 읽는다
나머지 HTTP 계층 테스트는 test_http_layer.py (단계 9 뒤에 켠다).
"""

from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.requests import Request

from app.api import admin_route, deps
from app.config import get_settings
from app.core.errors import AppError, install_handlers
from app.core.http import declared_length
from app.main import create_app


@pytest.fixture(autouse=True)
def _fresh_settings():
    yield
    get_settings.cache_clear()


def _make_app(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, str(v))
    get_settings.cache_clear()
    return create_app()


# --- 시작 검사, 배포 설정 ---


def test_dockerfile_does_not_trust_every_proxy():
    dockerfile = Path(__file__).resolve().parents[2] / "Dockerfile"
    cmd = [ln for ln in dockerfile.read_text(encoding="utf-8").splitlines() if ln.startswith("CMD")]
    assert cmd and "--forwarded-allow-ips" not in cmd[0]  # "*" 면 헤더 위조로 잠금, 요청 제한을 피할 수 있다


def test_prod_refuses_a_short_admin_key(monkeypatch):
    with pytest.raises(RuntimeError, match="32"):
        _make_app(monkeypatch, ENV="prod", ADMIN_KEY="short")


@pytest.mark.parametrize("key", ["", "k" * 32])
def test_prod_starts_with_empty_or_long_key(monkeypatch, key):
    assert _make_app(monkeypatch, ENV="prod", ADMIN_KEY=key)  # 비어 있으면 관리자 API 가 꺼진 상태로 뜬다


def test_local_allows_short_key(monkeypatch):
    assert _make_app(monkeypatch, ENV="local", ADMIN_KEY="short")


# --- 관리자 키 검사 순서 ---


class Body(BaseModel):
    name: str


def _admin_test_app(monkeypatch, calls: list):
    """AdminRoute 를 쓰는 작은 앱. require_admin 은 키가 'ok' 일 때만 통과하는 가짜로 바꾼다."""

    def fake_require_admin(request, key):
        calls.append(key)
        if key != "ok":
            raise AppError("UNAUTHORIZED", "관리자 키가 맞지 않습니다.")

    monkeypatch.setattr(deps, "require_admin", fake_require_admin)
    app = FastAPI()
    install_handlers(app)
    r = APIRouter(route_class=admin_route.AdminRoute)

    @r.put("/steps")
    def put_steps(body: Body):
        return {"name": body.name}

    app.include_router(r)
    return TestClient(app)


def test_admin_key_is_checked_before_body_parsing(monkeypatch):
    c = _admin_test_app(monkeypatch, [])
    r = c.put("/steps", content="{broken", headers={"Content-Type": "application/json"})
    assert (r.status_code, r.json()["error"]["code"]) == (401, "UNAUTHORIZED")  # 400 이 아니라 401
    r = c.put("/steps", content="{broken", headers={"Content-Type": "application/json", "X-Admin-Key": "ok"})
    assert (r.status_code, r.json()["error"]["code"]) == (400, "INVALID_INPUT")  # 키가 맞으면 그다음 본문 검사


def test_admin_key_is_checked_once_per_request(monkeypatch):
    calls = []
    c = _admin_test_app(monkeypatch, calls)
    assert c.put("/steps", json={"name": "a"}, headers={"X-Admin-Key": "ok"}).json() == {"name": "a"}
    assert calls == ["ok"]  # 실패 계수가 두 번 세어지지 않는다


def test_real_admin_router_runs_require_admin_first():
    # 실제 관리자 라우터에서도 키 검사(require_admin, BE-10)가 본문 해석보다 먼저 돈다: 깨진 JSON 이어도 키가 없으면 401
    c = TestClient(create_app())
    r = c.put("/api/v1/admin/walk-routes/1/steps", content="{broken", headers={"Content-Type": "application/json"})
    assert (r.status_code, r.json()["error"]["code"]) == (401, "UNAUTHORIZED")


def test_swagger_shows_admin_key_input():
    spec = TestClient(create_app()).get("/openapi.json").json()
    schemes = spec["components"]["securitySchemes"]
    assert any(v.get("type") == "apiKey" and v.get("name") == "X-Admin-Key" for v in schemes.values())
    assert spec["paths"]["/api/v1/admin/me"]["get"].get("security")
    assert "security" not in spec["paths"]["/api/v1/places"]["get"]  # 공개 API 에는 없다


# --- Content-Length ---


def _req(value):
    headers = [] if value is None else [(b"content-length", value.encode())]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers, "query_string": b""})


@pytest.mark.parametrize("value,expected", [(None, 0), ("0", 0), ("123", 123), ("abc", None), ("-1", None), ("1.5", None), ("", None)])
def test_declared_length(value, expected):
    assert declared_length(_req(value)) == expected


def test_csp_report_with_bad_content_length_is_204_not_500():
    c = TestClient(create_app())
    assert c.post("/csp-report", content=b"{}", headers={"Content-Length": "abc"}).status_code in (204, 400)
