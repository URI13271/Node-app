"""GET /api/v1/places/{id}/walk-routes (API 명세서 3.5, F-04, F-05). no-cache + ETag."""

from fastapi import APIRouter, Header, Path, Query

router = APIRouter(prefix="/places", tags=["walk-routes"])


@router.get("/{id}/walk-routes", responses={304: {"description": "변경 없음"}})
def list_walk_routes(
    id: int = Path(ge=1),
    parking_lot_id: int | None = Query(default=None, ge=1),
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
):
    """도보 경로와 단계. If-None-Match 가 맞으면 304."""
    raise NotImplementedError("TODO: GET /api/v1/places/{id}/walk-routes")
