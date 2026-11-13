"""공용 SQL 조각 (설계서 2.4.1). geography 변환을 빠뜨리지 않도록 한곳에 둔다.

뼈대: 본문은 비어 있다. 함수마다 NotImplementedError 를 구현으로 바꾼다.
"""

from sqlalchemy.sql import ColumnElement

COORD_DECIMALS = 6


def as_geojson(col, label: str) -> ColumnElement:
    raise NotImplementedError("TODO: app.repositories.geo_sql.as_geojson")


def lng(col) -> ColumnElement:
    raise NotImplementedError("TODO: app.repositories.geo_sql.lng")


def lat(col) -> ColumnElement:
    raise NotImplementedError("TODO: app.repositories.geo_sql.lat")


def length_m(col) -> ColumnElement:
    """선 길이(미터). geometry → geography 변환."""
    raise NotImplementedError("TODO: app.repositories.geo_sql.length_m")


def make_point(lng_: float, lat_: float) -> ColumnElement:
    raise NotImplementedError("TODO: app.repositories.geo_sql.make_point")


def parse(geojson_text: str | None) -> dict | None:
    raise NotImplementedError("TODO: app.repositories.geo_sql.parse")


def camera_of(row) -> dict | None:
    """camera_* 칼럼 3개를 camera 객체로 묶는다. 모두 NULL이면 None."""
    raise NotImplementedError("TODO: app.repositories.geo_sql.camera_of")
