"""scripts/fill_floors 의 이름 정규화, 면적, 매칭 판정."""
import pytest

from scripts.fill_floors import BAD, EST, NONE, OK, match, norm, ring_area_m2

REG = [
    {"mgmBldrgstPk": "1", "bldNm": "경상국립대학교", "dongNm": "중앙도서관", "grndFlrCnt": 5, "heit": 21.3, "archArea": 3000},
    {"mgmBldrgstPk": "2", "bldNm": "경상국립대학교", "dongNm": "제1학생회관", "grndFlrCnt": 3, "heit": 0, "archArea": 1500},
    {"mgmBldrgstPk": "3", "bldNm": "경상국립대학교", "dongNm": "교양학관동", "grndFlrCnt": 4, "heit": 16, "archArea": 2000},
    {"mgmBldrgstPk": "4", "bldNm": "", "dongNm": "301동", "grndFlrCnt": 2, "heit": 8, "archArea": 800},
]


def test_norm_drops_school_spaces_suffix():
    assert norm("경상국립대학교 중앙 도서관") == "중앙도서관"
    assert norm("교양학관동") == "교양학관"
    assert norm("제1학생회관") == "1학생회관"
    assert norm(None) == ""


def test_ring_area_square_about_100m():
    d = 100 / 111320 / 0.8187           # 35.1도에서 경도 100m
    ring = [[128.0, 35.1], [128.0 + d, 35.1], [128.0 + d, 35.1 + 100 / 110540], [128.0, 35.1 + 100 / 110540], [128.0, 35.1]]
    assert ring_area_m2(ring) == pytest.approx(10000, rel=0.01)


def test_match_exact_name():
    st, hit, _ = match("중앙도서관", 2900, REG)
    assert st == OK and hit["mgmBldrgstPk"] == "1"


def test_match_suffix_dong_is_exact():
    assert match("교양학관", 2100, REG)[0] == OK


def test_match_partial_name_needs_area():
    assert match("학생회관", 1450, REG)[0] == OK          # 포함 + 면적비 0.97
    assert match("학생회관", 300, REG)[0] == EST          # 포함만


def test_match_area_only_is_estimate():
    st, hit, _ = match(None, 820, REG)
    assert st == EST and hit["mgmBldrgstPk"] == "4"


def test_match_none_and_manual():
    assert match("Seismological Observatory", 50, REG)[0] == NONE
    assert match("아무거나", 50, REG, manual_pk="4")[0] == OK
    assert match("아무거나", 50, REG, manual_pk="999")[0] == BAD


def test_match_duplicate_names_need_review():
    reg = REG + [{"mgmBldrgstPk": "5", "dongNm": "중앙도서관", "archArea": 400}]
    assert match("중앙도서관", 2900, reg)[0] == OK        # 면적비로 하나 남음
    assert match("중앙도서관", 100, reg)[0] == BAD
