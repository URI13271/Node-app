"""관리자 저장소 쓰기 통합 테스트 (BE-14). 테스트 고정 데이터(seed_campus)로 확인한다.

완료 기준: PUT(replace_steps), PATCH(patch_step) 뒤 경로 버전(updated_at)이 바뀐다 (touch_route).
데이터를 바꾸는 테스트는 fresh_db 픽스처로 끝난 뒤 시드를 다시 적재한다.
"""

import pytest
from sqlalchemy import text

from app.db import read_tx, write_tx
from app.repositories import walk_route_repo as repo

PLACE_CENTER = (127.00135, 37.00036)  # 공학관 장소 좌표 = 공학관 건물 안
MAIN_ENTRANCE = (127.00135, 37.000198)  # 공학관 정문 (건물 남쪽 벽 바로 앞)
PATH_START = (127.001631, 37.000036)  # 공학관 앞 주차장 → 정문 경로의 첫 점
JUST_INSIDE_WALL = (127.00135, 37.000207)  # 공학관 남쪽 벽(위도 37.000203)에서 약 0.4m 안쪽
WALL_TOLERANCE_M = 1.0


@pytest.fixture()
def ids(app) -> dict:
    """다시 적재하면 id 가 바뀌므로 테스트마다 이름으로 찾는다."""
    with read_tx() as conn:
        route = conn.execute(
            text("""SELECT r.id FROM walk_route r JOIN parking_lot l ON l.id = r.parking_lot_id
                    JOIN entrance e ON e.id = r.entrance_id
                    WHERE l.name = '공학관 앞 주차장' AND e.name = '정문'""")
        ).scalar_one()
        steps = conn.execute(
            text("SELECT id FROM walk_route_step WHERE walk_route_id = :r ORDER BY step_order"), {"r": route}
        ).scalars().all()
        landmarks = dict(conn.execute(text("SELECT name, id FROM landmark")).all())
        place = conn.execute(text("SELECT id FROM place WHERE name = '공학관'")).scalar_one()
    return {"route": route, "steps": steps, "landmark": landmarks, "place": place}


def _version(conn, route_id: int):
    return conn.execute(text("SELECT updated_at FROM walk_route WHERE id = :r"), {"r": route_id}).scalar_one()


# ---------- 읽기 성격 (잠금, 소속, 거리, 건물) ----------


def test_lock_route_returns_current_version(ids):
    with write_tx() as conn:
        assert repo.lock_route(conn, ids["route"]) == _version(conn, ids["route"])
        assert repo.lock_route(conn, 999999) is None


def test_step_route_id(ids):
    with read_tx() as conn:
        assert repo.step_route_id(conn, ids["steps"][0]) == ids["route"]
        assert repo.step_route_id(conn, 999999) is None


def test_count_landmarks_in_route_place(ids):
    lm = ids["landmark"]
    with read_tx() as conn:
        assert repo.count_landmarks_in_route_place(conn, ids["route"], [lm["자판기 2대"], lm["벤치 쉼터"]]) == 2
        assert repo.count_landmarks_in_route_place(conn, ids["route"], [lm["자판기 2대"], lm["분수대"]]) == 1  # 분수대는 중앙도서관
        assert repo.count_landmarks_in_route_place(conn, ids["route"], [lm["자판기 2대"], lm["자판기 2대"]]) == 1  # 중복은 하나로
        assert repo.count_landmarks_in_route_place(conn, ids["route"], []) == 0


def test_distances_from_path_in_meters(ids):
    with read_tx() as conn:
        on_path, east = repo.distances_from_path(conn, ids["route"], [PATH_START, (PATH_START[0] + 0.001, PATH_START[1])])
    assert on_path < 0.1
    assert 70 < east < 100  # 경도 0.001도 ≈ 89m (위도 37도). 도 단위(0.001)가 아니라 미터


def test_buildings_containing(ids):
    with read_tx() as conn:
        inside, entrance, near_wall, outside = repo.buildings_containing(
            conn, ids["route"], [PLACE_CENTER, MAIN_ENTRANCE, JUST_INSIDE_WALL, PATH_START], WALL_TOLERANCE_M
        )
    assert inside == "공학관"
    assert entrance is None  # 벽 바로 앞은 건물 밖
    assert near_wall is None  # 벽에서 1m 안쪽까지는 GPS, 지도 오차로 보고 건물 밖으로 본다
    assert outside is None


# ---------- 쓰기 ----------


def test_replace_steps_and_touch_route(ids, fresh_db):
    lm = ids["landmark"]
    new_steps = [
        {"step_order": 1, "landmark_id": None, "instruction": "주차장 출구로 나가기", "location": PATH_START, "camera": None},
        {
            "step_order": 2,
            "landmark_id": lm["자판기 2대"],
            "instruction": "자판기를 왼쪽에 두고 정문까지",
            "location": MAIN_ENTRANCE,
            "camera": {"bearing": 10.0, "pitch": 50.0, "zoom": 18.0},
        },
    ]
    with write_tx() as conn:
        before = repo.lock_route(conn, ids["route"])
        repo.replace_steps(conn, ids["route"], new_steps, "test-req-1")
        after = repo.touch_route(conn, ids["route"])
    assert after > before

    with read_tx() as conn:
        steps = repo.list_steps(conn, [ids["route"]])
        who = conn.execute(
            text("SELECT DISTINCT updated_by FROM walk_route_step WHERE walk_route_id = :r"), {"r": ids["route"]}
        ).scalars().all()
        assert _version(conn, ids["route"]) == after
    assert [(s["step_order"], s["instruction"]) for s in steps] == [(1, "주차장 출구로 나가기"), (2, "자판기를 왼쪽에 두고 정문까지")]
    assert steps[0]["camera"] is None and steps[1]["camera"] == {"bearing": 10.0, "pitch": 50.0, "zoom": 18.0}
    assert steps[1]["landmark_name"] == "자판기 2대" and steps[1]["location"]["coordinates"] == list(MAIN_ENTRANCE)
    assert set(s["id"] for s in steps).isdisjoint(ids["steps"])  # 예전 단계는 지워짐
    assert who == ["test-req-1"]


def test_patch_step_only_given_columns(ids, fresh_db):
    step = ids["steps"][1]
    with read_tx() as conn:
        old = {s["id"]: s for s in repo.list_steps(conn, [ids["route"]])}[step]
    with write_tx() as conn:
        repo.patch_step(conn, step, {"instruction": "바뀐 문장", "camera": {"bearing": 90.0, "pitch": 40.0, "zoom": 19.0}}, "req-a")
    with read_tx() as conn:
        s = {x["id"]: x for x in repo.list_steps(conn, [ids["route"]])}[step]
    assert s["instruction"] == "바뀐 문장" and s["camera"] == {"bearing": 90.0, "pitch": 40.0, "zoom": 19.0}
    assert (s["landmark_id"], s["location"]) == (old["landmark_id"], old["location"])  # 안 보낸 칼럼은 그대로

    with write_tx() as conn:
        repo.patch_step(conn, step, {"camera": None}, "req-b")  # null → 카메라 셋 다 지움
    with read_tx() as conn:
        s = {x["id"]: x for x in repo.list_steps(conn, [ids["route"]])}[step]
    assert s["camera"] is None and s["instruction"] == "바뀐 문장"


def test_touch_route_changes_every_time_even_in_one_transaction(ids, fresh_db):
    """now() 는 트랜잭션 시작 시각이라 같은 트랜잭션 안에서 같은 값. clock_timestamp() 라서 매번 달라야 한다."""
    with write_tx() as conn:
        a = repo.touch_route(conn, ids["route"])
        b = repo.touch_route(conn, ids["route"])
    assert b > a


def test_touch_route_changes_etag_material(ids, fresh_db):
    with read_tx() as conn:
        before = repo.version_info(conn, ids["place"], None)
    with write_tx() as conn:
        repo.touch_route(conn, ids["route"])
    with read_tx() as conn:
        after = repo.version_info(conn, ids["place"], None)
    assert after[0] > before[0] and after[1] == before[1]  # 경로 수는 그대로, 시각만 올라감 → ETag 가 바뀜


def test_write_rolls_back_on_error(ids, fresh_db):
    with pytest.raises(RuntimeError):
        with write_tx() as conn:
            repo.replace_steps(conn, ids["route"], [], "req-x")  # 단계를 모두 지운 상태에서
            raise RuntimeError("저장 도중 실패")
    with read_tx() as conn:
        assert len(repo.list_steps(conn, [ids["route"]])) == len(ids["steps"])  # 지운 것이 되돌아옴
