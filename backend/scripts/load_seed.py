"""시드 적재 (설계서 1.3.5, ADR-008). 데이터 담당이 시연 데이터를 바꿀 때 실행한다.

사용법 (backend 디렉터리에서):
    python -m scripts.load_seed scripts/seeds/gnu-gajwa

- 파일 7개를 정해진 순서로 읽고, 파일 하나 = 트랜잭션 하나로 적재한다(설계서 2.7.4). 실패하면 그 파일만 되돌린다.
- place 는 key(seed_key)로 찾아 갱신하므로 장소 id 가 바뀌지 않는다(REQ-F-DATA-003).
- 하위 데이터(건물, 랜드마크, 입구, 주차장, 경로, 단계)는 시드에 있는 장소 단위로 지우고 다시 넣는다.
- 마지막에 적재 검사(REQ-F-PLACE-007): 장소마다 입구 1곳, 주차장 1곳 이상, 경로마다 단계 2개 이상.
- 보행 경로 검사(API 명세서 v1.2 부록 C): 경로가 건물 안을 1m 넘게 지나면(crosses_building), 단계 지점이
  건물 안이면(inside_building), 단계 지점이 경로 선에서 30m 넘게 떨어지면(too_far_from_path) 그 파일을 되돌리고 멈춘다.
- osm/walk_network.json 이 있으면 보행망을 walk_network_feature 에 지역(시드 폴더 이름) 단위로 넣고,
  경로가 횡단보도 5m 밖에서 차도를 건너는 곳을 [확인 필요]로 알린다(실패는 아님. 현장 조사 대상).
- 랜드마크와 ETag (검토 v1.1 9번): 도보 경로 응답에는 랜드마크 이름이 들어가지만 ETag 는 경로 updated_at 으로만 만든다.
  이 스크립트는 경로를 매번 지우고 다시 넣으므로 updated_at 이 적재 시각으로 바뀐다. 그래서 랜드마크만 바꿔
  다시 적재해도 ETag 가 바뀌어 브라우저가 옛 이름을 쓰지 않는다. 경로를 지우지 않고 고치는 방식으로 바꾸면
  랜드마크가 바뀐 장소의 walk_route.updated_at 을 따로 now() 로 올려야 한다.
- 반환값: 0 성공, 1 적재 검사 실패. 파일 하나의 검사(보행 경로, 단계 지점)에 걸리면 SystemExit 로 멈춘다(종료 코드 1).
"""

import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.config import get_settings

WALL_TOLERANCE_M = 1.0       # 벽에서 1m 안쪽부터 건물 안으로 본다 (GPS, 지도 오차)
MAX_INSIDE_BUILDING_M = 1.0  # 경로가 건물 안을 이만큼 넘게 지나면 실패
MAX_DISTANCE_FROM_PATH_M = 30.0
CROSSING_NEAR_M = 5.0
NETWORK_KIND = {0: "footway", 1: "sidewalk", 2: "crossing", 3: "steps", 4: "pedestrian", 5: "path", 6: "service", 7: "road"}

ORDER = ["places.json", "buildings.geojson", "landmarks.geojson", "entrances.geojson",
         "parking_lots.geojson", "walk_routes.geojson", "walk_route_steps.json"]


def _gj(geom: dict) -> str:
    return json.dumps(geom)


def _cam(c: dict | None) -> dict:
    return {"cb": c["bearing"] if c else None, "cp": c["pitch"] if c else None, "cz": c["zoom"] if c else None}


def _features(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["features"]


def _pairs(flat: list[int], o: list[float], u: float) -> list[list[float]]:
    return [[round(o[0] + flat[i] * u, 7), round(o[1] + flat[i + 1] * u, 7)] for i in range(0, len(flat), 2)]


def load_network(eng, seed_dir: Path) -> int | None:
    """osm/walk_network.json (+ manual_crossings.json) → walk_network_feature. 파일이 없으면 None."""
    path = seed_dir / "osm" / "walk_network.json"
    if not path.exists():
        return None
    net = json.loads(path.read_text(encoding="utf-8"))
    pts = _pairs(net["nodes"], net["o"], net["u"])
    rows = []
    for w in net["ways"]:
        rows.append(("osm", NETWORK_KIND[w[0]], {"type": "LineString", "coordinates": [pts[i] for i in w[1:]]}))
    for ring in net["areas"]:
        rows.append(("osm", "pedestrian_area", {"type": "Polygon", "coordinates": [[pts[i] for i in ring]]}))
    for i in net["crossings"][0::2]:
        rows.append(("osm", "crossing_node", {"type": "Point", "coordinates": pts[i]}))
    manual = seed_dir / "osm" / "manual_crossings.json"
    if manual.exists():
        for c in json.loads(manual.read_text(encoding="utf-8"))["crossings"]:
            rows.append(("manual", "crossing", {"type": "LineString", "coordinates": c["line"]}))
    area = seed_dir.name
    with eng.begin() as c:
        c.execute(text("DELETE FROM walk_network_feature WHERE area_key = :a"), {"a": area})
        for src, kind, g in rows:
            c.execute(text("""INSERT INTO walk_network_feature (area_key, kind, geom, source)
                VALUES (:a, :k, ST_SetSRID(ST_GeomFromGeoJSON(:g), 4326), :s)"""),
                      {"a": area, "k": kind, "g": _gj(g), "s": src})
    return len(rows)


_ROUTES = """
    WITH r AS (
        SELECT r.id, r.path, l.place_id, l.name AS lot, e.name AS ent FROM walk_route r
        JOIN parking_lot l ON l.id = r.parking_lot_id JOIN entrance e ON e.id = r.entrance_id
        WHERE l.place_id = ANY(:ids)),
    b AS (
        SELECT place_id, coalesce(name, '이름 없는 건물') AS name,
               ST_Buffer(footprint::geography, -:tol)::geometry AS inner_fp
        FROM building WHERE place_id = ANY(:ids) AND NOT ST_IsEmpty(ST_Buffer(footprint::geography, -:tol)::geometry))
"""


def check_routes(c, ids: list[int]) -> list[str]:
    """crosses_building: 경로 선이 건물(벽 1m 안쪽) 안을 1m 넘게 지나는지. 경로 적재 트랜잭션 안에서 부른다."""
    return list(c.execute(text(_ROUTES + """
        SELECT 'crosses_building: ' || r.lot || ' → ' || r.ent || ' 경로가 ' || b.name || ' 안을 '
               || round(ST_Length(ST_Intersection(r.path, b.inner_fp)::geography)::numeric, 1) || 'm 지남'
          FROM r JOIN b ON b.place_id = r.place_id
         WHERE ST_Intersects(r.path, b.inner_fp)
           AND ST_Length(ST_Intersection(r.path, b.inner_fp)::geography) > :max_in"""),
        {"ids": ids, "tol": WALL_TOLERANCE_M, "max_in": MAX_INSIDE_BUILDING_M}).scalars())


def check_steps(c, ids: list[int]) -> list[str]:
    """inside_building, too_far_from_path: 관리자 저장 검사와 같은 기준. 단계 적재 트랜잭션 안에서 부른다."""
    return list(c.execute(text(_ROUTES + """
        SELECT 'inside_building: ' || r.lot || ' → ' || r.ent || ' 단계 ' || s.step_order || ' 지점이 '
               || b.name || ' 안'
          FROM r JOIN walk_route_step s ON s.walk_route_id = r.id JOIN b ON b.place_id = r.place_id
         WHERE ST_Contains(b.inner_fp, s.location)
        UNION ALL
        SELECT 'too_far_from_path: ' || r.lot || ' → ' || r.ent || ' 단계 ' || s.step_order || ' 지점이 경로에서 '
               || round(ST_Distance(r.path::geography, s.location::geography)::numeric, 1) || 'm'
          FROM r JOIN walk_route_step s ON s.walk_route_id = r.id
         WHERE ST_Distance(r.path::geography, s.location::geography) > :max_d"""),
        {"ids": ids, "tol": WALL_TOLERANCE_M, "max_d": MAX_DISTANCE_FROM_PATH_M}).scalars())


def unmarked_crossings(c, ids: list[int], area_key: str) -> list[str]:
    """경로가 횡단보도(선, 점) 5m 밖에서 차도를 건너는 곳. 실패가 아니라 현장 확인 대상."""
    return list(c.execute(text("""
        WITH r AS (
            SELECT r.path, l.name AS lot, e.name AS ent FROM walk_route r
            JOIN parking_lot l ON l.id = r.parking_lot_id JOIN entrance e ON e.id = r.entrance_id
            WHERE l.place_id = ANY(:ids)),
        x AS (
            SELECT r.lot, r.ent, (ST_Dump(ST_Intersection(r.path, n.geom))).geom AS pt
            FROM r JOIN walk_network_feature n ON n.area_key = :area AND n.kind = 'road'
             AND ST_Crosses(r.path, n.geom))
        SELECT DISTINCT 'crossing_unmarked: ' || x.lot || ' → ' || x.ent || ' 횡단보도 없는 차도 횡단 '
               || round(ST_Y(x.pt)::numeric, 6) || ', ' || round(ST_X(x.pt)::numeric, 6)
          FROM x
         WHERE GeometryType(x.pt) = 'POINT' AND NOT EXISTS (
               SELECT 1 FROM walk_network_feature k WHERE k.area_key = :area
                  AND k.kind IN ('crossing', 'crossing_node')
                  AND ST_DWithin(k.geom::geography, x.pt::geography, :near))"""),
        {"ids": ids, "area": area_key, "near": CROSSING_NEAR_M}).scalars())


CONNECT_TIMEOUT_S = 5       # DB 가 꺼져 있거나 포트가 막혔을 때 무한 대기하지 않도록
LOCK_TIMEOUT = "10s"        # 다른 세션(멈춘 이전 적재, DB 도구의 열린 트랜잭션)이 표를 잡고 있으면 기다리지 않고 멈춘다


def load(seed_dir: Path) -> int:
    url = get_settings().MIGRATION_DATABASE_URL
    eng = create_engine(url, connect_args={"connect_timeout": CONNECT_TIMEOUT_S,
                                           "options": f"-c timezone=UTC -c lock_timeout={LOCK_TIMEOUT}"})
    host = url.split("@")[-1]
    print(f"[연결] {host} ...", flush=True)
    try:
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
        print("[연결] 성공", flush=True)
        return _load(eng, seed_dir)
    except OperationalError as e:
        msg = str(e.orig) if e.orig else str(e)
        if "lock timeout" in msg:
            print(f"[중단] 다른 DB 세션이 표를 잡고 있어 {LOCK_TIMEOUT} 안에 적재하지 못했습니다.\n"
                  "  멈춘 이전 load_seed 창, DB 도구(pgAdmin, DBeaver)의 커밋 안 한 트랜잭션을 닫고 다시 실행하세요.")
        else:
            print(f"[중단] DB 에 연결하지 못했습니다 ({host}).\n"
                  "  docker compose ps 로 majunggil-db 가 healthy 인지 확인하세요.\n"
                  f"  원인: {msg.strip().splitlines()[0] if msg.strip() else e}")
        return 1
    finally:
        eng.dispose()


def _load(eng, seed_dir: Path) -> int:
    missing = [f for f in ORDER if not (seed_dir / f).exists()]
    if missing:
        print(f"[중단] 파일이 없습니다: {', '.join(missing)}")
        return 1
    place_ids: dict[str, int] = {}

    # 0. 보행망 (선택)
    n_net = load_network(eng, seed_dir)
    if n_net is not None:
        print(f"[적재] osm/walk_network.json  {n_net}개 (지역 {seed_dir.name})")

    # 1. places.json (upsert by seed_key)
    with eng.begin() as c:
        for p in json.loads((seed_dir / "places.json").read_text(encoding="utf-8")):
            pid = c.execute(text("""
                INSERT INTO place (seed_key, name, category, address, location, description, cover_image_url,
                                   camera_bearing, camera_pitch, camera_zoom, arrival_radius_m)
                VALUES (:key, :name, :category, :address, ST_SetSRID(ST_GeomFromGeoJSON(:loc), 4326), :description,
                        :cover, :cb, :cp, :cz, :radius)
                ON CONFLICT (seed_key) DO UPDATE SET name = EXCLUDED.name, category = EXCLUDED.category,
                    address = EXCLUDED.address, location = EXCLUDED.location, description = EXCLUDED.description,
                    cover_image_url = EXCLUDED.cover_image_url, camera_bearing = EXCLUDED.camera_bearing,
                    camera_pitch = EXCLUDED.camera_pitch, camera_zoom = EXCLUDED.camera_zoom,
                    arrival_radius_m = EXCLUDED.arrival_radius_m
                RETURNING id"""), {
                "key": p["key"], "name": p["name"], "category": p["category"], "address": p.get("address"),
                "loc": _gj(p["location"]), "description": p.get("description"), "cover": p.get("cover_image_url"),
                "radius": p.get("arrival_radius_m", get_settings().DEFAULT_ARRIVAL_RADIUS_M), **_cam(p.get("camera")),
            }).scalar_one()
            place_ids[p["key"]] = pid
    print(f"[적재] places.json  {len(place_ids)}곳")
    ids = list(place_ids.values())

    def pid_of(props: dict) -> int:
        try:
            return place_ids[props["place_key"]]
        except KeyError as e:
            raise SystemExit(f"[중단] places.json 에 없는 place_key: {props.get('place_key')}") from e

    # 2. buildings
    with eng.begin() as c:
        c.execute(text("DELETE FROM building WHERE place_id = ANY(:ids)"), {"ids": ids})
        fs = _features(seed_dir / "buildings.geojson")
        for f in fs:
            pr = f["properties"]
            c.execute(text("""INSERT INTO building (place_id, name, footprint, height_m, floor_count, description, is_target, source)
                VALUES (:pid, :name, ST_SetSRID(ST_GeomFromGeoJSON(:g), 4326), :h, :fl, :d, :t, :src)"""),
                      {"pid": pid_of(pr), "name": pr.get("name"), "g": _gj(f["geometry"]), "h": pr.get("height_m"),
                       "fl": pr.get("floor_count"), "d": pr.get("description"), "t": pr.get("is_target", False),
                       "src": pr["source"]})
    print(f"[적재] buildings.geojson  {len(fs)}동")

    # 3. landmarks (key 는 적재 중에만 쓴다)
    landmark_ids: dict[tuple[str, str], int] = {}
    with eng.begin() as c:
        c.execute(text("DELETE FROM landmark WHERE place_id = ANY(:ids)"), {"ids": ids})
        fs = _features(seed_dir / "landmarks.geojson")
        for f in fs:
            pr = f["properties"]
            lid = c.execute(text("""INSERT INTO landmark (place_id, name, location, description, image_url)
                VALUES (:pid, :name, ST_SetSRID(ST_GeomFromGeoJSON(:g), 4326), :d, :img) RETURNING id"""),
                            {"pid": pid_of(pr), "name": pr["name"], "g": _gj(f["geometry"]),
                             "d": pr.get("description"), "img": pr.get("image_url")}).scalar_one()
            landmark_ids[(pr["place_key"], pr["key"])] = lid
    print(f"[적재] landmarks.geojson  {len(fs)}개")

    # 4. entrances
    with eng.begin() as c:
        c.execute(text("DELETE FROM entrance WHERE place_id = ANY(:ids)"), {"ids": ids})
        fs = _features(seed_dir / "entrances.geojson")
        for f in fs:
            pr = f["properties"]
            c.execute(text("""INSERT INTO entrance (place_id, name, location, description, is_main)
                VALUES (:pid, :name, ST_SetSRID(ST_GeomFromGeoJSON(:g), 4326), :d, :m)"""),
                      {"pid": pid_of(pr), "name": pr["name"], "g": _gj(f["geometry"]), "d": pr.get("description"),
                       "m": pr.get("is_main", False)})
    print(f"[적재] entrances.geojson  {len(fs)}곳")

    # 5. parking_lots
    with eng.begin() as c:
        c.execute(text("DELETE FROM parking_lot WHERE place_id = ANY(:ids)"), {"ids": ids})
        fs = _features(seed_dir / "parking_lots.geojson")
        for f in fs:
            pr = f["properties"]
            c.execute(text("""INSERT INTO parking_lot (place_id, name, location, capacity, is_free, description, priority,
                                                       area, camera_bearing, camera_pitch, camera_zoom)
                VALUES (:pid, :name, ST_SetSRID(ST_GeomFromGeoJSON(:g), 4326), :cap, :free, :d, :pri,
                        ST_SetSRID(ST_GeomFromGeoJSON(CAST(:area AS text)), 4326),
                        :cb, :cp, :cz)"""),
                      {"pid": pid_of(pr), "name": pr["name"], "g": _gj(f["geometry"]), "cap": pr.get("capacity"),
                       "free": pr.get("is_free"), "d": pr.get("description"), "pri": pr["priority"],
                       "area": _gj(pr["area"]) if pr.get("area") else None, **_cam(pr.get("camera"))})
    print(f"[적재] parking_lots.geojson  {len(fs)}곳")

    # 6. walk_routes (주차장 이름 + 입구 이름으로 찾는다)
    with eng.begin() as c:
        fs = _features(seed_dir / "walk_routes.geojson")
        for f in fs:
            pr = f["properties"]
            row = c.execute(text("""SELECT p.id AS lot, e.id AS ent FROM parking_lot p JOIN entrance e ON e.place_id = p.place_id
                WHERE p.place_id = :pid AND p.name = :lot AND e.name = :ent"""),
                            {"pid": pid_of(pr), "lot": pr["parking_lot_name"], "ent": pr["entrance_name"]}).first()
            if row is None:
                raise SystemExit(f"[중단] 주차장/입구를 찾을 수 없음: {pr['parking_lot_name']} → {pr['entrance_name']}")
            c.execute(text("""INSERT INTO walk_route (parking_lot_id, entrance_id, path, distance_m, walk_time_min, description)
                VALUES (:lot, :ent, ST_SetSRID(ST_GeomFromGeoJSON(:g), 4326),
                        ST_Length(ST_SetSRID(ST_GeomFromGeoJSON(:g), 4326)::geography), :wt, :d)"""),
                      {"lot": row.lot, "ent": row.ent, "g": _gj(f["geometry"]), "wt": pr.get("walk_time_min"),
                       "d": pr.get("description")})
        bad = check_routes(c, ids)
        if bad:  # 예외로 빠져나가면 이 파일의 트랜잭션만 되돌린다
            raise SystemExit("[중단] walk_routes.geojson 보행 경로 검사 실패\n  " + "\n  ".join(bad))
    print(f"[적재] walk_routes.geojson  {len(fs)}개 (건물 통과 검사 통과)")

    # 7. walk_route_steps
    with eng.begin() as c:
        steps = json.loads((seed_dir / "walk_route_steps.json").read_text(encoding="utf-8"))
        for s in steps:
            wr = s["walk_route"]
            route_id = c.execute(text("""SELECT r.id FROM walk_route r JOIN parking_lot p ON p.id = r.parking_lot_id
                JOIN entrance e ON e.id = r.entrance_id
                WHERE p.place_id = :pid AND p.name = :lot AND e.name = :ent"""),
                                 {"pid": place_ids[wr["place_key"]], "lot": wr["parking_lot_name"],
                                  "ent": wr["entrance_name"]}).scalar()
            if route_id is None:
                raise SystemExit(f"[중단] 경로를 찾을 수 없음: {wr}")
            lm = landmark_ids.get((wr["place_key"], s["landmark_key"])) if s.get("landmark_key") else None
            c.execute(text("""INSERT INTO walk_route_step (walk_route_id, step_order, landmark_id, instruction, location,
                                                           camera_bearing, camera_pitch, camera_zoom, updated_by)
                VALUES (:r, :o, :lm, :ins, ST_SetSRID(ST_GeomFromGeoJSON(:g), 4326), :cb, :cp, :cz, 'seed')"""),
                      {"r": route_id, "o": s["step_order"], "lm": lm, "ins": s["instruction"],
                       "g": _gj(s["location"]), **_cam(s.get("camera"))})
        bad = check_steps(c, ids)
        if bad:
            raise SystemExit("[중단] walk_route_steps.json 단계 지점 검사 실패\n  " + "\n  ".join(bad))
    print(f"[적재] walk_route_steps.json  {len(steps)}단계 (지점 검사 통과)")

    # 적재 검사
    with eng.begin() as c:
        problems = c.execute(text("""
            SELECT p.name || ': 입구 없음' FROM place p WHERE p.id = ANY(:ids)
              AND NOT EXISTS (SELECT 1 FROM entrance e WHERE e.place_id = p.id)
            UNION ALL SELECT p.name || ': 주차장 없음' FROM place p WHERE p.id = ANY(:ids)
              AND NOT EXISTS (SELECT 1 FROM parking_lot l WHERE l.place_id = p.id)
            UNION ALL SELECT '경로 ' || r.id || ': 단계 ' || count(s.id) || '개 (2개 이상 필요)'
              FROM walk_route r JOIN parking_lot l ON l.id = r.parking_lot_id
              LEFT JOIN walk_route_step s ON s.walk_route_id = r.id
              WHERE l.place_id = ANY(:ids) GROUP BY r.id HAVING count(s.id) < 2"""), {"ids": ids}).scalars().all()
    if problems:
        print("[검사 실패]\n  " + "\n  ".join(problems))
        return 1
    print("[검사 통과] 장소마다 입구, 주차장 있음 / 경로마다 단계 2개 이상")
    if n_net is not None:
        with eng.begin() as c:
            for w in unmarked_crossings(c, ids, seed_dir.name):
                print(f"[확인 필요] {w}")
    return 0


if __name__ == "__main__":
    sys.exit(load(Path(sys.argv[1] if len(sys.argv) > 1 else "scripts/seeds/gnu-gajwa")))
