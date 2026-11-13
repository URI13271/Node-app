"""건물 표시 높이 (설계서 2.4.5 (3), REQ-F-BLDG-002).

뼈대: 본문은 비어 있다. 함수마다 NotImplementedError 를 구현으로 바꾼다.
"""

FLOOR_HEIGHT_M = 3.0


DEFAULT_HEIGHT_M = 6.0


def render_height(height_m: float | None, floor_count: int | None) -> float:
    raise NotImplementedError("TODO: app.domain.building.render_height")
