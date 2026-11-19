"""GET /api/v1/places/{id}/buildings (API 명세서 3.4, F-02, F-03)."""

from fastapi import APIRouter, Path
from fastapi.responses import JSONResponse

from app.schemas.building import BuildingCollection
from app.services.building_service import BuildingService

router = APIRouter(prefix="/places", tags=["buildings"])
service = BuildingService()


@router.get("/{id}/buildings", response_model=BuildingCollection, responses={200: {"content": {"application/geo+json": {}}}})
def list_buildings(id: int = Path(ge=1)):
    """건물 GeoJSON (application/geo+json, Cache-Control: public, max-age=300)."""
    raise NotImplementedError("BE-11b 연습: list_buildings")
