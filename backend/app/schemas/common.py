"""공통 DTO: GeoPoint, Camera, ErrorBody (API 명세서 2장, 1.11).

뼈대: 본문은 비어 있다. 함수마다 NotImplementedError 를 구현으로 바꾼다.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class InModel(BaseModel):
    """모든 입력 DTO: 정의되지 않은 필드 거부, 문자열 앞뒤 공백 제거 (설계서 2.4.3)."""


class GeoPointIn(InModel):
    """TODO: 필드 정의 (API 명세서, 설계서 참고)"""


class Camera(BaseModel):
    """방위각 0 이상 360 미만, 기울기 0~85, 줌 0~22."""


GeoJSON = dict[str, Any]


def iso_seconds(dt: datetime | None) -> str | None:
    """ISO 8601 UTC, 초 단위. 예: 2026-11-12T05:20:00Z"""
    raise NotImplementedError("TODO: app.schemas.common.iso_seconds")


def iso_micros(dt: datetime) -> str:
    """경로 버전용. 마이크로초까지. 예: 2026-11-12T05:20:00.123456Z"""
    raise NotImplementedError("TODO: app.schemas.common.iso_micros")


class ErrorDetail(BaseModel):
    """TODO: 필드 정의 (API 명세서, 설계서 참고)"""


class ErrorInner(BaseModel):
    """TODO: 필드 정의 (API 명세서, 설계서 참고)"""


class ErrorBody(BaseModel):
    """TODO: 필드 정의 (API 명세서, 설계서 참고)"""


class HealthOut(BaseModel):
    """TODO: 필드 정의 (API 명세서, 설계서 참고)"""
