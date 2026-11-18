"""관리자 키 비교, 실패 잠금(BE-13)과 require_admin(BE-10). DB 없이 실행된다.

키 검사를 통과하면 핸들러까지 간다는 것을 GET /admin/me 의 200 으로 확인한다 (DB 를 쓰지 않는 관리자 API).
요청 ID, 보안 헤더까지 함께 보는 전체 검사는 tests/unit/test_http_layer.py (미들웨어 BE-17 뒤에 켬).
"""

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.core.security import FailureLimiter, key_matches
from app.main import create_app

KEY = "unit-test-admin-key-0123456789abcdef"
ME_URL = "/api/v1/admin/me"


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


@pytest.fixture(autouse=True)
def _fresh_settings():
    yield
    get_settings.cache_clear()


def _client(monkeypatch, **env) -> TestClient:
    monkeypatch.setenv("ENV", "local")
    monkeypatch.setenv("ADMIN_KEY", KEY)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    return TestClient(create_app())


@pytest.fixture()
def client(monkeypatch):
    return _client(monkeypatch)


def _code(r) -> tuple[int, str]:
    return r.status_code, r.json()["error"]["code"]


# ---------- key_matches ----------


def test_key_matches():
    assert key_matches("abc", "abc") and not key_matches("abd", "abc")
    assert not key_matches(None, "abc") and not key_matches("", "abc")
    assert not key_matches("abc", "")  # 설정 키가 비어 있으면 아무것도 통과하지 못한다


# ---------- FailureLimiter ----------


def test_failure_limiter_locks_after_five_and_expires():
    clock = FakeClock()
    lim = FailureLimiter(5, 600, clock)
    assert [lim.fail("1.1.1.1") for _ in range(4)] == [0, 0, 0, 0]
    assert lim.fail("1.1.1.1") == 600
    assert lim.retry_after("1.1.1.1") == 601 and lim.retry_after("2.2.2.2") == 0  # IP 별로 따로 센다
    clock.t = 599.5
    assert lim.retry_after("1.1.1.1") == 1  # 남은 0.5초도 1초로 올림
    clock.t = 600
    assert lim.retry_after("1.1.1.1") == 0


def test_failure_limiter_success_resets_count():
    lim = FailureLimiter(5, 600, FakeClock())
    for _ in range(4):
        lim.fail("ip")
    lim.success("ip")
    assert [lim.fail("ip") for _ in range(4)] == [0, 0, 0, 0]


def test_failure_limiter_reset_clears_locks():
    lim = FailureLimiter(1, 600, FakeClock())
    lim.fail("ip")
    lim.reset()
    assert lim.retry_after("ip") == 0


# ---------- require_admin (AdminRoute 를 거쳐) ----------


def test_without_key_or_wrong_key_is_401(client):
    assert _code(client.get(ME_URL)) == (401, "UNAUTHORIZED")
    assert _code(client.get(ME_URL, headers={"X-Admin-Key": "wrong"})) == (401, "UNAUTHORIZED")


def test_right_key_passes_to_the_handler(client):
    r = client.get(ME_URL, headers={"X-Admin-Key": KEY})
    assert r.status_code == 200 and r.json() == {"role": "admin"}


def test_five_wrong_keys_lock_even_the_right_key(client):
    wrong = {"X-Admin-Key": "wrong"}
    assert [client.get(ME_URL, headers=wrong).status_code for _ in range(4)] == [401] * 4
    fifth = client.get(ME_URL, headers=wrong)
    assert _code(fifth) == (429, "RATE_LIMITED")
    assert fifth.json()["error"]["details"][0]["reason"] == "locked"
    assert int(fifth.headers["Retry-After"]) == 600
    locked = client.get(ME_URL, headers={"X-Admin-Key": KEY})
    assert _code(locked) == (429, "RATE_LIMITED") and int(locked.headers["Retry-After"]) > 0  # 맞는 키도 막힘


def test_right_key_resets_the_failure_count(client):
    wrong = {"X-Admin-Key": "wrong"}
    assert [client.get(ME_URL, headers=wrong).status_code for _ in range(4)] == [401] * 4
    assert client.get(ME_URL, headers={"X-Admin-Key": KEY}).status_code == 200  # 통과 → 계수 지움
    assert [client.get(ME_URL, headers=wrong).status_code for _ in range(4)] == [401] * 4  # 다시 4번까지는 잠기지 않음


def test_x_forwarded_for_does_not_split_the_count(client):
    codes = [client.get(ME_URL, headers={"X-Admin-Key": "wrong", "X-Forwarded-For": f"10.0.0.{i}"}).status_code for i in range(6)]
    assert codes == [401, 401, 401, 401, 429, 429]


def test_broken_json_without_key_is_401_not_400(client):
    r = client.put("/api/v1/admin/walk-routes/1/steps", content="{broken", headers={"Content-Type": "application/json"})
    assert _code(r) == (401, "UNAUTHORIZED")


def test_prod_with_empty_key_is_always_401(monkeypatch):
    c = _client(monkeypatch, ENV="prod", ADMIN_KEY="")
    assert _code(c.get(ME_URL, headers={"X-Admin-Key": "anything"})) == (401, "UNAUTHORIZED")


def test_each_app_has_its_own_lock(monkeypatch):
    a, b = _client(monkeypatch), _client(monkeypatch)
    for _ in range(5):
        a.get(ME_URL, headers={"X-Admin-Key": "wrong"})
    assert a.get(ME_URL).status_code == 429 and b.get(ME_URL).status_code == 401
