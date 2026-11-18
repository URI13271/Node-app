"""라우터 공용 의존성: request_id, 관리자 키 검사, 클라이언트 IP (설계서 2.4.1)."""

from fastapi import Header, Request

from app.config import get_settings
from app.core.errors import AppError
from app.core.security import key_matches

# 429 사유 구분 (API 명세서 1.11): 키 잠금은 locked, 분당 횟수 초과(BE-17)는 too_many_requests.
# 관리자 화면은 locked 일 때만 저장한 키를 지우고, too_many_requests 는 키와 초안을 유지한 채 Retry-After 뒤 다시 시도한다.
LOCKED_DETAIL = [{"field": "header.X-Admin-Key", "reason": "locked", "message": "같은 IP에서 키를 연속 5회 틀려 10분 동안 막혔습니다."}]
LOCKED_MESSAGE = "관리자 키를 여러 번 틀려 잠시 막혔습니다."


def client_ip(request: Request) -> str:
    """X-Forwarded-For 를 직접 읽지 않는다. 프록시 뒤에서는 uvicorn 이 FORWARDED_ALLOW_IPS 범위 안에서 실제 IP 를 넣어 준다."""
    return request.client.host if request.client else "unknown"


def request_id(request: Request) -> str:
    """미들웨어(BE-17)가 request.state 에 넣은 값. 미들웨어가 없을 때는 오류 응답과 같은 "-"."""
    return getattr(request.state, "request_id", "-")


def require_admin(request: Request, x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")) -> None:
    """키 없음, 틀림 → 401. 같은 IP 연속 5회 실패 → 10분 429 (API 명세서 1.11).

    관리자 라우터의 AdminRoute 가 본문 해석 전에 이 함수를 부른다. 라우터 dependencies 에 다시 넣지 않는다 (실패 계수가 두 번 된다).
    잠긴 동안에는 맞는 키를 보내도 429 다. 맞는 키를 보내면 그 IP 의 실패 계수를 지운다.
    """
    limiter = request.app.state.admin_fail_limiter
    ip = client_ip(request)
    wait = limiter.retry_after(ip)
    if wait:
        raise AppError("RATE_LIMITED", LOCKED_MESSAGE, LOCKED_DETAIL, headers={"Retry-After": str(wait)})
    if not key_matches(x_admin_key, get_settings().ADMIN_KEY):
        locked = limiter.fail(ip)
        if locked:
            raise AppError("RATE_LIMITED", LOCKED_MESSAGE, LOCKED_DETAIL, headers={"Retry-After": str(locked)})
        raise AppError("UNAUTHORIZED", "관리자 키가 맞지 않습니다.")
    limiter.success(ip)
