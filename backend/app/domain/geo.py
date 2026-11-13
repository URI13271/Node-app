"""순수 기하 계산. DB와 HTTP에 의존하지 않는다.

뼈대: 본문은 비어 있다. 함수마다 NotImplementedError 를 구현으로 바꾼다.
"""

Lnglat = tuple[float, float]


def azimuth_deg(a: Lnglat, b: Lnglat) -> float | None:
    """a → b 구면 방위각. 북쪽 0도, 시계 방향. 두 점이 같으면 None."""
    raise NotImplementedError("TODO: app.domain.geo.azimuth_deg")
