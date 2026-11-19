"""건축물대장 표제부(공공데이터포털 15134735)로 buildings.geojson 의 층수와 높이를 채운다 (DA-04).

사용법 (backend 디렉터리에서, DB 필요 없음):
    python -m scripts.fill_floors scripts/seeds/gnu-gajwa --fetch    # API 로 받아 osm/building_register.json 저장 후 매칭
    python -m scripts.fill_floors scripts/seeds/gnu-gajwa            # 저장된 파일로 매칭만 다시 (floors_report.md)
    python -m scripts.fill_floors scripts/seeds/gnu-gajwa --apply    # '확인됨' 건물만 buildings.geojson 에 반영

인증키는 환경 변수 DATA_GO_KR_KEY (verify_seed --fetch-crosswalks 와 같은 키). 키는 파일에 쓰지 않는다.
조회 지번은 --lot 로 바꾼다. 기본값은 진주시 가좌동 900번지 전체와 182-1번지 [검증 필요].

매칭 판정
- 확인됨: 정규화한 이름이 대장의 동명칭 또는 건물명과 같고 후보가 하나, 또는 이름 포함 관계 + 면적비 0.67~1.5,
          또는 floor_map.json 에 사람이 적어 둔 매핑
- 추정: 이름 포함 관계만 맞음, 또는 이름 없이 면적비 0.85~1.18 인 후보가 하나 → 반영하지 않는다
- 확인 필요: 같은 이름 후보가 여럿
- 데이터 없음: 후보 없음
추정, 확인 필요 건물은 리포트를 보고 <seed_dir>/floor_map.json 에 {"OSM way id": "대장 mgmBldrgstPk"} 로 적으면 확인됨이 된다.
"""
import argparse
import datetime as dt
import json
import math
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
SIGUNGU_CD = "48170"                       # 경상남도 진주시
DEFAULT_LOTS = ["13100-0900", "13100-0182-0001"]   # 법정동코드-번[-지], 지 생략 시 그 번의 모든 지
OK, EST, BAD, NONE = "확인됨", "추정", "확인 필요", "데이터 없음"
NAME_AREA_RATIO = (0.67, 1.5)
AREA_ONLY_RATIO = (0.85, 1.18)
DROP_WORDS = ["경상국립대학교", "경상대학교", "국립", "가좌캠퍼스"]


# ---------- 순수 함수 (tests/unit/test_fill_floors.py) ----------

def norm(name: str | None) -> str:
    """비교용 이름: 학교 이름, 공백, 괄호, 앞의 '제', 끝의 '동' 을 뗀다."""
    if not name:
        return ""
    s = re.sub(r"\(.*?\)|\s", "", name)
    for w in DROP_WORDS:
        s = s.replace(w, "")
    s = re.sub(r"^제(?=\d)", "", s)
    s = re.sub(r"(?<=[가-힣\d])동$", "", s) if len(s) > 2 else s
    return s


def ring_area_m2(ring: list[list[float]]) -> float:
    """경위도 고리 면적 (작은 영역용 등거리 근사)."""
    if len(ring) < 4:
        return 0.0
    lat0 = sum(p[1] for p in ring) / len(ring)
    kx, ky = 111320.0 * math.cos(math.radians(lat0)), 110540.0
    pts = [(p[0] * kx, p[1] * ky) for p in ring]
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:], strict=False))) / 2


def to_num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def match(name: str | None, area: float, reg: list[dict], manual_pk: str | None = None) -> tuple[str, dict | None, str]:
    """(판정, 대장 행, 근거)."""
    if manual_pk:
        hit = next((r for r in reg if str(r.get("mgmBldrgstPk")) == str(manual_pk)), None)
        return (OK, hit, "floor_map.json 수동 매핑") if hit else (BAD, None, f"floor_map.json 의 PK {manual_pk} 가 대장에 없음")

    def ratio(r):
        a = to_num(r.get("archArea"))
        return area / a if a and area else None

    n = norm(name)
    if n:
        exact = [r for r in reg if n in (norm(r.get("dongNm")), norm(r.get("bldNm")))]
        if len(exact) == 1:
            return OK, exact[0], "이름 일치"
        if len(exact) > 1:
            close = [r for r in exact if (q := ratio(r)) and NAME_AREA_RATIO[0] <= q <= NAME_AREA_RATIO[1]]
            if len(close) == 1:
                return OK, close[0], f"이름 일치 {len(exact)}건 중 면적비 맞는 1건"
            return BAD, None, f"이름 일치 후보 {len(exact)}건: " + ", ".join(label(r) for r in exact[:5])
        part = [r for r in reg if len(n) >= 3 and any(
            m and len(m) >= 3 and (n in m or m in n) for m in (norm(r.get("dongNm")), norm(r.get("bldNm"))))]
        if len(part) == 1:
            q = ratio(part[0])
            if q and NAME_AREA_RATIO[0] <= q <= NAME_AREA_RATIO[1]:
                return OK, part[0], f"이름 포함 + 면적비 {q:.2f}"
            return EST, part[0], "이름 포함" + (f", 면적비 {q:.2f}" if q else ", 대장 건축면적 없음")
        if len(part) > 1:
            return BAD, None, f"이름 포함 후보 {len(part)}건: " + ", ".join(label(r) for r in part[:5])
    by_area = [r for r in reg if (q := ratio(r)) and AREA_ONLY_RATIO[0] <= q <= AREA_ONLY_RATIO[1]]
    if len(by_area) == 1:
        return EST, by_area[0], f"이름 불일치, 면적비 {ratio(by_area[0]):.2f} 후보 1건"
    return NONE, None, "후보 없음" if not by_area else f"면적만 비슷한 후보 {len(by_area)}건"


def label(r: dict) -> str:
    return " ".join(x for x in (r.get("bldNm"), r.get("dongNm")) if x and str(x).strip()) or str(r.get("mgmBldrgstPk"))


# ---------- 조회 ----------

def parse_lot(s: str) -> dict:
    parts = s.split("-")
    if len(parts) not in (2, 3):
        raise SystemExit(f"[중단] --lot 형식은 법정동코드-번[-지] 입니다: {s}")
    p = {"bjdongCd": parts[0], "platGbCd": "0", "bun": parts[1].zfill(4)}
    if len(parts) == 3:
        p["ji"] = parts[2].zfill(4)
    return p


def api_page(key: str, params: dict) -> tuple[list[dict], int]:
    q = urllib.parse.urlencode({"serviceKey": key, "_type": "json", **params})
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": "majunggil-seed-floors/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read().decode("utf-8", "replace")
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"<(?:returnAuthMsg|errMsg|resultMsg)>([^<]+)<", raw)
        raise SystemExit(f"[중단] API 가 JSON 이 아닌 응답을 줬습니다: {m.group(1) if m else raw[:200]}") from None
    resp = d.get("response", d)
    head = resp.get("header", {})
    if str(head.get("resultCode", "00")) not in ("00", "0", "03"):
        raise SystemExit(f"[중단] API 오류 {head.get('resultCode')}: {head.get('resultMsg')}")
    body = resp.get("body", {}) or {}
    items = body.get("items", []) or []
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):
        items = [items]
    return items, int(body.get("totalCount", 0) or 0)


def fetch(seed_dir: Path, lots: list[str]) -> None:
    key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not key:
        raise SystemExit("[중단] 환경 변수 DATA_GO_KR_KEY 에 공공데이터포털 인증키를 넣어 주세요")
    key = urllib.parse.unquote(key)
    keep = ("mgmBldrgstPk", "platPlc", "bun", "ji", "bldNm", "dongNm", "mainPurpsCdNm", "grndFlrCnt",
            "ugrndFlrCnt", "heit", "archArea", "totArea", "useAprDay", "regstrKindCdNm")
    rows, seen = [], set()
    for lot in lots:
        p = {"sigunguCd": SIGUNGU_CD, **parse_lot(lot)}
        page = 1
        while True:
            items, total = api_page(key, {**p, "numOfRows": 100, "pageNo": page})
            print(f"[조회] {lot} {page}쪽 {len(items)}건 (전체 {total})")
            for it in items:
                pk = it.get("mgmBldrgstPk")
                if pk not in seen:
                    seen.add(pk)
                    rows.append({k: it.get(k) for k in keep})
            if not items or page * 100 >= total:
                break
            page += 1
    out = {"src": f"국토교통부_건축HUB_건축물대장정보 서비스 표제부(공공데이터포털 15134735), 지번 {', '.join(lots)}, "
                  f"{dt.date.today()} 조회 (이용허락범위 제한 없음)", "items": rows}
    path = seed_dir / "osm/building_register.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[저장] {path} ({len(rows)}동)")
    if not rows:
        print("[경고] 0건입니다. --lot 의 법정동코드와 번지를 확인하세요 (토지이음 또는 건축HUB 에서 캠퍼스 지번 검색)")


# ---------- 매칭, 리포트, 반영 ----------

def bkey(f: dict) -> str:
    """같은 건물을 하나로 묶는 키: OSM way id, 없으면 바닥 모양 첫 점 (장소마다 같은 건물이 중복으로 들어 있다)."""
    m = re.search(r"OSM way (\d+)", f["properties"].get("description") or "")
    if m:
        return m.group(1)
    x, y = f["geometry"]["coordinates"][0][0][:2]
    return f"pt{x:.6f},{y:.6f}"


def run(seed_dir: Path, apply: bool) -> int:
    reg_path = seed_dir / "osm/building_register.json"
    if not reg_path.exists():
        raise SystemExit("[중단] osm/building_register.json 이 없습니다. --fetch 로 먼저 받으세요")
    reg_doc = json.loads(reg_path.read_text(encoding="utf-8"))
    reg = reg_doc["items"]
    fmap_path = seed_dir / "floor_map.json"
    fmap = json.loads(fmap_path.read_text(encoding="utf-8")) if fmap_path.exists() else {}
    bpath = seed_dir / "buildings.geojson"
    gj = json.loads(bpath.read_text(encoding="utf-8"))

    results, used = {}, set()           # OSM way 단위 (장소마다 같은 건물이 중복으로 들어 있다)
    for f in gj["features"]:
        pr = f["properties"]
        wid = bkey(f)
        if wid in results:
            if pr.get("is_target"):
                results[wid] = results[wid][:5] + (True,)
            continue
        area = ring_area_m2(f["geometry"]["coordinates"][0])
        st, hit, why = match(pr.get("name"), area, reg, fmap.get(wid))
        results[wid] = (st, hit, why, pr.get("name"), area, pr.get("is_target"))
        if hit:
            used.add(hit.get("mgmBldrgstPk"))

    order = {OK: 0, EST: 1, BAD: 2, NONE: 3}
    lines = [f"# 건물 층수 매칭 결과 ({seed_dir.name})", "",
             f"생성: {dt.datetime.now():%Y-%m-%d %H:%M}, `python -m scripts.fill_floors`", "",
             f"대장: {reg_doc['src']}, {len(reg)}동", "",
             "| 판정 | OSM way | 이름 | 면적㎡ | 대장 건물 | 지상층 | 높이m | 건축면적㎡ | PK | 근거 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for wid, (st, hit, why, name, area, tgt) in sorted(results.items(), key=lambda x: (not x[1][5], order[x[1][0]])):
        h = hit or {}
        lines.append(f"| {st} | {wid} | {(name or '(이름 없음)') + (' **목적**' if tgt else '')} | {area:.0f} | "
                     f"{label(h) if hit else ''} | {to_num(h.get('grndFlrCnt')) or ''} | {to_num(h.get('heit')) or ''} | "
                     f"{to_num(h.get('archArea')) or ''} | {h.get('mgmBldrgstPk') or ''} | {why} |")
    rest = [r for r in reg if r.get("mgmBldrgstPk") not in used]
    lines += ["", f"## 아직 연결되지 않은 대장 건물 {len(rest)}동", "",
              "floor_map.json 에 {\"OSM way id\": \"PK\"} 로 적으면 다음 실행부터 확인됨으로 반영된다", "",
              "| 대장 건물 | 용도 | 지상층 | 높이m | 건축면적㎡ | PK |", "|---|---|---|---|---|---|"]
    lines += [f"| {label(r)} | {r.get('mainPurpsCdNm') or ''} | {r.get('grndFlrCnt') or ''} | {r.get('heit') or ''} | "
              f"{r.get('archArea') or ''} | {r.get('mgmBldrgstPk')} |" for r in rest]

    counts = {}
    for st, *_ in results.values():
        counts[st] = counts.get(st, 0) + 1
    if apply:
        today = reg_doc["src"].split(", ")[-1].split(" ")[0]
        n = 0
        for f in gj["features"]:
            pr = f["properties"]
            wid = bkey(f)
            st, hit, *_ = results[wid]
            fl = to_num(hit.get("grndFlrCnt")) if st == OK and hit else None
            if not fl:
                continue
            pr["floor_count"] = int(fl)
            pr["height_m"] = to_num(hit.get("heit"))
            pr["source"] = "osm+public_data"          # 바닥 모양은 OSM, 층수는 건축물대장
            src = f"OSM way {wid}" if wid.isdigit() else (pr.get("description") or "").split(".")[0]
            pr["description"] = f"{src}. 층수: 건축물대장 표제부 {label(hit)} ({today} 조회)"
            n += 1
        bpath.write_text(json.dumps(gj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        lines += ["", "## 반영 (--apply)", "", f"- buildings.geojson feature {n}개에 floor_count, height_m, source 반영"]
        print(f"[반영] buildings.geojson feature {n}개 → load_seed 를 다시 실행하세요")
    (seed_dir / "floors_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    tgt = [(r[3], r[0]) for r in results.values() if r[5]]
    print("[목적 건물] " + ", ".join(f"{n} {s}" for n, s in tgt))
    print("[요약] OSM 건물 " + str(len(results)) + "동: " + ", ".join(f"{k} {v}" for k, v in counts.items())
          + f" → {seed_dir / 'floors_report.md'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("seed_dir", nargs="?", default="scripts/seeds/gnu-gajwa")
    ap.add_argument("--fetch", action="store_true", help="건축물대장 API 로 받아 osm/building_register.json 저장 (DATA_GO_KR_KEY 필요)")
    ap.add_argument("--lot", action="append", help="법정동코드-번[-지], 여러 번 쓸 수 있다 (기본 " + ", ".join(DEFAULT_LOTS) + ")")
    ap.add_argument("--apply", action="store_true", help="확인됨 건물만 buildings.geojson 에 반영")
    a = ap.parse_args()
    seed_dir = Path(a.seed_dir)
    if a.fetch:
        fetch(seed_dir, a.lot or DEFAULT_LOTS)
    return run(seed_dir, a.apply)


if __name__ == "__main__":
    sys.exit(main())
