"""GET /api/v1/places, GET /api/v1/places/{id} (API 명세서 3.2, 3.3, F-01).

라우터는 입력 검증(Query, Path)과 헤더만 맡고, 나머지는 서비스가 한다 (가이드 2.3).
"""

from fastapi import APIRouter, Path, Query, Response

from app.schemas.place import PlaceDetail, PlaceListOut
from app.services.place_service import PlaceService

router = APIRouter(prefix="/places", tags=["places"])
service = PlaceService()


@router.get("", response_model=PlaceListOut)
def list_places(
    response: Response,
    q: str | None = Query(default=None, max_length=50),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """장소 검색 (Cache-Control: public, max-age=60). 검색어 앞뒤 공백은 지우고, 비면 전체."""
    raise NotImplementedError("BE-11a 연습: list_places")


@router.get("/{id}", response_model=PlaceDetail)
def get_place(response: Response, id: int = Path(ge=1)):
    """장소 상세: 입구, 주차장, 랜드마크, 내비 목적지 (Cache-Control: public, max-age=60). 없으면 404."""
    response.headers["Cache-Control"] = "public, max-age=60"
    return service.detail(id)
