"""GET /health (BE-12). DB 없이 실행된다.

- DB 가 꺼진 경우: 아무도 듣지 않는 포트로 실제로 접속해 503 을 확인한다 (완료 기준: DB 를 끄면 503)
- DB 가 켜진 경우: get_engine 을 가짜로 바꿔 200 을 확인한다. 실제 DB 로는 tests/integration/test_public_api.py 에서 본다
"""

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.api import health as health_api
from app.config import APP_VERSION, get_settings
from app.db import reset_engine
from app.main import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def db_down(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://nobody:x@127.0.0.1:1/none")
    get_settings.cache_clear()
    reset_engine()
    yield
    get_settings.cache_clear()
    reset_engine()


class _FakeConn:
    def __init__(self, sqls: list[str]):
        self.sqls = sqls

    def execute(self, stmt):
        self.sqls.append(str(stmt))


class _FakeEngine:
    def __init__(self):
        self.sqls: list[str] = []

    @contextmanager
    def begin(self):
        yield _FakeConn(self.sqls)


def test_db_down_is_503(client, db_down):
    r = client.get("/health")
    assert r.status_code == 503
    assert r.json() == {"status": "error", "db": "unavailable", "version": APP_VERSION}
    assert r.headers["cache-control"] == "no-store"
    assert client.head("/health").status_code == 503


def test_db_up_is_200_with_short_timeout(client, monkeypatch):
    fake = _FakeEngine()
    monkeypatch.setattr(health_api, "get_engine", lambda: fake)
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "db": "ok", "version": APP_VERSION}
    assert r.headers["cache-control"] == "no-store"
    assert client.head("/health").status_code == 200
    assert fake.sqls[:2] == ["SET LOCAL statement_timeout = 1000", "SELECT 1"]  # SET 이 아니라 SET LOCAL


def test_db_error_message_is_not_logged(client, db_down, caplog):
    client.get("/health")
    logged = " ".join(r.getMessage() for r in caplog.records if r.name == "health")
    assert "health_db_unavailable OperationalError" in logged
    assert "127.0.0.1" not in logged and "nobody" not in logged
