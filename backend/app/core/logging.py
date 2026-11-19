"""JSON 구조화 로그, 감사 로그 (설계서 2.8.1, BE-18).

한 줄에 JSON 하나. 기본 필드(timestamp, level, logger, message)에 extra 로 넘긴 값을 그대로 붙인다.
로그 제외: 쿼리 문자열, 요청 본문, X-Admin-Key, IP, 단계 문장 원문 (설계서 2.7.3). 부르는 쪽이 넣지 않는다.
예외의 traceback 은 남기지 않고 종류(exc_type)만 남긴다. traceback 안에 접속 문자열이나 값이 들어갈 수 있어서다.
"""

import json
import logging
import sys
from datetime import UTC, datetime

_STD = set(vars(logging.LogRecord("", 0, "", 0, "", None, None)).keys()) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for k, v in record.__dict__.items():
            if k not in _STD and not k.startswith("_"):
                out[k] = v
        if record.exc_info and record.exc_info[0]:
            out.setdefault("exc_type", record.exc_info[0].__name__)
        return json.dumps(out, ensure_ascii=False, default=str)


def setup_logging(level: str) -> None:
    """루트 로거에 JSON 출력 하나만 둔다. 여러 번 불러도(테스트에서 앱을 여러 번 만들어도) 출력이 겹치지 않는다.

    다른 도구가 붙인 핸들러(pytest 의 로그 캡처 등)는 건드리지 않는다.
    """
    root = logging.getLogger()
    for h in root.handlers[:]:
        if getattr(h, "_majunggil_json", False) or type(h) is logging.StreamHandler:
            root.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler._majunggil_json = True
    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("uvicorn.access").disabled = True  # 접근 로그는 main.py 미들웨어가 직접 남김 (경로 패턴만)


audit_log = logging.getLogger("audit")
access_log = logging.getLogger("access")
