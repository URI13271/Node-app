"""GET /api/v1/places/{id}/walk-routes (API 명세서 3.5, F-04, F-05). no-cache + ETag."""

from fastapi import APIRouter, Header, Path, Query, Response

from app.schemas.walk_route import WalkRouteListOut
from app.services.walk_route_service import WalkRouteService

router = APIRouter(prefix="/places", tags=["walk-routes"])
service = WalkRouteService()


@router.get("/{id}/walk-routes", response_model=WalkRouteListOut, responses={304: {"description": "변경 없음"}})
def list_walk_routes(
    response: Response,
    id: int = Path(ge=1),
    parking_lot_id: int | None = Query(default=None, ge=1),
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
):
    """도보 경로와 단계. If-None-Match 가 맞으면 본문 없이 304 (ETag, Cache-Control 은 함께 보낸다)."""
    result = service.list_for_place(id, parking_lot_id, if_none_match)
    headers = {"ETag": result.etag, "Cache-Control": "no-cache"}
    if result.items is None:
        return Response(status_code=304, headers=headers)
    response.headers.update(headers)
    return WalkRouteListOut(items=result.items)
