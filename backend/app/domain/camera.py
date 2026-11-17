"""카메라 결정과 기본 카메라 계산 (설계서 2.4.5 (2), REQ-F-CAM-002, 003, REQ-F-ROUTE-006)."""
from dataclasses import dataclass

from app.domain.geo import Lnglat, azimuth_deg

DEFAULT_PLACE_PITCH, DEFAULT_PLACE_ZOOM = 60.0, 17.5
DEFAULT_STEP_PITCH, DEFAULT_STEP_ZOOM = 55.0, 18.5


@dataclass(frozen=True)
class Camera:
    bearing: float
    pitch: float
    zoom: float


def place_camera(stored: Camera | None, nav_parking: Lnglat, place: Lnglat) -> Camera:
    """저장값이 있으면 그 값, 없으면 내비 목적지 주차장 → 장소 방향."""
    if stored is not None:
        return stored
    bearing = azimuth_deg(nav_parking, place)
    return Camera(bearing if bearing is not None else 0.0, DEFAULT_PLACE_PITCH, DEFAULT_PLACE_ZOOM)


def parking_camera(stored: Camera | None, parking: Lnglat, place: Lnglat,
                   fallback_bearing: float) -> tuple[Camera, bool]:
    """주차장별 도착 방향 카메라와 camera_is_default (API 명세서 v1.1 3.3, 설계서 v2.3 2.4.5 (2)).

    저장값이 있으면 그 값. 없으면 "이 주차장 → 장소" 방향으로 계산한다. 우선순위 2 이하 주차장에서
    출발하는 경로도 실제로 다가가는 방향에서 본 모습이 나오게 하기 위함이다.
    주차장과 장소 좌표가 같으면 장소 카메라 방위각(fallback_bearing)을 쓴다.
    """
    if stored is not None:
        return stored, False
    bearing = azimuth_deg(parking, place)
    return Camera(bearing if bearing is not None else fallback_bearing, DEFAULT_PLACE_PITCH, DEFAULT_PLACE_ZOOM), True


def step_cameras(stored: list[Camera | None], locations: list[Lnglat], entrance: Lnglat,
                 fallback_bearing: float) -> list[tuple[Camera, bool]]:
    """단계별 (카메라, camera_is_default).

    저장값이 없으면 이 단계 → 다음 단계(마지막은 입구) 방향. 두 점이 같으면 이전 단계 방위각,
    그것도 없으면 장소 카메라 방위각(fallback_bearing).
    """
    out: list[tuple[Camera, bool]] = []
    prev_bearing: float | None = None
    for i, (cam, loc) in enumerate(zip(stored, locations, strict=True)):
        if cam is not None:
            out.append((cam, False))
            prev_bearing = cam.bearing
            continue
        target = locations[i + 1] if i + 1 < len(locations) else entrance
        b = azimuth_deg(loc, target)
        if b is None:
            b = prev_bearing if prev_bearing is not None else fallback_bearing
        out.append((Camera(b, DEFAULT_STEP_PITCH, DEFAULT_STEP_ZOOM), True))
        prev_bearing = b
    return out
