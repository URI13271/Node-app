"""앱 생성, 미들웨어, 라우터 등록 (설계서 2.4.1).

뼈대: 라우터 등록만 되어 있다. 아직 구현하지 않은 엔드포인트는 501 NOT_IMPLEMENTED 를 돌려준다.
"""

from pathlib import Path

from fastapi import FastAPI

from app.api import admin, buildings, health, places, walk_routes
from app.config import APP_VERSION, get_settings
from app.core.errors import install_handlers
from app.core.logging import setup_logging
from app.core.security import FailureLimiter
from app.frontend import FrontendFiles
from app.frontend import router as csp_router

MAX_BODY_BYTES = 64 * 1024  # 요청 본문 상한 (413). 미들웨어에서 쓴다
MIN_PROD_ADMIN_KEY_LEN = 32


def create_app() -> FastAPI:
    s = get_settings()
    # 운영에서 짧은 관리자 키로 뜨지 않게 시작 때 막는다. 비어 있으면 관리자 API 가 꺼진 것으로 본다 (config.py ADMIN_KEY 설명)
    if s.is_prod and s.ADMIN_KEY and len(s.ADMIN_KEY) < MIN_PROD_ADMIN_KEY_LEN:
        raise RuntimeError(f"ENV=prod 에서는 ADMIN_KEY 가 {MIN_PROD_ADMIN_KEY_LEN}자 이상이어야 합니다.")
    setup_logging(s.LOG_LEVEL)
    app = FastAPI(
        title="마중길 (majunggil) API",
        version=APP_VERSION,
        description="외곽 여행 3D 길 안내 MVP 백엔드 (뼈대)",
        docs_url=None if s.is_prod else "/docs",
        redoc_url=None,
        openapi_url=None if s.is_prod else "/openapi.json",
    )
    install_handlers(app)

    # 관리자 키 실패 잠금 (BE-13): 같은 IP 연속 ADMIN_FAIL_LIMIT 회 실패 → ADMIN_LOCK_S 초. deps.require_admin 이 쓴다
    app.state.admin_fail_limiter = FailureLimiter(s.ADMIN_FAIL_LIMIT, s.ADMIN_LOCK_S)
    # TODO: 분당 요청 수 제한기 (app.state.public_limiter, admin_limiter) - core/security.py SlidingWindowLimiter (BE-17)
    # TODO: 미들웨어. 순서(바깥 → 안): request_id + 접근 로그 + 보안 헤더 → 본문 크기(413), 형식(415) → 요청 횟수(429)
    #   Content-Length 는 int() 로 바로 바꾸지 말고 core/http.py declared_length() 를 쓴다.
    #   None(정수 아님, 음수) → 400 INVALID_INPUT, details [{"field": "header.Content-Length", "reason": "invalid_type"}]
    #   MAX_BODY_BYTES 초과 → 413 PAYLOAD_TOO_LARGE. 완료 기준은 tests/unit/test_http_layer.py
    # TODO: CORS (ALLOWED_ORIGINS 가 있을 때만)

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
