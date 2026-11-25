// js/draft-checks.js 단위 테스트 (프론트 작성 가이드 7.5 규칙)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { MIN_STEP_GAP_M, MAX_INSTRUCTION_CHARS, checkDraft, cleanInstruction, emptyCameraFields, instructionIssues } from '../js/draft-checks.js'

test('최소 단계 간격은 3m, 문장은 200자까지', () => {
  assert.equal(MIN_STEP_GAP_M, 3)
  assert.equal(MAX_INSTRUCTION_CHARS, 200)
})

test('cleanInstruction: 제어 문자를 지우고 앞뒤 공백을 뺀다 (줄바꿈은 남김)', () => {
  assert.equal(cleanInstruction('  a\u0007b\n c  '), 'ab\n c')
  assert.equal(cleanInstruction(null), '')
})

test('instructionIssues: 빈 문장, 공백만, 200자 초과는 error. 200자 정확히는 통과', () => {
  const issues = instructionIssues([
    { instruction: '정상 문장' },
    { instruction: '   ' },
    { instruction: 'a'.repeat(200) },
    { instruction: 'a'.repeat(201) },
  ])
  assert.deepEqual(issues.map((x) => [x.step, x.level]), [[2, 'error'], [4, 'error']])
  assert.match(issues[1].message, /201자/)
})

test('emptyCameraFields: 부분 입력만 오류로 보고 전체 빈 값은 자동 카메라로 허용', () => {
  assert.deepEqual(emptyCameraFields(null), [])
  assert.deepEqual(emptyCameraFields({ bearing: '', pitch: '', zoom: '' }), [])
  assert.deepEqual(emptyCameraFields({ bearing: 20, pitch: '', zoom: 18 }), ['pitch'])
})

test('checkDraft: 카메라 칸이 일부 비면 error', () => {
  const issues = checkDraft([
    { instruction: '첫 단계', location: { coordinates: [0.001, 0] }, camera: { bearing: 0, pitch: '', zoom: 18 } },
    { instruction: '둘째 단계', location: { coordinates: [0.003, 0] }, camera: null },
  ], [[0, 0], [0.004, 0]])
  assert.deepEqual(issues.map((issue) => [issue.step, issue.level]), [[1, 'error']])
  assert.match(issues[0].message, /pitch/)
})

test('checkDraft: 카메라 값은 API 범위 안이어야 한다', () => {
  const issues = checkDraft([
    { instruction: '첫 단계', location: { coordinates: [0, 0] }, camera: { bearing: 360, pitch: 0, zoom: 18 } },
    { instruction: '둘째 단계', location: { coordinates: [0.001, 0] }, camera: { bearing: 180, pitch: 86, zoom: 18 } },
  ], [[0, 0], [0.002, 0]])
  assert.equal(issues.filter((issue) => issue.field === 'camera').length, 2)
})

test('checkDraft: 단계 위치가 뒤로 가면 warning', () => {
  const issues = checkDraft([
    { instruction: '첫 단계', location: { coordinates: [0.003, 0] }, camera: null },
    { instruction: '둘째 단계', location: { coordinates: [0.001, 0] }, camera: null },
  ], [[0, 0], [0.004, 0]])
  assert.equal(issues[0].level, 'warning')
  assert.equal(issues[0].step, 2)
})

test('checkDraft: 이웃한 두 단계가 3m 미만이면 warning', () => {
  const issues = checkDraft([
    { instruction: '첫 단계', location: { coordinates: [0.001, 0] }, camera: null },
    { instruction: '둘째 단계', location: { coordinates: [0.00101, 0] }, camera: null },
  ], [[0, 0], [0.004, 0]])
  assert.equal(issues[0].level, 'warning')
  assert.match(issues[0].message, /거의 같습니다/)
})
