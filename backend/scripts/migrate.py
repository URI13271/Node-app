"""마이그레이션 실행기: migrations/*.sql 을 순서대로 적용, 되돌림, 현황 (설계서 2.2.3).

실행: python -m scripts.migrate up | down | status
"""

import sys


def up() -> int:
    raise NotImplementedError("TODO: scripts.migrate.up")


def down() -> int:
    raise NotImplementedError("TODO: scripts.migrate.down")


def status() -> int:
    raise NotImplementedError("TODO: scripts.migrate.status")


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "status"
    return {"up": up, "down": down, "status": status}[cmd]()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
