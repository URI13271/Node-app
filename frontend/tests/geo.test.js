// js/geo.js 단위 테스트. 실행: frontend 폴더에서 npm test (Node.js 20 이상, 설치 없음)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { distanceM, fractionOnPath, nearestVertex, pathLengthM, pathUntil, pointAlong } from '../js/geo.js'

const near = (actual, expected, tolerance = 0.01) => {
  assert.ok(Math.abs(actual - expected) <= tolerance, `${actual} 값이 ${expected} ± ${tolerance} 범위가 아닙니다`)
}

test('distanceM: 같은 점은 0m, 위도 0.001도 차이는 약 111m', () => {
  assert.equal(distanceM([128.1, 35.15], [128.1, 35.15]), 0)
  near(distanceM([0, 0], [0, 0.001]), 111.2, 0.2)
})

test('pathLengthM: 이웃한 점 사이 거리의 합', () => {
  const path = [[0, 0], [0.001, 0], [0.001, 0.001]]
  near(pathLengthM(path), distanceM(path[0], path[1]) + distanceM(path[1], path[2]))
  assert.equal(pathLengthM([]), 0)
  assert.equal(pathLengthM([[0, 0]]), 0)
})

test('nearestVertex: 경로에서 가장 가까운 꼭짓점 번호를 찾는다', () => {
  assert.equal(nearestVertex([[0, 0], [0.001, 0], [0.002, 0]], [0.0011, 0]), 1)
  assert.equal(nearestVertex([], [0, 0]), -1)
})

test('pointAlong: 경로 비율에 해당하는 점을 찾고 비율을 0~1로 제한한다', () => {
  const path = [[0, 0], [0.002, 0]]
  near(pointAlong(path, 0.5)[0], 0.001, 1e-9)
  assert.deepEqual(pointAlong(path, -1), path[0])
  assert.deepEqual(pointAlong(path, 2), path[1])
  assert.equal(pointAlong([], 0.5), null)
})

test('fractionOnPath: 시작은 0, 끝은 1, 경로 밖 점은 가장 가까운 지점을 기준으로 한다', () => {
  const path = [[0, 0], [0.002, 0]]
  near(fractionOnPath(path, [0, 0]), 0, 1e-9)
  near(fractionOnPath(path, [0.002, 0]), 1, 1e-9)
  near(fractionOnPath(path, [0.001, 0.001]), 0.5, 1e-4)
  near(fractionOnPath(path, [-0.001, 0.001]), 0, 1e-9)
  assert.equal(fractionOnPath([[0, 0]], [1, 1]), 0)
})

test('pathUntil: t=0.5이면 경로 길이가 절반인 선을 돌려준다', () => {
  const path = [[0, 0], [0.001, 0], [0.003, 0]]
  const half = pathUntil(path, 0.5)
  assert.equal(half.length, 3)
  near(half.at(-1)[0], 0.0015, 1e-9)
  near(pathLengthM(half), pathLengthM(path) / 2, 1e-6)
  assert.deepEqual(pathUntil([], 0.5), [])
})
