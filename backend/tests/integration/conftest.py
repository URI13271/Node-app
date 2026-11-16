import pytest
from fastapi.testclient import TestClient

from tests.conftest import SEED_DIR, TEST_ADMIN_KEY


def _reset_db():
    from scripts import load_seed, migrate
    while True:  # 전부 되돌린 뒤 다시 적용
        from sqlalchemy import create_engine, text

        from app.config import get_settings
        with create_engine(get_settings().MIGRATION_DATABASE_URL).begin() as c:
            c.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (version varchar(100) PRIMARY KEY, "
                           "applied_at timestamptz NOT NULL DEFAULT now(), checksum char(64) NOT NULL)"))
            n = c.execute(text("SELECT count(*) FROM schema_migrations")).scalar_one()
        if n == 0:
            break
        assert migrate.down() == 0
    assert migrate.up() == 0
    assert load_seed.load(SEED_DIR) == 0


@pytest.fixture(scope="session")
def app():
    from app.config import get_settings
    get_settings.cache_clear()
    from app.db import reset_engine
    reset_engine()
    _reset_db()
    from app.main import create_app
    return create_app()


@pytest.fixture()
def client(app):
    app.state.admin_fail_limiter.reset()
    app.state.public_limiter.reset()
    app.state.admin_limiter.reset()
    return TestClient(app)


@pytest.fixture()
def fresh_db(app):
    """데이터를 바꾸는 테스트 뒤에 시드를 다시 적재한다."""
    yield
    from scripts import load_seed
    assert load_seed.load(SEED_DIR) == 0


ADMIN = {"X-Admin-Key": TEST_ADMIN_KEY}


def place_id(client, name: str) -> int:
    return next(p["id"] for p in client.get("/api/v1/places").json()["items"] if p["name"] == name)
