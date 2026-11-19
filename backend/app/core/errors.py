"""오류 코드, AppError, 예외 처리기 (API 명세서 1.11, 설계서 2.6.5).

모든 오류 응답은 {"error": {code, message, request_id, timestamp, details}} 한 가지 모양이다.

DB 연결 실패, 시간 초과는 503 + Retry-After, 그 밖의 예외는 500 (BE-18). 로그에는 DB 접속 문자열을 가린다.
501(NOT_IMPLEMENTED)은 뼈대 전용이라 QA-03 에서 지운다.
검증 오류를 처음부터 명세 형식(400 INVALID_INPUT)으로 내보내서, 프론트 api.js 는 오류 형식 한 가지만 다루면 된다.
"""

import logging
import re
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("app")
RETRY_AFTER_S = "3"
# lock_timeout(55P03), statement_timeout(57014): 다시 시도하면 되는 오류
RETRYABLE_SQLSTATES = {"55P03", "57014"}
_DB_URL = re.compile(r"postgresql(\+\w+)?://[^@\s]+@")

STATUS_BY_CODE = {
    "INVALID_INPUT": 400,
    "UNAUTHORIZED": 401,
    "NOT_FOUND": 404,
    "METHOD_NOT_ALLOWED": 405,
    "CONFLICT": 409,
    "PAYLOAD_TOO_LARGE": 413,
    "UNSUPPORTED_MEDIA": 415,
    "RATE_LIMITED": 429,
    "INTERNAL": 500,
    "NOT_IMPLEMENTED": 501,  # 뼈대 전용. 구현이 끝나면 지운다
    "SERVICE_UNAVAILABLE": 503,
}


CODE_BY_STATUS = {v: k for k, v in STATUS_BY_CODE.items()}
MESSAGE_BY_CODE = {
    "INVALID_INPUT": "입력값을 확인하세요.",
    "UNAUTHORIZED": "인증이 필요합니다.",
    "NOT_FOUND": "요청한 주소를 찾을 수 없습니다.",
    "METHOD_NOT_ALLOWED": "지원하지 않는 메서드입니다.",
    "CONFLICT": "다른 곳에서 먼저 바뀌었습니다.",
    "PAYLOAD_TOO_LARGE": "요청 본문은 64KB 이하여야 합니다.",
    "UNSUPPORTED_MEDIA": "본문은 application/json 이어야 합니다.",
    "RATE_LIMITED": "요청이 너무 많습니다. 잠시 후 다시 시도하세요.",
    "INTERNAL": "서버 오류가 발생했습니다.",
    "NOT_IMPLEMENTED": "아직 구현하지 않았습니다.",
    "SERVICE_UNAVAILABLE": "잠시 후 다시 시도하세요.",
}


class AppError(Exception):
    def __init__(self, code: str, message: str, details: list[dict] | None = None, headers: dict[str, str] | None = None):
        super().__init__(message)
        self.code = code
        self.status = STATUS_BY_CODE[code]
        self.message = message
        self.details = details or []
        self.headers = headers or {}


def invalid(field: str, reason: str, message: str) -> AppError:
    """400 INVALID_INPUT, details 한 건. 서비스에서 raise invalid(...) 로 쓴다 (돌려주기만 하고 던지지 않는다)."""
    return AppError("INVALID_INPUT", MESSAGE_BY_CODE["INVALID_INPUT"], [{"field": field, "reason": reason, "message": message}])


def not_found(what: str) -> AppError:
    """404 NOT_FOUND. what 은 "장소", "경로" 처럼 찾지 못한 대상."""
    return AppError("NOT_FOUND", f"{what}을(를) 찾을 수 없습니다.")


def error_response(
    request: Request, code: str, message: str, details: list[dict] | None = None, headers: dict[str, str] | None = None
) -> JSONResponse:
    body = {
        "error": {
            "code": code,
            "message": message,
            "request_id": getattr(request.state, "request_id", "-"),
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "details": details or [],
        }
    }
    return JSONResponse(body, status_code=STATUS_BY_CODE[code], headers={"Cache-Control": "no-store", **(headers or {})})


# --- Pydantic 검증 오류 → details[].reason (API 명세서 1.11 reason 표) ---
_REASON_BY_TYPE = {
    "missing": "required",
    "extra_forbidden": "unknown_field",
    "string_too_short": "too_short",
    "string_too_long": "too_long",
    "too_short": "too_short",
    "too_long": "too_long",
    "greater_than": "out_of_range",
    "greater_than_equal": "out_of_range",
    "less_than": "out_of_range",
    "less_than_equal": "out_of_range",
    "invalid_geometry": "invalid_geometry",
}


def _field_path(loc: tuple[Any, ...]) -> str:
    """("body", "steps", 0, "instruction") → "steps[0].instruction", ("query", "limit") → "query.limit" """
    head, rest = loc[0], list(loc[1:])
    out = "" if head == "body" else str(head)
    for part in rest:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += ("." if out else "") + str(part)
    return out or str(head)


def _reason(err: dict) -> str:
    t = err["type"]
    loc = [str(x) for x in err["loc"]]
    if t == "missing" and "camera" in loc and loc[-1] in ("bearing", "pitch", "zoom"):
        return "incomplete_camera"
    if "location" in loc and t not in ("missing", "extra_forbidden"):
        return "invalid_geometry"
    return _REASON_BY_TYPE.get(t, "invalid_type")


def mask(msg: str) -> str:
    """postgresql://계정:비밀번호@ 부분을 가린다. 오류 메시지를 로그에 남기기 전에 쓴다."""
    return _DB_URL.sub("postgresql://***@", msg)


def _rid(request: Request) -> str:
    """로그와 오류 응답을 같은 요청 ID 로 이어 찾을 수 있게 한다."""
    return getattr(request.state, "request_id", "-")


def _unavailable(request: Request) -> JSONResponse:
    return error_response(request, "SERVICE_UNAVAILABLE", MESSAGE_BY_CODE["SERVICE_UNAVAILABLE"], headers={"Retry-After": RETRY_AFTER_S})


def _internal(request: Request) -> JSONResponse:
    return error_response(request, "INTERNAL", MESSAGE_BY_CODE["INTERNAL"])


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        return error_response(request, exc.code, exc.message, exc.details, exc.headers)

    @app.exception_handler(NotImplementedError)
    async def _todo(request: Request, exc: NotImplementedError):
        return error_response(request, "NOT_IMPLEMENTED", str(exc) or "아직 구현하지 않았습니다.")

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        details = [{"field": _field_path(tuple(e["loc"])), "reason": _reason(e), "message": e["msg"]} for e in exc.errors()]
        return error_response(request, "INVALID_INPUT", "입력값을 확인하세요.", details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        # 상태 코드는 그대로 두고 오류 형식만 맞춘다. 표에 없는 상태 코드(예: 418)만 500 INTERNAL
        code = CODE_BY_STATUS.get(exc.status_code)
        if code is None:
            return error_response(request, "INTERNAL", "서버 오류가 발생했습니다.")
        return error_response(
            request, code, MESSAGE_BY_CODE.get(code, "요청을 처리하지 못했습니다."), headers=getattr(exc, "headers", None)
        )

    # --- DB 오류, 그 밖의 예외 (BE-18). 응답에는 오류 내용을 넣지 않고 로그에만 (가려서) 남긴다 ---

    @app.exception_handler(PoolTimeoutError)
    @app.exception_handler(OperationalError)
    async def _db_unavailable(request: Request, exc: Exception):
        # 연결 실패, 연결 풀 대기 시간 초과, statement_timeout, lock_timeout (psycopg 는 모두 OperationalError 로 온다)
        log.error("db_unavailable", extra={"request_id": _rid(request), "error": mask(str(exc))[:300]})
        return _unavailable(request)

    @app.exception_handler(DBAPIError)
    async def _db_error(request: Request, exc: DBAPIError):
        sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
        if sqlstate in RETRYABLE_SQLSTATES:
            log.warning("db_timeout", extra={"request_id": _rid(request), "sqlstate": sqlstate})
            return _unavailable(request)
        log.error("db_error", extra={"request_id": _rid(request), "sqlstate": sqlstate, "error": mask(str(exc))[:300]})
        return _internal(request)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        # 맨 바깥(ServerErrorMiddleware)에서 처리돼 보안 헤더 미들웨어를 거치지 않는다. 그래서 응답 형식만 맞춘다
        log.error("unhandled", extra={"request_id": _rid(request), "exc_type": type(exc).__name__, "error": mask(str(exc))[:300]})
        return _internal(request)
