"""마이그레이션 실행기: migrations/*.sql 을 순서대로 적용, 되돌림, 현황 (설계서 2.2.3).

실행: python -m scripts.migrate up | down | status

- 파일 이름 규칙: NNN_이름.sql (적용), NNN_이름.down.sql (되돌림). 버전은 확장자를 뺀 이름(예: 001_init)
- 소유자 계정(MIGRATION_DATABASE_URL)으로 접속한다. 앱 계정에는 DDL 권한이 없다
- 파일 하나 = 트랜잭션 하나. 중간에 실패하면 그 파일과 적용 기록이 함께 되돌아간다
- 적용한 파일의 sha256 을 기록해 두고, 적용 뒤 내용이 바뀌면 up 을 멈춘다 (이미 적용한 파일은 고치지 말고 새 번호로 추가)
- down 은 마지막에 적용한 하나만 되돌린다
- 반환값: 0 성공, 1 실패. DB 오류(접속 실패, SQL 오류)는 main 이 잡아 메시지를 보여 주고 1 로 끝낸다
"""

import hashlib
import re
import sys
from pathlib import Path

import psycopg
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
UP_FILE = re.compile(r"^(\d{3}_[a-z0-9_]+)\.sql$")

CREATE_TABLE = (
    "CREATE TABLE IF NOT EXISTS schema_migrations ("
    "version varchar(100) PRIMARY KEY, "
    "applied_at timestamptz NOT NULL DEFAULT now(), "
    "checksum char(64) NOT NULL)"
)


def _files() -> list[tuple[str, Path]]:
    """(버전, 적용 파일) 목록을 번호 순으로."""
    found = [(m.group(1), p) for p in MIGRATIONS_DIR.iterdir() if (m := UP_FILE.match(p.name))]
    return sorted(found)


def _checksum(path: Path) -> str:
    # Windows 에서 줄바꿈이 CRLF 로 바뀌어도 같은 값이 나오게 LF 로 맞춘 뒤 계산한다
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _run_sql(conn: Connection, path: Path) -> None:
    # 파일 안에 문장이 여러 개라 드라이버 커서로 그대로 보낸다 (매개변수 없음)
    with conn.connection.cursor() as cur:
        cur.execute(path.read_text(encoding="utf-8"))


def _applied(conn: Connection) -> dict[str, str]:
    conn.execute(text(CREATE_TABLE))
    rows = conn.execute(text("SELECT version, checksum FROM schema_migrations ORDER BY version")).all()
    return {v: c for v, c in rows}


def _engine():
    return create_engine(get_settings().MIGRATION_DATABASE_URL)


def up() -> int:
    engine = _engine()
    try:
        with engine.begin() as conn:
            applied = _applied(conn)
        for version, path in _files():
            checksum = _checksum(path)
            if version in applied:
                if applied[version] != checksum:
                    print(f"[오류] {path.name} 이 적용 뒤에 바뀌었습니다. 고치지 말고 새 번호 파일로 추가하세요.")
                    return 1
                continue
            try:
                with engine.begin() as conn:
                    _run_sql(conn, path)
                    conn.execute(text("INSERT INTO schema_migrations (version, checksum) VALUES (:v, :c)"), {"v": version, "c": checksum})
            except Exception:
                print(f"[오류] {path.name} 적용 실패. 이 파일의 변경은 모두 되돌렸습니다.")
                raise
            print(f"적용: {version}")
        return 0
    finally:
        engine.dispose()


def down() -> int:
    engine = _engine()
    try:
        with engine.begin() as conn:
            applied = _applied(conn)
            if not applied:
                print("되돌릴 마이그레이션이 없습니다.")
                return 0
            version = max(applied)
            path = MIGRATIONS_DIR / f"{version}.down.sql"
            if not path.is_file():
                print(f"[오류] 되돌림 파일이 없습니다: {path.name}")
                return 1
            _run_sql(conn, path)
            conn.execute(text("DELETE FROM schema_migrations WHERE version = :v"), {"v": version})
        print(f"되돌림: {version}")
        return 0
    finally:
        engine.dispose()


def status() -> int:
    engine = _engine()
    try:
        with engine.begin() as conn:
            applied = _applied(conn)
            times = dict(conn.execute(text("SELECT version, applied_at FROM schema_migrations")).all())
        ok = True
        files = dict(_files())
        for version in sorted(set(files) | set(applied)):
            if version not in files:
                print(f"{version}  적용됨 ({times[version]:%Y-%m-%d %H:%M})  [파일 없음]")
                ok = False
            elif version not in applied:
                print(f"{version}  대기")
            elif applied[version] != _checksum(files[version]):
                print(f"{version}  적용됨 ({times[version]:%Y-%m-%d %H:%M})  [적용 뒤 파일이 바뀜]")
                ok = False
            else:
                print(f"{version}  적용됨 ({times[version]:%Y-%m-%d %H:%M})")
        return 0 if ok else 1
    finally:
        engine.dispose()


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "status"
    commands = {"up": up, "down": down, "status": status}
    if cmd not in commands:
        print(f"사용법: python -m scripts.migrate {' | '.join(commands)}")
        return 2
    try:
        return commands[cmd]()
    except (SQLAlchemyError, psycopg.Error) as e:
        print(f"[오류] {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
