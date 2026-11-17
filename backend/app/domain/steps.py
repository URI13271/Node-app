"""단계 저장 검사 중 DB 없이 하는 규칙 (설계서 2.4.5 (5) 1~4단계, 1.3.3).

카메라 범위와 필드 누락은 Pydantic 스키마가 먼저 검사한다. 여기서는 개수, 순서, 문장을 본다.
모든 위반을 한 번에 모아 돌려준다(API 명세서 3.7).
"""
import re
from dataclasses import dataclass

MIN_STEPS, MAX_STEPS = 2, 30
MAX_INSTRUCTION = 200
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


@dataclass(frozen=True)
class Violation:
    field: str
    reason: str
    message: str


def clean_instruction(text: str) -> str:
    """제어 문자 제거 후 앞뒤 공백 제거."""
    return _CONTROL.sub("", text).strip()


def check_instruction(text: str, field: str) -> Violation | None:
    n = len(clean_instruction(text))
    if n < 1:
        return Violation(field, "too_short", "문장을 입력하세요.")
    if n > MAX_INSTRUCTION:
        return Violation(field, "too_long", f"{MAX_INSTRUCTION}자 이하로 입력하세요.")
    return None


def check_steps(step_orders: list[int], instructions: list[str]) -> list[Violation]:
    out: list[Violation] = []
    n = len(step_orders)
    if n < MIN_STEPS:
        out.append(Violation("steps", "too_few_steps", f"단계는 {MIN_STEPS}개 이상이어야 합니다."))
    if n > MAX_STEPS:
        out.append(Violation("steps", "too_many_steps", f"단계는 {MAX_STEPS}개 이하여야 합니다."))
    if sorted(step_orders) != list(range(1, n + 1)):
        out.append(Violation("steps", "step_order_gap", "step_order는 1부터 빈틈없이 증가해야 합니다."))
    for i, text in enumerate(instructions):
        v = check_instruction(text, f"steps[{i}].instruction")
        if v:
            out.append(v)
    return out
