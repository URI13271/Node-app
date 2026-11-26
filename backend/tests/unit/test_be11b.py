"""BE-11b 추가 단위 테스트."""

import pytest

from app.domain.building import render_height
from app.repositories.place_repo import _like_escape


# UT-01 ~ UT-04
@pytest.mark.parametrize(
    "text, expected",
    [
        ("공학관", "공학관"),
        ("%", r"\%"),
        ("_", r"\_"),
        ("\\", "\\\\"),
    ],
    ids=[
        "UT-01",
        "UT-02",
        "UT-03",
        "UT-04",
    ],
)
def test_like_escape(text, expected):
    assert _like_escape(text) == expected


# 건물 높이 및 층수 추가 경계값 검증
@pytest.mark.parametrize(
    "height, levels, expected",
    [
        (-0.1, None, 6.0),
        (0.1, None, 0.1),
        (None, -1, 6.0),
        (None, 0, 6.0),
        (None, 1, 3.0),
    ],
    ids=[
        "BVA-01",
        "BVA-02",
        "BVA-03",
        "BVA-04",
        "BVA-05",
    ],
)
def test_render_height_boundary(height, levels, expected):
    assert render_height(
        height, levels
    ) == pytest.approx(expected)

