"""엔진, 연결 풀, 트랜잭션 도우미, naming_convention (설계서 2.4.1, 2.7.4).

서비스 메서드 하나 = 트랜잭션 하나. 서비스는 read_tx() 또는 write_tx() 블록 안에서 저장소 함수를 부른다.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Connection, Engine, MetaData, create_engine, text

from app.config import get_settings

# 제약, 인덱스 이름 규칙 (설계서 2.1.5). migrations/001_init.sql 의 이름과 같다.
NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
}
metadata = MetaData(naming_convention=NAMING_CONVENTION)

_engine: Engine | None = None


def get_engine() -> Engine:
    """연결 풀을 한 번 만들어 재사용한다 (세션 시간대 UTC)."""
    global _engine
    if _engine is None:
        s = get_settings()
        _engine = create_engine(
            s.DATABASE_URL,
            pool_size=s.DB_POOL_SIZE,
            max_overflow=s.DB_MAX_OVERFLOW,
            pool_timeout=s.DB_POOL_TIMEOUT_S,
            pool_pre_ping=True,  # 끊긴 연결을 미리 걸러낸다 (DB 재시작 뒤 첫 요청 실패 방지)
            connect_args={"options": "-c timezone=UTC", "connect_timeout": 3},
        )
    return _engine


def reset_engine() -> None:
    """테스트에서 DATABASE_URL 을 바꾼 뒤 호출."""
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None


@contextmanager
def read_tx() -> Iterator[Connection]:
    """읽기 전용 트랜잭션 (statement_timeout 적용)."""
    s = get_settings()
    with get_engine().connect() as conn, conn.begin():
        conn.execute(text("SET TRANSACTION READ ONLY"))  # 트랜잭션의 첫 문장이어야 한다
        conn.execute(text(f"SET LOCAL statement_timeout = {int(s.DB_STATEMENT_TIMEOUT_MS)}"))
        yield conn


@contextmanager
def write_tx() -> Iterator[Connection]:
    """관리자 저장 트랜잭션. 예외가 나면 전체 롤백 (statement_timeout, lock_timeout 적용)."""
    s = get_settings()
    with get_engine().connect() as conn, conn.begin():
        conn.execute(text(f"SET LOCAL statement_timeout = {int(s.DB_ADMIN_STATEMENT_TIMEOUT_MS)}"))
        conn.execute(text(f"SET LOCAL lock_timeout = {int(s.DB_LOCK_TIMEOUT_MS)}"))
        yield conn