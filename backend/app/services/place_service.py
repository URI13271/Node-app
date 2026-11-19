"""장소 검색, 상세 유스케이스 (F-01, F-02, F-04 내비 목적지).

서비스 메서드 하나 = read_tx 하나. 없는 장소는 여기서 404 로 바꾼다 (저장소는 None 만 돌려준다).
"""

from sqlalchemy import Connection

from app.core.errors import not_found
from app.db import read_tx
from app.domain.attribution import attributions
from app.domain.camera import Camera, parking_camera, place_camera
from app.domain.navigation import ParkingCandidate, select_navigation_target
from app.repositories import building_repo, place_repo
from app.schemas.common import iso_seconds
from app.schemas.place import PlaceDetail, PlaceListOut


def _candidates(lots: list[dict]) -> list[ParkingCandidate]:
    return [ParkingCandidate(lot["id"], lot["name"], lot["priority"], lot["lng"], lot["lat"]) for lot in lots]


class PlaceService:
    def search(self, q: str | None, limit: int, offset: int) -> PlaceListOut:
        raise NotImplementedError("BE-11a 연습: PlaceService.search")

    def detail(self, place_id: int) -> PlaceDetail:
        with read_tx() as conn:
            p = place_repo.get_place(conn, place_id)
            if p is None:
                raise not_found("장소")
            entrances = place_repo.list_entrances(conn, place_id)
            lots = place_repo.list_parking_lots(conn, place_id)
            landmarks = place_repo.list_landmarks(conn, place_id)
            sources = building_repo.list_sources(conn, place_id)
        nav = select_navigation_target(_candidates(lots))
        cam = place_camera(Camera(**p["camera"]) if p["camera"] else None, (nav.lng, nav.lat), (p["lng"], p["lat"]))
        for lot in lots:  # 주차장마다 도착 방향 카메라 (저장값이 없으면 "이 주차장 → 장소")
            lot_cam, is_default = parking_camera(
                Camera(**lot["camera"]) if lot["camera"] else None, (lot["lng"], lot["lat"]), (p["lng"], p["lat"]), cam.bearing
            )
            lot["camera"], lot["camera_is_default"] = lot_cam.__dict__, is_default
        return PlaceDetail(
            id=p["id"], name=p["name"], category=p["category"], location=p["location"],
            cover_image_url=p["cover_image_url"], address=p["address"], description=p["description"],
            camera=cam.__dict__, entrances=entrances, parking_lots=lots, landmarks=landmarks,
            navigation_target={"parking_lot_id": nav.id, "name": nav.name, "lng": nav.lng, "lat": nav.lat},
            arrival_radius_m=p["arrival_radius_m"], attributions=attributions(sources),
            last_verified_at=iso_seconds(p["last_verified_at"]),
        )


def place_camera_bearing(conn: Connection, place_id: int) -> float:
    """단계 카메라 계산의 마지막 대체값(설계서 2.4.5 (2))."""
    p = place_repo.get_place(conn, place_id)
    if p is None:
        raise not_found("장소")
    if p["camera"]:
        return p["camera"]["bearing"]
    nav = select_navigation_target(_candidates(place_repo.list_parking_lots(conn, place_id)))
    return place_camera(None, (nav.lng, nav.lat), (p["lng"], p["lat"])).bearing
