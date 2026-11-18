"""라우터 공용 의존성: request_id, 관리자 키 검사, 클라이언트 IP (설계서 2.4.1)."""

from fastapi import Header, Request


def client_ip(request: Request) -> str:
    """X-Forwarded-For 를 직접 읽지 않는다. 프록시 뒤에서는 uvicorn 이 FORWARDED_ALLOW_IPS 범위 안에서 실제 IP 를 넣어 준다."""
    return request.client.host if request.client else "unknown"


def request_id(request: Request) -> str:
    """미들웨어(BE-17)가 request.state 에 넣은 값. 미들웨어가 없을 때는 오류 응답과 같은 "-"."""
    return getattr(request.state, "request_id", "-")


def require_admin(request: Request, x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")) -> None:
    """키 없음, 틀림 → 401. 같은 IP 연속 5회 실패 → 10분 429 (API 명세서 1.11).

    관리자 라우터의 AdminRoute 가 본문 해석 전에 이 함수를 부른다. 라우터 dependencies 에 다시 넣지 않는다 (실패 계수가 두 번 된다).
    """
    raise NotImplementedError("TODO: app.api.deps.require_admin")
