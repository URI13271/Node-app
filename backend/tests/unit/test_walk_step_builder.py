"""scripts/build_walk_steps.py 단위 테스트 (DB 없이, shapely 필요). 시연 시드(gnu-gajwa)로 확인한다.

시드 폴더는 바꾸지 않는다. 파일을 쓰는 테스트는 tmp_path 에 복사한 시드로 한다.
"""

import json
import shutil

import pytest
from shapely.geometry import LineString, Point

from app.domain.steps import MAX_INSTRUCTION, MAX_STEPS, MIN_STEPS
from scripts.build_walk_steps import build_steps, eul, euro, load, main, turn_phrase
from tests.conftest import DEMO_SEED_DIR


@pytest.fixture(scope="module")
def built():
    steps, problems = build_steps(DEMO_SEED_DIR)
    return steps, problems


def _by_route(steps):
    out = {}
    for s in steps:
        wr = s["walk_route"]
        out.setdefault((wr["place_key"], wr["parking_lot_name"], wr["entrance_name"]), []).append(s)
    return out


def test_josa():
    assert eul("분수대") == "분수대를" and eul("학생회관") == "학생회관을"
    assert euro("북쪽 출입구") == "북쪽 출입구로" and euro("정문") == "정문으로" and euro("서쪽 길") == "서쪽 길로"


def test_turn_phrase_has_side_and_compass():
    assert turn_phrase(90, 180) == "오른쪽(남쪽)으로 꺾어"
    assert turn_phrase(90, 0) == "왼쪽(북쪽)으로 꺾어"
    assert turn_phrase(90, 100) is None


def test_every_route_passes_load_seed_rules(built):
    """load_seed 기준: 경로마다 2~30단계, step_order 연속, 문장 1~200자, 경로 30m 안, 건물 밖."""
    steps, problems = built
    assert problems == []
    w = load(DEMO_SEED_DIR)
    routes = json.loads((DEMO_SEED_DIR / "walk_routes.geojson").read_text(encoding="utf-8"))["features"]
    groups = _by_route(steps)
    assert len(groups) == len(routes)
    for f in routes:
        pr = f["properties"]
        ss = groups[(pr["place_key"], pr["parking_lot_name"], pr["entrance_name"])]
        assert MIN_STEPS <= len(ss) <= MAX_STEPS
        assert [s["step_order"] for s in ss] == list(range(1, len(ss) + 1))
        line = LineString([w.loc.m(*c) for c in f["geometry"]["coordinates"]])
        for s in ss:
            assert 1 <= len(s["instruction"].strip()) <= MAX_INSTRUCTION
            p = Point(w.loc.m(*s["location"]["coordinates"]))
            assert line.distance(p) <= 30
            assert not w.shrunk.contains(p)


def test_first_and_last_step(built):
    steps, _ = built
    for ss in _by_route(steps).values():
        assert ss[0]["instruction"].startswith("주차장에서 나와")
        assert ss[-1]["instruction"].endswith(f"{ss[-1]['walk_route']['entrance_name']}로 들어가기") \
            or ss[-1]["instruction"].endswith("으로 들어가기")


def test_landmark_keys_exist_for_place(built):
    steps, _ = built
    lms = json.loads((DEMO_SEED_DIR / "landmarks.geojson").read_text(encoding="utf-8"))["features"]
    keys = {(f["properties"]["place_key"], f["properties"]["key"]) for f in lms}
    for s in steps:
        if s["landmark_key"]:
            assert (s["walk_route"]["place_key"], s["landmark_key"]) in keys


def test_crossings_are_mentioned(built):
    """경로가 차도를 건너면 그 단계 문장에 건넌다는 말이 있다. 표시 없는 횡단은 주의 문구가 붙는다."""
    steps, _ = built
    text = " ".join(s["instruction"] for s in steps)
    assert "횡단보도로" in text
    assert "횡단보도 표시가 없는 곳이라 좌우를 살피고" in text   # 시드 README 체크리스트 2번 지점


def test_write_keeps_camera_and_is_stable(tmp_path):
    seed = tmp_path / DEMO_SEED_DIR.name
    shutil.copytree(DEMO_SEED_DIR, seed)
    path = seed / "walk_route_steps.json"
    assert main(seed, write=True, diff=False) == 0
    first = json.loads(path.read_text(encoding="utf-8"))
    first[0]["camera"] = {"bearing": 120, "pitch": 55, "zoom": 18}   # 사람이 고친 카메라 값
    path.write_text(json.dumps(first, ensure_ascii=False, indent=1), encoding="utf-8")
    assert main(seed, write=True, diff=False) == 0
    second = json.loads(path.read_text(encoding="utf-8"))
    assert second[0]["camera"] == {"bearing": 120, "pitch": 55, "zoom": 18}
    assert [s["instruction"] for s in second] == [s["instruction"] for s in first]
