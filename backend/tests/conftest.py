"""테스트 공용 설정.

통합 테스트는 실제 PostgreSQL + PostGIS 가 필요하다. 개발 DB를 지우지 않도록 별도 DB를 쓴다.
    TEST_DATABASE_URL            앱 계정 (DDL 없음)
    TEST_MIGRATION_DATABASE_URL  소유자 계정 (마이그레이션, 시드)
둘 다 없으면 통합 테스트는 건너뛴다(단위 테스트만 실행).
"""

import os

import pytest

TEST_DB = os.getenv("TEST_DATABASE_URL")
TEST_MIG_DB = os.getenv("TEST_MIGRATION_DATABASE_URL")


def pytest_collection_modifyitems(config, items):
    if TEST_DB and TEST_MIG_DB:
        return
    skip = pytest.mark.skip(reason="TEST_DATABASE_URL, TEST_MIGRATION_DATABASE_URL 이 없어 통합 테스트를 건너뜀")
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(skip)
