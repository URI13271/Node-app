"""관리자 키 비교, 실패 제한기, 요청 횟수 제한기 (설계서 2.7.1, 2.6.6).

서버 1대 기준의 메모리 계수기다. 서버를 여러 대 띄우면 서버별로 따로 센다(설계서 2.6.6에서 수용).
key_matches, FailureLimiter 는 BE-13, SlidingWindowLimiter(분당 요청 수)는 BE-17.
"""

import hmac
import threading
import time
from collections import deque


def key_matches(given: str | None, expected: str) -> bool:
    """비교 시간이 내용과 관계없도록 hmac.compare_digest 를 쓴다. 설정 키가 비어 있으면 어떤 값도 통과하지 못한다."""
    if not given or not expected:
        return False
    return hmac.compare_digest(given.encode(), expected.encode())


class FailureLimiter:
    """같은 IP에서 연속 N회 실패하면 lock_s 초 동안 잠근다. 성공하면 계수를 지운다.

    여러 요청이 동시에 들어와도 계수가 꼬이지 않게 잠금(threading.Lock) 안에서 센다. clock 은 테스트에서 바꿔 끼운다.
    """

    def __init__(self, limit: int, lock_s: int, clock=time.monotonic):
        self.limit, self.lock_s, self.clock = limit, lock_s, clock
        self._fails: dict[str, int] = {}
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def retry_after(self, ip: str) -> int:
        """잠겨 있으면 남은 초(올림), 아니면 0."""
        with self._lock:
            left = self._locked_until.get(ip, 0) - self.clock()
            return int(left) + 1 if left > 0 else 0

    def fail(self, ip: str) -> int:
        """실패 1회 기록. 잠금이 걸리면 남은 초를 돌려준다."""
        with self._lock:
            n = self._fails.get(ip, 0) + 1
            if n >= self.limit:
                self._fails.pop(ip, None)
                self._locked_until[ip] = self.clock() + self.lock_s
                return self.lock_s
            self._fails[ip] = n
            return 0

    def success(self, ip: str) -> None:
        with self._lock:
            self._fails.pop(ip, None)

    def reset(self) -> None:
        with self._lock:
            self._fails.clear()
            self._locked_until.clear()


class SlidingWindowLimiter:
    """IP별 분당 요청 수 제한. 최근 60초 안의 요청 시각을 IP마다 큐에 담아 센다."""

    def __init__(self, per_min: int, clock=time.monotonic):
        self.per_min, self.clock = per_min, clock
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def hit(self, ip: str) -> int:
        """허용이면 0, 초과면 다시 시도할 초. 초과한 요청은 세지 않는다 (막힌 요청이 창을 늘리지 않게)."""
        now = self.clock()
        with self._lock:
            q = self._hits.setdefault(ip, deque())
            while q and now - q[0] >= 60:
                q.popleft()
            if len(q) >= self.per_min:
                return int(60 - (now - q[0])) + 1
            q.append(now)
            return 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
