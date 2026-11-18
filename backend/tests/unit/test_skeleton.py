"""뼈대 확인: 앱이 뜨고, 라우터가 등록되어 있고, 화면 파일과 오류 형식이 맞는지 (DB 없이).

API 7개는 모두 구현됐다 (BE-11, BE-16). 501 검사는 없앴고, 기능 테스트는 tests/integration 에 있다.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

client = TestClient(create_app())

# 관리자 API 3개가 등록돼 있고 키 검사가 먼저 도는지 본다. 기능은 tests/integration/test_admin_api.py (BE-16)
ROUTES = [
    ("GET", "/api/v1/admin/me"),
    ("PUT", "/api/v1/admin/walk-routes/1/steps"),
    ("PATCH", "/api/v1/admin/walk-route-steps/1"),
]


# /health 는 DB 를 확인하므로(BE-12) tests/unit/test_health.py 로 옮겼다


@pytest.mark.parametrize("method,path", ROUTES)
def test_admin_routes_registered_and_need_key(method, path):
    # 관리자 키 검사(BE-10, BE-13)가 먼저 돌아서 키 없이는 401
    r = client.request(method, path, json={} if method in ("PUT", "PATCH") else None)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize("path", ["/", "/place.html", "/guide.html", "/admin.html", "/about.html", "/css/style.css", "/js/api.js"])
def test_frontend_served(path):
    r = client.get(path)
    assert r.status_code == 200


def test_frontend_missing_file_is_404_page():
    r = client.get("/nope.html")
    assert r.status_code == 404
    assert "없는 화면입니다" in r.text


def test_api_unknown_path_is_json_404():
    r = client.get("/api/v1/nope")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_api_wrong_method_is_json_405():
    r = client.post("/api/v1/places")
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_validation_error_is_400_invalid_input():
    r = client.get("/api/v1/places", params={"limit": 0})
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "INVALID_INPUT"
    assert err["details"][0] == {"field": "query.limit", "reason": "out_of_range", "message": err["details"][0]["message"]}


def test_frontend_headers():
    r = client.get("/guide.html")
    assert r.headers["cache-control"] == "no-cache"
    # 개발(ENV=local) 기본값은 Report-Only: 막지 않고 보고만
    assert "worker-src 'self' blob:" in r.headers["content-security-policy-report-only"]
    assert "content-security-policy" not in r.headers
    assert client.get("/js/api.js").headers["cache-control"] == "no-cache"


def _app_with(monkeypatch, **env):
    from app.config import get_settings

    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    try:
        return TestClient(create_app())
    finally:
        get_settings.cache_clear()


def test_csp_enforced_in_prod(monkeypatch):
    c = _app_with(monkeypatch, ENV="prod")
    r = c.get("/index.html")
    assert "content-security-policy" in r.headers
    assert "content-security-policy-report-only" not in r.headers


def test_csp_mode_override(monkeypatch):
    assert "content-security-policy" in _app_with(monkeypatch, CSP_MODE="enforce").get("/").headers
    off = _app_with(monkeypatch, CSP_MODE="off").get("/").headers
    assert "content-security-policy" not in off and "content-security-policy-report-only" not in off


def test_csp_report_is_logged(caplog):
    body = {
        "csp-report": {
            "document-uri": "http://localhost:8000/guide.html?id=1",
            "effective-directive": "img-src",
            "blocked-uri": "https://evil.example/x.png?token=1",
            "disposition": "report",
        }
    }
    with caplog.at_level("WARNING", logger="csp"):
        r = client.post("/csp-report", content=__import__("json").dumps(body), headers={"Content-Type": "application/csp-report"})
    assert r.status_code == 204
    rec = next(x for x in caplog.records if x.getMessage().startswith("csp_violation"))
    assert rec.directive == "img-src"
    assert rec.blocked == "https://evil.example/x.png"  # 쿼리 문자열은 남기지 않는다
    assert rec.page == "guide.html"


def test_csp_report_ignores_garbage():
    assert client.post("/csp-report", content=b"not json").status_code == 204
    assert client.post("/csp-report", content=b"x" * 20000).status_code == 204


def test_csp_report_cannot_forge_log_lines(caplog):
    body = {
        "csp-report": {
            "document-uri": "http://x/a.html",
            "effective-directive": "img-src\nINFO:fake",
            "blocked-uri": "https://e.example/x\r\nINFO:fake log line",
        }
    }
    with caplog.at_level("WARNING", logger="csp"):
        client.post("/csp-report", content=__import__("json").dumps(body))
    msg = next(x for x in caplog.records if x.getMessage().startswith("csp_violation")).getMessage()
    assert "\n" not in msg and "\r" not in msg


def test_csp_report_rejects_large_body_by_header(caplog):
    with caplog.at_level("WARNING", logger="csp"):
        r = client.post("/csp-report", content=b"{}", headers={"Content-Length": "999999"})
    assert r.status_code == 204
    assert not [x for x in caplog.records if x.getMessage().startswith("csp_violation")]


def test_http_exception_keeps_status():
    from fastapi import FastAPI, HTTPException

    from app.core.errors import install_handlers

    app = FastAPI()
    install_handlers(app)

    @app.get("/t/{status}")
    def raise_status(status: int):
        raise HTTPException(status)

    c = TestClient(app)
    for status, code in [(401, "UNAUTHORIZED"), (413, "PAYLOAD_TOO_LARGE"), (429, "RATE_LIMITED"), (418, "INTERNAL")]:
        r = c.get(f"/t/{status}")
        assert (r.status_code, r.json()["error"]["code"]) == (500 if status == 418 else status, code)


def test_head_requests():
    # HEAD /health 는 tests/unit/test_health.py 에서 본다
    assert client.head("/api/v1/places").status_code == 405
    assert client.head("/index.html").status_code == 200
