"""내비 목적지 선택, 예상 도보 시간 (설계서 2.4.5 (1), (4))."""
import math
from dataclasses import dataclass

WALK_M_PER_MIN = 67  # 시속 약 4km


class DataIntegrityError(Exception):
    """시드 적재 검사로 막혀야 하는 데이터 오류 (예: 주차장 없는 장소)."""


@dataclass(frozen=True)
class ParkingCandidate:
    id: int
    name: str
    priority: int
    lng: float
    lat: float


def select_navigation_target(parking_lots: list[ParkingCandidate]) -> ParkingCandidate:
    if not parking_lots:
        raise DataIntegrityError("주차장 없음")
    return min(parking_lots, key=lambda p: (p.priority, p.id))


def walk_time_min(stored: int | None, distance_m: float) -> int:
    if stored is not None:
        return stored
    return max(1, math.ceil(distance_m / WALK_M_PER_MIN))
