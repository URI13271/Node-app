"""관리자 키 비교, 실패 제한기, 요청 횟수 제한기 (설계서 2.7.1, 2.6.6).

서버 1대 기준의 메모리 계수기다. 서버를 여러 대 띄우면 서버별로 따로 센다(설계서 2.6.6에서 수용).

뼈대: 본문은 비어 있다. 함수마다 NotImplementedError 를 구현으로 바꾼다.
"""

import time


def key_matches(given: str | None, expected: str) -> bool:
    raise NotImplementedError("TODO: app.core.security.key_matches")


class FailureLimiter:
    """같은 IP에서 연속 N회 실패하면 lock_s 초 동안 잠근다. 성공하면 계수를 지운다."""

    def __init__(self, limit: int, lock_s: int, clock=time.monotonic):
        raise NotImplementedError("TODO: app.core.security.FailureLimiter.__init__")

    def retry_after(self, ip: str) -> int:
        raise NotImplementedError("TODO: app.core.security.FailureLimiter.retry_after")

    def fail(self, ip: str) -> int:
        """실패 1회 기록. 잠금이 걸리면 남은 초를 돌려준다."""
        raise NotImplementedError("TODO: app.core.security.FailureLimiter.fail")

    def success(self, ip: str) -> None:
        raise NotImplementedError("TODO: app.core.security.FailureLimiter.success")

    def reset(self) -> None:
        raise NotImplementedError("TODO: app.core.security.FailureLimiter.reset")


class SlidingWindowLimiter:
    """IP별 분당 요청 수 제한."""

    def __init__(self, per_min: int, clock=time.monotonic):
        raise NotImplementedError("TODO: app.core.security.SlidingWindowLimiter.__init__")

    def hit(self, ip: str) -> int:
        """허용이면 0, 초과면 다시 시도할 초."""
        raise NotImplementedError("TODO: app.core.security.SlidingWindowLimiter.hit")

    def reset(self) -> None:
        raise NotImplementedError("TODO: app.core.security.SlidingWindowLimiter.reset")
