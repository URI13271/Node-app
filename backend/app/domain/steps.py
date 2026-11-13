"""단계 저장 검사 중 DB 없이 하는 규칙 (설계서 2.4.5 (5) 1~4단계, 1.3.3).

카메라 범위와 필드 누락은 Pydantic 스키마가 먼저 검사한다. 여기서는 개수, 순서, 문장을 본다.
모든 위반을 한 번에 모아 돌려준다(API 명세서 3.7).

뼈대: 본문은 비어 있다. 함수마다 NotImplementedError 를 구현으로 바꾼다.
"""

from dataclasses import dataclass

MIN_STEPS, MAX_STEPS = (2, 30)


MAX_INSTRUCTION = 200


@dataclass(frozen=True)
class Violation:
    """TODO: 필드 정의 (API 명세서, 설계서 참고)"""


def clean_instruction(text: str) -> str:
    """제어 문자 제거 후 앞뒤 공백 제거."""
    raise NotImplementedError("TODO: app.domain.steps.clean_instruction")


def check_instruction(text: str, field: str) -> Violation | None:
    raise NotImplementedError("TODO: app.domain.steps.check_instruction")


def check_steps(step_orders: list[int], instructions: list[str]) -> list[Violation]:
    raise NotImplementedError("TODO: app.domain.steps.check_steps")
