"""엔진, 연결 풀, 트랜잭션 도우미, naming_convention (설계서 2.4.1, 2.7.4).

서비스 메서드 하나 = 트랜잭션 하나. 서비스는 read_tx() 또는 write_tx() 블록 안에서 저장소 함수를 부른다.

뼈대: 본문은 비어 있다.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Connection, Engine, MetaData

# 제약, 인덱스 이름 규칙 (설계서 2.1.5). migrations/001_init.sql 의 이름과 같다.
NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
}
metadata = MetaData(naming_convention=NAMING_CONVENTION)


def get_engine() -> Engine:
    """연결 풀을 한 번 만들어 재사용한다 (세션 시간대 UTC)."""
    raise NotImplementedError("TODO: app.db.get_engine")


def reset_engine() -> None:
    """테스트에서 DATABASE_URL 을 바꾼 뒤 호출."""
    raise NotImplementedError("TODO: app.db.reset_engine")


@contextmanager
def read_tx() -> Iterator[Connection]:
    """읽기 전용 트랜잭션 (statement_timeout 적용)."""
    raise NotImplementedError("TODO: app.db.read_tx")
    yield  # noqa


@contextmanager
def write_tx() -> Iterator[Connection]:
    """관리자 저장 트랜잭션. 예외가 나면 전체 롤백 (statement_timeout, lock_timeout 적용)."""
    raise NotImplementedError("TODO: app.db.write_tx")
    yield  # noqa
