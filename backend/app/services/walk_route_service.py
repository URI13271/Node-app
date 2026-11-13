"""도보 경로, 단계 조회 유스케이스 (F-04, F-05) + ETag (설계서 2.5.4).

뼈대: 본문은 비어 있다. 함수마다 NotImplementedError 를 구현으로 바꾼다.
"""

from dataclasses import dataclass

from sqlalchemy import Connection

from app.schemas.walk_route import WalkRouteOut


@dataclass
class RoutesResult:
    """TODO: 필드 정의 (API 명세서, 설계서 참고)"""


def make_etag(place_id: int, max_micros: int, count: int) -> str:
    """ETag = 장소 id + 경로 updated_at 최댓값(마이크로초) + 경로 수. 랜드마크가 바뀌면 load_seed 가 경로 updated_at 을 올린다."""
    raise NotImplementedError("TODO: app.services.walk_route_service.make_etag")


def build_routes(
    conn: Connection, place_id: int, parking_lot_id: int | None = None, only_route_id: int | None = None
) -> list[WalkRouteOut]:
    raise NotImplementedError("TODO: app.services.walk_route_service.build_routes")


class WalkRouteService:
    def list_for_place(self, place_id: int, parking_lot_id: int | None, if_none_match: str | None) -> RoutesResult:
        raise NotImplementedError("TODO: app.services.walk_route_service.WalkRouteService.list_for_place")
