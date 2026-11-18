"""조회 서비스 통합 테스트 (BE-09). 테스트 고정 데이터(seed_campus)로 응답 모양과 규칙을 확인한다.

PlaceService(검색, 상세, 내비 목적지, 카메라 기본값, 출처), BuildingService(표시 높이), WalkRouteService(ETag, 304, 소속 검사).
"""

import re

import pytest
from sqlalchemy import text

from app.core.errors import AppError
from app.db import read_tx
from app.domain.geo import azimuth_deg
from app.services.building_service import BuildingService
from app.services.place_service import PlaceService, place_camera_bearing
from app.services.walk_route_service import WalkRouteService, make_etag


@pytest.fixture(scope="module")
def ids(app) -> dict:
    with read_tx() as conn:
        return {
            "place": dict(conn.execute(text("SELECT name, id FROM place")).all()),
            "lot": dict(conn.execute(text("SELECT name, id FROM parking_lot")).all()),
        }


# ---------- PlaceService ----------


def test_search(ids):
    out = PlaceService().search(None, 20, 0)
    assert (out.total, out.limit, out.offset) == (3, 20, 0)
    assert [p.name for p in out.items] == ["공학관", "중앙도서관", "학생회관"]
    assert PlaceService().search("", 20, 0).total == 3  # 빈 검색어는 전체
    assert [p.name for p in PlaceService().search("학생", 20, 0).items] == ["학생회관"]


def test_detail_navigation_target_is_priority_1_lot(ids):
    d = PlaceService().detail(ids["place"]["공학관"])
    assert d.navigation_target.parking_lot_id == ids["lot"]["공학관 앞 주차장"]
    assert [p.name for p in d.parking_lots] == ["공학관 앞 주차장", "체육관 옆 주차장"]
    assert [e.name for e in d.entrances] == ["정문", "동쪽 출입구"] and len(d.landmarks) == 3
    assert d.arrival_radius_m == 150


def test_detail_default_camera_faces_place_from_nav_lot(ids):
    d = PlaceService().detail(ids["place"]["공학관"])
    nav, loc = d.navigation_target, d.location["coordinates"]  # location 은 GeoJSON dict
    assert d.camera.bearing == azimuth_deg((nav.lng, nav.lat), tuple(loc))
    assert (d.camera.pitch, d.camera.zoom) == (60.0, 17.5)


def test_detail_parking_cameras_stored_or_default(ids):
    lots = {p.name: p for p in PlaceService().detail(ids["place"]["공학관"]).parking_lots}
    assert lots["체육관 옆 주차장"].camera_is_default is False
    assert (lots["체육관 옆 주차장"].camera.bearing, lots["체육관 옆 주차장"].camera.zoom) == (330, 17.2)
    assert lots["공학관 앞 주차장"].camera_is_default is True


def test_detail_attributions_from_building_sources(ids):
    assert PlaceService().detail(ids["place"]["공학관"]).attributions == ["© OpenStreetMap contributors", "공공 건물 데이터", "직접 조사"]


def test_detail_unknown_place_is_404():
    with pytest.raises(AppError) as e:
        PlaceService().detail(999999)
    assert e.value.status == 404


def test_place_camera_bearing_matches_detail(ids):
    pid = ids["place"]["학생회관"]
    with read_tx() as conn:
        bearing = place_camera_bearing(conn, pid)
    assert bearing == PlaceService().detail(pid).camera.bearing


# ---------- BuildingService ----------


def test_buildings_render_height_and_target_first(ids):
    out = BuildingService().list_for_place(ids["place"]["공학관"])
    props = {f.properties.name: f.properties for f in out.features}
    assert out.features[0].properties.is_target is True and out.features[0].properties.name == "공학관"
    assert props["공학관"].render_height_m == 15.0  # 5층 × 3m
    assert props["체육관"].render_height_m == 14  # 높이값 우선
    assert props["공동실험관"].render_height_m == 6.0  # 둘 다 없으면 기본 6m
    assert out.attributions == ["© OpenStreetMap contributors", "공공 건물 데이터", "직접 조사"]


def test_buildings_unknown_place_is_404():
    with pytest.raises(AppError) as e:
        BuildingService().list_for_place(999999)
    assert e.value.status == 404


# ---------- WalkRouteService ----------


def test_make_etag_format():
    assert make_etag(3, 1700000000123456, 2) == 'W/"wr-3-1700000000123456-2"'


def test_routes_and_steps_shape(ids):
    res = WalkRouteService().list_for_place(ids["place"]["공학관"], None, None)
    assert re.fullmatch(rf'W/"wr-{ids["place"]["공학관"]}-\d+-2"', res.etag)
    first, second = res.items
    assert first.parking_lot_id == ids["lot"]["공학관 앞 주차장"]  # 우선순위순
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z", first.updated_at)  # 버전 문자열, 마이크로초
    assert first.distance_m == round(first.distance_m, 1) and first.walk_time_min >= 1
    assert [s.step_order for s in first.steps] == [1, 2]
    assert first.steps[0].landmark is None and first.steps[1].landmark.name == "자판기 2대"
    assert all(s.camera_is_default for s in first.steps + second.steps)  # seed_campus 단계에는 카메라 저장값 없음
    assert (first.steps[0].camera.pitch, first.steps[0].camera.zoom) == (55.0, 18.5)


def test_if_none_match_skips_body(ids):
    pid = ids["place"]["공학관"]
    etag = WalkRouteService().list_for_place(pid, None, None).etag
    assert WalkRouteService().list_for_place(pid, None, etag).items is None
    assert WalkRouteService().list_for_place(pid, None, f'W/"other", {etag}').items is None  # 여러 값 중 하나
    assert WalkRouteService().list_for_place(pid, None, 'W/"other"').items is not None


def test_filter_by_parking_lot(ids):
    pid, lot = ids["place"]["공학관"], ids["lot"]["체육관 옆 주차장"]
    res = WalkRouteService().list_for_place(pid, lot, None)
    assert [r.parking_lot_id for r in res.items] == [lot] and res.etag.endswith('-1"')


def test_parking_lot_of_other_place_is_400(ids):
    with pytest.raises(AppError) as e:
        WalkRouteService().list_for_place(ids["place"]["공학관"], ids["lot"]["도서관 주차장"], None)
    assert e.value.status == 400 and e.value.details[0]["reason"] == "not_in_place"


def test_routes_unknown_place_is_404():
    with pytest.raises(AppError) as e:
        WalkRouteService().list_for_place(999999, None, None)
    assert e.value.status == 404
