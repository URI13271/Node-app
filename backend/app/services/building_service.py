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
        with read_tx() as conn:
            if not place_repo.place_exists(conn, place_id):
                raise not_found("장소")

            rows = building_repo.list_buildings(conn, place_id)

        features = [
            {
                "id": r["id"],
                "geometry": r["footprint"],
                "properties": {
                    "name": r["name"],
                    "floor_count": r["floor_count"],
                    "render_height_m": render_height(
                        r["height_m"], r["floor_count"]
                    ),
                    "is_target": r["is_target"],
                },
            }
            for r in rows
        ]

        return BuildingCollection(
            features=features,
            attributions=attributions([r["source"] for r in rows]),
        )
