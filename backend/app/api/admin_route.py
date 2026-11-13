"""관리자 라우트: 본문을 해석하기 전에 관리자 키를 먼저 검사한다 (API 명세서 1.9, 1.11).

FastAPI 는 의존성(Depends)보다 JSON 본문 해석을 먼저 한다. 그래서 라우터 dependencies 로 키를 검사하면
키 없이 깨진 JSON 을 보냈을 때 401 이 아니라 400(INVALID_INPUT)이 나가 "키가 없으면 401" 규칙이 깨진다.
라우트 핸들러를 한 겹 감싸 키 검사를 맨 앞으로 옮긴다. 키 검사 로직은 deps.require_admin 한 곳만 쓴다
(실패 횟수가 두 번 세어지지 않도록 라우터 dependencies 에 require_admin 을 넣지 않는다).
출처: 팀원 보완 backend_supplement.patch (2026-11-13)
"""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.routing import APIRoute

from app.api import deps


class AdminRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def guarded(request: Request) -> Response:
            deps.require_admin(request, request.headers.get("X-Admin-Key"))
            return await handler(request)

        return guarded
