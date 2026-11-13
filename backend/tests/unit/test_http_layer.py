"""HTTP 계층 단위 테스트 (DB 불필요): 인증 순서, 401/429 잠금, 413/415, 요청 ID, 보안 헤더, 오류 본문 모양.

6차 점검 기준 "401/429 및 요청 ID·보안 헤더 확인"을 DB 없이 자동으로 확인한다.
한계 계수기 클래스 자체는 test_domain.py 가 보고, DB 에 닿는 요청(조회, 저장 성공 경로)은 tests/integration 이 맡는다.

출처: 팀원 보완 backend_supplement.patch (27개).
뼈대에서는 deps.py, core/security.py, main.py 미들웨어가 아직 없어서 대부분 501 이 난다. 그래서 파일 전체를 건너뛴다.
백엔드 작성 가이드 단계 9 를 끝내면 아래 pytestmark 줄을 지우고 모두 통과해야 한다 (단계 9 완료 기준).
지금도 통과하는 2개(Dockerfile, 운영 키 길이)는 test_http_now.py 로 옮겼다.
"""

import re

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import MAX_BODY_BYTES, create_app

pytestmark = pytest.mark.skip(reason="백엔드 작성 가이드 단계 9 (deps.py, security.py, main.py 미들웨어) 구현 후 이 줄을 지운다")

KEY = "unit-test-admin-key-0123456789abcdef"
JSON = {"Content-Type": "application/json"}
STEPS_URL = "/api/v1/admin/walk-routes/1/steps"
PATCH_URL = "/api/v1/admin/walk-route-steps/1"
ME_URL = "/api/v1/admin/me"
UNKNOWN_URL = "/api/v1/no-such-path"
ERROR_KEYS = {"code", "message", "request_id", "timestamp", "details"}
SECURITY_HEADERS = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "same-origin", "X-Frame-Options": "DENY"}


@pytest.fixture(autouse=True)
def _fresh_settings():
    yield
    get_settings.cache_clear()


def _make_app(monkeypatch, **env):
    monkeypatch.setenv("ENV", "local")
    monkeypatch.setenv("ADMIN_KEY", KEY)
    for k, v in env.items():
        monkeypatch.setenv(k, str(v))
    get_settings.cache_clear()
    return create_app()


def _client(monkeypatch, **env) -> TestClient:
    return TestClient(_make_app(monkeypatch, **env), raise_server_exceptions=False)


@pytest.fixture
def client(monkeypatch):
    return _client(monkeypatch)


def _assert_error(r, status: int, code: str) -> dict:
    assert r.status_code == status
    body = r.json()["error"]
    assert set(body) == ERROR_KEYS
    assert body["code"] == code
    assert body["request_id"] == r.headers["X-Request-ID"]
    assert r.headers["Cache-Control"] == "no-store"
    return body


# --- 관리자 키: 401, 잠금(429) ---


def test_admin_without_key_is_401(client):
    _assert_error(client.get(ME_URL), 401, "UNAUTHORIZED")


def test_wrong_key_is_401_and_right_key_is_200(client):
    _assert_error(client.get(ME_URL, headers={"X-Admin-Key": "wrong"}), 401, "UNAUTHORIZED")
    ok = client.get(ME_URL, headers={"X-Admin-Key": KEY})
    assert ok.status_code == 200 and ok.json() == {"role": "admin"}
    assert ok.headers["Cache-Control"] == "no-store"


def test_five_wrong_keys_lock_even_the_right_key(client):
    wrong = {"X-Admin-Key": "wrong"}
    assert [client.get(ME_URL, headers=wrong).status_code for _ in range(4)] == [401] * 4
    fifth = client.get(ME_URL, headers=wrong)
    body = _assert_error(fifth, 429, "RATE_LIMITED")
    assert body["details"][0]["reason"] == "locked"
    assert int(fifth.headers["Retry-After"]) > 0
    _assert_error(client.get(ME_URL, headers={"X-Admin-Key": KEY}), 429, "RATE_LIMITED")  # 맞는 키도 막힘


def test_right_key_resets_the_failure_count(client):
    wrong = {"X-Admin-Key": "wrong"}
    assert [client.get(ME_URL, headers=wrong).status_code for _ in range(4)] == [401] * 4
    assert client.get(ME_URL, headers={"X-Admin-Key": KEY}).status_code == 200
    assert [client.get(ME_URL, headers=wrong).status_code for _ in range(4)] == [401] * 4  # 다시 4번까지는 잠기지 않음


def test_app_ignores_x_forwarded_for(client):
    # 앱은 request.client 만 본다. 헤더 값을 바꿔 보내도 같은 IP 로 세어 5번째에 잠긴다.
    # 프록시를 믿을 범위는 uvicorn 설정(Dockerfile, FORWARDED_ALLOW_IPS)이 정한다.
    codes = [client.get(ME_URL, headers={"X-Admin-Key": "wrong", "X-Forwarded-For": f"10.0.0.{i}"}).status_code for i in range(6)]
    assert codes == [401, 401, 401, 401, 429, 429]


# --- 인증은 본문 해석보다 먼저 ---


@pytest.mark.parametrize("method,url", [("PUT", STEPS_URL), ("PATCH", PATCH_URL)], ids=["put", "patch"])
def test_broken_json_without_key_is_401_not_400(client, method, url):
    _assert_error(client.request(method, url, content="{broken", headers=JSON), 401, "UNAUTHORIZED")


@pytest.mark.parametrize("method,url", [("PUT", STEPS_URL), ("PATCH", PATCH_URL)], ids=["put", "patch"])
def test_broken_json_with_key_is_400(client, method, url):
    r = client.request(method, url, content="{broken", headers={**JSON, "X-Admin-Key": KEY})
    _assert_error(r, 400, "INVALID_INPUT")


# --- 413, 415, Content-Length ---


def test_body_over_64kb_is_413(client):
    r = client.put(STEPS_URL, content=b"x" * (MAX_BODY_BYTES + 1), headers={**JSON, "X-Admin-Key": KEY})
    _assert_error(r, 413, "PAYLOAD_TOO_LARGE")


def test_put_without_json_content_type_is_415(client):
    r = client.put(STEPS_URL, content="a=1", headers={"Content-Type": "text/plain", "X-Admin-Key": KEY})
    _assert_error(r, 415, "UNSUPPORTED_MEDIA")


@pytest.mark.parametrize("value", ["abc", "-1", "1.5"])
def test_invalid_content_length_is_400_not_500(client, value):
    body = _assert_error(client.get(ME_URL, headers={"Content-Length": value}), 400, "INVALID_INPUT")
    assert body["details"][0]["field"] == "header.Content-Length"


# --- 요청 횟수 제한 (사유가 locked 와 달라야 프론트가 키를 지우지 않는다) ---


def test_public_rate_limit_returns_429_with_retry_after(monkeypatch):
    c = _client(monkeypatch, RATE_LIMIT_PUBLIC_PER_MIN=3)
    assert [c.get(UNKNOWN_URL).status_code for _ in range(3)] == [404] * 3
    r = c.get(UNKNOWN_URL)
    body = _assert_error(r, 429, "RATE_LIMITED")
    assert body["details"][0]["reason"] == "too_many_requests"
    assert int(r.headers["Retry-After"]) >= 1


def test_admin_rate_limit_is_separate_from_key_lock(monkeypatch):
    c = _client(monkeypatch, RATE_LIMIT_ADMIN_PER_MIN=2)
    assert [c.get(ME_URL, headers={"X-Admin-Key": KEY}).status_code for _ in range(2)] == [200, 200]
    body = _assert_error(c.get(ME_URL, headers={"X-Admin-Key": KEY}), 429, "RATE_LIMITED")
    assert body["details"][0]["reason"] == "too_many_requests"


# --- 요청 ID, 보안 헤더, 오류 본문 ---


def test_request_id_is_echoed_or_generated(client):
    r = client.get(ME_URL, headers={"X-Request-ID": "my-trace-1"})
    assert r.headers["X-Request-ID"] == "my-trace-1"
    assert r.json()["error"]["request_id"] == "my-trace-1"
    assert re.fullmatch(r"[0-9a-f-]{36}", client.get(ME_URL).headers["X-Request-ID"])


def test_request_id_is_cut_to_64_chars(client):
    assert len(client.get(ME_URL, headers={"X-Request-ID": "a" * 200}).headers["X-Request-ID"]) == 64


@pytest.mark.parametrize(
    "call",
    [
        lambda c: c.get(ME_URL),
        lambda c: c.get(UNKNOWN_URL),
        lambda c: c.put(STEPS_URL, content=b"x" * (MAX_BODY_BYTES + 1), headers=JSON),
        lambda c: c.put(STEPS_URL, content="a", headers={"Content-Type": "text/plain"}),
    ],
    ids=["401", "404", "413", "415"],
)
def test_security_headers_are_on_error_responses_too(client, call):
    r = call(client)
    for name, value in SECURITY_HEADERS.items():
        assert r.headers[name] == value
    assert r.headers["X-Request-ID"]


def test_hsts_header_only_in_prod(monkeypatch):
    assert "Strict-Transport-Security" not in _client(monkeypatch).get(UNKNOWN_URL).headers
    assert "Strict-Transport-Security" in _client(monkeypatch, ENV="prod").get(UNKNOWN_URL).headers


def test_unknown_path_and_wrong_method_use_the_standard_error_body(client):
    _assert_error(client.get(UNKNOWN_URL), 404, "NOT_FOUND")
    _assert_error(client.get(STEPS_URL), 405, "METHOD_NOT_ALLOWED")


# --- 운영 시작 검사 ---


def test_prod_with_empty_key_starts_and_admin_api_is_always_401(monkeypatch):
    c = _client(monkeypatch, ENV="prod", ADMIN_KEY="")
    _assert_error(c.get(ME_URL, headers={"X-Admin-Key": "anything"}), 401, "UNAUTHORIZED")
