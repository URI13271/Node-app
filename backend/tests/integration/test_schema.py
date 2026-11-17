"""tables.py 와 실제 DB 칼럼 비교 (BE-03).

migrate up 만 하면 돌아간다 (시드 적재 불필요). 앱 계정(DATABASE_URL)으로 읽어서 권한도 함께 확인한다.
비교: 테이블 목록, 칼럼 이름과 순서, 타입(길이, 기하 종류, SRID 포함), NULL 허용, 기본 키.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from app.db import metadata
from app.repositories import tables  # noqa: F401  (import 해야 metadata 에 표가 등록된다)

IGNORED = {"spatial_ref_sys", "schema_migrations"}  # PostGIS 기본 표, 마이그레이션 기록

COLUMNS_SQL = """
SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
ORDER BY c.relname, a.attnum
"""

PK_SQL = """
SELECT c.relname, a.attname
FROM pg_index i
JOIN pg_class c ON c.oid = i.indrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY (i.indkey)
WHERE n.nspname = 'public' AND i.indisprimary
"""


def _norm(type_name: str) -> str:
    """DB 표기(character varying(100), geometry(Point,4326))와 SQLAlchemy 표기(VARCHAR(100), geometry(POINT,4326))를 맞춘다."""
    return type_name.lower().replace("character varying", "varchar").replace(" ", "")


def _expected(table) -> list[tuple[str, str, bool]]:
    dialect = postgresql.dialect()
    return [(c.name, _norm(c.type.compile(dialect=dialect)), not c.nullable) for c in table.columns]


@pytest.fixture(scope="module")
def db():
    from app.config import get_settings

    get_settings.cache_clear()
    from app.db import get_engine, reset_engine

    reset_engine()
    from scripts import migrate

    assert migrate.up() == 0
    with get_engine().connect() as conn:
        cols: dict[str, list[tuple[str, str, bool]]] = {}
        for table, name, type_name, not_null in conn.execute(text(COLUMNS_SQL)):
            if table not in IGNORED:
                cols.setdefault(table, []).append((name, _norm(type_name), not_null))
        pks: dict[str, set[str]] = {}
        for table, name in conn.execute(text(PK_SQL)):
            pks.setdefault(table, set()).add(name)
    return cols, pks


def test_same_tables(db):
    cols, _ = db
    assert set(cols) == set(metadata.tables)


@pytest.mark.parametrize("name", sorted(metadata.tables))
def test_columns(db, name):
    cols, _ = db
    assert cols[name] == _expected(metadata.tables[name])


@pytest.mark.parametrize("name", sorted(metadata.tables))
def test_primary_key(db, name):
    _, pks = db
    assert pks[name] == {c.name for c in metadata.tables[name].primary_key.columns}
