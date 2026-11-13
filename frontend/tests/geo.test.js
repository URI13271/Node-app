// js/geo.js 단위 테스트. 실행: frontend 폴더에서 npm test (Node.js 20 이상, 설치 없음)
// 함수를 구현하면 test.todo 를 test 로 바꾸고 기대값을 넣는다.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { distanceM } from '../js/geo.js'

test('geo.js 를 불러온다', () => {
  assert.equal(typeof distanceM, 'function')
})

test.todo('distanceM: 같은 점은 0m, 위도 0.001도 차이는 약 111m')
test.todo('fractionOnPath: 시작점 0, 끝점 1, 경로 밖 점은 가장 가까운 지점 기준')
test.todo('pathUntil: t=0.5 이면 길이가 절반인 선')
