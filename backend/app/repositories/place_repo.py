"""place, entrance, parking_lot, landmark 조회 SQL.

공간 SQL 은 geo_sql 함수만 쓴다. 없으면 None, 목록은 정해진 순서로 돌려준다.
"""

from sqlalchemy import Connection, func, select

from app.repositories.geo_sql import as_geojson, camera_of, lat, lng, parse
from app.repositories.tables import entrance, landmark, parking_lot, place

# 이름 정렬은 DB 기본 로케일에 맡기지 않는다. Docker 이미지 기본값(en_US.utf8, glibc)은 한글을 가나다순으로 정렬하지 않는다
# (예: 공학관, 학생회관, 중앙도서관). "C" 는 유니코드 순서라 완성형 한글이 가나다순이 되고, 어느 DB에나 있다.
NAME_COLLATION = "C"


def _like_escape(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_places(conn: Connection, q: str | None, limit: int, offset: int) -> tuple[int, list[dict]]:
    cond = []
    if q:
        cond.append(place.c.name.ilike(f"%{_like_escape(q)}%", escape="\\"))
    total = conn.execute(select(func.count()).select_from(place).where(*cond)).scalar_one()
    rows = conn.execute(
        select(place.c.id, place.c.name, place.c.category, place.c.cover_image_url,
               as_geojson(place.c.location, "location"))
        .where(*cond).order_by(place.c.name.collate(NAME_COLLATION), place.c.id).limit(limit).offset(offset)
    ).mappings().all()
    return total, [{**r, "location": parse(r["location"])} for r in rows]


def get_place(conn: Connection, place_id: int) -> dict | None:
    r = conn.execute(
        select(place.c.id, place.c.name, place.c.category, place.c.address, place.c.description,
               place.c.cover_image_url, place.c.camera_bearing, place.c.camera_pitch, place.c.camera_zoom,
               place.c.arrival_radius_m, place.c.last_verified_at,
               as_geojson(place.c.location, "location"),
               lng(place.c.location).label("lng"), lat(place.c.location).label("lat"))
        .where(place.c.id == place_id)
    ).mappings().first()
    if r is None:
        return None
    return {**r, "location": parse(r["location"]), "camera": camera_of(r),
            "lng": float(r["lng"]), "lat": float(r["lat"])}


def place_exists(conn: Connection, place_id: int) -> bool:
    return conn.execute(
        select(place.c.id).where(place.c.id == place_id)
    ).first() is not None


def list_entrances(conn: Connection, place_id: int) -> list[dict]:
    rows = conn.execute(
        select(entrance.c.id, entrance.c.name, entrance.c.is_main, entrance.c.description,
               as_geojson(entrance.c.location, "location"))
        .where(entrance.c.place_id == place_id)
        .order_by(entrance.c.is_main.desc(), entrance.c.name.collate(NAME_COLLATION), entrance.c.id)
    ).mappings().all()
    return [{**r, "location": parse(r["location"])} for r in rows]


def list_parking_lots(conn: Connection, place_id: int) -> list[dict]:
    rows = conn.execute(
        select(parking_lot.c.id, parking_lot.c.name, parking_lot.c.priority, parking_lot.c.capacity,
               parking_lot.c.is_free, parking_lot.c.description,
               parking_lot.c.camera_bearing, parking_lot.c.camera_pitch, parking_lot.c.camera_zoom,
               as_geojson(parking_lot.c.location, "location"), as_geojson(parking_lot.c.area, "area"),
               lng(parking_lot.c.location).label("lng"), lat(parking_lot.c.location).label("lat"))
        .where(parking_lot.c.place_id == place_id)
        .order_by(parking_lot.c.priority, parking_lot.c.id)
    ).mappings().all()
    return [{**r, "location": parse(r["location"]), "area": parse(r["area"]), "camera": camera_of(r),
             "lng": float(r["lng"]), "lat": float(r["lat"])} for r in rows]


def list_landmarks(conn: Connection, place_id: int) -> list[dict]:
    rows = conn.execute(
        select(landmark.c.id, landmark.c.name, landmark.c.image_url, as_geojson(landmark.c.location, "location"))
        .where(landmark.c.place_id == place_id).order_by(landmark.c.name.collate(NAME_COLLATION), landmark.c.id)
    ).mappings().all()
    return [{**r, "location": parse(r["location"])} for r in rows]
