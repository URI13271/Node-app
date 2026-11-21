"""building 조회 SQL.

공간 SQL 은 geo_sql 함수만 쓴다. 없으면 None, 목록은 정해진 순서로 돌려준다.
"""

from sqlalchemy import Connection, select

from app.repositories.geo_sql import as_geojson, parse
from app.repositories.tables import building


def list_buildings(conn: Connection, place_id: int) -> list[dict]:
    rows = conn.execute(
        select(
            building.c.id,
            building.c.name,
            building.c.floor_count,
            building.c.height_m,
            building.c.is_target,
            building.c.source,
            as_geojson(building.c.footprint, "footprint"),
        )
        .where(building.c.place_id == place_id)
        .order_by(building.c.is_target.desc(), building.c.id)
    ).mappings().all()

    return [
        {**r, "footprint": parse(r["footprint"])}
        for r in rows
    ]


def list_sources(conn: Connection, place_id: int) -> list[str]:
    return list(
        conn.execute(
            select(building.c.source)
            .where(building.c.place_id == place_id)
            .distinct()
        ).scalars()
    )
