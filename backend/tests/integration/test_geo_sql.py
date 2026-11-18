"""repositories/geo_sql.py 통합 테스트 (BE-06). 테스트 고정 데이터(seed_campus)로 확인한다.

완료 기준: 좌표 소수점 6자리, GeoJSON 형식.
"""

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.db import read_tx
from app.repositories import geo_sql as g
from app.repositories.tables import parking_lot, place, walk_route


def _decimals(x: float) -> int:
    s = repr(x)
    return len(s.split(".")[1]) if "." in s else 0


def _coords(geom: dict) -> list[list[float]]:
    c = geom["coordinates"]
    if geom["type"] == "Point":
        return [c]
    if geom["type"] == "LineString":
        return c
    return [p for ring in c for p in ring]  # Polygon


@pytest.mark.parametrize("table,col", [(place, "location"), (walk_route, "path"), (parking_lot, "area")])
def test_as_geojson_is_geojson_with_6_decimals(app, table, col):
    with read_tx() as conn:
        rows = conn.execute(select(g.as_geojson(table.c[col], "geom")).where(table.c[col].is_not(None))).scalars().all()
    assert rows
    expected_type = {"location": "Point", "path": "LineString", "area": "Polygon"}[col]
    for text_ in rows:
        geom = g.parse(text_)
        assert geom["type"] == expected_type
        for lng_, lat_ in _coords(geom):
            assert -180 <= lng_ <= 180 and -90 <= lat_ <= 90
            assert _decimals(lng_) <= 6 and _decimals(lat_) <= 6


def test_lng_lat_round_to_6_decimals(app):
    with read_tx() as conn:
        row = conn.execute(select(g.lng(place.c.location).label("lng"), g.lat(place.c.location).label("lat"))
                           .where(place.c.name == "공학관")).one()
    assert isinstance(row.lng, Decimal) and isinstance(row.lat, Decimal)
    assert (float(row.lng), float(row.lat)) == (127.00135, 37.00036)  # seed_campus/places.json
    assert -row.lng.as_tuple().exponent <= 6 and -row.lat.as_tuple().exponent <= 6


def test_length_m_uses_geography(app):
    """도(degree) 단위가 아니라 미터. 시드 적재 때 저장한 distance_m 과 같아야 한다."""
    with read_tx() as conn:
        rows = conn.execute(select(g.length_m(walk_route.c.path).label("len"), walk_route.c.distance_m)).all()
    assert rows
    for r in rows:
        assert r.len > 10 and r.len == pytest.approx(r.distance_m, abs=0.01)


def test_long_decimals_are_cut_to_6(app):
    """시드 좌표는 이미 6자리라, 자리수가 긴 점을 만들어 반올림을 직접 확인한다."""
    pt = g.make_point(128.0998816789, 35.1527954321)
    with read_tx() as conn:
        row = conn.execute(select(g.as_geojson(pt, "geom"), g.lng(pt).label("lng"), g.lat(pt).label("lat"))).one()
    assert g.parse(row.geom)["coordinates"] == [128.099882, 35.152795]
    assert (row.lng, row.lat) == (Decimal("128.099882"), Decimal("35.152795"))


def test_make_point_round_trip(app):
    with read_tx() as conn:
        text_ = conn.execute(select(func.ST_AsGeoJSON(g.make_point(128.099881, 35.152795), 6))).scalar_one()
        srid = conn.execute(select(func.ST_SRID(g.make_point(128.0, 35.0)))).scalar_one()
    assert g.parse(text_) == {"type": "Point", "coordinates": [128.099881, 35.152795]}
    assert srid == 4326


def test_parse_handles_none():
    assert g.parse(None) is None and g.parse("") is None


def test_camera_of(app):
    cols = [parking_lot.c.name, parking_lot.c.camera_bearing, parking_lot.c.camera_pitch, parking_lot.c.camera_zoom]
    with read_tx() as conn:
        rows = {r["name"]: r for r in conn.execute(select(*cols)).mappings()}
    assert g.camera_of(rows["체육관 옆 주차장"]) == {"bearing": 330, "pitch": 60, "zoom": 17.2}  # seed_campus/parking_lots.geojson
    assert g.camera_of(rows["공학관 앞 주차장"]) is None
