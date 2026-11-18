"""GET /health (API 명세서 3.1, BE-12).

DB 에 SELECT 1 을 보내 확인한다. 실패하면 503 {"status": "error", "db": "unavailable"}.
모니터링 도구가 오래 기다리지 않도록 1초 제한을 건다. 제한은 SET LOCAL 이라 연결을 풀에 돌려줘도 남지 않는다.
"""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import APP_VERSION
from app.db import get_engine
from app.schemas.common import HealthOut

router = APIRouter(tags=["health"])
log = logging.getLogger("health")
HEALTH_TIMEOUT_MS = 1000


def db_ok() -> bool:
    try:
        with get_engine().begin() as conn:
            conn.execute(text(f"SET LOCAL statement_timeout = {HEALTH_TIMEOUT_MS}"))
            conn.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError as e:
        # 예외 메시지에는 호스트, 포트가 들어 있어 종류만 남긴다
        log.warning("health_db_unavailable %s", type(e).__name__)
        return False


@router.api_route("/health", methods=["GET", "HEAD"], response_model=HealthOut)  # 모니터링 도구용으로 HEAD 도 받는다
def health():
    headers = {"Cache-Control": "no-store"}
    if db_ok():
        return JSONResponse({"status": "ok", "db": "ok", "version": APP_VERSION}, headers=headers)
    return JSONResponse({"status": "error", "db": "unavailable", "version": APP_VERSION}, status_code=503, headers=headers)
