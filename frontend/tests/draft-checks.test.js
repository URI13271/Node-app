// js/draft-checks.js 단위 테스트 (프론트 작성 가이드 7.5 규칙)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { MIN_STEP_GAP_M, MAX_INSTRUCTION, cleanInstruction, instructionIssues } from '../js/draft-checks.js'

test('최소 단계 간격은 3m, 문장은 200자까지', () => {
  assert.equal(MIN_STEP_GAP_M, 3)
  assert.equal(MAX_INSTRUCTION, 200)
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

test.todo('카메라 칸이 비어 있으면 error (빈 칸이 0으로 저장되는 것 방지)')
test.todo('단계 순서와 경로 진행 순서가 어긋나면 warning')
test.todo('두 단계 사이가 3m 미만이면 warning')
