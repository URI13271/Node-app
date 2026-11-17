"""건물 표시 높이 (설계서 2.4.5 (3), REQ-F-BLDG-002)."""
FLOOR_HEIGHT_M = 3.0
DEFAULT_HEIGHT_M = 6.0


def render_height(height_m: float | None, floor_count: int | None) -> float:
    if height_m is not None and height_m > 0:
        return round(height_m, 1)
    if floor_count is not None and floor_count > 0:
        return round(floor_count * FLOOR_HEIGHT_M, 1)
    return DEFAULT_HEIGHT_M
