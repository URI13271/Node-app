"""walk_route, walk_route_step 조회와 쓰기 SQL.

쓰기 함수는 admin 모듈이 쓴다(설계서 2.4.1 모듈 경계 예외). 잠금 순서는 walk_route → walk_route_step.

조회 함수(위쪽 5개)는 BE-07, 쓰기 함수(아래쪽 8개)는 BE-14. 쓰기 함수는 write_tx 안에서만 부른다.
"""

from datetime import datetime

from sqlalchemy import Connection, Float, cast, delete, func, insert, select, text, update

from app.repositories.geo_sql import as_geojson, camera_of, length_m, make_point, parse
from app.repositories.tables import entrance, landmark, parking_lot, walk_route, walk_route_step

# ---------- 조회 ----------


def _route_filter(place_id: int, parking_lot_id: int | None):
    cond = [parking_lot.c.place_id == place_id]
    if parking_lot_id is not None:
        cond.append(walk_route.c.parking_lot_id == parking_lot_id)
    return cond


def version_info(conn: Connection, place_id: int, parking_lot_id: int | None) -> tuple[int, int]:
    """ETag 재료: (updated_at 최댓값의 마이크로초 Unix 시각, 경로 수). 설계서 2.5.4."""
    micros = func.coalesce(func.floor(func.extract("epoch", func.max(walk_route.c.updated_at)) * 1_000_000), 0)
    r = conn.execute(
        select(cast(micros, Float).label("m"), func.count().label("n"))
        .select_from(walk_route.join(parking_lot, parking_lot.c.id == walk_route.c.parking_lot_id))
        .where(*_route_filter(place_id, parking_lot_id))
    ).one()
    return int(r.m), int(r.n)


def parking_lot_place(conn: Connection, parking_lot_id: int) -> int | None:
    return conn.execute(select(parking_lot.c.place_id).where(parking_lot.c.id == parking_lot_id)).scalar()


def list_routes(conn: Connection, place_id: int, parking_lot_id: int | None) -> list[dict]:
    """주차장 우선순위, 경로 id 순. distance_m 이 비어 있으면 선 길이로 채운다."""
    rows = conn.execute(
        select(
            walk_route.c.id,
            walk_route.c.parking_lot_id,
            walk_route.c.entrance_id,
            walk_route.c.walk_time_min,
            walk_route.c.description,
            walk_route.c.updated_at,
            as_geojson(walk_route.c.path, "path"),
            func.coalesce(walk_route.c.distance_m, length_m(walk_route.c.path)).label("distance_m"),
            as_geojson(entrance.c.location, "entrance_location"),
        )
        .select_from(
            walk_route.join(parking_lot, parking_lot.c.id == walk_route.c.parking_lot_id).join(
                entrance, entrance.c.id == walk_route.c.entrance_id
            )
        )
        .where(*_route_filter(place_id, parking_lot_id))
        .order_by(parking_lot.c.priority, walk_route.c.id)
    ).mappings().all()
    return [{**r, "path": parse(r["path"]), "entrance_location": parse(r["entrance_location"])} for r in rows]


def list_steps(conn: Connection, route_ids: list[int]) -> list[dict]:
    """경로 id, step_order 순. 랜드마크 이름을 함께 돌려준다 (랜드마크가 지워졌으면 None)."""
    if not route_ids:
        return []
    rows = conn.execute(
        select(
            walk_route_step.c.id,
            walk_route_step.c.walk_route_id,
            walk_route_step.c.step_order,
            walk_route_step.c.instruction,
            walk_route_step.c.landmark_id,
            landmark.c.name.label("landmark_name"),
            walk_route_step.c.camera_bearing,
            walk_route_step.c.camera_pitch,
            walk_route_step.c.camera_zoom,
            as_geojson(walk_route_step.c.location, "location"),
        )
        .select_from(walk_route_step.outerjoin(landmark, landmark.c.id == walk_route_step.c.landmark_id))
        .where(walk_route_step.c.walk_route_id.in_(route_ids))
        .order_by(walk_route_step.c.walk_route_id, walk_route_step.c.step_order)
    ).mappings().all()
    return [{**r, "location": parse(r["location"]), "camera": camera_of(r)} for r in rows]


def route_place_id(conn: Connection, route_id: int) -> int | None:
    return conn.execute(
        select(parking_lot.c.place_id)
        .select_from(walk_route.join(parking_lot, parking_lot.c.id == walk_route.c.parking_lot_id))
        .where(walk_route.c.id == route_id)
    ).scalar()


# ---------- 쓰기 (admin, BE-14) ----------


def lock_route(conn: Connection, route_id: int) -> datetime | None:
    """walk_route 행 FOR UPDATE. 없으면 None. 돌려주는 값은 현재 버전(updated_at)."""
    return conn.execute(select(walk_route.c.updated_at).where(walk_route.c.id == route_id).with_for_update()).scalar()


def step_route_id(conn: Connection, step_id: int) -> int | None:
    return conn.execute(select(walk_route_step.c.walk_route_id).where(walk_route_step.c.id == step_id)).scalar()


def count_landmarks_in_route_place(conn: Connection, route_id: int, landmark_ids: list[int]) -> int:
    """landmark_ids 중 경로가 속한 장소의 랜드마크 수. 서비스가 len(set(ids)) 와 비교해 다른 장소 랜드마크를 막는다."""
    if not landmark_ids:
        return 0
    return conn.execute(
        select(func.count(func.distinct(landmark.c.id)))
        .select_from(
            landmark.join(parking_lot, parking_lot.c.place_id == landmark.c.place_id).join(
                walk_route, walk_route.c.parking_lot_id == parking_lot.c.id
            )
        )
        .where(walk_route.c.id == route_id, landmark.c.id.in_(landmark_ids))
    ).scalar_one()


def distances_from_path(conn: Connection, route_id: int, points: list[tuple[float, float]]) -> list[float]:
    """각 점과 경로 선 사이 거리(m), geography 기준."""
    path = select(walk_route.c.path).where(walk_route.c.id == route_id).scalar_subquery()
    out = []
    for lng_, lat_ in points:
        d = conn.execute(select(cast(func.ST_Distance(func.Geography(path), func.Geography(make_point(lng_, lat_))), Float))).scalar_one()
        out.append(float(d))
    return out


def buildings_containing(conn: Connection, route_id: int, points: list[tuple[float, float]], wall_tolerance_m: float) -> list[str | None]:
    """각 점이 경로가 속한 장소의 건물 안(벽에서 wall_tolerance_m 안쪽)이면 그 건물 이름, 아니면 None.

    벽 위나 벽 바로 앞(입구 지점)은 건물 밖으로 본다. API 명세서 v1.2 부록 C. load_seed 의 inside_building 과 같은 기준.
    """
    out: list[str | None] = []
    for lng_, lat_ in points:
        name = conn.execute(
            text("""
            SELECT coalesce(b.name, '이름 없는 건물') FROM building b
            JOIN parking_lot l ON l.place_id = b.place_id JOIN walk_route r ON r.parking_lot_id = l.id
            WHERE r.id = :rid
              AND ST_Contains(ST_Buffer(b.footprint::geography, -:tol)::geometry,
                              ST_SetSRID(ST_MakePoint(:lng, :lat), 4326))
            ORDER BY b.is_target DESC, b.id LIMIT 1"""),
            {"rid": route_id, "tol": wall_tolerance_m, "lng": lng_, "lat": lat_},
        ).scalar()
        out.append(name)
    return out


def _camera_columns(cam: dict | None) -> dict:
    return {
        "camera_bearing": cam["bearing"] if cam else None,
        "camera_pitch": cam["pitch"] if cam else None,
        "camera_zoom": cam["zoom"] if cam else None,
    }


def replace_steps(conn: Connection, route_id: int, steps: list[dict], updated_by: str) -> None:
    """경로의 단계를 모두 지우고 새로 넣는다. steps 원소: step_order, landmark_id, instruction, location(lng, lat), camera."""
    conn.execute(delete(walk_route_step).where(walk_route_step.c.walk_route_id == route_id))
    for s in steps:
        conn.execute(
            insert(walk_route_step).values(
                walk_route_id=route_id,
                step_order=s["step_order"],
                landmark_id=s["landmark_id"],
                instruction=s["instruction"],
                location=make_point(*s["location"]),
                **_camera_columns(s["camera"]),
                updated_at=func.clock_timestamp(),
                updated_by=updated_by,
            )
        )


def patch_step(conn: Connection, step_id: int, values: dict, updated_by: str) -> None:
    """values 에 있는 칼럼만 바꾼다. camera 키가 있으면 칼럼 3개로 풀고, None 이면 셋 다 지운다."""
    v = dict(values)
    if "camera" in v:
        v.update(_camera_columns(v.pop("camera")))
    conn.execute(
        update(walk_route_step).where(walk_route_step.c.id == step_id).values(**v, updated_at=func.clock_timestamp(), updated_by=updated_by)
    )


def touch_route(conn: Connection, route_id: int) -> datetime:
    """버전 갱신. now()가 아니라 clock_timestamp()를 써야 저장 시점마다 값이 달라진다(설계서 2.7.4)."""
    return conn.execute(
        update(walk_route).where(walk_route.c.id == route_id).values(updated_at=func.clock_timestamp()).returning(walk_route.c.updated_at)
    ).scalar_one()
