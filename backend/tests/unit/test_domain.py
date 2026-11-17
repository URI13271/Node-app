"""domain/ 순수 함수 단위 테스트 (설계서 2.4.5). DB 없이 실행된다.

관리자 키, 요청 제한기(core/security.py) 테스트는 BE-13, BE-17 에서 따로 추가한다.
"""
import pytest

from app.domain.attribution import attributions
from app.domain.building import render_height
from app.domain.camera import Camera, parking_camera, place_camera, step_cameras
from app.domain.geo import azimuth_deg
from app.domain.navigation import DataIntegrityError, ParkingCandidate, select_navigation_target, walk_time_min
from app.domain.steps import check_steps, clean_instruction


def test_azimuth_cardinal_directions():
    o = (127.0, 37.0)
    assert azimuth_deg(o, (127.0, 37.001)) == 0.0
    assert azimuth_deg(o, (127.001, 37.0)) == pytest.approx(90.0, abs=0.1)
    assert azimuth_deg(o, (127.0, 36.999)) == 180.0
    assert azimuth_deg(o, (126.999, 37.0)) == pytest.approx(270.0, abs=0.1)
    assert azimuth_deg(o, o) is None


def test_place_camera_uses_stored_value_first():
    stored = Camera(10, 50, 17)
    assert place_camera(stored, (127, 37), (127, 37.001)) is stored
    assert place_camera(None, (127, 37), (127, 37.001)) == Camera(0.0, 60.0, 17.5)


def test_parking_camera_faces_place_from_that_lot():
    """우선순위 2 주차장도 자기 위치에서 건물을 보는 방향이어야 한다 (프로토타입 검토 v1.2 2.1)."""
    place = (127.0, 37.0)
    east_lot = (127.001, 37.0)                                  # 장소의 동쪽 주차장 → 서쪽(270°)을 봐야 함
    cam, is_default = parking_camera(None, east_lot, place, fallback_bearing=10.0)
    assert is_default is True and cam.bearing == pytest.approx(270.0, abs=0.1) and (cam.pitch, cam.zoom) == (60.0, 17.5)
    stored = Camera(330, 60, 17.2)
    assert parking_camera(stored, east_lot, place, 10.0) == (stored, False)
    assert parking_camera(None, place, place, 10.0)[0].bearing == 10.0   # 같은 좌표면 장소 카메라 방향


def test_step_cameras_default_points_to_next_step_and_last_to_entrance():
    locs = [(127.0, 37.0), (127.0, 37.001)]
    cams = step_cameras([None, None], locs, entrance=(127.001, 37.001), fallback_bearing=123.0)
    assert cams[0] == (Camera(0.0, 55.0, 18.5), True)
    assert cams[1][0].bearing == pytest.approx(90.0, abs=0.1) and cams[1][1] is True


def test_step_cameras_same_point_falls_back():
    locs = [(127.0, 37.0), (127.0, 37.0)]
    cams = step_cameras([None, None], locs, entrance=(127.0, 37.0), fallback_bearing=45.0)
    assert cams[0][0].bearing == 45.0        # 이전 단계 없음 → 장소 카메라 방위각
    assert cams[1][0].bearing == 45.0        # 이전 단계 방위각
    stored = step_cameras([Camera(1, 2, 3), None], locs, (127.0, 37.0), 45.0)
    assert stored[0] == (Camera(1, 2, 3), False) and stored[1][0].bearing == 1


@pytest.mark.parametrize("h,fl,expected", [(12.34, 5, 12.3), (None, 5, 15.0), (None, None, 6.0), (0, None, 6.0)])
def test_render_height(h, fl, expected):
    assert render_height(h, fl) == expected


@pytest.mark.parametrize("stored,dist,expected", [(None, 84.2, 2), (None, 20, 1), (None, 55.7, 1), (5, 999, 5)])
def test_walk_time_min(stored, dist, expected):
    assert walk_time_min(stored, dist) == expected


def test_navigation_target_lowest_priority_then_id():
    lots = [ParkingCandidate(3, "B", 1, 0, 0), ParkingCandidate(2, "A", 1, 0, 0), ParkingCandidate(1, "C", 2, 0, 0)]
    assert select_navigation_target(lots).id == 2
    with pytest.raises(DataIntegrityError):
        select_navigation_target([])


def test_check_steps_collects_all_violations():
    vs = check_steps([1, 3], ["  ", "가" * 201])
    reasons = {v.reason for v in vs}
    assert reasons == {"step_order_gap", "too_short", "too_long"}
    assert {v.reason for v in check_steps([1], ["a"])} == {"too_few_steps"}
    assert check_steps([2, 1], ["a", "b"]) == []
    assert {v.reason for v in check_steps(list(range(1, 32)), ["a"] * 31)} == {"too_many_steps"}


def test_clean_instruction_removes_control_chars():
    assert clean_instruction(" 정문\x07으로 ") == "정문으로"


def test_attributions_unique_ordered_default():
    assert attributions(["manual", "osm", "manual"]) == ["© OpenStreetMap contributors", "직접 조사"]
    assert attributions([]) == ["직접 조사"]
