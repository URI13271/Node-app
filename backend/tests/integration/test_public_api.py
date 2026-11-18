"""여행객 조회 API 4개 (API 명세서 3.2~3.5, F-01~F-05, BE-11). 테스트 고정 데이터(seed_campus)로 확인한다.

- 응답 필드 이름이 frontend/mock/ 의 예시 응답과 같은지 (프론트가 ?mock=0 으로 바꿔도 그대로 동작해야 한다)
- 시연 시드(gnu-gajwa) 건물 응답이 gzip 후 200KB 이하인지
- load_seed 적재 검사(crosses_building, inside_building)가 실제로 막는지 (BE-04 에서 미뤄 둔 테스트)

요청 제한과 공통 헤더(BE-17)는 그 작업에서 테스트를 추가한다.
conftest 의 client 픽스처는 요청 제한기(BE-17)를 초기화하므로, 여기서는 제한기 없이 쓰는 api 픽스처를 쓴다.
"""

import gzip
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import DEMO_SEED_DIR, SEED_DIR
from tests.integration.conftest import place_id

MOCK_DIR = Path(__file__).resolve().parents[3] / "frontend" / "mock"


@pytest.fixture()
def api(app) -> TestClient:
    return TestClient(app)


def _same_keys(real, mock, path="") -> list[str]:
    """mock 에 있는 키가 실제 응답에 모두 있는지 (null 이라 빠진 키는 제외)."""
    out = []
    if isinstance(mock, dict) and isinstance(real, dict):
        for k, v in mock.items():
            if k not in real:
                out.append(f"{path}.{k} 없음")
            else:
                out += _same_keys(real[k], v, f"{path}.{k}")
    elif isinstance(mock, list) and isinstance(real, list) and mock and real:
        out += _same_keys(real[0], mock[0], f"{path}[0]")
    return out


def _mock(name: str):
    return json.loads((MOCK_DIR / name).read_text(encoding="utf-8"))


# ---------- GET /health (BE-12) ----------


def test_health_with_real_db(api):
    r = api.get("/health")
    assert r.status_code == 200 and r.json()["db"] == "ok" and r.json()["status"] == "ok"
    assert r.headers["cache-control"] == "no-store"


# ---------- GET /places ----------


def test_places_list_and_search(api):
    r = api.get("/api/v1/places")
    body = r.json()
    assert r.status_code == 200 and (body["total"], body["limit"], body["offset"]) == (3, 20, 0)
    assert [p["name"] for p in body["items"]] == ["공학관", "중앙도서관", "학생회관"]
    assert r.headers["cache-control"] == "public, max-age=60"
    assert api.get("/api/v1/places", params={"q": " 도서 "}).json()["total"] == 1  # 앞뒤 공백 무시
    assert api.get("/api/v1/places", params={"q": "%"}).json()["total"] == 0  # % 는 글자 그대로
    assert api.get("/api/v1/places", params={"q": "없는곳"}).json() == {"total": 0, "limit": 20, "offset": 0, "items": []}


def test_places_invalid_query(api):
    r = api.get("/api/v1/places", params={"limit": 0})
    assert r.status_code == 400
    detail = r.json()["error"]["details"][0]
    assert (detail["field"], detail["reason"]) == ("query.limit", "out_of_range")
    assert api.get("/api/v1/places", params={"q": "가" * 51}).status_code == 400
    assert api.get("/api/v1/places", params={"limit": "abc"}).json()["error"]["details"][0]["reason"] == "invalid_type"


# ---------- GET /places/{id} ----------


def test_place_detail_shape(api):
    d = api.get(f"/api/v1/places/{place_id(api, '공학관')}").json()
    assert d["entrances"][0]["is_main"] is True
    assert [lot["priority"] for lot in d["parking_lots"]] == [1, 2]
    assert d["navigation_target"]["name"] == "공학관 앞 주차장"
    assert set(d["camera"]) == {"bearing", "pitch", "zoom"} and d["camera"]["pitch"] == 60
    assert d["parking_lots"][1]["camera"] == {"bearing": 330, "pitch": 60, "zoom": 17.2}
    assert d["parking_lots"][1]["camera_is_default"] is False
    lot1 = d["parking_lots"][0]
    assert lot1["camera_is_default"] is True and lot1["area"]["type"] == "Polygon"
    assert lot1["camera"]["bearing"] == d["camera"]["bearing"]  # 1순위 주차장 → 장소 방향 = 장소 카메라
    assert d["arrival_radius_m"] == 150 and "직접 조사" in d["attributions"]
    lng, lat = d["location"]["coordinates"]
    assert len(str(lng).split(".")[1]) <= 6 and len(str(lat).split(".")[1]) <= 6


def test_place_not_found_and_bad_id(api):
    r = api.get("/api/v1/places/99999")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
    assert r.headers["cache-control"] == "no-store"
    assert api.get("/api/v1/places/0").status_code == 400


# ---------- GET /places/{id}/buildings ----------


def test_buildings(api):
    r = api.get(f"/api/v1/places/{place_id(api, '공학관')}/buildings")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/geo+json")
    assert r.headers["cache-control"] == "public, max-age=300"
    fc = r.json()
    assert fc["type"] == "FeatureCollection" and fc["features"][0]["properties"]["is_target"] is True
    heights = {f["properties"]["name"]: f["properties"]["render_height_m"] for f in fc["features"]}
    assert (heights["공학관"], heights["체육관"], heights["공동실험관"]) == (15.0, 14.0, 6.0)
    assert api.get("/api/v1/places/99999/buildings").status_code == 404


# ---------- GET /places/{id}/walk-routes ----------


def test_walk_routes_etag_and_filter(api):
    pid = place_id(api, "공학관")
    r = api.get(f"/api/v1/places/{pid}/walk-routes")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"
    etag = r.headers["etag"]
    assert etag.startswith(f'W/"wr-{pid}-') and etag.endswith('-2"')
    items = r.json()["items"]
    assert len(items) == 2 and all(len(i["steps"]) >= 2 for i in items)
    first = items[0]
    assert first["distance_m"] > 0 and first["walk_time_min"] >= 1
    assert first["steps"][0]["camera_is_default"] is True and first["steps"][0]["camera"]["pitch"] == 55
    assert len(first["updated_at"].split(".")[1]) == 7  # 마이크로초 6자리 + Z

    not_modified = api.get(f"/api/v1/places/{pid}/walk-routes", headers={"If-None-Match": etag})
    assert not_modified.status_code == 304 and not_modified.content == b""
    assert not_modified.headers["etag"] == etag and not_modified.headers["cache-control"] == "no-cache"

    lot = first["parking_lot_id"]
    only = api.get(f"/api/v1/places/{pid}/walk-routes", params={"parking_lot_id": lot}).json()["items"]
    assert [i["parking_lot_id"] for i in only] == [lot]


def test_walk_routes_parking_lot_of_other_place(api):
    lib, eng = place_id(api, "중앙도서관"), place_id(api, "공학관")
    lot_of_eng = api.get(f"/api/v1/places/{eng}").json()["parking_lots"][0]["id"]
    r = api.get(f"/api/v1/places/{lib}/walk-routes", params={"parking_lot_id": lot_of_eng})
    assert r.status_code == 400 and r.json()["error"]["details"][0]["reason"] == "not_in_place"
    assert api.get("/api/v1/places/99999/walk-routes").status_code == 404


# ---------- frontend/mock 과 필드 이름 비교 ----------


def test_response_fields_match_frontend_mock(api):
    pid = place_id(api, "공학관")
    pairs = [
        ("/api/v1/places", "places.json"),
        (f"/api/v1/places/{pid}", "places/1.json"),
        (f"/api/v1/places/{pid}/buildings", "places/1/buildings.json"),
        (f"/api/v1/places/{pid}/walk-routes", "places/1/walk-routes.json"),
    ]
    problems = []
    for url, mock_file in pairs:
        problems += [f"{url}: {p}" for p in _same_keys(api.get(url).json(), _mock(mock_file))]
    assert problems == []


# ---------- 시연 시드 (gnu-gajwa) ----------


def test_demo_seed_buildings_gzip_under_200kb(app, api, fresh_db):
    """완료 기준: 건물 응답 gzip 후 200KB 이하. 건물이 가장 많은 시연 장소로 잰다."""
    from scripts import load_seed

    try:
        assert load_seed.load(DEMO_SEED_DIR) == 0
        sizes = {}
        for p in api.get("/api/v1/places", params={"limit": 100}).json()["items"]:
            r = api.get(f"/api/v1/places/{p['id']}/buildings")
            sizes[p["name"]] = len(gzip.compress(r.content))
        assert max(sizes.values()) <= 200 * 1024, sizes
    finally:
        _delete_demo_seed()


def _delete_demo_seed():
    from sqlalchemy import create_engine, text

    from app.config import get_settings

    eng = create_engine(get_settings().MIGRATION_DATABASE_URL)
    try:
        with eng.begin() as c:
            c.execute(text("DELETE FROM place WHERE seed_key LIKE 'gnu-%'"))
            c.execute(text("DELETE FROM walk_network_feature WHERE area_key = 'gnu-gajwa'"))
    finally:
        eng.dispose()


# ---------- load_seed 적재 검사 (BE-04) ----------


def _copy_seed(tmp_path, edit):
    import shutil

    d = tmp_path / "seed_campus"
    shutil.copytree(SEED_DIR, d)
    edit(d)
    return d


def test_load_seed_rejects_route_through_building(app, fresh_db, tmp_path):
    """crosses_building: 경로가 건물(벽 1m 안쪽) 안을 1m 넘게 지나면 경로 파일을 되돌리고 멈춘다."""
    from scripts import load_seed

    def edit(d):
        p = d / "walk_routes.geojson"
        fc = json.loads(p.read_text(encoding="utf-8"))
        fc["features"][0]["geometry"]["coordinates"] = [[127.001631, 37.000036], [127.0012, 37.0004], [127.00135, 37.000198]]
        p.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SystemExit) as e:
        load_seed.load(_copy_seed(tmp_path, edit))
    assert "crosses_building" in str(e.value) and "공학관" in str(e.value)


def test_load_seed_rejects_step_inside_building(app, fresh_db, tmp_path):
    """inside_building: 단계 지점이 건물 안이면 단계 파일을 되돌리고 멈춘다."""
    from scripts import load_seed

    def edit(d):
        p = d / "walk_route_steps.json"
        steps = json.loads(p.read_text(encoding="utf-8"))
        steps[1]["location"]["coordinates"] = [127.00135, 37.0003]  # 공학관 남쪽 벽에서 11m 안쪽
        p.write_text(json.dumps(steps, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SystemExit) as e:
        load_seed.load(_copy_seed(tmp_path, edit))
    assert "inside_building" in str(e.value)
