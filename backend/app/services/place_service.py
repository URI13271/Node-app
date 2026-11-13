"""장소 검색, 상세 유스케이스 (F-01, F-02, F-04 내비 목적지).

뼈대: 본문은 비어 있다. 함수마다 NotImplementedError 를 구현으로 바꾼다.
"""

from sqlalchemy import Connection

from app.schemas.place import PlaceDetail, PlaceListOut


class PlaceService:
    def search(self, q: str | None, limit: int, offset: int) -> PlaceListOut:
        raise NotImplementedError("TODO: app.services.place_service.PlaceService.search")

    def detail(self, place_id: int) -> PlaceDetail:
        raise NotImplementedError("TODO: app.services.place_service.PlaceService.detail")


def place_camera_bearing(conn: Connection, place_id: int) -> float:
    """단계 카메라 계산의 마지막 대체값(설계서 2.4.5 (2))."""
    raise NotImplementedError("TODO: app.services.place_service.place_camera_bearing")
