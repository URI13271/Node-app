"""출처 값 → 화면 표기 문자열 (설계서 2.4.5 (6), REQ-NF-ATTR-001). 표기 조건은 [검증 필요]."""
ATTRIBUTION_TEXT = {
    "osm": "© OpenStreetMap contributors",
    "vworld": "브이월드",
    "public_data": "공공 건물 데이터",
    "manual": "직접 조사",
}
_ORDER = ["osm", "vworld", "public_data", "manual"]


def attributions(sources: list[str]) -> list[str]:
    """중복 없이, 고정 순서로. 건물이 없으면 ["직접 조사"].
    한 건물에 출처가 둘이면 "osm+public_data" 처럼 + 로 잇는다 (바닥 모양 OSM, 층수 건축물대장)."""
    uniq = {p for s in sources for p in (s or "").split("+") if p in ATTRIBUTION_TEXT}
    if not uniq:
        return [ATTRIBUTION_TEXT["manual"]]
    return [ATTRIBUTION_TEXT[s] for s in _ORDER if s in uniq]
