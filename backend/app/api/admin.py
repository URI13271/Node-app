"""관리자 API (API 명세서 3.6~3.8, F-06, N-04). 모든 엔드포인트가 AdminRoute 로 키 검사를 먼저 거친다 (admin_route.py)."""

from fastapi import APIRouter, Path, Security
from fastapi.security import APIKeyHeader

from app.api.admin_route import AdminRoute

# Swagger(/docs) 의 Authorize 버튼에 X-Admin-Key 입력칸을 보이게 하는 표시용 의존성이다.
# 값을 읽기만 하고 검사, 실패 계수는 하지 않는다 (auto_error=False). 실제 검사는 AdminRoute → deps.require_admin
admin_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False, description="관리자 키 (32자 이상)")

router = APIRouter(prefix="/admin", tags=["admin"], route_class=AdminRoute, dependencies=[Security(admin_key_header)])


@router.get("/me")
def me():
    """관리자 키 확인 (Cache-Control: no-store)."""
    raise NotImplementedError("TODO: GET /api/v1/admin/me")


@router.put("/walk-routes/{id}/steps")
def replace_steps(id: int = Path(ge=1)):
    """경로의 단계 전체 교체. expected_updated_at 이 다르면 409."""
    raise NotImplementedError("TODO: PUT /api/v1/admin/walk-routes/{id}/steps")


@router.patch("/walk-route-steps/{id}")
def patch_step(id: int = Path(ge=1)):
    """단계 하나 부분 수정. 키가 없으면 그대로, null 이면 지운다."""
    raise NotImplementedError("TODO: PATCH /api/v1/admin/walk-route-steps/{id}")
