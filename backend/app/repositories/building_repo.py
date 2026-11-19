"""building 조회 SQL.

공간 SQL 은 geo_sql 함수만 쓴다. 없으면 None, 목록은 정해진 순서로 돌려준다.
"""

from sqlalchemy import Connection, select

from app.repositories.geo_sql import as_geojson, parse
from app.repositories.tables import building


def list_buildings(conn: Connection, place_id: int) -> list[dict]:
    raise NotImplementedError("BE-11b 연습: list_buildings")


def list_sources(conn: Connection, place_id: int) -> list[str]:
    raise NotImplementedError("BE-11b 연습: list_sources")
