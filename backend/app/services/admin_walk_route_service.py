"""관리자 단계 저장 유스케이스 (F-06). 설계서 2.4.5 (5), 2.7.4.

트랜잭션 하나 안에서: 행 잠금 → 버전 비교 → 랜드마크 소속 → 지점 거리 → 지점이 건물 밖인지 → 교체 → 버전 갱신 → 감사 로그.

뼈대: 본문은 비어 있다. 함수마다 NotImplementedError 를 구현으로 바꾼다.
"""

from app.schemas.admin import StepPatchIn, StepPatchOut, StepsReplaceIn
from app.schemas.walk_route import WalkRouteOut

MAX_DISTANCE_FROM_PATH_M = 30.0


WALL_TOLERANCE_M = 1.0


class AdminWalkRouteService:
    def replace_steps(self, route_id: int, body: StepsReplaceIn, request_id: str) -> WalkRouteOut:
        raise NotImplementedError("TODO: app.services.admin_walk_route_service.AdminWalkRouteService.replace_steps")

    def patch_step(self, step_id: int, body: StepPatchIn, request_id: str) -> StepPatchOut:
        raise NotImplementedError("TODO: app.services.admin_walk_route_service.AdminWalkRouteService.patch_step")
