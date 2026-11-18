"""관리자 단계 저장 유스케이스 (F-06). 설계서 2.4.5 (5), 2.7.4.

트랜잭션 하나 안에서: 행 잠금 → 버전 비교 → 랜드마크 소속 → 지점 거리 → 지점이 건물 밖인지 → 교체 → 버전 갱신 → 감사 로그.
DB 없이 하는 검사(단계 수 2~30, 순서, 문장 길이)는 트랜잭션 전에 모든 위반을 한 번에 모아 400 으로 돌려준다.
DB 검사에 걸리면 예외로 write_tx 를 빠져나가 아무것도 저장되지 않는다.
감사 로그에는 단계 문장 원문을 남기지 않는다 (설계서 2.7.3).
"""

from app.core.errors import AppError, invalid, not_found
from app.core.logging import audit_log
from app.db import write_tx
from app.domain.steps import Violation, check_instruction, check_steps, clean_instruction
from app.repositories import walk_route_repo
from app.schemas.admin import StepPatchIn, StepPatchOut, StepsReplaceIn
from app.schemas.common import iso_micros
from app.schemas.walk_route import WalkRouteOut
from app.services.walk_route_service import build_routes

MAX_DISTANCE_FROM_PATH_M = 30.0
WALL_TOLERANCE_M = 1.0  # 벽에서 1m 안쪽부터 건물 안 (scripts/load_seed.py 와 같은 값, API 명세서 v1.2 부록 C)


NOT_IN_PLACE = "같은 장소의 랜드마크만 고를 수 있습니다."


def _violations(vs: list[Violation]) -> AppError:
    return AppError("INVALID_INPUT", "입력값을 확인하세요.", [{"field": v.field, "reason": v.reason, "message": v.message} for v in vs])


def _conflict(current) -> AppError:
    """409. 관리자 화면이 비교 대화상자에 보여 줄 수 있게 현재 버전을 함께 돌려준다."""
    return AppError(
        "CONFLICT",
        "다른 관리자가 먼저 이 경로를 수정했습니다. 새로 불러온 뒤 다시 저장하세요.",
        [{"field": "expected_updated_at", "reason": "stale", "message": f"현재 버전: {iso_micros(current)}"}],
    )


def _first_foreign_landmark(conn, route_id: int, steps) -> int:
    """다른 장소 랜드마크를 고른 첫 단계의 위치(body.steps 기준). 개수가 안 맞을 때만 부른다."""
    for i, s in enumerate(steps):
        if s.landmark_id is not None and walk_route_repo.count_landmarks_in_route_place(conn, route_id, [s.landmark_id]) == 0:
            return i
    return 0


class AdminWalkRouteService:
    def replace_steps(self, route_id: int, body: StepsReplaceIn, request_id: str) -> WalkRouteOut:
        # 1~4: DB 없이 하는 검사 (모든 위반을 한 번에)
        vs = check_steps([s.step_order for s in body.steps], [s.instruction for s in body.steps])
        if vs:
            raise _violations(vs)
        steps = sorted(body.steps, key=lambda s: s.step_order)
        with write_tx() as conn:
            current = walk_route_repo.lock_route(conn, route_id)  # 5
            if current is None:
                raise not_found("경로")
            if current != body.expected_updated_at:  # 6 (같은 시각이면 같은 버전. 마이크로초까지 비교)
                raise _conflict(current)
            lm_ids = sorted({s.landmark_id for s in steps if s.landmark_id is not None})
            if walk_route_repo.count_landmarks_in_route_place(conn, route_id, lm_ids) != len(lm_ids):  # 7
                bad = _first_foreign_landmark(conn, route_id, body.steps)
                raise invalid(f"steps[{bad}].landmark_id", "not_in_place", NOT_IN_PLACE)
            dists = walk_route_repo.distances_from_path(conn, route_id, [tuple(s.location.coordinates) for s in steps])  # 8
            for s, d in zip(steps, dists, strict=True):
                if d > MAX_DISTANCE_FROM_PATH_M:
                    i = body.steps.index(s)
                    message = f"경로 선에서 {MAX_DISTANCE_FROM_PATH_M:.0f}m 이내여야 합니다 (현재 {d:.1f}m)."
                    raise invalid(f"steps[{i}].location", "too_far_from_path", message)
            inside = walk_route_repo.buildings_containing(  # 8-2
                conn, route_id, [tuple(s.location.coordinates) for s in steps], WALL_TOLERANCE_M
            )
            for s, name in zip(steps, inside, strict=True):
                if name is not None:
                    i = body.steps.index(s)
                    message = f"지점이 건물({name}) 안에 있습니다. 건물 밖 길 위로 옮기세요."
                    raise invalid(f"steps[{i}].location", "inside_building", message)
            rows = [
                {
                    "step_order": s.step_order,
                    "instruction": clean_instruction(s.instruction),
                    "landmark_id": s.landmark_id,
                    "location": tuple(s.location.coordinates),
                    "camera": s.camera.model_dump() if s.camera else None,
                }
                for s in steps
            ]
            walk_route_repo.replace_steps(conn, route_id, rows, body.updated_by)  # 9
            walk_route_repo.touch_route(conn, route_id)  # 10
            place_id = walk_route_repo.route_place_id(conn, route_id)
            result = build_routes(conn, place_id, only_route_id=route_id)[0]
        audit_log.info(
            "steps.replace",
            extra={
                "request_id": request_id,
                "action": "steps.replace",
                "walk_route_id": route_id,
                "step_count": len(steps),
                "actor": body.updated_by,
                "result": "ok",
            },
        )
        return result

    def patch_step(self, step_id: int, body: StepPatchIn, request_id: str) -> StepPatchOut:
        given = body.model_fields_set - {"updated_by", "expected_updated_at"}
        if not given:
            raise invalid("body", "no_changes", "고칠 항목(instruction, landmark_id, camera)이 없습니다.")
        if "instruction" in given:
            if body.instruction is None:
                raise invalid("instruction", "required", "문장은 null 일 수 없습니다.")
            v = check_instruction(body.instruction, "instruction")
            if v:
                raise _violations([v])
        with write_tx() as conn:
            route_id = walk_route_repo.step_route_id(conn, step_id)
            if route_id is None:
                raise not_found("단계")
            current = walk_route_repo.lock_route(conn, route_id)
            if body.expected_updated_at is not None and current != body.expected_updated_at:
                raise _conflict(current)
            if "landmark_id" in given and body.landmark_id is not None:
                if walk_route_repo.count_landmarks_in_route_place(conn, route_id, [body.landmark_id]) != 1:
                    raise invalid("landmark_id", "not_in_place", NOT_IN_PLACE)
            values = {}
            if "instruction" in given:
                values["instruction"] = clean_instruction(body.instruction)
            if "landmark_id" in given:
                values["landmark_id"] = body.landmark_id
            if "camera" in given:
                values["camera"] = body.camera.model_dump() if body.camera else None
            walk_route_repo.patch_step(conn, step_id, values, body.updated_by)
            new_version = walk_route_repo.touch_route(conn, route_id)
            place_id = walk_route_repo.route_place_id(conn, route_id)
            route = build_routes(conn, place_id, only_route_id=route_id)[0]
        step = next(s for s in route.steps if s.id == step_id)
        audit_log.info(
            "step.patch",
            extra={
                "request_id": request_id,
                "action": "step.patch",
                "walk_route_id": route_id,
                "step_id": step_id,
                "fields": sorted(given),
                "actor": body.updated_by,
                "result": "ok",
            },
        )
        return StepPatchOut(**step.model_dump(), walk_route_id=route_id, walk_route_updated_at=iso_micros(new_version))
