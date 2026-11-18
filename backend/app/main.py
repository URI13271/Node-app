"""앱 생성, 미들웨어, 라우터 등록 (설계서 2.4.1).

미들웨어 순서(바깥 → 안): request_id + 접근 로그 + 보안 헤더 → 본문 크기(413), 형식(415) → 요청 횟수(429) (BE-17).
바깥 미들웨어가 안쪽 오류 응답(413, 415, 429)에도 요청 ID 와 보안 헤더를 붙인다.
"""

import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, buildings, health, places, walk_routes
from app.api.deps import client_ip
from app.config import APP_VERSION, get_settings
from app.core.errors import error_response, install_handlers
from app.core.http import declared_length
from app.core.logging import access_log, setup_logging
from app.core.security import FailureLimiter, SlidingWindowLimiter
from app.frontend import FrontendFiles
from app.frontend import router as csp_router

MAX_BODY_BYTES = 64 * 1024  # 요청 본문 상한 (413)
MIN_PROD_ADMIN_KEY_LEN = 32
REQUEST_ID_MAX = 64
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "DENY",
}
BAD_LENGTH = [{"field": "header.Content-Length", "reason": "invalid_type", "message": "Content-Length 는 0 이상의 정수여야 합니다."}]


def _rate_limited(request: Request, wait: int):
    # reason 이 locked(관리자 키 잠금)와 달라야 관리자 화면이 저장한 키를 지우지 않는다 (API 명세서 1.11)
    details = [{"field": "", "reason": "too_many_requests", "message": f"{wait}초 뒤 다시 시도하세요."}]
    return error_response(request, "RATE_LIMITED", "요청이 너무 많습니다. 잠시 후 다시 시도하세요.", details, {"Retry-After": str(wait)})


def create_app() -> FastAPI:
    s = get_settings()
    # 운영에서 짧은 관리자 키로 뜨지 않게 시작 때 막는다. 비어 있으면 관리자 API 가 꺼진 것으로 본다 (config.py ADMIN_KEY 설명)
    if s.is_prod and s.ADMIN_KEY and len(s.ADMIN_KEY) < MIN_PROD_ADMIN_KEY_LEN:
        raise RuntimeError(f"ENV=prod 에서는 ADMIN_KEY 가 {MIN_PROD_ADMIN_KEY_LEN}자 이상이어야 합니다.")
    setup_logging(s.LOG_LEVEL)
    app = FastAPI(
        title="마중길 (majunggil) API",
        version=APP_VERSION,
        description="외곽 여행 3D 길 안내 MVP 백엔드",
        docs_url=None if s.is_prod else "/docs",
        redoc_url=None,
        openapi_url=None if s.is_prod else "/openapi.json",
    )
    install_handlers(app)

    # 관리자 키 실패 잠금 (BE-13): 같은 IP 연속 ADMIN_FAIL_LIMIT 회 실패 → ADMIN_LOCK_S 초. deps.require_admin 이 쓴다
    app.state.admin_fail_limiter = FailureLimiter(s.ADMIN_FAIL_LIMIT, s.ADMIN_LOCK_S)
    # 분당 요청 수 (BE-17): 공개 API 와 /csp-report 는 public, 관리자 API 는 admin. 키 잠금과는 따로 센다
    app.state.public_limiter = SlidingWindowLimiter(s.RATE_LIMIT_PUBLIC_PER_MIN)
    app.state.admin_limiter = SlidingWindowLimiter(s.RATE_LIMIT_ADMIN_PER_MIN)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        """안쪽 미들웨어: 본문 크기(413), 형식(415), 요청 횟수(429). 걸리면 라우터까지 가지 않는다.

        /csp-report 는 브라우저가 보내는 보고라 크기, 형식 검사를 하지 않고 항상 204 로 답한다 (frontend.py 가 8KB 까지만 읽음).
        """
        path = request.url.path
        if path != "/csp-report":
            length = declared_length(request)
            if length is None:
                return error_response(request, "INVALID_INPUT", "입력값을 확인하세요.", BAD_LENGTH)
            if length > MAX_BODY_BYTES:
                return error_response(request, "PAYLOAD_TOO_LARGE", "요청 본문은 64KB 이하여야 합니다.")
            if request.method in ("PUT", "PATCH") and not request.headers.get("content-type", "").startswith("application/json"):
                return error_response(request, "UNSUPPORTED_MEDIA", "본문은 application/json 이어야 합니다.")
        if path.startswith("/api/") or path == "/csp-report":
            limiter = app.state.admin_limiter if path.startswith("/api/v1/admin") else app.state.public_limiter
            wait = limiter.hit(client_ip(request))
            if wait:
                return _rate_limited(request, wait)
        return await call_next(request)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        """바깥 미들웨어: 요청 ID(받은 값을 64자로 자르거나 새로 만듦), 보안 헤더, 접근 로그."""
        rid = (request.headers.get("X-Request-ID") or "")[:REQUEST_ID_MAX] or str(uuid.uuid4())
        request.state.request_id = rid
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        if s.is_prod:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        route = request.scope.get("route")
        access_log.info(
            "request",
            extra={
                "request_id": rid,
                "method": request.method,
                "path_pattern": getattr(route, "path", "unmatched"),  # 실제 URL, 쿼리 문자열은 남기지 않음 (설계서 2.7.3)
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        return response

    if s.allowed_origins:  # 같은 주소로 화면을 내보내면 필요 없다. 다른 도메인에서 API 를 부를 때만 켠다
        app.add_middleware(
            CORSMiddleware,
            allow_origins=s.allowed_origins,
            allow_methods=["GET", "PUT", "PATCH"],
            allow_headers=["Content-Type", "X-Admin-Key", "X-Request-ID", "If-None-Match"],
            expose_headers=["ETag", "X-Request-ID", "Retry-After"],
        )

    app.include_router(health.router)
    app.include_router(csp_router)  # POST /csp-report (보안 정책 위반 보고)
    for r in (places.router, buildings.router, walk_routes.router, admin.router):
        app.include_router(r, prefix="/api/v1")

    # HTML 프론트(frontend/)를 같은 주소로 내보낸다 (app/frontend.py).
    # 라우터 등록 뒤에 둬야 /api, /health, /docs 가 먼저 잡힌다. 없는 화면 파일은 404.html, /api 아래 없는 경로는 JSON 404
    frontend = Path(s.FRONTEND_DIR) if s.FRONTEND_DIR else Path(__file__).resolve().parents[2] / "frontend"
    if frontend.is_dir():
        app.mount("/", FrontendFiles(directory=frontend, html=True, csp_mode=s.csp_mode), name="frontend")
    return app


app = create_app()
