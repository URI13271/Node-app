"""JSON 구조화 로그, 감사 로그 (설계서 2.8.1).

로그 제외: 쿼리 문자열, 요청 본문, X-Admin-Key, IP, 단계 문장 원문 (설계서 2.7.3).

뼈대: 기본 로그만 켠다. JSON 형식은 TODO.
"""

import logging


def setup_logging(level: str) -> None:
    # TODO: JsonFormatter 로 바꾸고, uvicorn.access 로그를 끈 뒤 미들웨어가 직접 남긴다
    logging.basicConfig(level=level)


audit_log = logging.getLogger("audit")
access_log = logging.getLogger("access")
