"""현장 조사 체크리스트(seeds/<지역>/README.md)를 데이터와 알고리즘으로 검사한다.

사용법 (backend 디렉터리에서, DB 필요 없음):
    python -m scripts.verify_seed scripts/seeds/gnu-gajwa                    # 지금 있는 데이터로 검사
    python -m scripts.verify_seed scripts/seeds/gnu-gajwa --fetch            # OSM 최신 태그를 osm/extra_osm.json 에 받은 뒤 검사
    python -m scripts.verify_seed scripts/seeds/gnu-gajwa --crosswalk-csv 횡단보도.csv   # 공공데이터 횡단보도 좌표와 대조
    python -m scripts.verify_seed scripts/seeds/gnu-gajwa --fetch-crosswalks  # 공공데이터 API 로 받아 저장 후 대조

--fetch-crosswalks 는 공공데이터포털 전국횡단보도표준데이터(15028201) 오픈 API 를 쓴다.
인증키는 환경 변수 DATA_GO_KR_KEY 에 넣는다 (일반 인증키 Decoding 값, Encoding 값도 받는다). 키는 파일에 쓰지 않는다.
받은 결과는 <seed_dir>/public_crosswalks.json 에 저장되고, 다음 실행부터는 이 파일을 자동으로 읽는다.
    python -m scripts.verify_seed scripts/seeds/gnu-gajwa --apply            # 근거가 있는 값만 시드 파일에 반영

결과는 콘솔과 <seed_dir>/verify_report.md 에 쓴다. 판정은 네 가지다.
- 확인됨: 데이터 근거가 있다 (OSM 태그, 공공데이터, 기하 검사)
- 추정: 기하 검사는 통과했지만 직접 근거는 없다, 또는 면적 같은 계산값이다
- 확인 필요: 검사에 걸렸다 (다른 건물 벽 위, 막힌 길, 경로에서 벗어난 단계 등)
- 데이터 없음: 이 항목을 판정할 데이터가 없다

항목별 방법
1 입구: 목적 건물 벽까지 거리, 붙은 건물과의 공유 벽 길이(부속 건물 판정), 다른 건물 벽 위 여부,
  보행망 연결 가능 여부, OSM entrance 점과의 거리
2 표시 없는 횡단: OSM 최신 crossing 점/선, 공공데이터 횡단보도 좌표를 반경 안에서 찾는다.
  없으면 횡단보도만 쓰는 우회 경로 길이를 계산해 비교한다
3 추가 횡단보도: 근거 데이터에 있는데 보행망에 없는 횡단보도를 찾아 경로를 다시 만든다.
  근거가 없어도 차도 위 가상 횡단 지점마다 경로를 다시 만들어, 어디에 있으면 얼마나 줄어드는지 순위를 낸다
4 인도: 경로를 2m 간격으로 잘라 인도, 보행로, 구내 도로(인도 없음) 비율을 낸다. OSM barrier, construction 과 교차 검사
5 계단: 경로 위 계단 구간 위치와 길이, OSM 계단 태그(step_count, ramp, handrail, wheelchair)
6 랜드마크: 단계 지점에서 40m 안, 건물에 가리지 않는 대상(시야선 검사)을 찾는다. 단계 지점이 경로 위에 있는지도 본다
7 층수: OSM building:levels, height 를 목적 건물과 겹침 비율(IoU)로 맞춘다
8 주차장: OSM amenity=parking 의 capacity, fee, access 태그. 없으면 면적 / 25㎡ 로 면수를 추정한다
"""
import argparse
import csv
import datetime as dt
import json
import math
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import nearest_points

from scripts import build_walk_routes as bw

OK, EST, BAD, NONE = "확인됨", "추정", "확인 필요", "데이터 없음"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
ENTRANCE_WALL_M = 2.0        # 입구가 벽에서 이만큼 안이면 벽 위로 본다
SHARED_WALL_M = 3.0          # 이 길이 이상 벽을 같이 쓰면 부속 건물로 본다
OSM_ENTRANCE_MATCH_M = 8.0
CROSSING_EVIDENCE_M = 8.0
CSV_EVIDENCE_M = 15.0
CROSSING_HALF_M = 7.0        # 가상 횡단보도 선의 반 길이 (차도 중심선에서 양쪽 인도까지)
HYPO_SPACING_M = 15.0
HYPO_CORRIDOR_M = 120.0
DETOUR_RATIO = 1.5           # 경로 길이 / 직선 거리 가 이보다 크면 가상 횡단 분석
LANDMARK_MAX_M = 40.0
STEP_ON_ROUTE_M = 5.0
PARKING_M2_PER_SPACE = 25.0  # 통로 포함 1면당 면적 (추정용)
BLOCKING_BARRIERS = {"fence", "wall", "hedge", "retaining_wall", "guard_rail", "city_wall", "jersey_barrier"}
WARN_NODE_BARRIERS = {"gate", "turnstile", "lift_gate", "swing_gate", "chain"}


# ---------- 데이터 읽기 ----------

def jload(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def fix(poly):
    return poly if poly.is_valid else poly.buffer(0)


def iou(a, b) -> float:
    u = a.union(b).area
    return a.intersection(b).area / u if u else 0.0


class Seed:
    def __init__(self, seed_dir: Path, csv_path: str | None):
        self.dir = seed_dir
        self.net, self.loc, self.nodes, self.polys, self.shrunk, self.manual = bw.load_world(seed_dir)
        self.g = bw.Graph(self.net, self.nodes, self.shrunk, self.manual)
        self.places = {p["key"]: p for p in jload(seed_dir / "places.json")}
        self.buildings = jload(seed_dir / "buildings.geojson")
        self.entrances = jload(seed_dir / "entrances.geojson")
        self.landmarks = jload(seed_dir / "landmarks.geojson")
        self.parking = jload(seed_dir / "parking_lots.geojson")
        self.routes = jload(seed_dir / "walk_routes.geojson")
        self.steps = jload(seed_dir / "walk_route_steps.json")
        self.manual_json = jload(seed_dir / "osm/manual_crossings.json")
        bld = jload(seed_dir / "osm/buildings_osm.json")
        self.osm_bld = [(b.get("n"), fix(Polygon([self.loc.m(*p) for p in bw._pairs(b["g"], bld["o"], bld["u"])])))
                        for b in bld["buildings"]]
        self.targets = {f["properties"]["place_key"]: fix(self.poly(f["geometry"]["coordinates"][0]))
                        for f in self.buildings["features"] if f["properties"].get("is_target")}
        self.extra = self._load_extra()
        self.csv_pts = self._load_csv(csv_path) if csv_path else None
        self.pub_src = None
        pub = seed_dir / "public_crosswalks.json"
        if pub.exists():
            d = jload(pub)
            self.pub_src = d.get("src")
            pts = [Point(self.loc.m(it["lng"], it["lat"])) for it in d.get("items", [])]
            self.csv_pts = (self.csv_pts or []) + pts

    def m(self, lnglat) -> tuple[float, float]:
        return self.loc.m(*lnglat)

    def poly(self, ring):
        return Polygon([self.m(p) for p in ring])

    def ll(self, p) -> str:
        lng, lat = self.loc.ll(p.x, p.y)
        return f"{lat:.6f}, {lng:.6f}"

    def lnglat(self, p) -> list[float]:
        return list(self.loc.ll(p.x, p.y))

    def _load_extra(self):
        p = self.dir / "osm/extra_osm.json"
        if not p.exists():
            return None
        d = jload(p)
        nodes, ways = [], []
        for e in d.get("elements", []):
            t = e.get("tags", {})
            if e["type"] == "node":
                nodes.append((Point(self.loc.m(e["lon"], e["lat"])), t, e["id"]))
            elif e["type"] == "way" and e.get("geometry"):
                pts = [self.loc.m(q["lon"], q["lat"]) for q in e["geometry"]]
                if len(pts) < 2:
                    continue
                area = len(pts) >= 4 and pts[0] == pts[-1] and ("building" in t or t.get("amenity") == "parking")
                ways.append((fix(Polygon(pts)) if area else LineString(pts), t, e["id"]))
        return {"nodes": nodes, "ways": ways, "src": d.get("src", "osm/extra_osm.json")}

    def _load_csv(self, path: str):
        raw = Path(path).read_bytes()
        for enc in ("utf-8-sig", "cp949", "euc-kr"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise SystemExit(f"[중단] CSV 인코딩을 읽지 못했습니다: {path}")
        rows = list(csv.DictReader(text.splitlines()))
        if not rows:
            return []
        keys = list(rows[0])
        latk = next((k for k in keys if "위도" in k or k.strip().lower() in ("lat", "latitude", "y")), None)
        lngk = next((k for k in keys if "경도" in k or k.strip().lower() in ("lng", "lon", "longitude", "x")), None)
        if not latk or not lngk:
            raise SystemExit(f"[중단] CSV 에서 위도, 경도 열을 찾지 못했습니다. 열 이름: {keys}")
        pts = []
        for r in rows:
            try:
                lat, lng = float(r[latk]), float(r[lngk])
            except (TypeError, ValueError):
                continue
            p = Point(self.loc.m(lng, lat))
            if abs(p.x) < 5000 and abs(p.y) < 5000:   # 캠퍼스 근처만
                pts.append(p)
        return pts

    def route_specs(self):
        ents = {(f["properties"]["place_key"], f["properties"]["name"]): f["geometry"]["coordinates"]
                for f in self.entrances["features"]}
        out = []
        for f in self.routes["features"]:
            pr = f["properties"]
            name = f"{pr['parking_lot_name']} → {self.places[pr['place_key']]['name']} {pr['entrance_name']}"
            out.append((name, pr, self.m(f["geometry"]["coordinates"][0]),
                        self.m(ents[(pr["place_key"], pr["entrance_name"])]),
                        LineString([self.m(c) for c in f["geometry"]["coordinates"]])))
        return out

    def osm_with(self, key, values=None, kind="both"):
        if not self.extra:
            return []
        src = (self.extra["nodes"] if kind in ("node", "both") else []) + (self.extra["ways"] if kind in ("way", "both") else [])
        return [x for x in src if key in x[1] and (values is None or x[1][key] in values)]


# ---------- 경로 다시 만들기 ----------

def run_routes(s: Seed, manual: list[LineString], only: set[str] | None = None, penalty: float | None = None):
    old = bw.MAIN_ROAD_PENALTY_M
    if penalty is not None:
        bw.MAIN_ROAD_PENALTY_M = penalty
    try:
        try:
            g = bw.Graph(s.net, s.nodes, s.shrunk, manual)
        except SystemExit:
            return None
        res = {}
        for name, _pr, start, end, _line in s.route_specs():
            if only and name not in only:
                continue
            try:
                line = LineString([start, *g.route(start, end, s.shrunk), end]).simplify(0.3)
                res[name] = (line, bw.check_path(line, g, s.shrunk))
            except bw.NoRoute:
                res[name] = None
        return res
    finally:
        bw.MAIN_ROAD_PENALTY_M = old


def crossing_line_at(s: Seed, p: Point) -> LineString | None:
    """p 에서 가장 가까운 차도에 수직인 횡단 선 (양 끝 CROSSING_HALF_M)."""
    best = None
    for i in s.g.main_tree.query(p.buffer(5)):
        road = s.g.main_lines[i]
        d = road.distance(p)
        if d <= 5 and (best is None or d < best[0]):
            best = (d, road)
    if not best:
        return None
    road = best[1]
    t = road.project(p)
    a, b = road.interpolate(max(t - 2, 0)), road.interpolate(min(t + 2, road.length))
    dx, dy = b.x - a.x, b.y - a.y
    n = math.hypot(dx, dy) or 1.0
    q = road.interpolate(t)
    nx, ny = -dy / n * CROSSING_HALF_M, dx / n * CROSSING_HALF_M
    return LineString([(q.x + nx, q.y + ny), (q.x - nx, q.y - ny)])


# ---------- 보고서 ----------

class Report:
    def __init__(self):
        self.sections: list[tuple[str, list[tuple[str, str, str]], list[str]]] = []

    def section(self, title: str):
        rows, notes = [], []
        self.sections.append((title, rows, notes))
        return rows, notes

    def md(self, header: list[str]) -> str:
        out = [*header, ""]
        for title, rows, notes in self.sections:
            out += [f"## {title}", ""]
            if rows:
                out += ["| 판정 | 대상 | 근거 |", "|---|---|---|"]
                out += [f"| {a} | {b} | {c.replace('|', '/')} |" for a, b, c in rows]
                out.append("")
            prev = None
            for n in notes:
                is_item = n.startswith("- ")
                if prev is not None and (not is_item or not prev):
                    out.append("")
                out.append(n)
                prev = is_item
            if notes:
                out.append("")
        return "\n".join(out)

    def console(self):
        for title, rows, notes in self.sections:
            print(f"\n== {title}")
            for a, b, c in rows:
                print(f"[{a}] {b}: {c}")
            for n in notes:
                print(f"    {n}")


# ---------- 항목별 검사 ----------

def check_entrances(s: Seed, rep: Report):
    rows, notes = rep.section("1. 입구 위치")
    osm_ents = s.osm_with("entrance", kind="node")
    for f in s.entrances["features"]:
        pr = f["properties"]
        pk, xy = pr["place_key"], s.m(f["geometry"]["coordinates"])
        pt, tgt = Point(xy), s.targets.get(pr["place_key"])
        who = f"{s.places[pk]['name']} {pr['name']}{' (대표)' if pr.get('is_main') else ''}"
        if tgt is None:
            rows.append((NONE, who, "buildings.geojson 에 목적 건물(is_target)이 없음"))
            continue
        # 목적 건물과 벽을 같이 쓰는 건물은 부속 건물로 보고 한 덩어리로 본다
        annex, others = [], []
        for name, p in s.osm_bld:
            if iou(p, tgt) > 0.8:
                continue
            shared = p.boundary.intersection(tgt.buffer(0.5)).length
            (annex if shared >= SHARED_WALL_M else others).append((name, p, shared))
        complex_ = fix(tgt.union(*[p for _, p, _ in annex])) if annex else tgt
        d_tgt, d_cx = pt.distance(tgt.exterior), pt.distance(complex_.exterior if complex_.geom_type == "Polygon" else complex_.boundary)
        touching = [n or "이름 없는 건물" for n, p, _ in others if p.distance(pt) < 1.5]
        s.g._temp = []
        reach = s.g.connectors(xy, s.shrunk)
        s.g._clear_temp()
        ev = [f"목적 건물 벽까지 {d_tgt:.1f}m"]
        on_annex = d_tgt > ENTRANCE_WALL_M and d_cx <= ENTRANCE_WALL_M
        if on_annex:
            sh = max(sh for _, p, sh in annex if p.distance(pt) < ENTRANCE_WALL_M + 1)
            ev.append(f"붙은 건물 벽 위 (목적 건물과 공유 벽 {sh:.0f}m, 부속 건물로 판정)")
        ev.append(f"보행망 연결 후보 {len(reach)}개")
        bad = []
        if d_cx > ENTRANCE_WALL_M:
            bad.append(f"건물 벽에서 {d_cx:.1f}m 떨어짐")
        if touching:
            bad.append(f"다른 건물 벽 위: {', '.join(touching)}")
        if not reach:
            bad.append("60m 안에 이을 보행로 없음")
        if bad:
            rows.append((BAD, who, "; ".join(bad + ev)))
            continue
        on_tgt = [(p, t) for p, t, _ in osm_ents if p.distance(complex_) < ENTRANCE_WALL_M]
        if s.extra is None:
            rows.append((EST, who, "; ".join(ev) + ". OSM 출입구 태그는 --fetch 뒤에 대조"))
        elif not on_tgt:
            rows.append((EST, who, "; ".join(ev) + ". OSM 최신 데이터에도 이 건물의 entrance 점이 없음"))
        else:
            d, (p, t) = min(((p.distance(pt), (p, t)) for p, t in on_tgt), key=lambda x: x[0])
            if d <= OSM_ENTRANCE_MATCH_M:
                rows.append((OK, who, f"OSM entrance={t.get('entrance')} 점과 {d:.1f}m; " + "; ".join(ev)))
            else:
                cands = ", ".join(f"({s.ll(p)} entrance={t.get('entrance')})" for p, t in on_tgt)
                rows.append((BAD if pr.get("is_main") else EST, who,
                             f"OSM 에는 이 위치 출입구가 없음, 가장 가까운 OSM 출입구 {d:.0f}m: {cands}; " + "; ".join(ev)))
            mains = [p for p, t in on_tgt if t.get("entrance") == "main"]
            if pr.get("is_main") and mains and min(p.distance(pt) for p in mains) > OSM_ENTRANCE_MATCH_M:
                notes.append(f"{who}: OSM 정문(entrance=main)은 {', '.join(s.ll(p) for p in mains)}")


def crossing_evidence(s: Seed, p: Point) -> list[str]:
    ev, seen = [], set()
    for q, t, oid in s.osm_with("highway", {"crossing"}, "node") + s.osm_with("crossing", kind="node"):
        if oid in seen:
            continue
        seen.add(oid)
        if q.distance(p) <= CROSSING_EVIDENCE_M:
            ev.append(f"OSM node {oid} crossing={t.get('crossing', 'yes')} {q.distance(p):.1f}m")
    for q, _t, oid in s.osm_with("footway", {"crossing"}, "way"):
        if q.distance(p) <= CROSSING_EVIDENCE_M:
            ev.append(f"OSM way {oid} footway=crossing {q.distance(p):.1f}m")
    for q in s.csv_pts or []:
        if q.distance(p) <= CSV_EVIDENCE_M:
            ev.append(f"공공데이터 횡단보도 {q.distance(p):.1f}m")
    return ev


def check_unmarked(s: Seed, rep: Report, base: dict):
    rows, notes = rep.section("2. 횡단보도 표시 없는 차도 횡단")
    srcs = ["2026-11-11 OSM 보행망"] + (["OSM 최신 태그"] if s.extra else []) + (["공공데이터 횡단보도"] if s.csv_pts is not None else [])
    found = False
    strict = None
    for name, res in base.items():
        if not res:
            continue
        for p in res[1]["unmarked_crossings"]:
            found = True
            ev = crossing_evidence(s, p)
            if ev:
                rows.append((OK, f"{name} @ {s.ll(p)}", "횡단보도 근거 있음: " + "; ".join(ev) + " → --apply 로 manual_crossings 에 추가"))
                continue
            if strict is None:
                strict = run_routes(s, s.manual, penalty=1e6)
            alt = strict.get(name) if strict else None
            alt_txt = (f"횡단보도만 쓰는 우회 경로 {alt[0].length:.0f}m (지금 {res[0].length:.0f}m, +{alt[0].length - res[0].length:.0f}m)"
                       if alt and not alt[1]["unmarked_crossings"] else "보행망 안에서는 횡단보도만으로 이 입구까지 가는 경로가 없음")
            rows.append((EST if s.extra or s.csv_pts is not None else NONE, f"{name} @ {s.ll(p)}",
                         f"{', '.join(srcs)} 어디에도 횡단보도 없음. {alt_txt}"))
    if not found:
        notes.append("표시 없는 횡단 지점을 지나는 경로 없음")
    if not (s.extra or s.csv_pts is not None):
        notes.append("근거 데이터가 2026-11-11 OSM 하나뿐이다. --fetch, --crosswalk-csv 를 붙이면 판정이 강해진다")


def check_extra_crossings(s: Seed, rep: Report, base: dict) -> list[dict]:
    rows, notes = rep.section("3. 보행망에 없는 횡단보도와 경로 단축")
    to_add = []
    # (a) 근거 데이터에 있는데 보행망에 없는 횡단보도
    cands, ids = [], set()
    for q, _t, oid in s.osm_with("highway", {"crossing"}, "node") + s.osm_with("crossing", kind="node"):
        if oid not in ids:
            ids.add(oid)
            cands.append((q, f"OSM node {oid}"))
    for q, _t, oid in s.osm_with("footway", {"crossing"}, "way"):
        cands.append((q.interpolate(0.5, normalized=True), f"OSM way {oid}"))
    for q in s.csv_pts or []:
        cands.append((q, "공공데이터"))
    seen = []
    for q, src in cands:
        if s.g.near_crossing(q) or not s.g.near_main(q, 5.0) or any(q.distance(x) < 8 for x in seen):
            continue
        seen.append(q)
        line = crossing_line_at(s, q)
        res = run_routes(s, [*s.manual, line]) if line else None
        if not res:
            rows.append((BAD, f"{src} @ {s.ll(q)}", "보행망에 잇지 못함 (양 끝 10m 안에 인도 없음)"))
            continue
        gains = [f"{n} {base[n][0].length:.0f}→{r[0].length:.0f}m" for n, r in res.items()
                 if r and base.get(n) and base[n][0].length - r[0].length > 5]
        rows.append((OK, f"{src} @ {s.ll(q)}", ("경로 단축: " + "; ".join(gains)) if gains else "어느 경로도 짧아지지 않음"))
        if gains:
            to_add.append({"line": [s.lnglat(Point(c)) for c in line.coords],
                           "memo": f"{src} 근거, verify_seed 자동 추가 {dt.date.today()}"})
    if not cands:
        notes.append("근거 데이터(--fetch, --crosswalk-csv)가 없어 실제 횡단보도 대조는 건너뜀")
    # (b) 가상 횡단 지점 민감도: 돌아가는 경로만
    for name, _pr, start, end, _ in s.route_specs():
        r = base.get(name)
        if not r:
            continue
        straight = Point(start).distance(Point(end))
        if straight == 0 or r[0].length / straight < DETOUR_RATIO:
            continue
        corridor = LineString([start, end]).buffer(HYPO_CORRIDOR_M)
        samples = []
        for road in s.g.main_lines:
            seg = road.intersection(corridor)
            for part in getattr(seg, "geoms", [seg]):
                if part.is_empty or part.geom_type != "LineString":
                    continue
                k = 0.0
                while k <= part.length:
                    p = part.interpolate(k)
                    if not s.g.near_crossing(p.buffer(20)):
                        samples.append(p)
                    k += HYPO_SPACING_M
        best = []
        for p in samples:
            line = crossing_line_at(s, p)
            res = run_routes(s, [*s.manual, line], only={name}) if line else None
            nr = res.get(name) if res else None
            if nr and r[0].length - nr[0].length > 20:
                best.append((nr[0].length, p))
        best.sort(key=lambda x: x[0])
        picked = []
        for length, p in best:
            if all(p.distance(q) > 30 for _, q in picked):
                picked.append((length, p))
            if len(picked) == 3:
                break
        if picked:
            notes.append(f"가정 분석, {name} (지금 {r[0].length:.0f}m, 직선 {straight:.0f}m): 아래 지점에 횡단보도가 있다면")
            notes += [f"- {s.ll(p)} → {length:.0f}m ({r[0].length - length:.0f}m 단축)" for length, p in picked]
            notes.append("  이 지점들을 공공데이터 CSV, 항공사진 판독 결과와 대조하면 된다")
    return to_add


def samples_along(s: Seed, line: LineString, step: float = 2.0):
    n = max(2, int(line.length / step) + 1)
    out = []
    for i in range(n):
        d = min(line.length, i * step)
        p = line.interpolate(d)
        best = None
        for k in s.g.edge_tree.query(p.buffer(3)):
            dd = s.g.edges[k][3].distance(p)
            if dd <= 3 and (best is None or dd < best[0]):
                best = (dd, s.g.edges[k][2])
        out.append((d, p, best[1] if best else None))
    return out


def check_paths(s: Seed, rep: Report, base: dict):
    rows4, notes4 = rep.section("4. 인도와 막힌 길")
    rows5, notes5 = rep.section("5. 계단")
    barriers_w = [(g, t, i) for g, t, i in s.osm_with("barrier", kind="way") if t["barrier"] in BLOCKING_BARRIERS]
    barriers_n = [(g, t, i) for g, t, i in s.osm_with("barrier", kind="node") if t["barrier"] in WARN_NODE_BARRIERS]
    constr = s.osm_with("highway", {"construction"}, "way")
    steps_osm = s.osm_with("highway", {"steps"}, "way")
    label = {0: "보행로", 1: "인도", 2: "횡단보도", 3: "계단", 4: "광장", 5: "오솔길", 6: "구내 도로(인도 없음)", None: "연결선"}
    for name, *_ in s.route_specs():
        r = base.get(name)
        if not r:
            rows4.append((BAD, name, "경로를 만들지 못함"))
            continue
        line = r[0]
        smp = samples_along(s, line)
        share: dict[str, float] = {}
        for (d0, _, k), (d1, _, _) in zip(smp, smp[1:], strict=False):
            share[label[k]] = share.get(label[k], 0) + (d1 - d0)
        comp = ", ".join(f"{k} {v:.0f}m" for k, v in sorted(share.items(), key=lambda x: -x[1]))
        problems = []
        for g, t, i in barriers_w:
            if line.crosses(g) or line.distance(g) < 0.3:
                problems.append(f"OSM way {i} barrier={t['barrier']} 와 교차 @ {s.ll(nearest_points(line, g)[0])}")
        for g, t, i in barriers_n:
            if line.distance(g) < 2:
                problems.append(f"OSM node {i} barrier={t['barrier']} (access={t.get('access', '?')})")
        for g, _t, i in constr:
            if line.distance(g) < 3:
                problems.append(f"OSM way {i} 공사 중 도로 근처")
        if problems:
            rows4.append((BAD, name, "; ".join(problems) + f". 구성: {comp}"))
        elif s.extra is None:
            rows4.append((EST, name, f"구성: {comp}, 차도 위 {r[1]['on_main_road_m']}m. 울타리, 공사는 --fetch 뒤에 검사"))
        else:
            svc = share.get(label[6], 0)
            tail = f". 인도 없는 구내 도로 {svc:.0f}m" if svc >= 30 else ""
            rows4.append((OK if svc < 30 else EST, name, f"OSM barrier, construction 과 교차 없음. 구성: {comp}{tail}"))
        # 계단 구간
        runs, cur = [], []
        for _d, p, k in smp:
            if k == 3:
                cur.append(p)
            elif cur:
                runs.append(cur)
                cur = []
        if cur:
            runs.append(cur)
        if not runs:
            rows5.append((OK, name, "경로에 계단 없음 (OSM highway=steps 기준)"))
            continue
        desc = []
        for run in runs:
            mid = run[len(run) // 2]
            tags = [t for g, t, _ in steps_osm if g.distance(mid) < 3]
            extra = ""
            if tags:
                t = tags[0]
                extra = " " + ", ".join(f"{k}={t[k]}" for k in ("step_count", "ramp", "handrail", "wheelchair", "incline") if k in t)
            desc.append(f"{s.ll(mid)} 약 {max(2, 2 * (len(run) - 1))}m{extra}")
        rows5.append((OK, name, f"계단 {len(runs)}곳: " + "; ".join(desc)))
    notes5.append("경사도는 고도 데이터(DEM)가 없어 계산하지 않았다. 휠체어 가능 여부는 OSM wheelchair, ramp 태그가 있을 때만 나온다")


def visible(s: Seed, p: Point, target) -> tuple[bool, float]:
    q = nearest_points(target.exterior if target.geom_type == "Polygon" else target, p)[0]
    seg = LineString([p, q])
    hit = seg.intersection(s.shrunk)
    if target.geom_type == "Polygon":
        hit = hit.difference(target.buffer(1.5))
    return hit.length < 0.5, seg.length


def check_landmarks(s: Seed, rep: Report, base: dict) -> list[tuple[dict, str | None, list | None]]:
    rows, notes = rep.section("6. 단계 지점과 랜드마크")
    changes = []
    lines = {(pr["place_key"], pr["parking_lot_name"], pr["entrance_name"]): base.get(name)
             for name, pr, *_ in s.route_specs()}
    all_bld = s.osm_bld + [(f["properties"].get("name"), fix(s.poly(f["geometry"]["coordinates"][0])))
                           for f in s.buildings["features"]]
    pois = [(g, t.get("name") or t.get("amenity") or t.get("tourism") or t.get("man_made"), t) for g, t, _ in
            s.osm_with("amenity", kind="node") + s.osm_with("tourism", kind="node") + s.osm_with("historic", kind="node")
            + s.osm_with("man_made", kind="node") + s.osm_with("leisure", kind="node")]
    for st in s.steps:
        wr = st["walk_route"]
        r = lines.get((wr["place_key"], wr["parking_lot_name"], wr["entrance_name"]))
        who = f"{s.places[wr['place_key']]['name']} {wr['parking_lot_name']}→{wr['entrance_name']} {st['step_order']}단계"
        p = Point(s.m(st["location"]["coordinates"]))
        new_loc = None
        off = r[0].distance(p) if r else None
        if off is not None and off > STEP_ON_ROUTE_M:
            q = r[0].interpolate(r[0].project(p))
            new_loc = s.lnglat(q)
            p = q
        # 같은 장소의 랜드마크 중 보이는 것
        cands = []
        for f in s.landmarks["features"]:
            if f["properties"]["place_key"] != wr["place_key"]:
                continue
            lp = Point(s.m(f["geometry"]["coordinates"]))
            target = next((b for _, b in all_bld if b.contains(lp)), lp)
            ok, d = visible(s, p, target)
            if ok and d <= LANDMARK_MAX_M:
                cands.append((d, f["properties"]["key"], f["properties"]["name"]))
        cands.sort()
        new_key = None
        if st.get("landmark_key") is None and cands:
            new_key = cands[0][1]
        # 랜드마크 목록에 없는 새 후보 (이름 있는 건물, OSM 시설)
        fresh = []
        for n, b in all_bld:
            if n and not any(n in c[2] for c in cands):
                ok, d = visible(s, p, b)
                if ok and d <= 25:
                    fresh.append((d, n))
        for g, n, _t in pois:
            ok, d = visible(s, p, g)
            if n and ok and d <= LANDMARK_MAX_M:
                fresh.append((d, n))
        best_by_name: dict[str, float] = {}
        for d, n in fresh:
            best_by_name[n] = min(d, best_by_name.get(n, d))
        fresh = sorted((d, n) for n, d in best_by_name.items())[:3]
        ev = []
        if off is not None and off > STEP_ON_ROUTE_M:
            ev.append(f"지점이 경로에서 {off:.0f}m 벗어남 → 경로 위 {s.ll(p)} 로 옮김(--apply)")
        if cands:
            ev.append("보이는 랜드마크: " + ", ".join(f"{k} {d:.0f}m" for d, k, _ in cands))
        if fresh:
            ev.append("새 후보: " + ", ".join(f"{n} {d:.0f}m" for d, n in fresh))
        cur = st.get("landmark_key")
        if cur and not any(k == cur for _, k, _ in cands):
            ev.append(f"지금 landmark_key={cur} 는 40m 안에서 보이지 않음")
            status = BAD
        elif off is not None and off > STEP_ON_ROUTE_M:
            status = BAD
        elif cands or fresh:
            status = OK
        else:
            status = NONE
            ev.append("40m 안에 보이는 대상 없음, 방향과 거리로만 안내")
        rows.append((status, who, "; ".join(ev)))
        if new_key or new_loc:
            changes.append((st, new_key, new_loc))
    notes.append("시야선 검사는 건물 바닥 모양만 본다. 나무, 차량, 간판 크기는 반영하지 않는다")
    notes.append("camera 가 null 인 단계는 서버(app/domain/camera.py)가 진행 방향으로 기본값을 계산하므로 비워 둬도 된다")
    return changes


def check_floors(s: Seed, rep: Report) -> dict:
    rows, notes = rep.section("7. 건물 층수")
    osm_b = s.osm_with("building", kind="way")
    found = {}
    for f in s.buildings["features"]:
        pr = f["properties"]
        if not pr.get("is_target"):
            continue
        poly = fix(s.poly(f["geometry"]["coordinates"][0]))
        match = max(((iou(poly, g), t, i) for g, t, i in osm_b if g.geom_type == "Polygon"), default=None, key=lambda x: x[0])
        who = f"{pr['name']} ({s.places[pr['place_key']]['name']} 목적 건물)"
        if s.extra is None:
            rows.append((NONE, who, "--fetch 로 OSM 최신 태그를 받아야 판정 가능"))
            continue
        if not match or match[0] < 0.6:
            rows.append((NONE, who, "OSM 최신 데이터에서 같은 건물을 찾지 못함"))
            continue
        _, t, i = match
        lv, h = t.get("building:levels"), t.get("height")
        if lv or h:
            found[pr["name"]] = (lv, h)
            rows.append((OK, who, f"OSM way {i} building:levels={lv}, height={h}"))
        else:
            rows.append((NONE, who, f"OSM way {i} 에 층수, 높이 태그 없음"))
    with_lv = sum(1 for _, t, _ in osm_b if "building:levels" in t or "height" in t)
    if s.extra:
        notes.append(f"영역 안 OSM 건물 {len(osm_b)}동 중 층수나 높이가 있는 건물 {with_lv}동")
    notes.append("OSM 에 없으면 건축물대장 표제부로 채운다: python -m scripts.fill_floors <seed_dir> --fetch (DATA_GO_KR_KEY), "
                 "결과는 floors_report.md")
    return found


def check_parking(s: Seed, rep: Report) -> list:
    rows, notes = rep.section("8. 주차장")
    osm_p = [x for x in s.osm_with("amenity", {"parking"}, "way") if x[0].geom_type == "Polygon"]
    changes, done = [], set()
    for f in s.parking["features"]:
        pr = f["properties"]
        if pr["name"] in done or not pr.get("area"):
            continue
        done.add(pr["name"])
        area = fix(s.poly(pr["area"]["coordinates"][0]))
        est = round(area.area / PARKING_M2_PER_SPACE)
        ev = [f"면적 {area.area:.0f}㎡ → 추정 {est}면"]
        if est > 300:
            ev.append("영역이 지나치게 큼, OSM 영역이 여러 주차장이나 도로를 묶었을 수 있어 parking_lots.geojson 의 area 를 다시 봐야 함")
            rows.append((BAD, pr["name"], "; ".join(ev)))
            continue
        match = max(((iou(area, g), t, i) for g, t, i in osm_p), default=None, key=lambda x: x[0])
        if match and match[0] >= 0.5:
            _, t, i = match
            tg = {k: t[k] for k in ("capacity", "fee", "access", "opening_hours", "name") if k in t}
            if tg:
                ev.insert(0, f"OSM way {i} " + ", ".join(f"{k}={v}" for k, v in tg.items()))
                changes.append((pr["name"], tg))
                rows.append((OK if "capacity" in tg or "fee" in tg else EST, pr["name"], "; ".join(ev)))
                continue
            ev.insert(0, f"OSM way {i} 에 capacity, fee 태그 없음")
        elif s.extra is None:
            ev.insert(0, "OSM 태그는 --fetch 뒤에 대조")
        rows.append((EST, pr["name"], "; ".join(ev)))
    notes.append(f"추정 면수는 1면당 통로 포함 {PARKING_M2_PER_SPACE:.0f}㎡ 로 나눈 값이라 capacity 에는 넣지 않는다. "
                 "요금, 개방 시간은 학교 공지가 근거다")
    return changes


# ---------- 반영 ----------

def apply_changes(s: Seed, crossings: list[dict], step_changes, floors: dict, parking: list):
    wrote = []
    if crossings:
        s.manual_json["crossings"] += crossings
        (s.dir / "osm/manual_crossings.json").write_text(json.dumps(s.manual_json, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        wrote.append(f"manual_crossings.json 횡단보도 {len(crossings)}곳 추가 → build_walk_routes 를 다시 실행하세요")
    if step_changes:
        for st, key, loc in step_changes:
            if key:
                st["landmark_key"] = key
            if loc:
                st["location"]["coordinates"] = loc
        (s.dir / "walk_route_steps.json").write_text(json.dumps(s.steps, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        wrote.append(f"walk_route_steps.json 단계 {len(step_changes)}개 (landmark_key 채움, 경로 밖 지점 옮김)")
    if floors:
        n = 0
        for f in s.buildings["features"]:
            v = floors.get(f["properties"]["name"])
            if not v:
                continue
            lv, h = v
            if lv and str(lv).isdigit():
                f["properties"]["floor_count"] = int(lv)
            if h:
                m = re.match(r"[\d.]+", str(h))
                if m:
                    f["properties"]["height_m"] = float(m.group())
            f["properties"]["description"] = "층수: OSM 태그 (verify_seed)"
            n += 1
        (s.dir / "buildings.geojson").write_text(json.dumps(s.buildings, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        wrote.append(f"buildings.geojson 층수 {n}개 feature")
    if parking:
        tags = dict(parking)
        for f in s.parking["features"]:
            t = tags.get(f["properties"]["name"])
            if not t:
                continue
            if str(t.get("capacity", "")).isdigit():
                f["properties"]["capacity"] = int(t["capacity"])
            if t.get("fee") in ("no", "yes"):
                f["properties"]["is_free"] = t["fee"] == "no"
        (s.dir / "parking_lots.geojson").write_text(json.dumps(s.parking, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        wrote.append("parking_lots.geojson capacity, is_free (OSM 태그가 있는 것만)")
    return wrote


def fetch(seed_dir: Path, net: dict) -> None:
    m = re.search(r"bbox ([\d.]+),([\d.]+),([\d.]+),([\d.]+)", net.get("src", ""))
    if not m:
        raise SystemExit("[중단] walk_network.json 의 src 에서 bbox 를 찾지 못했습니다")
    w, so, e, n = m.groups()
    bb = f"{so},{w},{n},{e}"
    parts = ['node["entrance"]', 'node["highway"="crossing"]', 'node["crossing"]', 'way["footway"="crossing"]',
             'way["highway"="steps"]', 'way["highway"="construction"]', 'way["barrier"]', 'node["barrier"]',
             'way["building"]', 'way["amenity"="parking"]', 'node["amenity"]', 'node["tourism"]', 'node["historic"]',
             'node["man_made"]', 'node["leisure"]']
    q = "[out:json][timeout:90];(" + "".join(f"{p}({bb});" for p in parts) + ");out body geom;"
    body, last = None, None
    for url in OVERPASS:
        try:
            req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(),
                                         headers={"User-Agent": "majunggil-seed-verify/1.0"})
            with urllib.request.urlopen(req, timeout=150) as r:
                body = r.read()
            break
        except Exception as ex:  # noqa: BLE001 (다음 서버로 넘어간다)
            last = ex
            print(f"[경고] {url} 실패: {ex}")
    if body is None:
        raise SystemExit(f"[중단] Overpass 조회 실패: {last}")
    d = json.loads(body)
    d["src"] = f"OpenStreetMap Overpass API, bbox {w},{so},{e},{n}, {dt.date.today()} 조회 (© OpenStreetMap contributors, ODbL)"
    out = seed_dir / "osm/extra_osm.json"
    out.write_text(json.dumps(d, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[저장] {out} (요소 {len(d.get('elements', []))}개)")


CROSSWALK_API = "https://api.data.go.kr/openapi/tn_pubr_public_crosswalk_api"
CROSSWALK_KEEP_M = 3000.0    # 캠퍼스 bbox 에서 이 거리 안의 횡단보도만 저장


def _pick(item: dict, *names: str):
    for k, v in item.items():
        kl = k.lower()
        if any(n == kl or n in k for n in names):
            return v
    return None


def _api_page(key: str, params: dict) -> tuple[list[dict], int]:
    q = urllib.parse.urlencode({"serviceKey": key, "type": "json", **params})
    req = urllib.request.Request(f"{CROSSWALK_API}?{q}", headers={"User-Agent": "majunggil-seed-verify/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read().decode("utf-8", "replace")
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        msg = re.search(r"<(?:returnAuthMsg|errMsg|resultMsg)>([^<]+)<", raw)
        raise SystemExit(f"[중단] API 가 JSON 이 아닌 응답을 줬습니다: {msg.group(1) if msg else raw[:200]}") from None
    resp = d.get("response", d)
    head = resp.get("header", {})
    code = str(head.get("resultCode", "00"))
    if code not in ("00", "0", "03"):        # 03 = 데이터 없음
        raise SystemExit(f"[중단] API 오류 {code}: {head.get('resultMsg')}")
    body = resp.get("body", {}) or {}
    items = body.get("items", []) or []
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):
        items = [items]
    return items, int(body.get("totalCount", 0) or 0)


def fetch_crosswalks(seed_dir: Path, net: dict, sido: str, sigungu: str) -> None:
    import os
    key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not key:
        raise SystemExit("[중단] 환경 변수 DATA_GO_KR_KEY 에 공공데이터포털 인증키를 넣어 주세요")
    key = urllib.parse.unquote(key)          # Encoding 키를 넣어도 한 번만 인코딩되게
    loc = bw.Local(net["o"])
    m = re.search(r"bbox ([\d.]+),([\d.]+),([\d.]+),([\d.]+)", net.get("src", ""))
    w, so, e, n = (float(x) for x in m.groups())
    area = Polygon([loc.m(w, so), loc.m(e, so), loc.m(e, n), loc.m(w, n)]).buffer(CROSSWALK_KEEP_M)
    rows, per = 1000, {}
    for filt in ({"ctprvnNm": sido, "signguNm": sigungu}, {"ctprvnNm": sido}):
        got, page, total = [], 1, None
        while True:
            items, total = _api_page(key, {"pageNo": page, "numOfRows": rows, **filt})
            got += items
            print(f"[조회] {filt} {page}쪽 {len(items)}건 (전체 {total})")
            if not items or page * rows >= total:
                break
            page += 1
        per = filt
        if got:
            break
        print(f"[경고] {filt} 조건 결과 0건, 조건을 넓혀 다시 조회")
    keep = []
    for it in got:
        lat, lng = _pick(it, "latitude", "위도"), _pick(it, "longitude", "경도")
        try:
            lat, lng = float(lat), float(lng)
        except (TypeError, ValueError):
            continue
        if area.contains(Point(loc.m(lng, lat))):
            keep.append({"lat": lat, "lng": lng, "no": _pick(it, "crslkmanageno", "관리번호"),
                         "kind": _pick(it, "crslkknd", "종류"), "road": _pick(it, "rdnm", "도로명"),
                         "base_date": _pick(it, "referencedate", "기준일자")})
    out = {"src": f"공공데이터포털 전국횡단보도표준데이터 API, 조건 {per}, {dt.date.today()} 조회 (이용허락범위 제한 없음)",
           "items": keep}
    (seed_dir / "public_crosswalks.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[저장] {seed_dir / 'public_crosswalks.json'} (전체 {len(got)}건 중 캠퍼스 {CROSSWALK_KEEP_M / 1000:.0f}km 안 {len(keep)}건)")
    if got and not keep:
        print("[경고] 캠퍼스 근처 횡단보도가 0건입니다. 교내 도로는 지자체 관리 대상이 아니라 빠져 있을 수 있습니다")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("seed_dir", nargs="?", default="scripts/seeds/gnu-gajwa")
    ap.add_argument("--fetch", action="store_true", help="OSM Overpass 에서 태그 데이터를 받아 osm/extra_osm.json 에 저장")
    ap.add_argument("--crosswalk-csv", help="공공데이터 횡단보도 CSV (위도, 경도 열)")
    ap.add_argument("--fetch-crosswalks", action="store_true",
                    help="공공데이터포털 전국횡단보도표준데이터 API 로 받아 public_crosswalks.json 저장 (DATA_GO_KR_KEY 필요)")
    ap.add_argument("--sido", default="경상남도", help="--fetch-crosswalks 시도명 (기본 경상남도)")
    ap.add_argument("--sigungu", default="진주시", help="--fetch-crosswalks 시군구명 (기본 진주시)")
    ap.add_argument("--apply", action="store_true", help="근거가 있는 값만 시드 파일에 반영")
    a = ap.parse_args()
    seed_dir = Path(a.seed_dir)
    if a.fetch:
        fetch(seed_dir, jload(seed_dir / "osm/walk_network.json"))
    if a.fetch_crosswalks:
        fetch_crosswalks(seed_dir, jload(seed_dir / "osm/walk_network.json"), a.sido, a.sigungu)
    s = Seed(seed_dir, a.crosswalk_csv)
    base = {name: None for name, *_ in s.route_specs()}
    for name, _pr, _st, _en, line in s.route_specs():
        base[name] = (line, bw.check_path(line, s.g, s.shrunk))   # 지금 walk_routes.geojson 의 선 그대로 검사
    rep = Report()
    check_entrances(s, rep)
    check_unmarked(s, rep, base)
    crossings = check_extra_crossings(s, rep, base)
    check_paths(s, rep, base)
    step_changes = check_landmarks(s, rep, base)
    floors = check_floors(s, rep)
    parking = check_parking(s, rep)
    rep.console()
    srcs = ["2026-11-11 OSM 스냅샷(osm/*.json)"] + ([s.extra["src"]] if s.extra else []) + \
           ([f"공공데이터 횡단보도 {len(s.csv_pts)}점 ({a.crosswalk_csv or s.pub_src})"] if s.csv_pts is not None else [])
    header = [f"# 시드 자동 검사 결과 ({seed_dir.name})", "",
              f"생성: {dt.datetime.now():%Y-%m-%d %H:%M}, `python -m scripts.verify_seed`", "",
              "사용한 데이터: " + "; ".join(srcs), "",
              "판정: 확인됨(데이터 근거 있음), 추정(기하 검사만 통과 또는 계산값), 확인 필요(검사에 걸림), 데이터 없음"]
    if a.apply:
        wrote = apply_changes(s, crossings, step_changes, floors, parking)
        header += ["", "## 반영한 내용 (--apply)", ""] + [f"- {w}" for w in wrote or ["반영할 근거가 없음"]]
        for w in wrote or ["반영할 근거가 없음"]:
            print(f"[반영] {w}")
    (seed_dir / "verify_report.md").write_text(rep.md(header) + "\n", encoding="utf-8")
    counts = {}
    for _, rows, _ in rep.sections:
        for r in rows:
            counts[r[0]] = counts.get(r[0], 0) + 1
    print("\n[요약] " + ", ".join(f"{k} {v}" for k, v in counts.items()) + f" → {seed_dir / 'verify_report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
