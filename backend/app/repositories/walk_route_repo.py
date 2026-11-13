"""walk_route, walk_route_step 조회와 쓰기 SQL.

쓰기 함수는 admin 모듈이 쓴다(설계서 2.4.1 모듈 경계 예외). 잠금 순서는 walk_route → walk_route_step.

뼈대: 본문은 비어 있다. 함수마다 NotImplementedError 를 구현으로 바꾼다.
"""

from datetime import datetime

from sqlalchemy import Connection


def version_info(conn: Connection, place_id: int, parking_lot_id: int | None) -> tuple[int, int]:
    """ETag 재료: (updated_at 최댓값의 마이크로초 Unix 시각, 경로 수). 설계서 2.5.4."""
    raise NotImplementedError("TODO: app.repositories.walk_route_repo.version_info")


def parking_lot_place(conn: Connection, parking_lot_id: int) -> int | None:
    raise NotImplementedError("TODO: app.repositories.walk_route_repo.parking_lot_place")


def list_routes(conn: Connection, place_id: int, parking_lot_id: int | None) -> list[dict]:
    raise NotImplementedError("TODO: app.repositories.walk_route_repo.list_routes")


def list_steps(conn: Connection, route_ids: list[int]) -> list[dict]:
    raise NotImplementedError("TODO: app.repositories.walk_route_repo.list_steps")


def route_place_id(conn: Connection, route_id: int) -> int | None:
    raise NotImplementedError("TODO: app.repositories.walk_route_repo.route_place_id")


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
