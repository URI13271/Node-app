"""관리자 서비스 통합 테스트 (BE-15). 테스트 고정 데이터(seed_campus)로 확인한다.

완료 기준: 동시 수정 409, 잘못된 단계 400. 그 밖에 검사 순서(DB 없는 검사는 한 번에), 소속, 거리, 건물 안, 롤백, 감사 로그.
데이터를 바꾸는 테스트는 fresh_db 픽스처로 끝난 뒤 시드를 다시 적재한다.
"""

import logging

import pytest
from sqlalchemy import text

from app.core.errors import AppError
from app.db import read_tx
from app.schemas.admin import StepPatchIn, StepsReplaceIn
from app.services.admin_walk_route_service import AdminWalkRouteService
from app.services.walk_route_service import WalkRouteService

PATH_START = (127.001631, 37.000036)  # 공학관 앞 주차장 → 정문 경로의 첫 점
MAIN_ENTRANCE = (127.00135, 37.000198)  # 공학관 정문 (경로의 끝 근처, 건물 밖)
PLACE_CENTER = (127.00135, 37.00036)  # 공학관 건물 안
FAR_AWAY = (127.0040, 37.0000)  # 경로에서 200m 넘게 떨어진 곳

service = AdminWalkRouteService()


@pytest.fixture()
def ctx(app) -> dict:
    with read_tx() as conn:
        place = conn.execute(text("SELECT id FROM place WHERE name = '공학관'")).scalar_one()
        landmarks = dict(conn.execute(text("SELECT name, id FROM landmark")).all())
    route = WalkRouteService().list_for_place(place, None, None).items[0]  # 공학관 앞 주차장 → 정문
    return {"place": place, "route": route, "landmark": landmarks}


def _current(ctx):
    return next(r for r in WalkRouteService().list_for_place(ctx["place"], None, None).items if r.id == ctx["route"].id)


def _step(order: int, location=PATH_START, landmark_id=None, instruction=None, camera=None) -> dict:
    return {
        "step_order": order,
        "instruction": instruction or f"{order}번째 안내",
        "landmark_id": landmark_id,
        "location": {"type": "Point", "coordinates": list(location)},
        "camera": camera,
    }


def _replace_body(version: str, steps: list[dict], who: str = "관리자A") -> StepsReplaceIn:
    return StepsReplaceIn.model_validate({"expected_updated_at": version, "updated_by": who, "steps": steps})


def _error(fn) -> AppError:
    with pytest.raises(AppError) as e:
        fn()
    return e.value


# ---------- PUT: 단계 전체 교체 ----------


def test_replace_steps_saves_and_bumps_version(ctx, fresh_db, caplog):
    before = _current(ctx).updated_at
    body = _replace_body(before, [_step(1), _step(2, MAIN_ENTRANCE, ctx["landmark"]["자판기 2대"], "정문\x07 앞까지  ")])
    with caplog.at_level(logging.INFO, logger="audit"):
        out = service.replace_steps(ctx["route"].id, body, "req-1")
    assert out.id == ctx["route"].id and out.updated_at > before
    assert [s.instruction for s in out.steps] == ["1번째 안내", "정문 앞까지"]  # 제어 문자, 앞뒤 공백 제거
    assert out.steps[1].landmark.name == "자판기 2대"
    assert out == _current(ctx)  # 응답 = 다시 조회한 결과
    audit = [r for r in caplog.records if r.name == "audit"]
    assert len(audit) == 1 and (audit[0].action, audit[0].step_count, audit[0].actor) == ("steps.replace", 2, "관리자A")
    assert "정문" not in str(audit[0].__dict__)  # 단계 문장 원문은 남기지 않음


def test_concurrent_edit_is_409(ctx, fresh_db):
    """두 관리자가 같은 버전을 보고 저장: 먼저 저장한 쪽만 성공, 뒤쪽은 409 + 현재 버전."""
    version = _current(ctx).updated_at
    first = service.replace_steps(ctx["route"].id, _replace_body(version, [_step(1), _step(2)], "A"), "req-a")
    e = _error(lambda: service.replace_steps(ctx["route"].id, _replace_body(version, [_step(1), _step(2)], "B"), "req-b"))
    assert (e.status, e.code) == (409, "CONFLICT")
    assert e.details[0]["reason"] == "stale" and first.updated_at in e.details[0]["message"]


def test_dbless_violations_are_collected_at_once(ctx):
    """순서 빈틈과 문장 길이 위반을 한꺼번에 돌려준다. DB 를 보기 전에 막는다 (없는 경로여도 400)."""
    steps = [_step(1, instruction=" "), _step(3, instruction="가" * 201)]
    e = _error(lambda: service.replace_steps(999999, _replace_body(_current(ctx).updated_at, steps), "r"))
    assert e.status == 400 and {d["reason"] for d in e.details} == {"step_order_gap", "too_short", "too_long"}


@pytest.mark.parametrize("n,reason", [(1, "too_few_steps"), (31, "too_many_steps")])
def test_step_count_limits(ctx, n, reason):
    steps = [_step(i) for i in range(1, n + 1)]
    e = _error(lambda: service.replace_steps(ctx["route"].id, _replace_body(_current(ctx).updated_at, steps), "r"))
    assert e.status == 400 and [d["reason"] for d in e.details] == [reason]


def test_unknown_route_is_404(ctx):
    e = _error(lambda: service.replace_steps(999999, _replace_body(_current(ctx).updated_at, [_step(1), _step(2)]), "r"))
    assert e.status == 404


def test_landmark_of_other_place_points_to_that_step(ctx):
    lm = ctx["landmark"]
    steps = [_step(1, landmark_id=lm["자판기 2대"]), _step(2, landmark_id=lm["분수대"])]  # 분수대는 중앙도서관
    e = _error(lambda: service.replace_steps(ctx["route"].id, _replace_body(_current(ctx).updated_at, steps), "r"))
    assert e.status == 400 and (e.details[0]["field"], e.details[0]["reason"]) == ("steps[1].landmark_id", "not_in_place")


def test_step_too_far_from_path(ctx):
    steps = [_step(1), _step(2, FAR_AWAY)]
    e = _error(lambda: service.replace_steps(ctx["route"].id, _replace_body(_current(ctx).updated_at, steps), "r"))
    assert (e.details[0]["field"], e.details[0]["reason"]) == ("steps[1].location", "too_far_from_path")


def test_step_inside_building(ctx):
    steps = [_step(1), _step(2, PLACE_CENTER)]
    e = _error(lambda: service.replace_steps(ctx["route"].id, _replace_body(_current(ctx).updated_at, steps), "r"))
    assert (e.details[0]["field"], e.details[0]["reason"]) == ("steps[1].location", "inside_building")
    assert "공학관" in e.details[0]["message"]


def test_failed_save_changes_nothing(ctx):
    before = _current(ctx)
    _error(lambda: service.replace_steps(ctx["route"].id, _replace_body(before.updated_at, [_step(1), _step(2, FAR_AWAY)]), "r"))
    assert _current(ctx) == before  # 단계도 버전도 그대로


# ---------- PATCH: 단계 하나 부분 수정 ----------


def _patch(data: dict) -> StepPatchIn:
    return StepPatchIn.model_validate({"updated_by": "관리자A", **data})


def test_patch_instruction_and_version(ctx, fresh_db):
    route = _current(ctx)
    step = route.steps[1]
    out = service.patch_step(step.id, _patch({"instruction": "  바뀐 문장 ", "expected_updated_at": route.updated_at}), "req-p")
    assert out.instruction == "바뀐 문장" and out.walk_route_id == route.id
    assert out.walk_route_updated_at > route.updated_at
    assert out.landmark == step.landmark  # 보내지 않은 항목은 그대로
    assert _current(ctx).updated_at == out.walk_route_updated_at


def test_patch_camera_null_goes_back_to_default(ctx, fresh_db):
    step = _current(ctx).steps[0]
    out = service.patch_step(step.id, _patch({"camera": {"bearing": 90, "pitch": 40, "zoom": 19}}), "r")
    assert out.camera_is_default is False and out.camera.bearing == 90
    out = service.patch_step(step.id, _patch({"camera": None}), "r")
    assert out.camera_is_default is True  # null 이면 저장값을 지우고 서버 기본 카메라


def test_patch_stale_version_is_409_but_omitted_version_is_not_checked(ctx, fresh_db):
    route = _current(ctx)
    step = route.steps[0]
    service.patch_step(step.id, _patch({"instruction": "먼저 저장"}), "r")  # 버전 생략 → 검사 없이 저장
    e = _error(lambda: service.patch_step(step.id, _patch({"instruction": "늦게 저장", "expected_updated_at": route.updated_at}), "r"))
    assert (e.status, e.code) == (409, "CONFLICT")


@pytest.mark.parametrize(
    "data,field,reason",
    [
        ({}, "body", "no_changes"),
        ({"instruction": None}, "instruction", "required"),
        ({"instruction": "가" * 201}, "instruction", "too_long"),
    ],
)
def test_patch_invalid_body(ctx, data, field, reason):
    step = _current(ctx).steps[0]
    e = _error(lambda: service.patch_step(step.id, _patch(data), "r"))
    assert e.status == 400 and (e.details[0]["field"], e.details[0]["reason"]) == (field, reason)


def test_patch_landmark_of_other_place_and_unknown_step(ctx):
    step = _current(ctx).steps[0]
    e = _error(lambda: service.patch_step(step.id, _patch({"landmark_id": ctx["landmark"]["분수대"]}), "r"))
    assert (e.status, e.details[0]["reason"]) == (400, "not_in_place")
    assert _error(lambda: service.patch_step(999999, _patch({"instruction": "x"}), "r")).status == 404
