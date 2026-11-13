"""장소 DTO (API 명세서 3.2, 3.3 / 설계서 2.4.3).

뼈대: 본문은 비어 있다. 함수마다 NotImplementedError 를 구현으로 바꾼다.
"""

from typing import Literal

from pydantic import BaseModel

Category = Literal["pension", "campsite", "temple", "restaurant", "trailhead", "attraction", "campus", "other"]


class PlaceSummary(BaseModel):
    """TODO: 필드 정의 (API 명세서, 설계서 참고)"""


class PlaceListOut(BaseModel):
    """TODO: 필드 정의 (API 명세서, 설계서 참고)"""


class EntranceOut(BaseModel):
    """TODO: 필드 정의 (API 명세서, 설계서 참고)"""


class ParkingOut(BaseModel):
    """TODO: 필드 정의 (API 명세서, 설계서 참고)"""


class LandmarkOut(BaseModel):
    """TODO: 필드 정의 (API 명세서, 설계서 참고)"""


class NavigationTarget(BaseModel):
    """TODO: 필드 정의 (API 명세서, 설계서 참고)"""


class PlaceDetail(PlaceSummary):
    """TODO: 필드 정의 (API 명세서, 설계서 참고)"""
