"""GET /api/v1/places, GET /api/v1/places/{id} (API 명세서 3.2, 3.3, F-01)."""

from fastapi import APIRouter, Path, Query

router = APIRouter(prefix="/places", tags=["places"])


@router.get("")
def list_places(
    q: str | None = Query(default=None, max_length=50), limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0)
):
    """장소 검색 (Cache-Control: public, max-age=60)."""
    raise NotImplementedError("TODO: GET /api/v1/places")


@router.get("/{id}")
def get_place(id: int = Path(ge=1)):
    """장소 상세: 입구, 주차장, 랜드마크, 내비 목적지 (Cache-Control: public, max-age=60)."""
    raise NotImplementedError("TODO: GET /api/v1/places/{id}")
