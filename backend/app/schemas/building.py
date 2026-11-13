"""건물 GeoJSON DTO (API 명세서 3.4).

뼈대: 본문은 비어 있다. 함수마다 NotImplementedError 를 구현으로 바꾼다.
"""

from pydantic import BaseModel


class BuildingProps(BaseModel):
    """TODO: 필드 정의 (API 명세서, 설계서 참고)"""


class BuildingFeature(BaseModel):
    """TODO: 필드 정의 (API 명세서, 설계서 참고)"""


class BuildingCollection(BaseModel):
    """TODO: 필드 정의 (API 명세서, 설계서 참고)"""
