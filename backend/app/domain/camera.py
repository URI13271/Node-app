"""카메라 결정과 기본 카메라 계산 (설계서 2.4.5 (2), REQ-F-CAM-002, 003, REQ-F-ROUTE-006).

뼈대: 본문은 비어 있다. 함수마다 NotImplementedError 를 구현으로 바꾼다.
"""

from dataclasses import dataclass

from app.domain.geo import Lnglat

DEFAULT_PLACE_PITCH, DEFAULT_PLACE_ZOOM = (60.0, 17.5)


DEFAULT_STEP_PITCH, DEFAULT_STEP_ZOOM = (55.0, 18.5)


@dataclass(frozen=True)
class Camera:
    """TODO: 필드 정의 (API 명세서, 설계서 참고)"""


def place_camera(stored: Camera | None, nav_parking: Lnglat, place: Lnglat) -> Camera:
    """저장값이 있으면 그 값, 없으면 내비 목적지 주차장 → 장소 방향."""
    raise NotImplementedError("TODO: app.domain.camera.place_camera")


def parking_camera(stored: Camera | None, parking: Lnglat, place: Lnglat, fallback_bearing: float) -> tuple[Camera, bool]:
    """주차장별 도착 방향 카메라와 camera_is_default (API 명세서 v1.1 3.3, 설계서 v2.3 2.4.5 (2))."""
    raise NotImplementedError("TODO: app.domain.camera.parking_camera")


def step_cameras(
    stored: list[Camera | None], locations: list[Lnglat], entrance: Lnglat, fallback_bearing: float
) -> list[tuple[Camera, bool]]:
    """단계별 (카메라, camera_is_default)."""
    raise NotImplementedError("TODO: app.domain.camera.step_cameras")
