"""건물 GeoJSON DTO (API 명세서 3.4)."""
from typing import Literal

from pydantic import BaseModel

from app.schemas.common import GeoJSON


class BuildingProps(BaseModel):
    name: str | None
    floor_count: int | None
    render_height_m: float
    is_target: bool


class BuildingFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: int
    geometry: GeoJSON
    properties: BuildingProps


class BuildingCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[BuildingFeature]
    attributions: list[str]
