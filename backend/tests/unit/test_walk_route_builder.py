"""scripts/build_walk_routes.py 단위 테스트 (DB 없이, shapely 필요). 시연 시드(gnu-gajwa)로 확인한다.

시드 폴더는 바꾸지 않는다. 파일을 쓰는 테스트는 tmp_path 에 복사한 시드로 한다.
"""

import json
import shutil
from pathlib import Path

import pytest
from shapely.geometry import LineString

from scripts.build_walk_routes import Graph, build, check_path, load_world
from tests.conftest import DEMO_SEED_DIR

# 시드 README 현장 조사 체크리스트 2번의 표시 없는 횡단 지점(35.152795, 128.099881)을 가로지르는 가상의 횡단보도
MANUAL_LINE = [[128.099897, 35.152866], [128.099865, 35.152724]]


def _world(seed_dir: Path = DEMO_SEED_DIR):
    net, loc, nodes, polys, shrunk, manual = load_world(seed_dir)
    return loc, Graph(net, nodes, shrunk, manual), shrunk, manual


def _routes(seed_dir: Path) -> list[dict]:
    return json.loads((seed_dir / "walk_routes.geojson").read_text(encoding="utf-8"))["features"]


def _copy_seed(tmp_path: Path) -> Path:
    dst = tmp_path / DEMO_SEED_DIR.name  # 폴더 이름(지역 key)을 그대로 쓴다
    shutil.copytree(DEMO_SEED_DIR, dst)
    return dst


@pytest.fixture(scope="module")
def rebuilt(tmp_path_factory) -> Path:
    """시드를 복사해 경로를 다시 만든 결과 (테스트 여러 개가 같이 쓴다)."""
    seed = _copy_seed(tmp_path_factory.mktemp("rebuilt"))
    assert build(seed, write=True) == 0
    return seed


def test_routes_do_not_pass_through_buildings(rebuilt):
    """TODO 1: 보행망 위 최단 경로가 건물을 통과하지 않음 (건물 통과 0m). 저장된 경로와 새로 만든 경로 모두."""
    loc, g, shrunk, _ = _world()
    for seed in (DEMO_SEED_DIR, rebuilt):
        features = _routes(seed)
        assert len(features) == 6
        for f in features:
            line = LineString([loc.m(*c) for c in f["geometry"]["coordinates"]])
            assert check_path(line, g, shrunk)["inside_building_m"] == 0, f["properties"]


def test_roads_are_crossed_only_at_crosswalks(rebuilt):
    """TODO 2: 차도는 횡단보도에서만 건넘 (횡단보도 밖 횡단 0곳). 표시 없는 횡단 지점은 bad 가 아니라 확인 필요로 따로 센다."""
    loc, g, shrunk, _ = _world()
    for seed in (DEMO_SEED_DIR, rebuilt):
        for f in _routes(seed):
            line = LineString([loc.m(*c) for c in f["geometry"]["coordinates"]])
            assert check_path(line, g, shrunk)["bad_crossings"] == [], f["properties"]


def test_manual_crossing_is_used(tmp_path):
    """TODO 3: manual_crossings.json 의 횡단보도를 경로에 포함. 표시 없는 횡단이 사라지고 경로가 그 횡단보도를 지난다."""
    seed = _copy_seed(tmp_path)
    (seed / "osm" / "manual_crossings.json").write_text(json.dumps({"crossings": [{"line": MANUAL_LINE}]}), encoding="utf-8")
    assert build(seed, write=True) == 0

    loc, g, shrunk, manual = _world(seed)
    assert len(manual) == 1
    route = next(
        f for f in _routes(seed) if f["properties"]["place_key"] == "gnu-liberal-arts" and f["properties"]["entrance_name"] == "북쪽 출입구"
    )
    line = LineString([loc.m(*c) for c in route["geometry"]["coordinates"]])
    res = check_path(line, g, shrunk)
    assert res["unmarked_crossings"] == [] and res["bad_crossings"] == []
    assert line.distance(manual[0]) < 1.0


def test_check_mode_does_not_write(tmp_path):
    """TODO 4: --check 는 파일을 바꾸지 않음."""
    seed = _copy_seed(tmp_path)
    path = seed / "walk_routes.geojson"
    path.write_text(path.read_text(encoding="utf-8").replace("\n", "\n\n"), encoding="utf-8")  # 다시 쓰면 반드시 달라지는 모양
    before, mtime = path.read_bytes(), path.stat().st_mtime_ns
    assert build(seed, write=False) == 0
    assert path.read_bytes() == before and path.stat().st_mtime_ns == mtime


def test_rebuild_gives_same_routes_as_saved(rebuilt):
    """같은 입력이면 같은 경로 (사전 계산 결과를 언제든 다시 만들 수 있어야 한다). 줄바꿈 차이는 보지 않는다."""
    assert _routes(rebuilt) == _routes(DEMO_SEED_DIR)


def test_straight_line_through_library_is_detected():
    """처음 초안처럼 주차장에서 입구까지 곧게 그은 선은 도서관 옆 건물을 지난다 (검사가 실제로 잡아내는지)."""
    loc, g, shrunk, _ = _world()
    line = LineString(
        [loc.m(128.099082, 35.154176), loc.m(128.09887, 35.1537), loc.m(128.098874, 35.153359), loc.m(128.099135, 35.153266)]
    )
    assert check_path(line, g, shrunk)["inside_building_m"] > 1
