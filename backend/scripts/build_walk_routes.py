"""OSM 보행망 위에서 도보 경로 선을 만든다 (API 명세서 v1.2 부록 C).

실행: python -m scripts.build_walk_routes scripts/seeds/<지역> [--check]
"""

import sys
from pathlib import Path


def build(seed_dir: Path, write: bool) -> int:
    raise NotImplementedError("TODO: scripts.build_walk_routes.build")


if __name__ == "__main__":
    raise SystemExit(build(Path(sys.argv[1]), write="--check" not in sys.argv))
