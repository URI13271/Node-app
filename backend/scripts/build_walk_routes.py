"""보행망 위에서 도보 경로를 다시 만든다 (보행 경로 적용, API 명세서 v1.2 부록 C).

사용법 (backend 디렉터리에서, DB 필요 없음):
    python -m scripts.build_walk_routes scripts/seeds/gnu-gajwa            # walk_routes.geojson 다시 쓰기
    python -m scripts.build_walk_routes scripts/seeds/gnu-gajwa --check    # 쓰지 않고 검사만

입력
- osm/walk_network.json      : OSM 보행망 (인도, 보행로, 횡단보도, 계단, 광장, 구내 도로, 차도)
- osm/buildings_osm.json     : OSM 건물 바닥 모양 (주변 건물 포함 전체)
- osm/manual_crossings.json  : 현장 조사로 확인한 횡단보도 (OSM 에 없는 것). 없으면 건너뛴다.
- buildings.geojson, entrances.geojson, walk_routes.geojson (출발점 = 각 경로의 첫 좌표, 그대로 유지)

길 종류와 규칙
- 보행로: 인도(sidewalk), 보행로(footway), 횡단보도(crossing), 계단(steps, 1.5배), 광장(pedestrian), 오솔길(path)
- 구내 도로(service): 주차장 통로, 건물 사이 길. 인도가 따로 없으므로 걸을 수 있되 2배. 아무 데서나 건너도 된다.
- 차도(residential 등): 인도가 따로 그려진 큰 길. 차도 위를 따라 걷는 선은 만들지 않고, 건너는 것은 횡단보도 지점에서만.
  보행로가 횡단보도가 아닌 차도 지점에 닿아 있으면 그 지점을 지날 때 300m 를 더해 사실상 쓰지 않게 한다.
  OSM 횡단보도 점이 차도 한쪽 인도에만 이어져 있으면, 건너편 12m 안의 보행로에 이어 준다.
  보행로가 횡단보도 표시 없이 차도에 끝나는 점(표시 없는 횡단 지점)도 같은 방법으로 잇되 300m 벌점을 둔다.
  다른 길이 전혀 없을 때만 쓰이며, 쓰인 경로는 [확인 필요]로 출력하고 현장 조사 목록에 올린다.
- 출발점과 입구는 60m 안의 보행로나 구내 도로 위 가장 가까운 점에 곧게 잇는다.
  건물을 지나거나 차도를 가로지르는 연결선, 차도에 붙은 점(횡단보도 5m 밖)으로의 연결선은 쓰지 않는다.

통과 기준 (서버 검사와 같다)
- 건물 안 길이 0m (벽에서 1m 안쪽부터 건물 안으로 본다)
- 차도를 가로지르는 곳은 모두 횡단보도 5m 안

출력은 기존 walk_routes.geojson 형식 그대로다. 사전 계산 경로 원칙(MVP 범위 정의서)은 바뀌지 않는다.
"""
import argparse
import heapq
import json
import math
import sys
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

KIND = {0: "footway", 1: "sidewalk", 2: "crossing", 3: "steps", 4: "pedestrian", 5: "path", 6: "service", 7: "road"}
SERVICE, MAIN = 6, 7
FACTOR = {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.5, 4: 1.0, 5: 1.1, SERVICE: 2.0}
AREA_FACTOR = 1.0          # 광장 안 가로지르기
CONNECTOR_FACTOR = 1.3     # 출발점, 입구 연결선
MAIN_ROAD_PENALTY_M = 300.0
CONNECTOR_MAX_M = 60.0
CONNECTOR_K = 20
WALL_TOLERANCE_M = 1.0     # 서버 검사(crosses_building)와 같은 값
CROSSING_NEAR_M = 5.0
CROSSING_LINK_M = 12.0
WALK_SPEED_M_PER_MIN = 67.0   # 시속 4km

LAT0 = 35.153
KX = 111320.0 * math.cos(math.radians(LAT0))
KY = 110574.0


class NoRoute(Exception):
    pass


class Local:
    """위경도 ↔ 평면 미터 (캠퍼스 1km 안에서는 오차 0.1% 수준)."""

    def __init__(self, o: list[float]):
        self.lng0, self.lat0 = o

    def m(self, lng: float, lat: float) -> tuple[float, float]:
        return ((lng - self.lng0) * KX, (lat - self.lat0) * KY)

    def ll(self, x: float, y: float) -> tuple[float, float]:
        return (round(self.lng0 + x / KX, 6), round(self.lat0 + y / KY, 6))


def _pairs(flat: list[int], o: list[float], u: float) -> list[tuple[float, float]]:
    return [(o[0] + flat[i] * u, o[1] + flat[i + 1] * u) for i in range(0, len(flat), 2)]


def load_world(seed_dir: Path):
    net = json.loads((seed_dir / "osm/walk_network.json").read_text(encoding="utf-8"))
    bld = json.loads((seed_dir / "osm/buildings_osm.json").read_text(encoding="utf-8"))
    loc = Local(net["o"])
    nodes = [loc.m(*p) for p in _pairs(net["nodes"], net["o"], net["u"])]

    polys = []
    for b in bld["buildings"]:
        polys.append(Polygon([loc.m(*p) for p in _pairs(b["g"], bld["o"], bld["u"])]))
    for f in json.loads((seed_dir / "buildings.geojson").read_text(encoding="utf-8"))["features"]:
        polys.append(Polygon([loc.m(*p) for p in f["geometry"]["coordinates"][0]]))
    shrunk = unary_union([p.buffer(-WALL_TOLERANCE_M) for p in polys if p.is_valid])

    manual = []
    mpath = seed_dir / "osm/manual_crossings.json"
    if mpath.exists():
        for c in json.loads(mpath.read_text(encoding="utf-8"))["crossings"]:
            manual.append(LineString([loc.m(*p) for p in c["line"]]))
    return net, loc, nodes, polys, shrunk, manual


def inside_len(line: LineString, shrunk) -> float:
    return line.intersection(shrunk).length


class Graph:
    def __init__(self, net: dict, nodes: list[tuple[float, float]], shrunk, manual: list[LineString] = ()):
        self.nodes = list(nodes)
        self.adj: dict[int, list[tuple[int, float, int]]] = {}
        self.main_nodes: set[int] = set()
        self.main_lines: list[LineString] = []
        self.crossing_nodes = set(net["crossings"][0::2])
        self.crossing_lines: list[LineString] = []
        self.dropped: list[str] = []
        self.edges: list[tuple[int, int, int, LineString]] = []
        self.main_ways: list[list[int]] = []
        self._temp: list[int] = []
        for w in net["ways"]:
            kind, idx = w[0], w[1:]
            if kind == MAIN:
                self.main_nodes.update(idx)
                self.main_lines.append(LineString([self.nodes[i] for i in idx]))
                self.main_ways.append(idx)
                continue
            if kind == 2:
                self.crossing_lines.append(LineString([self.nodes[i] for i in idx]))
            for a, b in zip(idx, idx[1:], strict=False):
                seg = LineString([self.nodes[a], self.nodes[b]])
                if inside_len(seg, shrunk) > 0.5:
                    self.dropped.append(f"{KIND[kind]} {a}-{b} 건물 안 {inside_len(seg, shrunk):.1f}m")
                    continue
                self._add(a, b, seg.length * FACTOR[kind], kind)
                self.edges.append((a, b, kind, seg))
        # 광장(area:highway=pedestrian 등): 둘레 점끼리 광장 안으로 곧게 잇는다
        for ring in net["areas"]:
            poly = Polygon([self.nodes[i] for i in ring]).buffer(0.3)
            uniq = list(dict.fromkeys(ring))
            for i, a in enumerate(uniq):
                for b in uniq[i + 1:]:
                    seg = LineString([self.nodes[a], self.nodes[b]])
                    if poly.covers(seg) and inside_len(seg, shrunk) == 0:
                        self._add(a, b, seg.length * AREA_FACTOR, 4)
        self.main_tree = STRtree(self.main_lines)
        self.edge_tree = STRtree([e[3] for e in self.edges])
        ped_nodes = {v for a, b, _, _ in self.edges for v in (a, b)}
        self.implicit_nodes = (self.main_nodes & ped_nodes) - self.crossing_nodes
        self.linked = self._link_crossings()
        # 현장 조사로 확인한 횡단보도: 양 끝을 가까운 보행로에 잇고, 차도와 만나는 점을 횡단 지점으로 둔다
        for line in manual:
            self._add_manual_crossing(line, shrunk)
        self.crossing_marks = [Point(self.nodes[i]) for i in self.crossing_nodes] + self.crossing_lines
        self.crossing_tree = STRtree(self.crossing_marks)

    def _add(self, a: int, b: int, cost: float, kind: int) -> None:
        self.adj.setdefault(a, []).append((b, cost, kind))
        self.adj.setdefault(b, []).append((a, cost, kind))

    def _link_crossings(self) -> int:
        """차도 위 횡단 지점(횡단보도, 표시 없는 횡단 지점)의 양쪽 중 보행로가 닿지 않은 쪽을 12m 안의 보행로에 잇는다."""
        added = 0
        for way in self.main_ways:
            for j, c in enumerate(way):
                if c not in self.crossing_nodes and c not in self.implicit_nodes:
                    continue
                a, b = way[max(j - 1, 0)], way[min(j + 1, len(way) - 1)]
                (ax, ay), (bx, by), (cx, cy) = self.nodes[a], self.nodes[b], self.nodes[c]
                dx, dy = bx - ax, by - ay

                def side(x: float, y: float, cx=cx, cy=cy, dx=dx, dy=dy) -> int:
                    return 1 if dx * (y - cy) - dy * (x - cx) > 0 else -1
                have = {side(*self.nodes[v]) for v, _, _ in self.adj.get(c, [])}
                pc = Point(cx, cy)
                for sd in (1, -1):
                    if sd in have:
                        continue
                    best = None
                    for k in self.edge_tree.query(pc.buffer(CROSSING_LINK_M)):
                        seg = self.edges[k][3]
                        q = seg.interpolate(seg.project(pc))
                        d = q.distance(pc)
                        if d < 0.5 or d > CROSSING_LINK_M or side(q.x, q.y) != sd:
                            continue
                        if self.crosses_main(LineString([pc, q])):
                            continue
                        if best is None or d < best[0]:
                            best = (d, k)
                    if best:
                        v = self._split(best[1], pc)
                        self._add(c, v, best[0], 2)
                        added += 1
        return added

    def _add_manual_crossing(self, line: LineString, shrunk) -> None:
        self.crossing_lines.append(line)
        ends = []
        for p in (line.coords[0], line.coords[-1]):
            pt = Point(p)
            best = min(((self.edges[k][3].distance(pt), k) for k in self.edge_tree.query(pt.buffer(10))), default=None)
            if best is None:
                raise SystemExit(f"[중단] 수동 횡단보도 끝점 10m 안에 보행로가 없습니다: {p}")
            ends.append(self._split(best[1], pt))
        a, b = ends
        self._add(a, b, line.length, 2)

    def _split(self, k: int, pt: Point, temp: bool = False) -> int:
        """선 k 위에서 pt 와 가장 가까운 점에 지점을 만들고 양 끝과 잇는다."""
        a, b, kind, seg = self.edges[k]
        q = seg.interpolate(seg.project(pt))
        v = len(self.nodes)
        self.nodes.append((q.x, q.y))
        if temp:
            self._temp.append(v)
        ta, tb = Point(self.nodes[a]).distance(q), Point(self.nodes[b]).distance(q)
        self._add(v, a, ta * FACTOR[kind], kind)
        self._add(v, b, tb * FACTOR[kind], kind)
        return v

    def crosses_main(self, seg: LineString) -> bool:
        return any(seg.crosses(self.main_lines[i]) for i in self.main_tree.query(seg))

    def near_main(self, geom, tol: float = 1.0) -> bool:
        return any(geom.distance(self.main_lines[i]) < tol for i in self.main_tree.query(geom.buffer(tol)))

    def near_crossing(self, geom) -> bool:
        return len(self.crossing_tree.query(geom, predicate="dwithin", distance=CROSSING_NEAR_M)) > 0

    def connectors(self, p: tuple[float, float], shrunk) -> list[tuple[int, float]]:
        """p 에서 가까운 보행로나 구내 도로 위의 점으로 곧게 잇는다 (임시 지점, route 가 끝나면 지운다)."""
        pt = Point(p)
        cand = []
        for k in self.edge_tree.query(pt.buffer(CONNECTOR_MAX_M)):
            seg = self.edges[k][3]
            q = seg.interpolate(seg.project(pt))
            cand.append((q.distance(pt), k, q))
        cand.sort(key=lambda t: t[0])
        out = []
        for d, k, q in cand:
            if d > CONNECTOR_MAX_M or len(out) >= CONNECTOR_K:
                break
            con = LineString([p, (q.x, q.y)])
            if d > 0.01 and (inside_len(con, shrunk) > 0 or self.crosses_main(con)):
                continue
            if self.near_main(q) and not self.near_crossing(q):
                continue
            out.append((self._split(k, pt, temp=True), d * CONNECTOR_FACTOR))
        return out

    def _clear_temp(self) -> None:
        temp = set(self._temp)
        for v in self._temp:
            for u, _, _ in self.adj.pop(v, []):
                if u in self.adj:
                    self.adj[u] = [e for e in self.adj[u] if e[0] not in temp]
        del self.nodes[len(self.nodes) - len(self._temp):]
        self._temp = []

    def route(self, start: tuple[float, float], end: tuple[float, float], shrunk) -> list[tuple[float, float]]:
        """다익스트라. 횡단보도가 아닌 차도 지점을 지나면 벌점."""
        self._temp = []
        try:
            src = self.connectors(start, shrunk)
            dst = dict(self.connectors(end, shrunk))
            if not src or not dst:
                raise NoRoute(f"{'출발점' if not src else '입구'} 근처 {CONNECTOR_MAX_M:.0f}m 안에 이을 수 있는 보행로가 없습니다.")
            START = -1
            dist: dict[int, float] = {}
            prev: dict[int, int] = {}
            pq: list[tuple[float, int]] = []
            for v, c in src:
                if c < dist.get(v, math.inf):
                    dist[v], prev[v] = c, START
                    heapq.heappush(pq, (c, v))
            best, best_node = math.inf, None
            while pq:
                c, u = heapq.heappop(pq)
                if c > dist.get(u, math.inf):
                    continue
                if c >= best:
                    break
                if u in dst and c + dst[u] < best:
                    best, best_node = c + dst[u], u
                pen = MAIN_ROAD_PENALTY_M if u in self.main_nodes and u not in self.crossing_nodes else 0.0
                for v, w, _kind in self.adj.get(u, []):
                    nc = c + w + pen
                    if nc < dist.get(v, math.inf):
                        dist[v], prev[v] = nc, u
                        heapq.heappush(pq, (nc, v))
            if best_node is None:
                raise NoRoute("출발점과 입구가 보행망으로 이어지지 않습니다.")
            seq, u = [], best_node
            while u != START:
                seq.append(u)
                u = prev[u]
            return [self.nodes[i] for i in reversed(seq)]
        finally:
            self._clear_temp()


def check_path(line: LineString, g: Graph, shrunk) -> dict:
    """서버 검사와 같은 기준으로 결과를 확인한다."""
    implicit = STRtree([Point(g.nodes[i]) for i in g.implicit_nodes])
    bad, unmarked, total = [], [], 0
    for i in g.main_tree.query(line):
        road = g.main_lines[i]
        if not line.crosses(road):
            continue
        inter = line.intersection(road)
        pts = [inter] if inter.geom_type == "Point" else [p for p in getattr(inter, "geoms", []) if p.geom_type == "Point"]
        total += len(pts)
        for p in pts:
            if g.near_crossing(p):
                continue
            (unmarked if len(implicit.query(p, predicate="dwithin", distance=CROSSING_NEAR_M)) else bad).append(p)
    on_main = sum(line.intersection(r.buffer(1.5)).length for r in g.main_lines)
    return {"inside_building_m": round(inside_len(line, shrunk), 2), "crossings": total, "bad_crossings": bad,
            "unmarked_crossings": unmarked, "on_main_road_m": round(on_main, 1)}


def build(seed_dir: Path, write: bool) -> int:
    net, loc, nodes, polys, shrunk, manual = load_world(seed_dir)
    g = Graph(net, nodes, shrunk, manual)
    for d in g.dropped:
        print(f"[제외] 건물을 지나는 보행망 구간: {d}")
    print(f"[보완] 한쪽만 이어진 횡단보도 {g.linked}곳을 건너편 보행로에 이음, 수동 횡단보도 {len(manual)}곳")
    ents = {(f["properties"]["place_key"], f["properties"]["name"]): f["geometry"]["coordinates"]
            for f in json.loads((seed_dir / "entrances.geojson").read_text(encoding="utf-8"))["features"]}
    routes_path = seed_dir / "walk_routes.geojson"
    fc = json.loads(routes_path.read_text(encoding="utf-8"))
    ok = True
    for f in fc["features"]:
        pr = f["properties"]
        name = f"{pr['parking_lot_name']} → {pr['place_key']} {pr['entrance_name']}"
        start = loc.m(*f["geometry"]["coordinates"][0])
        end = loc.m(*ents[(pr["place_key"], pr["entrance_name"])])
        try:
            coords = g.route(start, end, shrunk)
        except NoRoute as e:
            ok = False
            print(f"[실패] {name}: {e} (기존 선 유지)")
            continue
        line = LineString([start, *coords, end]).simplify(0.3)
        res = check_path(line, g, shrunk)
        good = res["inside_building_m"] <= 0 and not res["bad_crossings"]
        ok &= good
        tag = "실패" if not good else ("확인 필요" if res["unmarked_crossings"] else "통과")
        print(f"[{tag}] {name}: {line.length:.0f}m, 점 {len(line.coords)}개, "
              f"건물 안 {res['inside_building_m']}m, 차도 횡단 {res['crossings']}곳"
              f"(표시 없는 횡단 지점 {len(res['unmarked_crossings'])}곳, 그 밖 {len(res['bad_crossings'])}곳)")
        for p in res["unmarked_crossings"]:
            lng_, lat_ = loc.ll(p.x, p.y)
            print(f"    횡단보도 표시 없는 차도 횡단: {lat_:.6f}, {lng_:.6f} → 현장에서 횡단보도 여부 확인")
        f["geometry"]["coordinates"] = [list(loc.ll(x, y)) for x, y in line.coords]
        pr["walk_time_min"] = max(1, math.ceil(line.length / WALK_SPEED_M_PER_MIN))
    if write:
        routes_path.write_text(json.dumps(fc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"[저장] {routes_path}")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("seed_dir", nargs="?", default="scripts/seeds/gnu-gajwa")
    ap.add_argument("--check", action="store_true", help="파일을 쓰지 않고 검사만")
    a = ap.parse_args()
    sys.exit(build(Path(a.seed_dir), write=not a.check))
