"""building 조회 SQL.

뼈대: 본문은 비어 있다. 함수마다 NotImplementedError 를 구현으로 바꾼다.
"""

from sqlalchemy import Connection


def list_buildings(conn: Connection, place_id: int) -> list[dict]:
    raise NotImplementedError("TODO: app.repositories.building_repo.list_buildings")


def list_sources(conn: Connection, place_id: int) -> list[str]:
    raise NotImplementedError("TODO: app.repositories.building_repo.list_sources")
