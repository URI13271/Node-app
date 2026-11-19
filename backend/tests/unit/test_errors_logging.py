"""503, 500 처리기와 JSON 로그 (BE-18). DB 없이 실행된다.

완료 기준: DB 를 끈 상태에서 조회 API 가 503 JSON 오류 형식. 아무도 듣지 않는 포트로 실제로 접속해 확인한다.
시간 초과, 그 밖의 DB 오류, 예상 못 한 예외는 서비스를 가짜로 바꿔 오류를 일으킨다.
"""

import json
import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.api import places as places_api
from app.config import get_settings
from app.core.errors import mask
from app.core.logging import JsonFormatter, setup_logging
from app.db import reset_engine
from app.main import create_app

ERROR_KEYS = {"code", "message", "request_id", "timestamp", "details"}
SECRET_URL = "postgresql+psycopg://majunggil_app:secret-pass@db.internal:5432/majunggil"


class _PgError(Exception):
    def __init__(self, msg: str, sqlstate: str | None = None):
        super().__init__(msg)
        self.sqlstate = sqlstate


@pytest.fixture()
def client():
    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture()
def db_down(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://nobody:x@127.0.0.1:1/none")
    get_settings.cache_clear()
    reset_engine()
    yield
    get_settings.cache_clear()
    reset_engine()


def _raise_in_search(monkeypatch, exc: Exception):
    def boom(*_args, **_kwargs):
        raise exc

    monkeypatch.setattr(places_api.service, "search", boom)


def _assert_error(r, status: int, code: str) -> dict:
    assert r.status_code == status
    body = r.json()["error"]
    assert set(body) == ERROR_KEYS and body["code"] == code and body["details"] == []
    assert r.headers["Cache-Control"] == "no-store"
    return body


# ---------- 503 ----------


def test_db_down_public_api_is_503(client, db_down):
    """완료 기준. 요청 ID 와 보안 헤더도 붙어 있어야 한다 (미들웨어 안쪽에서 처리됨)."""
    r = client.get("/api/v1/places", headers={"X-Request-ID": "rid-503"})
    body = _assert_error(r, 503, "SERVICE_UNAVAILABLE")
    assert r.headers["Retry-After"] == "3"
    assert body["request_id"] == "rid-503" and r.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.parametrize(
    "exc",
    [
        OperationalError("SELECT 1", {}, _PgError("canceling statement due to statement timeout", "57014")),
        OperationalError("SELECT 1", {}, _PgError("canceling statement due to lock timeout", "55P03")),
        PoolTimeoutError("QueuePool limit of size 5 overflow 5 reached"),
    ],
    ids=["statement_timeout", "lock_timeout", "pool_timeout"],
)
def test_timeouts_are_503(client, monkeypatch, exc):
    _raise_in_search(monkeypatch, exc)
    r = client.get("/api/v1/places")
    _assert_error(r, 503, "SERVICE_UNAVAILABLE")
    assert r.headers["Retry-After"] == "3"


# ---------- 500 ----------


def test_other_db_error_is_500(client, monkeypatch):
    _raise_in_search(monkeypatch, ProgrammingError("SELECT nope", {}, _PgError('relation "nope" does not exist', "42P01")))
    _assert_error(client.get("/api/v1/places"), 500, "INTERNAL")


def test_unexpected_exception_is_500_without_details(client, monkeypatch):
    _raise_in_search(monkeypatch, RuntimeError(f"내부 정보가 담긴 메시지 {SECRET_URL}"))
    r = client.get("/api/v1/places", headers={"X-Request-ID": "rid-500"})
    body = _assert_error(r, 500, "INTERNAL")
    assert body["request_id"] == "rid-500"
    assert "secret-pass" not in r.text and "내부 정보" not in r.text  # 응답에 오류 내용을 넣지 않는다


# ---------- 로그 ----------


def test_db_url_is_masked_in_logs(client, monkeypatch, caplog):
    _raise_in_search(monkeypatch, RuntimeError(f"connect failed: {SECRET_URL}"))
    with caplog.at_level(logging.ERROR, logger="app"):
        client.get("/api/v1/places", headers={"X-Request-ID": "rid-log"})
    rec = next(r for r in caplog.records if r.getMessage() == "unhandled")
    assert rec.exc_type == "RuntimeError" and rec.request_id == "rid-log"  # 응답의 request_id 로 로그를 찾을 수 있다
    assert "secret-pass" not in rec.error and "majunggil_app" not in rec.error and "postgresql://***@" in rec.error


def test_mask():
    assert mask(f"x {SECRET_URL} y") == "x postgresql://***@db.internal:5432/majunggil y"
    assert mask("postgresql://u:p@h/db") == "postgresql://***@h/db"
    assert mask("no url here") == "no url here"


def test_json_formatter_one_line_with_extra_fields():
    rec = logging.LogRecord("access", logging.INFO, __file__, 1, "request", None, None)
    rec.request_id, rec.status, rec.path_pattern = "rid-1", 200, "/api/v1/places/{id}"
    line = JsonFormatter().format(rec)
    assert "\n" not in line
    out = json.loads(line)
    assert (out["level"], out["logger"], out["message"]) == ("INFO", "access", "request")
    assert (out["request_id"], out["status"], out["path_pattern"]) == ("rid-1", 200, "/api/v1/places/{id}")
    assert out["timestamp"].endswith("Z")


def test_json_formatter_keeps_exception_type_only():
    try:
        raise ValueError(f"secret {SECRET_URL}")
    except ValueError:
        import sys

        rec = logging.LogRecord("app", logging.ERROR, __file__, 1, "boom", None, sys.exc_info())
    out = json.loads(JsonFormatter().format(rec))
    assert out["exc_type"] == "ValueError" and "Traceback" not in json.dumps(out) and "secret-pass" not in json.dumps(out)


def test_setup_logging_is_idempotent_and_keeps_other_handlers():
    root = logging.getLogger()
    other = logging.NullHandler()
    root.addHandler(other)
    try:
        setup_logging("INFO")
        setup_logging("INFO")
        ours = [h for h in root.handlers if getattr(h, "_majunggil_json", False)]
        assert len(ours) == 1 and isinstance(ours[0].formatter, JsonFormatter)
        assert other in root.handlers  # pytest 로그 캡처 같은 다른 핸들러는 그대로
        assert logging.getLogger("uvicorn.access").disabled is True
    finally:
        root.removeHandler(other)
