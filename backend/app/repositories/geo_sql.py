"""공용 SQL 조각 (설계서 2.4.1). geography 변환을 빠뜨리지 않도록 한곳에 둔다.

저장소 파일에서 func.ST_... 를 직접 쓰지 말고 여기 함수를 쓴다 (백엔드 작성 가이드 4.3).
좌표는 소수점 6자리(약 0.1m)로 자른다 (N-01).
"""

import json

from sqlalchemy import Float, Numeric, cast, func
from sqlalchemy.sql import ColumnElement

COORD_DECIMALS = 6


def as_geojson(col, label: str) -> ColumnElement:
    """geometry 칼럼 → GeoJSON 문자열 (좌표 6자리). 파이썬에서는 parse() 로 dict 로 바꾼다."""
    return func.ST_AsGeoJSON(col, COORD_DECIMALS).label(label)


def lng(col) -> ColumnElement:
    """점의 경도 (6자리 반올림). 결과는 Decimal 이라 응답에 넣을 때 float() 로 바꾼다."""
    return func.round(cast(func.ST_X(col), Numeric), COORD_DECIMALS)


def lat(col) -> ColumnElement:
    """점의 위도 (6자리 반올림). 결과는 Decimal 이라 응답에 넣을 때 float() 로 바꾼다."""
    return func.round(cast(func.ST_Y(col), Numeric), COORD_DECIMALS)


def length_m(col) -> ColumnElement:
    """선 길이(미터). geometry → geography 변환."""
    return cast(func.ST_Length(func.Geography(col)), Float)


def make_point(lng_: float, lat_: float) -> ColumnElement:
    """경도, 위도 → SRID 4326 점. 값은 바인딩 파라미터로 들어간다."""
    return func.ST_SetSRID(func.ST_MakePoint(lng_, lat_), 4326)


def parse(geojson_text: str | None) -> dict | None:
    return json.loads(geojson_text) if geojson_text else None


def camera_of(row) -> dict | None:
    """camera_* 칼럼 3개를 camera 객체로 묶는다. 모두 NULL이면 None.

    DB 제약(ck_*_camera_all_or_none)이 셋이 함께 있거나 함께 없음을 보장하므로 bearing 하나만 본다.
    """
    if row["camera_bearing"] is None:
        return None
    return {"bearing": row["camera_bearing"], "pitch": row["camera_pitch"], "zoom": row["camera_zoom"]}
