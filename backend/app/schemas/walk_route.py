"""도보 경로, 단계 DTO (API 명세서 3.5).

뼈대: 본문은 비어 있다. 함수마다 NotImplementedError 를 구현으로 바꾼다.
"""

from pydantic import BaseModel


class LandmarkRef(BaseModel):
    """TODO: 필드 정의 (API 명세서, 설계서 참고)"""


class StepOut(BaseModel):
    """TODO: 필드 정의 (API 명세서, 설계서 참고)"""


class WalkRouteOut(BaseModel):
    """TODO: 필드 정의 (API 명세서, 설계서 참고)"""


class WalkRouteListOut(BaseModel):
    """TODO: 필드 정의 (API 명세서, 설계서 참고)"""
