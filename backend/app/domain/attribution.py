"""출처 값 → 화면 표기 문자열 (설계서 2.4.5 (6), REQ-NF-ATTR-001). 표기 조건은 [검증 필요].

뼈대: 본문은 비어 있다. 함수마다 NotImplementedError 를 구현으로 바꾼다.
"""


def attributions(sources: list[str]) -> list[str]:
    """중복 없이, 고정 순서로. 건물이 없으면 ["직접 조사"]."""
    raise NotImplementedError("TODO: app.domain.attribution.attributions")
