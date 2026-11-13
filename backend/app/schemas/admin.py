"""관리자 입력, 출력 DTO (API 명세서 3.6~3.8).

뼈대: 본문은 비어 있다. 함수마다 NotImplementedError 를 구현으로 바꾼다.
"""

from pydantic import BaseModel

from app.schemas.common import InModel
from app.schemas.walk_route import StepOut


class AdminMeOut(BaseModel):
    """TODO: 필드 정의 (API 명세서, 설계서 참고)"""


class StepIn(InModel):
    """TODO: 필드 정의 (API 명세서, 설계서 참고)"""


class StepsReplaceIn(InModel):
    """TODO: 필드 정의 (API 명세서, 설계서 참고)"""


class StepPatchIn(InModel):
    """키가 없으면 그대로 두고, null 이면 지운다. model_fields_set 으로 구분한다."""


class StepPatchOut(StepOut):
    """TODO: 필드 정의 (API 명세서, 설계서 참고)"""
