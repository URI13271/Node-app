// 관리자 단계 초안 검사 (프론트 작성 가이드 7.5). 서버로 보내기 전에 화면에서 거른다.
//  - 오류(저장 막음): 문장이 비었거나 200자 초과, 카메라 칸이 비어 있음
//  - 경고(확인 후 저장): 단계 순서와 경로 진행 순서가 어긋남, 두 단계 사이가 3m 미만
import { todo } from './util.js'

export const MIN_STEP_GAP_M = 3
export const MAX_INSTRUCTION = 200 // 서버 규칙: 제어 문자를 지우고 앞뒤 공백을 뺀 뒤 1~200자 (API 명세서 3.7)

/** 서버(domain/steps.py)와 같은 방식으로 문장 정리: 탭, 줄바꿈을 뺀 제어 문자를 지우고 앞뒤 공백을 뺀다 */
export function cleanInstruction(text) {
  return String(text ?? '').replace(/[\x00-\x08\x0b-\x1f\x7f]/g, '').trim()
}

/** 문장 검사 → [{step, level: 'error', message}]. 비었거나 200자를 넘으면 저장을 막는다 (서버 400 too_short, too_long 을 미리 알림) */
export function instructionIssues(steps) {
  const out = []
  steps.forEach((s, i) => {
    const n = cleanInstruction(s.instruction).length
    if (n === 0) out.push({ step: i + 1, level: 'error', message: `${i + 1}단계 문장이 비어 있습니다.` })
    else if (n > MAX_INSTRUCTION) out.push({ step: i + 1, level: 'error', message: `${i + 1}단계 문장이 ${MAX_INSTRUCTION}자를 넘습니다 (${n}자).` })
  })
  return out
}

/** 비어 있는 카메라 칸 이름 목록 → ['bearing', 'zoom'] */
export function emptyCameraFields(camera) { return todo('emptyCameraFields') }

/** 초안 문제 목록 → [{step, level: 'error'|'warning', message}]. TODO: instructionIssues + 카메라 빈 칸 + 순서 + 3m 간격을 합친다 */
export function checkDraft(steps, path) { return todo('checkDraft') }
