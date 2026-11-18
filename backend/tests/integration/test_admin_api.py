"""관리자 API 3개 (API 명세서 3.6~3.8, F-06, N-04, BE-16). 테스트 고정 데이터(seed_campus)로 확인한다.

완료 기준: 키 검사, 잠금 429, PUT, PATCH, 409.
분당 요청 수 제한(429 too_many_requests), 413, 415 는 미들웨어(BE-17) 테스트에서 본다.
conftest 의 client 픽스처는 분당 제한기(BE-17)도 초기화하므로, 여기서는 관리자 키 잠금만 초기화하는 api 픽스처를 쓴다.
"""

import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import ADMIN, place_id


@pytest.fixture()
def api(app) -> TestClient:
    app.state.admin_fail_limiter.reset()  # 앞 테스트의 실패 계수가 남지 않게
    return TestClient(app)


def _route(api, place_name="공학관", idx=0):
    pid = place_id(api, place_name)
    return pid, api.get(f"/api/v1/places/{pid}/walk-routes").json()["items"][idx]


def _body(route, **over):
    steps = [
        {
            "step_order": s["step_order"],
            "instruction": s["instruction"],
            "landmark_id": s["landmark"]["id"] if s["landmark"] else None,
            "location": s["location"],
            "camera": None if s["camera_is_default"] else s["camera"],
        }
        for s in route["steps"]
    ]
    return {"expected_updated_at": route["updated_at"], "updated_by": "테스트", "steps": steps, **over}


# ---------- GET /admin/me, 키 검사 ----------


def test_me_requires_key(api):
    assert api.get("/api/v1/admin/me").status_code == 401
    assert api.get("/api/v1/admin/me", headers={"X-Admin-Key": "wrong"}).status_code == 401
    r = api.get("/api/v1/admin/me", headers=ADMIN)
    assert r.status_code == 200 and r.json() == {"role": "admin"} and r.headers["cache-control"] == "no-store"


def test_lockout_after_five_failures_even_with_right_key(api):
    codes = [api.get("/api/v1/admin/me", headers={"X-Admin-Key": "bad"}).status_code for _ in range(5)]
    assert codes == [401, 401, 401, 401, 429]
    r = api.get("/api/v1/admin/me", headers=ADMIN)
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 500
    assert r.json()["error"]["details"][0]["reason"] == "locked"


def test_all_admin_routes_check_key_first(api):
    _, route = _route(api)
    put = api.put(f"/api/v1/admin/walk-routes/{route['id']}/steps", content="{broken", headers={"Content-Type": "application/json"})
    patch = api.patch(f"/api/v1/admin/walk-route-steps/{route['steps'][0]['id']}", json={"updated_by": "a", "instruction": "b"})
    assert put.status_code == 401 and patch.status_code == 401  # 깨진 JSON 이어도 400 이 아니라 401


# ---------- PUT /admin/walk-routes/{id}/steps ----------


def test_put_replaces_steps_and_changes_version(api, fresh_db):
    pid, route = _route(api)
    etag_before = api.get(f"/api/v1/places/{pid}/walk-routes").headers["etag"]
    body = _body(route)
    body["steps"][0]["instruction"] = "  수정한 첫 단계 문장  "
    body["steps"][1]["camera"] = {"bearing": 10, "pitch": 50, "zoom": 18}
    r = api.put(f"/api/v1/admin/walk-routes/{route['id']}/steps", json=body, headers=ADMIN)
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    out = r.json()
    assert out["updated_at"] != route["updated_at"]
    assert out["steps"][0]["instruction"] == "수정한 첫 단계 문장"
    assert out["steps"][1]["camera"] == {"bearing": 10, "pitch": 50, "zoom": 18} and not out["steps"][1]["camera_is_default"]
    assert {s["id"] for s in out["steps"]}.isdisjoint({s["id"] for s in route["steps"]})  # 새 id 발급

    again = api.get(f"/api/v1/places/{pid}/walk-routes")  # 다른 기기(새 조회)에 바로 반영, ETag 변경
    assert again.headers["etag"] != etag_before
    assert again.json()["items"][0]["steps"][0]["instruction"] == "수정한 첫 단계 문장"

    stale = api.put(f"/api/v1/admin/walk-routes/{route['id']}/steps", json=body, headers=ADMIN)  # 같은 본문 다시 → 409
    assert stale.status_code == 409 and stale.json()["error"]["details"][0]["reason"] == "stale"


def test_put_version_string_round_trips_without_parsing(api, fresh_db):
    """화면은 받은 updated_at 문자열을 해석하지 않고 그대로 돌려보낸다 (개발뼈대 검토 v1.1 8번). 마이크로초가 살아 있어야 409 가 안 난다."""
    _, route = _route(api)
    assert len(route["updated_at"].split(".")[1]) == 7  # 마이크로초 6자리 + Z
    first = api.put(f"/api/v1/admin/walk-routes/{route['id']}/steps", json=_body(route), headers=ADMIN)
    second = api.put(f"/api/v1/admin/walk-routes/{route['id']}/steps", json=_body(first.json()), headers=ADMIN)
    assert (first.status_code, second.status_code) == (200, 200)


def test_put_validation_collects_all_format_errors(api):
    _, route = _route(api)
    body = _body(route)
    body["steps"][0]["step_order"] = 3
    body["steps"][1]["instruction"] = "가" * 201
    r = api.put(f"/api/v1/admin/walk-routes/{route['id']}/steps", json=body, headers=ADMIN)
    assert r.status_code == 400
    assert {d["reason"] for d in r.json()["error"]["details"]} == {"step_order_gap", "too_long"}
    body = _body(route)
    body["steps"] = body["steps"][:1]
    r = api.put(f"/api/v1/admin/walk-routes/{route['id']}/steps", json=body, headers=ADMIN)
    assert r.json()["error"]["details"][0]["reason"] == "too_few_steps"


@pytest.mark.parametrize(
    "mutate,reason,field",
    [
        (lambda b: b["steps"][0].update(color="red"), "unknown_field", "steps[0].color"),
        (lambda b: b["steps"][0].pop("landmark_id"), "required", "steps[0].landmark_id"),
        (lambda b: b["steps"][0].update(camera={"bearing": 10}), "incomplete_camera", "steps[0].camera.pitch"),
        (lambda b: b["steps"][0].update(camera={"bearing": 10, "pitch": 90, "zoom": 18}), "out_of_range", "steps[0].camera.pitch"),
        (
            lambda b: b["steps"][0].update(location={"type": "Point", "coordinates": [200, 37]}),
            "invalid_geometry",
            "steps[0].location.coordinates",
        ),
        (lambda b: b.pop("updated_by"), "required", "updated_by"),
        (lambda b: b.update(expected_updated_at="2026-11-19T01:00:00"), "invalid_type", "expected_updated_at"),  # 시간대 없음
    ],
)
def test_put_schema_errors(api, mutate, reason, field):
    _, route = _route(api)
    body = _body(route)
    mutate(body)
    r = api.put(f"/api/v1/admin/walk-routes/{route['id']}/steps", json=body, headers=ADMIN)
    assert r.status_code == 400
    d = r.json()["error"]["details"]
    assert any(x["reason"] == reason and x["field"] == field for x in d), d


def test_put_db_rules(api, fresh_db):
    _, route = _route(api, "공학관")
    _, other = _route(api, "중앙도서관")
    url = f"/api/v1/admin/walk-routes/{route['id']}/steps"

    body = _body(route)
    body["steps"][0]["landmark_id"] = other["steps"][0]["landmark"]["id"]  # 다른 장소 랜드마크
    r = api.put(url, json=body, headers=ADMIN)
    assert r.status_code == 400 and r.json()["error"]["details"][0]["reason"] == "not_in_place"

    body = _body(route)
    body["steps"][0]["location"] = {"type": "Point", "coordinates": [127.01, 37.01]}  # 경로에서 멀리
    r = api.put(url, json=body, headers=ADMIN)
    assert r.status_code == 400 and r.json()["error"]["details"][0]["reason"] == "too_far_from_path"

    body = _body(route)
    body["steps"][1]["location"] = {"type": "Point", "coordinates": [127.00135, 37.0003]}  # 공학관 안 (경로 11m)
    r = api.put(url, json=body, headers=ADMIN)
    d = r.json()["error"]["details"][0]
    assert r.status_code == 400 and (d["reason"], d["field"]) == ("inside_building", "steps[1].location") and "공학관" in d["message"]

    body = _body(route)
    body["steps"][-1]["location"] = {"type": "Point", "coordinates": [127.00135, 37.000206]}  # 벽 0.3m 안쪽(입구 지점): 허용
    assert api.put(url, json=body, headers=ADMIN).status_code == 200
    assert api.put("/api/v1/admin/walk-routes/99999/steps", json=body, headers=ADMIN).status_code == 404


# ---------- PATCH /admin/walk-route-steps/{id} ----------


def test_patch_step(api, fresh_db):
    _, route = _route(api)
    step = route["steps"][1]
    url = f"/api/v1/admin/walk-route-steps/{step['id']}"
    body = {"updated_by": "테스트", "instruction": "돌계단으로 올라가면 정문", "expected_updated_at": route["updated_at"]}
    r = api.patch(url, json=body, headers=ADMIN)
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    out = r.json()
    assert out["instruction"] == "돌계단으로 올라가면 정문" and out["walk_route_id"] == route["id"]
    assert out["walk_route_updated_at"] != route["updated_at"]
    assert out["landmark"] == step["landmark"]  # 키가 없으면 그대로

    # landmark_id: null 은 연결 해제, camera: null 은 기본 카메라로
    body = {"updated_by": "테스트", "landmark_id": None, "camera": None, "expected_updated_at": out["walk_route_updated_at"]}
    r2 = api.patch(url, json=body, headers=ADMIN)
    assert r2.status_code == 200 and r2.json()["landmark"] is None and r2.json()["camera_is_default"] is True

    stale = {"updated_by": "테스트", "instruction": "x", "expected_updated_at": route["updated_at"]}  # 오래된 버전 → 409
    assert api.patch(url, json=stale, headers=ADMIN).status_code == 409


def test_patch_errors(api):
    _, route = _route(api)
    url = f"/api/v1/admin/walk-route-steps/{route['steps'][0]['id']}"

    def reason(body):
        return api.patch(url, json=body, headers=ADMIN).json()["error"]["details"][0]["reason"]

    assert reason({"updated_by": "a"}) == "no_changes"
    assert reason({"updated_by": "a", "step_order": 2}) == "unknown_field"
    assert reason({"updated_by": "a", "instruction": "가" * 201}) == "too_long"
    assert api.patch("/api/v1/admin/walk-route-steps/99999", json={"updated_by": "a", "instruction": "b"}, headers=ADMIN).status_code == 404
    assert api.patch(url, json={"updated_by": "a", "instruction": "b"}).status_code == 401
