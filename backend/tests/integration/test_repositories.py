"""조회 저장소 통합 테스트 (BE-07). 테스트 고정 데이터(seed_campus)의 값과 함수별로 비교한다.

place_repo 6개, building_repo 2개, walk_route_repo 조회 5개. 쓰기 함수는 BE-14 에서 따로 테스트한다.
"""

from datetime import datetime

import pytest

from app.db import read_tx
from app.repositories import building_repo, place_repo, walk_route_repo


@pytest.fixture(scope="module")
def ids(app) -> dict:
    """이름 → id. 다시 적재하면 id 가 바뀔 수 있어 테스트마다 이름으로 찾는다."""
    from sqlalchemy import text

    with read_tx() as conn:
        places = dict(conn.execute(text("SELECT name, id FROM place")).all())
        lots = dict(conn.execute(text("SELECT name, id FROM parking_lot")).all())
    return {"place": places, "lot": lots}


# ---------- place_repo ----------


def test_search_places_all_sorted_by_name(ids):
    with read_tx() as conn:
        total, items = place_repo.search_places(conn, None, 20, 0)
    assert total == 3
    assert [p["name"] for p in items] == ["공학관", "중앙도서관", "학생회관"]
    assert set(items[0]) == {"id", "name", "category", "cover_image_url", "location"}
    assert items[0]["location"] == {"type": "Point", "coordinates": [127.00135, 37.00036]}


def test_search_places_filter_and_paging(ids):
    with read_tx() as conn:
        assert place_repo.search_places(conn, "도서", 20, 0)[0] == 1
        assert place_repo.search_places(conn, "없는장소", 20, 0) == (0, [])
        total, page = place_repo.search_places(conn, None, 1, 1)
    assert total == 3 and [p["name"] for p in page] == ["중앙도서관"]  # total 은 페이지와 상관없이 전체 개수


def test_search_places_escapes_like_wildcards(ids):
    """% 와 _ 는 와일드카드가 아니라 글자로 찾는다 (모든 장소가 걸리면 안 됨)."""
    with read_tx() as conn:
        assert place_repo.search_places(conn, "%", 20, 0)[0] == 0
        assert place_repo.search_places(conn, "_", 20, 0)[0] == 0


def test_get_place(ids):
    with read_tx() as conn:
        p = place_repo.get_place(conn, ids["place"]["공학관"])
        missing = place_repo.get_place(conn, 999999)
    assert missing is None
    assert p["name"] == "공학관" and p["category"] == "campus" and p["arrival_radius_m"] == 150
    assert (p["lng"], p["lat"]) == (127.00135, 37.00036) and isinstance(p["lng"], float)
    assert p["camera"] is None  # seed_campus 장소에는 카메라 저장값이 없음


def test_place_exists(ids):
    with read_tx() as conn:
        assert place_repo.place_exists(conn, ids["place"]["학생회관"]) is True
        assert place_repo.place_exists(conn, 999999) is False


def test_list_entrances_main_first(ids):
    with read_tx() as conn:
        rows = place_repo.list_entrances(conn, ids["place"]["공학관"])
    assert [(e["name"], e["is_main"]) for e in rows] == [("정문", True), ("동쪽 출입구", False)]
    assert rows[0]["location"]["type"] == "Point"


def test_list_parking_lots_by_priority_with_camera(ids):
    with read_tx() as conn:
        rows = place_repo.list_parking_lots(conn, ids["place"]["공학관"])
    assert [(p["name"], p["priority"]) for p in rows] == [("공학관 앞 주차장", 1), ("체육관 옆 주차장", 2)]
    assert rows[0]["camera"] is None
    assert rows[1]["camera"] == {"bearing": 330, "pitch": 60, "zoom": 17.2}
    assert rows[0]["area"]["type"] == "Polygon" and isinstance(rows[0]["lng"], float)
    assert (rows[0]["capacity"], rows[0]["is_free"]) == (30, True)


def test_list_landmarks_sorted_by_name(ids):
    with read_tx() as conn:
        rows = place_repo.list_landmarks(conn, ids["place"]["학생회관"])
    assert [r["name"] for r in rows] == sorted(["편의점 간판", "붉은 벽돌 3층 건물", "버스 정류장", "화단"])


def test_unknown_place_gives_empty_lists(ids):
    with read_tx() as conn:
        assert place_repo.list_entrances(conn, 999999) == []
        assert place_repo.list_parking_lots(conn, 999999) == []
        assert place_repo.list_landmarks(conn, 999999) == []


# ---------- building_repo ----------


def test_list_buildings_target_first(ids):
    with read_tx() as conn:
        rows = building_repo.list_buildings(conn, ids["place"]["공학관"])
    assert len(rows) == 8 and rows[0]["name"] == "공학관" and rows[0]["is_target"] is True
    assert sum(r["is_target"] for r in rows) == 1
    assert rows[0]["footprint"]["type"] == "Polygon"
    gym = next(r for r in rows if r["name"] == "체육관")
    assert (gym["height_m"], gym["floor_count"]) == (14, None)


def test_list_sources_unique(ids):
    with read_tx() as conn:
        assert sorted(building_repo.list_sources(conn, ids["place"]["공학관"])) == ["manual", "osm", "public_data"]
        assert building_repo.list_sources(conn, 999999) == []


# ---------- walk_route_repo (조회) ----------


def test_version_info(ids):
    with read_tx() as conn:
        micros, n = walk_route_repo.version_info(conn, ids["place"]["공학관"], None)
        one = walk_route_repo.version_info(conn, ids["place"]["공학관"], ids["lot"]["체육관 옆 주차장"])
        none = walk_route_repo.version_info(conn, 999999, None)
    assert n == 2 and one[1] == 1
    assert abs(micros / 1_000_000 - datetime.now().timestamp()) < 24 * 3600  # 마이크로초 Unix 시각
    assert none == (0, 0)


def test_parking_lot_place(ids):
    with read_tx() as conn:
        assert walk_route_repo.parking_lot_place(conn, ids["lot"]["도서관 주차장"]) == ids["place"]["중앙도서관"]
        assert walk_route_repo.parking_lot_place(conn, 999999) is None


def test_list_routes_by_lot_priority(ids):
    with read_tx() as conn:
        rows = walk_route_repo.list_routes(conn, ids["place"]["공학관"], None)
        only = walk_route_repo.list_routes(conn, ids["place"]["공학관"], ids["lot"]["체육관 옆 주차장"])
    assert [r["parking_lot_id"] for r in rows] == [ids["lot"]["공학관 앞 주차장"], ids["lot"]["체육관 옆 주차장"]]
    assert [r["description"] for r in only] == ["차도를 한 번 건넘"]
    r = rows[0]
    assert r["path"]["type"] == "LineString" and r["entrance_location"]["type"] == "Point"
    assert r["distance_m"] > 0 and isinstance(r["updated_at"], datetime)


def test_list_steps_ordered_with_landmark_name(ids):
    with read_tx() as conn:
        routes = walk_route_repo.list_routes(conn, ids["place"]["공학관"], None)
        steps = walk_route_repo.list_steps(conn, [r["id"] for r in routes])
        assert walk_route_repo.list_steps(conn, []) == []
    assert len(steps) == 5
    first = [s for s in steps if s["walk_route_id"] == routes[0]["id"]]
    assert [s["step_order"] for s in first] == [1, 2]
    assert [s["landmark_name"] for s in first] == [None, "자판기 2대"]
    assert first[0]["camera"] is None and first[0]["location"]["type"] == "Point"


def test_route_place_id(ids):
    with read_tx() as conn:
        routes = walk_route_repo.list_routes(conn, ids["place"]["학생회관"], None)
        assert {walk_route_repo.route_place_id(conn, r["id"]) for r in routes} == {ids["place"]["학생회관"]}
        assert walk_route_repo.route_place_id(conn, 999999) is None
