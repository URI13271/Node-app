"""시드 적재: scripts/seeds/<지역>/ 의 GeoJSON, JSON 을 DB에 넣고 적재 검사를 한다.

실행: python -m scripts.load_seed scripts/seeds/<지역>

규칙 (검토 v1.1 9번): 도보 경로 응답에는 랜드마크 이름이 들어가지만 ETag 는 경로 updated_at 으로만 만든다.
그래서 랜드마크(이름, 위치)를 바꾸면 그 장소의 walk_route.updated_at 도 now() 로 바꾼다. 안 그러면 브라우저가 옛 이름을 계속 쓴다.
"""

import sys
from pathlib import Path


def load(seed_dir: Path) -> int:
    raise NotImplementedError("TODO: scripts.load_seed.load")


if __name__ == "__main__":
    raise SystemExit(load(Path(sys.argv[1])))
