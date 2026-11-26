
"""BE-11b 추가 통합 테스트."""

import pytest

from app.db import read_tx
from app.repositories import building_repo, place_repo


# 1. 건물 조회 API 예외 처리
# IT-06 ~ IT-09
@pytest.mark.parametrize(
    "place_id, expected",
    [
        ("999999", 404),
        ("0", 400),
        ("-1", 400),
        ("abc", 400),
    ],
    ids=[
        "IT-06",
        "IT-07",
        "IT-08",
        "IT-09",
    ],
)
def test_buildings_invalid_id(client, place_id, expected):
    response = client.get(
        f"/api/v1/places/{place_id}/buildings"
    )

    assert response.status_code == expected


# 2. 미존재 장소의 건물 목록 조회
# IT-15
def test_list_buildings_unknown_place(app):
    with read_tx() as conn:
        rows = building_repo.list_buildings(
            conn, 999999
        )

    assert rows == []


# 3. 검색 결과의 이름 확인
# IT-18 보완
def test_search_places_returns_library(app):
    with read_tx() as conn:
        total, rows = place_repo.search_places(
            conn, "도서", 20, 0
        )

    assert total == 1
    assert [row["name"] for row in rows] == [
        "중앙도서관"
    ]


# 4. 장소 ID 추가 경계값 검증
@pytest.mark.parametrize(
    "place_id",
    [1, 2],
    ids=["BVA-06", "BVA-07"],
)
def test_buildings_valid_id_boundary(client, place_id):
    response = client.get(
        f"/api/v1/places/{place_id}/buildings"
    )

    assert response.status_code in (200, 404)
