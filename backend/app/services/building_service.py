"""건물 입체 데이터 유스케이스 (F-02, F-03).

표시 높이는 domain.building.render_height, 출처 표기는 domain.attribution.attributions 로 만든다.
"""

from app.core.errors import not_found
from app.db import read_tx
from app.domain.attribution import attributions
from app.domain.building import render_height
from app.repositories import building_repo, place_repo
from app.schemas.building import BuildingCollection


class BuildingService:
    def list_for_place(self, place_id: int) -> BuildingCollection:
        raise NotImplementedError("BE-11b 연습: BuildingService.list_for_place")
