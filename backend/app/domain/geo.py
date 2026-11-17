"""순수 기하 계산. DB와 HTTP에 의존하지 않는다."""
import math

Lnglat = tuple[float, float]


def azimuth_deg(a: Lnglat, b: Lnglat) -> float | None:
    """a → b 구면 방위각. 북쪽 0도, 시계 방향. 두 점이 같으면 None.

    PostGIS degrees(ST_Azimuth(a::geography, b::geography)) 와 같은 값을 목표로 한다(통합 테스트에서 비교).
    """
    if a == b:
        return None
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    deg = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
    return round(deg, 1) % 360.0
