"""GET /health (API 명세서 3.1)."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import APP_VERSION

router = APIRouter(tags=["health"])


@router.api_route("/health", methods=["GET", "HEAD"])  # 모니터링 도구용으로 HEAD 도 받는다
def health():
    # TODO: DB 연결 확인 (SELECT 1). 실패하면 503 {"status": "error", "db": "unavailable"}
    return JSONResponse({"status": "ok", "db": "unchecked", "version": APP_VERSION}, headers={"Cache-Control": "no-store"})
