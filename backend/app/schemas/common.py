"""공통 DTO: GeoPoint, Camera, ErrorBody (API 명세서 2장, 1.11)."""
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field
from pydantic_core import PydanticCustomError


class InModel(BaseModel):
    """모든 입력 DTO: 정의되지 않은 필드 거부, 문자열 앞뒤 공백 제거 (설계서 2.4.3)."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _check_coords(v: list[float]) -> list[float]:
    if len(v) != 2 or not (-180 <= v[0] <= 180) or not (-90 <= v[1] <= 90):
        raise PydanticCustomError("invalid_geometry", "좌표는 [경도, 위도] 범위 안이어야 합니다.")
    return v


class GeoPointIn(InModel):
    type: Literal["Point"]
    coordinates: Annotated[list[float], AfterValidator(_check_coords)]


class Camera(BaseModel):
    """방위각 0 이상 360 미만, 기울기 0~85, 줌 0~22."""
    model_config = ConfigDict(extra="forbid")
    bearing: float = Field(ge=0, lt=360)
    pitch: float = Field(ge=0, le=85)
    zoom: float = Field(ge=0, le=22)


GeoJSON = dict[str, Any]


def iso_seconds(dt: datetime | None) -> str | None:
    """ISO 8601 UTC, 초 단위. 예: 2026-11-12T05:20:00Z"""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def iso_micros(dt: datetime) -> str:
    """경로 버전용. 마이크로초까지. 예: 2026-11-12T05:20:00.123456Z"""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class ErrorDetail(BaseModel):
    field: str
    reason: str
    message: str


class ErrorInner(BaseModel):
    code: str
    message: str
    request_id: str
    timestamp: str
    details: list[ErrorDetail] = []


class ErrorBody(BaseModel):
    error: ErrorInner


class HealthOut(BaseModel):
    status: Literal["ok", "error"]
    db: Literal["ok", "unavailable"]
    version: str
