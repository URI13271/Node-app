"""도보 경로, 단계 조회 유스케이스 (F-04, F-05) + ETag (설계서 2.5.4).

ETag 는 장소 id + 경로 updated_at 최댓값(마이크로초) + 경로 수. If-None-Match 가 맞으면 단계 조회를 건너뛰고 304 를 알린다.
랜드마크가 바뀌면 load_seed 가 경로 updated_at 을 올린다(경로를 다시 넣음).
"""

from dataclasses import dataclass

from sqlalchemy import Connection

from app.core.errors import invalid, not_found
from app.db import read_tx
from app.domain.camera import Camera, step_cameras
from app.domain.navigation import walk_time_min
from app.repositories import place_repo, walk_route_repo
from app.schemas.common import iso_micros
from app.schemas.walk_route import WalkRouteOut
from app.services.place_service import place_camera_bearing


@dataclass
class RoutesResult:
    etag: str
    items: list[WalkRouteOut] | None  # None 이면 304 (라우터가 본문 없이 응답)


def make_etag(place_id: int, max_micros: int, count: int) -> str:
    """ETag = 장소 id + 경로 updated_at 최댓값(마이크로초) + 경로 수. 랜드마크가 바뀌면 load_seed 가 경로 updated_at 을 올린다."""
    return f'W/"wr-{place_id}-{max_micros}-{count}"'


def build_routes(
    conn: Connection, place_id: int, parking_lot_id: int | None = None, only_route_id: int | None = None
) -> list[WalkRouteOut]:
    """경로 + 단계 + 카메라 기본값을 응답 모양으로 조립한다. 관리자 저장 뒤 응답(only_route_id)에도 쓴다."""
    routes = walk_route_repo.list_routes(conn, place_id, parking_lot_id)
    if only_route_id is not None:
        routes = [r for r in routes if r["id"] == only_route_id]
    steps = walk_route_repo.list_steps(conn, [r["id"] for r in routes])
    fallback = place_camera_bearing(conn, place_id) if routes else 0.0
    out = []
    for r in routes:
        rs = [s for s in steps if s["walk_route_id"] == r["id"]]
        cams = step_cameras(
            [Camera(**s["camera"]) if s["camera"] else None for s in rs],
            [tuple(s["location"]["coordinates"]) for s in rs],
            tuple(r["entrance_location"]["coordinates"]), fallback,
        )
        dist = round(float(r["distance_m"]), 1)
        out.append(WalkRouteOut(
            id=r["id"], parking_lot_id=r["parking_lot_id"], entrance_id=r["entrance_id"], path=r["path"],
            distance_m=dist, walk_time_min=walk_time_min(r["walk_time_min"], dist),
            description=r["description"], updated_at=iso_micros(r["updated_at"]),
            steps=[{
                "id": s["id"], "step_order": s["step_order"], "instruction": s["instruction"],
                "landmark": {"id": s["landmark_id"], "name": s["landmark_name"]} if s["landmark_id"] else None,
                "location": s["location"], "camera": cam.__dict__, "camera_is_default": is_default,
            } for s, (cam, is_default) in zip(rs, cams, strict=True)],
        ))
    return out


class WalkRouteService:
    def list_for_place(self, place_id: int, parking_lot_id: int | None, if_none_match: str | None) -> RoutesResult:
        with read_tx() as conn:
            if not place_repo.place_exists(conn, place_id):
                raise not_found("장소")
            if parking_lot_id is not None and walk_route_repo.parking_lot_place(conn, parking_lot_id) != place_id:
                raise invalid("query.parking_lot_id", "not_in_place", "이 장소의 주차장이 아닙니다.")
            micros, count = walk_route_repo.version_info(conn, place_id, parking_lot_id)
            etag = make_etag(place_id, micros, count)
            if if_none_match and etag in [t.strip() for t in if_none_match.split(",")]:
                return RoutesResult(etag, None)  # 단계 조회를 건너뛴다
            return RoutesResult(etag, build_routes(conn, place_id, parking_lot_id))
