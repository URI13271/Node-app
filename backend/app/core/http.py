"""HTTP 요청 헤더를 안전하게 읽는 도구 (main.py 미들웨어, frontend.py /csp-report 가 같이 쓴다)."""

from starlette.requests import Request


def declared_length(request: Request) -> int | None:
    """Content-Length 헤더 값. 헤더가 없으면 0, 정수가 아니거나 음수면 None.

    int() 를 바로 쓰면 'abc' 같은 값에서 예외가 나 500 이 된다. None 이면 부르는 쪽이 400 INVALID_INPUT 으로 답한다.
    """
    raw = request.headers.get("content-length")
    if raw is None:
        return 0
    try:
        n = int(raw)
    except ValueError:
        return None
    return n if n >= 0 else None
