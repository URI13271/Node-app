"""walk_route, walk_route_step 조회와 쓰기 SQL.

쓰기 함수는 admin 모듈이 쓴다(설계서 2.4.1 모듈 경계 예외). 잠금 순서는 walk_route → walk_route_step.

조회 함수(위쪽 5개)는 BE-07, 쓰기 함수(아래쪽)는 BE-14 에서 구현한다.
"""

from datetime import datetime

from sqlalchemy import Connection, Float, cast, func, select

from app.repositories.geo_sql import as_geojson, camera_of, length_m, parse
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
    raise NotImplementedError("TODO: app.repositories.walk_route_repo.lock_route")


def step_route_id(conn: Connection, step_id: int) -> int | None:
    raise NotImplementedError("TODO: app.repositories.walk_route_repo.step_route_id")


def count_landmarks_in_route_place(conn: Connection, route_id: int, landmark_ids: list[int]) -> int:
    raise NotImplementedError("TODO: app.repositories.walk_route_repo.count_landmarks_in_route_place")


def distances_from_path(conn: Connection, route_id: int, points: list[tuple[float, float]]) -> list[float]:
    """각 점과 경로 선 사이 거리(m), geography 기준."""
    raise NotImplementedError("TODO: app.repositories.walk_route_repo.distances_from_path")


def buildings_containing(conn: Connection, route_id: int, points: list[tuple[float, float]], wall_tolerance_m: float) -> list[str | None]:
    """각 점이 경로가 속한 장소의 건물 안(벽에서 wall_tolerance_m 안쪽)이면 그 건물 이름, 아니면 None."""
    raise NotImplementedError("TODO: app.repositories.walk_route_repo.buildings_containing")


def replace_steps(conn: Connection, route_id: int, steps: list[dict], updated_by: str) -> None:
    raise NotImplementedError("TODO: app.repositories.walk_route_repo.replace_steps")


def patch_step(conn: Connection, step_id: int, values: dict, updated_by: str) -> None:
    raise NotImplementedError("TODO: app.repositories.walk_route_repo.patch_step")


def touch_route(conn: Connection, route_id: int) -> datetime:
    """버전 갱신. now()가 아니라 clock_timestamp()를 써야 저장 시점마다 값이 달라진다(설계서 2.7.4)."""
    raise NotImplementedError("TODO: app.repositories.walk_route_repo.touch_route")
