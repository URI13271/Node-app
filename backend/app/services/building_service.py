"""건물 입체 데이터 유스케이스 (F-02, F-03).

뼈대: 본문은 비어 있다. 함수마다 NotImplementedError 를 구현으로 바꾼다.
"""

from app.schemas.building import BuildingCollection


class BuildingService:
    def list_for_place(self, place_id: int) -> BuildingCollection:
        raise NotImplementedError("TODO: app.services.building_service.BuildingService.list_for_place")
