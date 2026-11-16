"""관리자 입력, 출력 DTO (API 명세서 3.6~3.8)."""


from pydantic import AwareDatetime, BaseModel, Field

from app.schemas.common import Camera, GeoPointIn, InModel
from app.schemas.walk_route import StepOut


class AdminMeOut(BaseModel):
    role: str = "admin"


class StepIn(InModel):
    step_order: int = Field(ge=1)
    instruction: str                 # 길이 규칙은 domain/steps.py 가 한 번에 검사
    landmark_id: int | None          # 키는 필수, 값은 null 허용
    location: GeoPointIn
    camera: Camera | None            # 키는 필수, null 이면 서버 기본 카메라


class StepsReplaceIn(InModel):
    expected_updated_at: AwareDatetime
    updated_by: str = Field(min_length=1, max_length=50)
    steps: list[StepIn]


class StepPatchIn(InModel):
    """키가 없으면 그대로 두고, null 이면 지운다. model_fields_set 으로 구분한다."""
    updated_by: str = Field(min_length=1, max_length=50)
    expected_updated_at: AwareDatetime | None = None
    instruction: str | None = None
    landmark_id: int | None = None
    camera: Camera | None = None


class StepPatchOut(StepOut):
    walk_route_id: int
    walk_route_updated_at: str
