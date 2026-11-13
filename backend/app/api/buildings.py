"""GET /api/v1/places/{id}/buildings (API 명세서 3.4, F-02, F-03)."""

from fastapi import APIRouter, Path

router = APIRouter(prefix="/places", tags=["buildings"])


@router.get("/{id}/buildings")
def list_buildings(id: int = Path(ge=1)):
    """건물 GeoJSON (application/geo+json, Cache-Control: public, max-age=300)."""
    raise NotImplementedError("TODO: GET /api/v1/places/{id}/buildings")
