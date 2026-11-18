"""HTML 프론트(frontend/)를 API와 같은 주소로 내보낸다. 같은 주소라 CORS 가 필요 없다.

- /api 아래 없는 경로는 화면(404.html)이 아니라 JSON 404 로 돌려준다 (오류 형식은 core/errors.py).
- Cache-Control: no-cache. 빌드 없는 ES 모듈이라 배포 직후 옛 JS와 새 JS가 섞이지 않도록 매번 ETag 로 재검증한다.
- 보안 정책(CSP): 지도(MapLibre)와 배경 지도, 글꼴이 쓰는 주소만 허용한다.
  개발 중(ENV=local)에는 Report-Only 로 막지 않고 위반만 /csp-report 로 받아 로그에 남긴다. 운영(ENV=prod)은 실제로 막는다.
"""

import json
import logging
import re

from fastapi import APIRouter, Request, Response
from starlette.exceptions import HTTPException
from starlette.routing import Match, Mount
from starlette.staticfiles import StaticFiles

from app.core.http import declared_length

csp_log = logging.getLogger("csp")

# 배경 지도 OpenFreeMap liberty 는 스타일, 타일, 글꼴(glyphs), 아이콘(sprite)을 모두 tiles.openfreemap.org 에서 받는다.
# MapLibre 는 지도 계산용 worker 를 blob: 주소로 만든다 (worker-src blob:, 옛 Safari 용 child-src blob:).
# 배경 지도 공급원을 바꾸면 img-src, connect-src 의 주소도 함께 바꾼다. [검증 필요: 정식 배포 전 브라우저 콘솔에 CSP 위반이 없는지 확인]
MAP_HOST = "https://tiles.openfreemap.org"
CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com",
        f"img-src 'self' data: blob: {MAP_HOST}",
        f"connect-src 'self' {MAP_HOST}",
        "worker-src 'self' blob:",
        "child-src blob:",
        "object-src 'none'",
        "base-uri 'self'",
        "frame-ancestors 'none'",
        "report-uri /csp-report",  # 위반 보고 받을 곳 (아래 csp_report)
    ]
)


HEADER_BY_MODE = {"report-only": "Content-Security-Policy-Report-Only", "enforce": "Content-Security-Policy"}


def _other_method_exists(scope) -> bool:
    """같은 경로의 API 라우트가 다른 메서드로 있는지. 라우터는 메서드가 안 맞으면 이 화면 mount 로 넘겨 버리므로 여기서 405 를 가린다."""
    router = scope.get("router")
    for route in getattr(router, "routes", []):
        if not isinstance(route, Mount) and route.matches(scope)[0] == Match.PARTIAL:
            return True
    return False


class FrontendFiles(StaticFiles):
    def __init__(self, *args, csp_mode: str = "report-only", **kwargs):
        super().__init__(*args, **kwargs)
        self.csp_header = HEADER_BY_MODE.get(csp_mode)  # off 면 None

    async def get_response(self, path, scope):
        if scope["method"] not in ("GET", "HEAD"):
            raise HTTPException(405)
        # Windows 에서는 StaticFiles 가 경로를 api\v1\nope 처럼 넘겨서 / 로 맞춘 뒤 비교한다
        url_path = path.replace("\\", "/")
        if url_path == "api" or url_path.startswith("api/"):
            # 라우터에 안 걸린 /api 요청. 경로는 있는데 메서드가 다르면(예: PUT 전용 경로에 GET) 405, HEAD 도 405,
            # 나머지는 없는 경로라 404 (core/errors.py 처리기가 {"error": {...}} 형식으로 감싼다)
            raise HTTPException(405 if scope["method"] == "HEAD" or _other_method_exists(scope) else 404)
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        if self.csp_header and response.headers.get("content-type", "").startswith("text/html"):
            response.headers[self.csp_header] = CSP
        return response


# --- CSP 위반 보고 받기 ---
# 브라우저가 위반을 발견하면 report-uri 로 {"csp-report": {...}} 를 POST 한다 (Content-Type: application/csp-report).
# 누구나 보낼 수 있는 경로라 내용을 믿지 않는다.
#  - 본문은 8KB 까지만 읽는다 (Content-Length 먼저 보고, 실제로 읽으면서도 센다)
#  - 로그에 넣는 값은 제어 문자(줄바꿈 포함)를 ? 로 바꾸고 300자로 자른다 (가짜 로그 줄 방지)
#  - 쿼리 문자열은 남기지 않는다 (설계서 2.7.3). 항상 204 로 답한다
# 요청 횟수 제한: main.py 미들웨어가 이 경로에도 공개 API 와 같은 분당 제한을 건다 (BE-17).
router = APIRouter(tags=["csp"], include_in_schema=False)
MAX_REPORT_BYTES = 8 * 1024
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def _clean(value, n: int = 300) -> str:
    return _CTRL.sub("?", str(value or ""))[:n]


def _no_query(url: str) -> str:
    return url.split("?", 1)[0].split("#", 1)[0] if url else ""


async def _read_limited(request: Request) -> bytes | None:
    """본문을 MAX_REPORT_BYTES 까지만 읽는다. 넘으면 None."""
    declared = declared_length(request)
    if declared is None or declared > MAX_REPORT_BYTES:
        return None
    raw = b""
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > MAX_REPORT_BYTES:
            return None
    return raw


@router.post("/csp-report", status_code=204)
async def csp_report(request: Request) -> Response:
    raw = await _read_limited(request)
    if raw is None:
        return Response(status_code=204)
    try:
        r = json.loads(raw or b"{}").get("csp-report", {})
        if not isinstance(r, dict):
            return Response(status_code=204)
    except (ValueError, AttributeError):
        return Response(status_code=204)
    line = r.get("line-number")
    v = {
        "directive": _clean(r.get("effective-directive") or r.get("violated-directive"), 60),
        "blocked": _clean(_no_query(str(r.get("blocked-uri") or ""))),
        "page": _clean(_no_query(str(r.get("document-uri") or "")).split("://", 1)[-1].split("/", 1)[-1]),
        "source": _clean(_no_query(str(r.get("source-file") or ""))),
        "line": line if isinstance(line, int) else None,
        "mode": _clean(r.get("disposition"), 20),
    }
    # 터미널에서 바로 읽히도록 메시지에도 넣는다. 예: WARNING:csp:csp_violation img-src blocked=https://... page=guide.html
    csp_log.warning(
        "csp_violation %s blocked=%s page=%s source=%s:%s", v["directive"], v["blocked"], v["page"], v["source"], v["line"], extra=v
    )
    return Response(status_code=204)
