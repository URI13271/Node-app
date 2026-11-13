"""내비 목적지 선택, 예상 도보 시간 (설계서 2.4.5 (1), (4)).

뼈대: 본문은 비어 있다. 함수마다 NotImplementedError 를 구현으로 바꾼다.
"""

from dataclasses import dataclass

WALK_M_PER_MIN = 67


class DataIntegrityError(Exception):
    """시드 적재 검사로 막혀야 하는 데이터 오류 (예: 주차장 없는 장소)."""


@dataclass(frozen=True)
class ParkingCandidate:
    """TODO: 필드 정의 (API 명세서, 설계서 참고)"""


def select_navigation_target(parking_lots: list[ParkingCandidate]) -> ParkingCandidate:
    raise NotImplementedError("TODO: app.domain.navigation.select_navigation_target")


def walk_time_min(stored: int | None, distance_m: float) -> int:
    raise NotImplementedError("TODO: app.domain.navigation.walk_time_min")
