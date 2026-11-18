"""관리자 API (API 명세서 3.6~3.8, F-06, N-04). 모든 엔드포인트가 AdminRoute 로 키 검사를 먼저 거친다 (admin_route.py).

라우터는 키 검사(AdminRoute), 입력 검증(Pydantic), Cache-Control 만 맡는다. 검사 순서, 409, 감사 로그는 서비스(BE-15).
"""

from fastapi import APIRouter, Depends, Path, Response, Security
from fastapi.security import APIKeyHeader

from app.api.admin_route import AdminRoute
from app.api.deps import request_id
from app.schemas.admin import AdminMeOut, StepPatchIn, StepPatchOut, StepsReplaceIn
from app.schemas.walk_route import WalkRouteOut
from app.services.admin_walk_route_service import AdminWalkRouteService

# Swagger(/docs) 의 Authorize 버튼에 X-Admin-Key 입력칸을 보이게 하는 표시용 의존성이다.
# 값을 읽기만 하고 검사, 실패 계수는 하지 않는다 (auto_error=False). 실제 검사는 AdminRoute → deps.require_admin
admin_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False, description="관리자 키 (32자 이상)")

router = APIRouter(prefix="/admin", tags=["admin"], route_class=AdminRoute, dependencies=[Security(admin_key_header)])
service = AdminWalkRouteService()


@router.get("/me", response_model=AdminMeOut)
def me(response: Response):
    """관리자 키 확인 (Cache-Control: no-store). 키가 맞으면 {"role": "admin"}."""
    response.headers["Cache-Control"] = "no-store"
    return AdminMeOut()


@router.put("/walk-routes/{id}/steps", response_model=WalkRouteOut)
def replace_steps(body: StepsReplaceIn, response: Response, id: int = Path(ge=1), rid: str = Depends(request_id)):
    """경로의 단계 전체 교체. expected_updated_at 이 다르면 409. 응답은 저장 뒤의 경로 (새 updated_at 포함)."""
    result = service.replace_steps(id, body, rid)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.patch("/walk-route-steps/{id}", response_model=StepPatchOut)
def patch_step(body: StepPatchIn, response: Response, id: int = Path(ge=1), rid: str = Depends(request_id)):
    """단계 하나 부분 수정. 키가 없으면 그대로, null 이면 지운다."""
    result = service.patch_step(id, body, rid)
    response.headers["Cache-Control"] = "no-store"
    return result
