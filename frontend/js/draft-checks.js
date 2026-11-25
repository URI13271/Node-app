// 관리자 단계 초안 검사 (프론트 작성 가이드 7.5). 서버로 보내기 전에 화면에서 거른다.
//  - 오류(저장 막음): 문장이 비었거나 200자 초과, 단계 수, 카메라 칸이 일부만 비었거나 범위 밖
//  - 경고(확인 후 저장): 단계 순서와 경로 진행 순서가 어긋남, 두 단계 사이가 3m 미만
// 서버 검사가 최종 기준이다. 화면 검사는 미리 알려 주는 용도다.
import { distanceM, fractionOnPath } from './geo.js'

// 이웃한 두 단계 지점이 이보다 가까우면 경고
export const MIN_STEP_GAP_M = 3
// 서버 규칙: 제어 문자를 지우고 앞뒤 공백을 뺀 뒤 1~200자 (API 명세서 3.7)
export const MAX_INSTRUCTION = 200
const CAMERA_FIELDS = ['bearing', 'pitch', 'zoom']

/** 서버(domain/steps.py)와 같은 방식으로 문장 정리: 탭, 줄바꿈을 뺀 제어 문자를 지우고 앞뒤 공백을 뺀다 */
export function cleanInstruction(text) {
  return String(text ?? '').replace(/[\x00-\x08\x0b-\x1f\x7f]/g, '').trim()
}

/** 문장 검사 → [{step, level: 'error', field, message}]. 비었거나 200자를 넘으면 저장을 막는다 (서버 400 too_short, too_long 을 미리 알림) */
export function instructionIssues(steps) {
  const out = []
  steps.forEach((step, index) => {
    const length = cleanInstruction(step.instruction).length
    if (length === 0) out.push({ step: index + 1, level: 'error', field: 'instruction', message: `${index + 1}단계 문장이 비어 있습니다.` })
    else if (length > MAX_INSTRUCTION) out.push({ step: index + 1, level: 'error', field: 'instruction', message: `${index + 1}단계 문장이 ${MAX_INSTRUCTION}자를 넘습니다 (${length}자).` })
  })
  return out
}

/** 부분 입력된 카메라의 빈 칸을 돌려준다. 전체 빈 값은 자동 카메라로 허용한다. */
export function emptyCameraFields(camera) {
  if (!camera) return []
  const empty = (value) => value === null || value === undefined || value === ''
  if (CAMERA_FIELDS.every((field) => empty(camera[field]))) return []
  return CAMERA_FIELDS.filter((field) => empty(camera[field]))
}

/** 단계 위치를 [경도, 위도]로. GeoJSON Point 와 좌표 배열 둘 다 받는다 */
function stepPoint(step) {
  const point = step?.location?.coordinates || step?.location
  return Array.isArray(point) && point.length === 2 && point.every(Number.isFinite) ? point : null
}

function pathCoordinates(path) {
  const points = Array.isArray(path) ? path : path?.coordinates
  return Array.isArray(points) ? points : []
}

/**
 * 초안 문제 목록 → [{step, level: 'error'|'warning', field, message}]. step 0 은 경로 전체에 대한 문제
 *   error: 문장, 단계 수 2~30, 카메라 빈 칸, 카메라 범위 (bearing 0 이상 360 미만, pitch 0~85, zoom 0~22)
 *   warning: 경로 진행 순서가 뒤로 감, 이웃한 두 단계가 3m 미만
 * 범위는 서버 schemas/common.py Camera, domain/steps.py 와 같다
 */
export function checkDraft(steps, path) {
  const items = Array.isArray(steps) ? steps : []
  const route = pathCoordinates(path)
  const out = instructionIssues(items)

  if (items.length < 2) out.push({ step: 0, level: 'error', field: 'steps', message: '안내 단계는 2개 이상이어야 합니다.' })
  if (items.length > 30) out.push({ step: 0, level: 'error', field: 'steps', message: '안내 단계는 30개 이하여야 합니다.' })

  items.forEach((step, index) => {
    const missing = emptyCameraFields(step.camera)
    if (missing.length) {
      const field = missing[0]
      out.push({ step: index + 1, level: 'error', field: 'camera', message: `${index + 1}단계 카메라의 ${field} 칸이 비어 있습니다.` })
    }
    if (step.camera) {
      const limits = { bearing: [0, 360, false], pitch: [0, 85, true], zoom: [0, 22, true] }
      for (const [field, [min, max, inclusiveMax]] of Object.entries(limits)) {
        const value = step.camera[field]
        if (value === '' || value === null || value === undefined) continue
        const number = Number(value)
        if (!Number.isFinite(number) || number < min || (inclusiveMax ? number > max : number >= max)) {
          out.push({ step: index + 1, level: 'error', field: 'camera', message: `${index + 1}단계 카메라의 ${field} 값이 허용 범위를 벗어났습니다.` })
        }
      }
    }
  })

  if (route.length < 2) return out
  let previousFraction = null
  let previousPoint = null
  items.forEach((step, index) => {
    const point = stepPoint(step)
    if (!point) return
    const progress = fractionOnPath(route, point)
    if (previousFraction != null && progress + 1e-6 < previousFraction) {
      out.push({ step: index + 1, level: 'warning', field: 'location', message: `${index + 1}단계가 ${index}단계보다 경로 앞쪽에 있습니다.` })
    }
    if (previousPoint && distanceM(previousPoint, point) < MIN_STEP_GAP_M) {
      out.push({ step: index + 1, level: 'warning', field: 'location', message: `${index}단계와 ${index + 1}단계 지점이 거의 같습니다.` })
    }
    previousFraction = progress
    previousPoint = point
  })
  return out
}
