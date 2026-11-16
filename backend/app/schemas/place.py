"""장소 DTO (API 명세서 3.2, 3.3 / 설계서 2.4.3)."""
from typing import Literal

from pydantic import BaseModel

from app.schemas.common import Camera, GeoJSON

Category = Literal["pension", "campsite", "temple", "restaurant", "trailhead", "attraction", "campus", "other"]


class PlaceSummary(BaseModel):
    id: int
    name: str
    category: Category
    location: GeoJSON
    cover_image_url: str | None


class PlaceListOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[PlaceSummary]


class EntranceOut(BaseModel):
    id: int
    name: str
    is_main: bool
    description: str | None
    location: GeoJSON


class ParkingOut(BaseModel):
    id: int
    name: str
    priority: int
    capacity: int | None
    is_free: bool | None
    description: str | None
    location: GeoJSON
    area: GeoJSON | None
    camera: Camera                 # v1.1: 항상 값이 있다. 저장값이 없으면 서버 계산값
    camera_is_default: bool        # v1.1: true 면 camera 는 "이 주차장 → 장소" 방향 계산값


class LandmarkOut(BaseModel):
    id: int
    name: str
    image_url: str | None
    location: GeoJSON


class NavigationTarget(BaseModel):
    parking_lot_id: int
    name: str
    lng: float
    lat: float


class PlaceDetail(PlaceSummary):
    address: str | None
    description: str | None
    camera: Camera
    entrances: list[EntranceOut]
    parking_lots: list[ParkingOut]
    landmarks: list[LandmarkOut]
    navigation_target: NavigationTarget
    arrival_radius_m: int
    attributions: list[str]
    last_verified_at: str | None
