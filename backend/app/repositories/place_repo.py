"""place, entrance, parking_lot, landmark 조회 SQL.

뼈대: 본문은 비어 있다. 함수마다 NotImplementedError 를 구현으로 바꾼다.
"""

from sqlalchemy import Connection


def search_places(conn: Connection, q: str | None, limit: int, offset: int) -> tuple[int, list[dict]]:
    raise NotImplementedError("TODO: app.repositories.place_repo.search_places")


def get_place(conn: Connection, place_id: int) -> dict | None:
    raise NotImplementedError("TODO: app.repositories.place_repo.get_place")


def place_exists(conn: Connection, place_id: int) -> bool:
    raise NotImplementedError("TODO: app.repositories.place_repo.place_exists")


def list_entrances(conn: Connection, place_id: int) -> list[dict]:
    raise NotImplementedError("TODO: app.repositories.place_repo.list_entrances")


def list_parking_lots(conn: Connection, place_id: int) -> list[dict]:
    raise NotImplementedError("TODO: app.repositories.place_repo.list_parking_lots")


def list_landmarks(conn: Connection, place_id: int) -> list[dict]:
    raise NotImplementedError("TODO: app.repositories.place_repo.list_landmarks")
