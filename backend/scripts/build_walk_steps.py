"""경로 선과 보행망 데이터로 단계(지점, 문장, 랜드마크)를 만든다 (DA-03 단계 문장 자동 작성).

사용법 (backend 디렉터리에서, DB 필요 없음):
    python -m scripts.build_walk_steps scripts/seeds/gnu-gajwa           # walk_route_steps.json 다시 쓰기
    python -m scripts.build_walk_steps scripts/seeds/gnu-gajwa --check   # 쓰지 않고 결과만 출력
    python -m scripts.build_walk_steps scripts/seeds/gnu-gajwa --check --diff   # 지금 파일의 문장과 나란히 출력

순서: build_walk_routes 로 경로를 만든 뒤 이 스크립트를 돌리고, load_seed 로 적재한다.
경로 선이 바뀔 때마다 다시 돌리면 단계 지점이 늘 새 선 위에 놓인다.

입력 (모두 시드 폴더 안. 현장 조사 자료 없이 지금 데이터만 쓴다)
- walk_routes.geojson : 경로 선
- osm/walk_network.json, osm/buildings_osm.json, buildings.geojson : 길 종류(계단, 횡단보도, 광장, 구내 도로), 차도, 건물
- entrances.geojson, places.json : 도착 입구와 건물 이름
- landmarks.geojson : 문장에 넣고 landmark_key 로 잇는 대상

만드는 방법
1. 경로를 1m 간격으로 잘라 지점마다 2m 안의 가장 가까운 보행망 구간 종류를 붙인다 (없으면 광장 안인지, 아니면 연결선)
2. 사건을 찾는다: 방향 전환(35도 이상), 계단, 횡단보도, 표시 없는 차도 횡단, 광장 진입
3. 15m 안에 붙은 사건은 한 단계로 묶는다. 단계 지점은 묶음의 첫 사건 위치라 경로 위에 놓인다 (30m 검사 통과)
4. 문장: "[하는 일] [대상]을 [왼쪽]에 두고 약 Nm 걷기". 방향은 "오른쪽(서쪽)"처럼 상대 방향과 방위를 같이 적는다
5. landmark_key: 단계 지점 40m 안에서 건물에 가리지 않는 landmarks.geojson 대상 중 가장 가까운 것
6. camera: 기본 null (서버가 자동 계산). 지금 파일에 같은 경로, 10m 안 단계의 camera 값이 있으면 이어 받는다

데이터에 없는 정보(간판, 색, 출입문 모양)는 쓰지 않는다. 문장의 모든 요소는 OSM 태그, 시드 파일, 기하 계산에서 나온다.
"""
import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from app.domain.steps import MAX_STEPS, MIN_STEPS, check_steps
from scripts.build_walk_routes import SERVICE, Graph, _pairs, load_world

SAMPLE_M = 1.0            # 경로 자르는 간격
EDGE_SNAP_M = 2.0         # 이 안의 보행망 구간 종류를 붙인다
TURN_DEG = 35.0           # 이 각도 이상 바뀌면 방향 전환
HEADING_WINDOW_M = 10.0   # 방향 전환 앞뒤 방향을 재는 길이
CLUSTER_M = 15.0          # 앞 사건이 끝난 뒤 이 안에 오는 사건은 한 단계로 묶는다
CLUSTER_SPAN_M = 40.0     # 한 단계가 덮는 최대 길이
REF_MIN_LEG_M = 15.0      # 이보다 짧은 다리에는 기준 대상을 붙이지 않는다
STEPS_MIN_M = 2.0         # 계단 구간 최소 길이
CROSSING_MIN_M = 3.0      # 횡단보도 선 구간 최소 길이
PLAZA_MIN_M = 15.0        # 광장 구간 최소 길이
SERVICE_MIN_M = 25.0      # 다리 안 구내 도로가 이보다 길면 차 주의를 붙인다
LANDMARK_MAX_M = 40.0     # verify_seed 와 같은 기준
BUILDING_REF_M = 20.0     # 건물 이름을 기준 대상으로 쓰는 거리
CAMERA_KEEP_M = 10.0
MAX_PER_ROUTE = 12        # 서버 상한(30)보다 작게. 안내가 잘게 쪼개지지 않도록
COMPASS = ["북", "북동", "동", "남동", "남", "남서", "서", "북서"]


# ---------- 문장 도구 ----------

def _jong(word: str) -> int | None:
    """마지막 글자의 받침 번호 (0 = 받침 없음). 한글이 아니면 None."""
    ch = word.rstrip()[-1:]
    if not ch or not "가" <= ch <= "힣":
        return None
    return (ord(ch) - 0xAC00) % 28


def eul(word: str) -> str:
    return word + ("을" if _jong(word) else "를")


def euro(word: str) -> str:
    j = _jong(word)
    return word + ("으로" if j and j != 8 else "로")   # 8 = ㄹ 받침


def bearing(a, b) -> float:
    return math.degrees(math.atan2(b[0] - a[0], b[1] - a[1])) % 360


def compass(deg: float) -> str:
    return COMPASS[int(((deg + 22.5) % 360) // 45)]


def turn_delta(h0: float, h1: float) -> float:
    """+ 는 오른쪽(시계 방향), - 는 왼쪽."""
    return (h1 - h0 + 180) % 360 - 180


def turn_phrase(h_in: float, h_out: float) -> str | None:
    d = turn_delta(h_in, h_out)
    lr = "오른쪽" if d > 0 else "왼쪽"
    to = f"{lr}({compass(h_out)}쪽)으로"
    if abs(d) < TURN_DEG:
        return None
    if abs(d) < 60:
        return f"살짝 {to} 틀어"
    if abs(d) <= 150:
        return f"{to} 꺾어"
    return f"뒤로 돌아 {compass(h_out)}쪽으로"


def dist_phrase(m: float) -> str:
    return "조금" if m < 15 else f"약 {int(round(m / 10.0)) * 10}m"


# ---------- 세계(경로 주변 데이터) ----------

@dataclass
class Ref:
    name: str
    geom: object            # Point 또는 Polygon (미터 좌표)
    key: str | None = None  # landmarks.geojson key (건물 이름이면 None)


@dataclass
class World:
    loc: object
    g: Graph
    shrunk: object
    areas: list
    landmarks: dict          # place_key → [Ref]
    buildings: list          # [Ref] 한글 이름 있는 건물
    targets: dict            # place_key → (이름, Polygon)
    entrances: dict


def load(seed_dir: Path) -> World:
    net, loc, nodes, polys, shrunk, manual = load_world(seed_dir)
    g = Graph(net, nodes, shrunk, manual)
    areas = [Polygon([g.nodes[i] for i in ring]).buffer(0.5) for ring in net["areas"]]

    named: dict[str, list] = {}
    bfc = json.loads((seed_dir / "buildings.geojson").read_text(encoding="utf-8"))["features"]
    targets = {}
    places = {p["key"]: p for p in json.loads((seed_dir / "places.json").read_text(encoding="utf-8"))}
    for f in bfc:
        pr = f["properties"]
        poly = Polygon([loc.m(*c) for c in f["geometry"]["coordinates"][0]])
        if pr.get("is_target"):
            targets[pr["place_key"]] = (places[pr["place_key"]]["name"], poly)
        if pr.get("name") and _jong(pr["name"]) is not None:
            named.setdefault(pr["name"], []).append(poly)
    bosm = json.loads((seed_dir / "osm/buildings_osm.json").read_text(encoding="utf-8"))
    for b in bosm["buildings"]:
        n = b.get("n")
        if n and _jong(n) is not None:
            named.setdefault(n, []).append(Polygon([loc.m(*p) for p in _pairs(b["g"], bosm["o"], bosm["u"])]))
    buildings = []
    for n, ps in named.items():
        geom = unary_union([p if p.is_valid else p.buffer(0) for p in ps])
        buildings.append(Ref(n, geom))

    all_polys = [r.geom for r in buildings] + [p for p in polys if p.is_valid]
    landmarks: dict[str, list] = {}
    for f in json.loads((seed_dir / "landmarks.geojson").read_text(encoding="utf-8"))["features"]:
        pr = f["properties"]
        pt = Point(loc.m(*f["geometry"]["coordinates"]))
        geom = next((p for p in all_polys if p.contains(pt)), pt)   # 건물 안 점이면 건물 전체를 대상으로
        landmarks.setdefault(pr["place_key"], []).append(Ref(pr["name"], geom, pr["key"]))

    ents = {(f["properties"]["place_key"], f["properties"]["name"]): Point(loc.m(*f["geometry"]["coordinates"]))
            for f in json.loads((seed_dir / "entrances.geojson").read_text(encoding="utf-8"))["features"]}
    return World(loc, g, shrunk, areas, landmarks, buildings, targets, ents)


def visible(w: World, p: Point, geom) -> tuple[bool, float]:
    """p 에서 대상까지 곧은 선이 다른 건물을 지나지 않는가 (verify_seed 와 같은 방법)."""
    q = geom if geom.geom_type == "Point" else geom.exterior.interpolate(geom.exterior.project(p)) \
        if geom.geom_type == "Polygon" else geom.boundary.interpolate(geom.boundary.project(p))
    seg = LineString([p, q])
    hit = seg.intersection(w.shrunk)
    if geom.geom_type != "Point":
        hit = hit.difference(geom.buffer(1.5))
    return hit.length < 0.5, seg.length


# ---------- 경로 분석 ----------

@dataclass
class Event:
    s: float
    kind: str               # turn, steps, crossing, unmarked, plaza
    s_end: float | None = None

    @property
    def end(self) -> float:
        return self.s if self.s_end is None else self.s_end


@dataclass
class Cluster:
    events: list = field(default_factory=list)
    start: bool = False
    arrive: bool = False
    base: float = 0.0       # 사건이 없을 때 위치 (출발 0, 도착 경로 끝)

    @property
    def s0(self) -> float:
        return min(e.s for e in self.events) if self.events else self.base

    @property
    def s1(self) -> float:
        return max(e.end for e in self.events) if self.events else self.base

    def has(self, *kinds) -> bool:
        return any(e.kind in kinds for e in self.events)


class Route:
    def __init__(self, w: World, coords: list):
        self.w = w
        self.line = LineString([w.loc.m(*c) for c in coords])
        self.L = self.line.length
        n = max(2, int(self.L / SAMPLE_M) + 1)
        self.ss = [min(self.L, i * SAMPLE_M) for i in range(n)]
        self.kinds = [self._kind(self.pt(s)) for s in self.ss]

    def pt(self, s: float) -> Point:
        return self.line.interpolate(max(0.0, min(self.L, s)))

    def heading(self, a: float, b: float) -> float:
        a, b = max(0.0, a), min(self.L, b)
        if b - a < 0.5:
            a, b = max(0.0, b - 1.0), min(self.L, a + 1.0)
        pa, pb = self.pt(a), self.pt(b)
        return bearing((pa.x, pa.y), (pb.x, pb.y))

    def _kind(self, p: Point) -> int:
        g = self.w.g
        best = None
        for k in g.edge_tree.query(p.buffer(EDGE_SNAP_M)):
            d = g.edges[k][3].distance(p)
            if d <= EDGE_SNAP_M and (best is None or d < best[0]):
                best = (d, g.edges[k][2])
        if best:
            return best[1]
        if any(a.contains(p) for a in self.w.areas):
            return 4
        return -1   # 출발점, 입구 연결선

    def runs(self, kind: int, min_len: float) -> list[tuple[float, float]]:
        out, start, last = [], None, None
        for s, k in zip(self.ss, self.kinds, strict=True):
            if k == kind:
                if start is None:
                    start = s
                last = s
            elif start is not None and s - last > 2 * SAMPLE_M:
                if last - start >= min_len:
                    out.append((start, last))
                start = None
        if start is not None and last - start >= min_len:
            out.append((start, last))
        return out

    def length_of(self, kind: int, a: float, b: float) -> float:
        return sum(SAMPLE_M for s, k in zip(self.ss, self.kinds, strict=True) if a <= s < b and k == kind)

    def events(self) -> list[Event]:
        ev: list[Event] = []
        for a, b in self.runs(3, STEPS_MIN_M):
            ev.append(Event(a, "steps", b))
        for a, _b in self.runs(4, PLAZA_MIN_M):
            ev.append(Event(a, "plaza"))
        # 횡단: 횡단보도 선 구간 + 차도와 만나는 점
        cross = [Event(a, "crossing", b) for a, b in self.runs(2, CROSSING_MIN_M)]
        g = self.w.g
        for i in g.main_tree.query(self.line):
            road = g.main_lines[i]
            if not self.line.crosses(road):
                continue
            inter = self.line.intersection(road)
            pts = [inter] if inter.geom_type == "Point" else [p for p in getattr(inter, "geoms", []) if p.geom_type == "Point"]
            for p in pts:
                s = self.line.project(p)
                kind = "crossing" if g.near_crossing(p) else "unmarked"
                cross.append(Event(max(0.0, s - 4.0), kind, min(self.L, s + 4.0)))
        cross.sort(key=lambda e: e.s)
        merged: list[Event] = []
        for e in cross:
            if merged and e.s - merged[-1].end <= 6.0:
                m = merged[-1]
                m.s_end = max(m.end, e.end)
                if e.kind == "crossing":
                    m.kind = "crossing"
            else:
                merged.append(e)
        ev += merged
        # 방향 전환: 단순화한 선의 꼭짓점마다 앞뒤 10m 방향을 비교
        turns = []
        for c in list(self.line.simplify(2.5).coords)[1:-1]:
            s = self.line.project(Point(c))
            d = turn_delta(self.heading(s - HEADING_WINDOW_M, s), self.heading(s, s + HEADING_WINDOW_M))
            if abs(d) >= TURN_DEG:
                turns.append((s, abs(d)))
        kept: list[tuple[float, float]] = []
        for s, d in turns:
            if kept and s - kept[-1][0] < 8.0:
                if d > kept[-1][1]:
                    kept[-1] = (s, d)
            else:
                kept.append((s, d))
        ev += [Event(s, "turn") for s, _ in kept]
        return sorted(ev, key=lambda e: e.s)

    def clusters(self) -> list[Cluster]:
        cs = [Cluster(start=True)]
        for e in self.events():
            if e.s < CLUSTER_M:                       # 출발 직후 사건은 첫 단계에 넣는다
                cs[0].events.append(e)
            elif len(cs) > 1 and e.s - cs[-1].s1 <= CLUSTER_M and e.s - cs[-1].s0 <= CLUSTER_SPAN_M:
                cs[-1].events.append(e)
            else:
                cs.append(Cluster([e]))
        # 도착 직전 사건은 마지막 단계에 넣는다
        arrive = Cluster(arrive=True, base=self.L)
        while len(cs) > 1 and cs[-1].s0 > self.L - CLUSTER_M:
            arrive.events = cs.pop().events + arrive.events
        cs.append(arrive)
        # 너무 많으면 방향 전환만 있는 묶음부터 각도가 작은 순서로 뺀다
        while len(cs) > MAX_PER_ROUTE:
            cand = [(abs(self.net_turn(c, cs)), i) for i, c in enumerate(cs)
                    if not c.start and not c.arrive and not c.has("steps", "crossing", "unmarked", "plaza")]
            if not cand:
                break
            cs.pop(min(cand)[1])
        return cs

    def heading_in(self, c: Cluster) -> float:
        """단계에 들어올 때 방향. 횡단이 있으면 건너는 방향을 기준으로 삼는다 ("건넌 뒤 오른쪽")."""
        cr = [e for e in c.events if e.kind in ("crossing", "unmarked")]
        if cr:
            return self.heading(cr[-1].s, cr[-1].end)
        return self.heading(c.s0 - HEADING_WINDOW_M, c.s0)

    def net_turn(self, c: Cluster, cs: list[Cluster]) -> float:
        i = cs.index(c)
        nxt = cs[i + 1].s0 if i + 1 < len(cs) else self.L
        return turn_delta(self.heading_in(c), self.heading(c.s1, min(c.s1 + HEADING_WINDOW_M, nxt)))

    def step_point(self, s: float) -> Point:
        """경로 위 점. 건물 벽 1m 안쪽이면 경로를 따라 물러난다."""
        for back in range(0, 30):
            p = self.pt(s - back)
            if not self.w.shrunk.contains(p):
                return p
        return self.pt(s)


# ---------- 기준 대상(랜드마크, 건물) ----------

def side_word(h: float, p: Point, geom) -> str | None:
    q = geom if geom.geom_type == "Point" else geom.exterior.interpolate(geom.exterior.project(p)) \
        if geom.geom_type == "Polygon" else geom.boundary.interpolate(geom.boundary.project(p))
    if p.distance(q) < 1.0:
        return None
    d = turn_delta(h, bearing((p.x, p.y), (q.x, q.y)))
    if 40 <= abs(d) <= 140:
        return "오른쪽" if d > 0 else "왼쪽"
    return None


def norm(name: str) -> str:
    """"중앙도서관 건물"과 "중앙도서관"을 같은 대상으로 본다."""
    return name.removesuffix(" 건물").strip()


def pick_ref(r: Route, place_key: str, a: float, b: float, avoid: set) -> tuple[Ref, str] | None:
    """다리 [a, b] 옆에 보이는 대상과 방향. 랜드마크를 건물 이름보다 먼저 쓴다."""
    w = r.w
    pools = [(w.landmarks.get(place_key, []), LANDMARK_MAX_M), (w.buildings, BUILDING_REF_M)]
    for pool, limit in pools:
        best = None
        for ref in pool:
            s = a
            while s <= b:
                p = r.pt(s)
                if p.distance(ref.geom) <= limit:
                    ok, d = visible(w, p, ref.geom)
                    side = side_word(r.heading(s - 3, s + 3), p, ref.geom)
                    if ok and side and norm(ref.name) not in avoid:
                        if best is None or d < best[0]:
                            best = (d, ref, side)
                        break
                s += 3.0
        if best:
            return best[1], best[2]
    return None


def step_landmark(w: World, place_key: str, p: Point, prefer: Ref | None) -> str | None:
    cands = []
    for ref in w.landmarks.get(place_key, []):
        ok, d = visible(w, p, ref.geom)
        if ok and d <= LANDMARK_MAX_M:
            cands.append((d, ref.key))
    if prefer and prefer.key and any(k == prefer.key for _, k in cands):
        return prefer.key
    return min(cands)[1] if cands else None


# ---------- 문장 ----------

ACTION = {
    "steps": "계단을 지나",
    "plaza": "광장으로 들어가",
    "crossing": "횡단보도로 {dir}쪽 건너편으로 건넌 뒤",
    "unmarked": "횡단보도 표시가 없는 곳이라 좌우를 살피고 {dir}쪽 건너편으로 건넌 뒤",
}


def instruction(r: Route, cs: list[Cluster], i: int, place_key: str, entrance: str, used: set) -> tuple[str, Ref | None]:
    c = cs[i]
    parts = ["주차장에서 나와"] if c.start else []
    seen = set()
    for e in c.events:
        if e.kind in ACTION and e.kind not in seen:
            parts.append(ACTION[e.kind].format(dir=compass(r.heading(e.s, e.end))))
            seen.add(e.kind)
    nxt = cs[i + 1].s0 if i + 1 < len(cs) else r.L
    a = c.s1
    h_out = r.heading(a, min(a + HEADING_WINDOW_M, nxt if nxt > a + 1 else r.L))
    if not c.start:
        tp = turn_phrase(r.heading_in(c), h_out)
        if tp:
            parts.append(tp)

    if c.arrive:
        name, poly = r.w.targets[place_key]
        ref = pick_ref(r, place_key, a, r.L, used | {norm(name)})
        ref_txt = f"{eul(ref[0].name)} {ref[1]}에 두고 " if ref else ""
        h_end = r.heading(r.L - HEADING_WINDOW_M, r.L)
        side = side_word(h_end, r.pt(max(0.0, r.L - 3.0)), poly)
        where = f"{side}에 보이는 " if side else ""
        if ref_txt and where:
            ref_txt = ref_txt.rstrip() + " 걷다가 "
        parts.append(f"{ref_txt}{where}{name} {euro(entrance)} 들어가기")
        return " ".join(parts), (ref[0] if ref else None)

    leg = nxt - a
    ref = pick_ref(r, place_key, a, nxt, used) if leg >= REF_MIN_LEG_M else None
    ref_txt = f"{eul(ref[0].name)} {ref[1]}에 두고 " if ref else ""
    tail = f"{dist_phrase(leg)} 걷기"
    if not any(p.endswith("꺾어") or p.endswith("틀어") or p.startswith("뒤로") for p in parts):
        cr = [e for e in c.events if e.kind in ("crossing", "unmarked")]
        to = compass(r.heading(a, nxt))
        if cr and compass(r.heading(cr[-1].s, cr[-1].end)) == to:
            tail = f"그대로 {tail}"          # "동쪽 건너편으로 건넌 뒤 동쪽으로" 반복을 피한다
        else:
            tail = f"{to}쪽으로 {tail}"
    parts.append(ref_txt + tail)
    text = " ".join(parts)
    if r.length_of(SERVICE, a, nxt) >= SERVICE_MIN_M:
        text += " (인도가 없는 구내 도로라 차 주의)"
    return text, (ref[0] if ref else None)


# ---------- 실행 ----------

def build_steps(seed_dir: Path) -> tuple[list[dict], list[str]]:
    w = load(seed_dir)
    routes = json.loads((seed_dir / "walk_routes.geojson").read_text(encoding="utf-8"))["features"]
    old_path = seed_dir / "walk_route_steps.json"
    old = json.loads(old_path.read_text(encoding="utf-8")) if old_path.exists() else []
    out, problems = [], []
    for f in routes:
        pr = f["properties"]
        wr = {"place_key": pr["place_key"], "parking_lot_name": pr["parking_lot_name"], "entrance_name": pr["entrance_name"]}
        r = Route(w, f["geometry"]["coordinates"])
        cs = r.clusters()
        used: set[str] = set()
        steps = []
        for i, c in enumerate(cs):
            text, ref = instruction(r, cs, i, pr["place_key"], pr["entrance_name"], used)
            used = {norm(ref.name)} if ref else set()
            p = r.step_point(c.s0 if c.events or c.start else max(0.0, r.L - 2.0))
            camera = None
            for o in old:
                if o["walk_route"] == wr and o.get("camera"):
                    q = Point(w.loc.m(*o["location"]["coordinates"]))
                    if q.distance(p) <= CAMERA_KEEP_M:
                        camera = o["camera"]
                        break
            steps.append({
                "walk_route": wr,
                "step_order": i + 1,
                "instruction": text,
                "landmark_key": step_landmark(w, pr["place_key"], p, ref),
                "location": {"type": "Point", "coordinates": list(w.loc.ll(p.x, p.y))},
                "camera": camera,
            })
        name = f"{pr['parking_lot_name']} → {pr['place_key']} {pr['entrance_name']}"
        for v in check_steps([s["step_order"] for s in steps], [s["instruction"] for s in steps]):
            problems.append(f"{name}: {v.field} {v.message}")
        for s in steps:
            q = Point(w.loc.m(*s["location"]["coordinates"]))
            if r.line.distance(q) > 30:
                problems.append(f"{name} {s['step_order']}단계: 경로에서 {r.line.distance(q):.1f}m")
            if w.shrunk.contains(q):
                problems.append(f"{name} {s['step_order']}단계: 건물 안")
        out += steps
    assert MIN_STEPS <= 2 and MAX_PER_ROUTE <= MAX_STEPS
    return out, problems


def main(seed_dir: Path, write: bool, diff: bool) -> int:
    steps, problems = build_steps(seed_dir)
    path = seed_dir / "walk_route_steps.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    cur = None
    for s in steps:
        wr = s["walk_route"]
        key = (wr["place_key"], wr["parking_lot_name"], wr["entrance_name"])
        if key != cur:
            cur = key
            print(f"\n[{wr['place_key']}] {wr['parking_lot_name']} → {wr['entrance_name']}")
            if diff:
                print("  지금 파일:")
                for o in old:
                    if o["walk_route"] == wr:
                        print(f"    {o['step_order']}. {o['instruction']}")
                print("  새 문장:")
        lm = f" [{s['landmark_key']}]" if s["landmark_key"] else ""
        print(f"    {s['step_order']}. {s['instruction']}{lm}")
    for p in problems:
        print(f"[실패] {p}")
    if problems:
        return 1
    if write:
        path.write_text(json.dumps(steps, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"\n[저장] {path} ({len(steps)}단계)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("seed_dir", nargs="?", default="scripts/seeds/gnu-gajwa")
    ap.add_argument("--check", action="store_true", help="파일을 쓰지 않고 결과만 출력")
    ap.add_argument("--diff", action="store_true", help="지금 파일의 문장을 함께 출력")
    a = ap.parse_args()
    sys.exit(main(Path(a.seed_dir), write=not a.check, diff=a.diff))
