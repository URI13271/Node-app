"""도보 경로, 단계 DTO (API 명세서 3.5)."""
from pydantic import BaseModel

from app.schemas.common import Camera, GeoJSON


class LandmarkRef(BaseModel):
    id: int
    name: str


class StepOut(BaseModel):
    id: int
    step_order: int
    instruction: str
    landmark: LandmarkRef | None
    location: GeoJSON
    camera: Camera
    camera_is_default: bool


class WalkRouteOut(BaseModel):
    id: int
    parking_lot_id: int
    entrance_id: int
    path: GeoJSON
    distance_m: float
    walk_time_min: int
    description: str | None
    updated_at: str
    steps: list[StepOut]


class WalkRouteListOut(BaseModel):
    items: list[WalkRouteOut]
