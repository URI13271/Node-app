// js/map.js 중 DOM 없이 도는 규칙 단위 테스트 (대체 지도 전환, 프론트 작성 가이드 7.2)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  BASEMAP_TIMEOUT_MS, ATTRIBUTION_OPTIONS, attributionPosition,
  shouldFallbackFromMapError, shouldFallbackOnTimeout, unpackCampusContext,
} from '../js/map.js'

test('배경 지도 대기 시간은 8초', () => {
  assert.equal(BASEMAP_TIMEOUT_MS, 8000)
})

test('출처 표기는 접을 수 있게 두고 정보 페이지로 연결한다', () => {
  assert.equal(ATTRIBUTION_OPTIONS.compact, true)
  assert.match(ATTRIBUTION_OPTIONS.customAttribution, /href="\/about\.html"/)
})

test('출처 위치: 3D 안내 화면은 오른쪽 위, 나머지는 오른쪽 아래', () => {
  const box = (cls) => ({ classList: { contains: (c) => c === cls } })
  assert.equal(attributionPosition(box('map-full')), 'top-right')
  assert.equal(attributionPosition(box('map-preview')), 'bottom-right')
})

test('8초 안에 배경 지도가 오지 않았을 때만 대체 지도로 바꾼다', () => {
  assert.equal(shouldFallbackOnTimeout({ loaded: false, fallback: false }), true)
  assert.equal(shouldFallbackOnTimeout({ loaded: true, fallback: false }), false)
  assert.equal(shouldFallbackOnTimeout({ loaded: false, fallback: true }), false)
})

test('외부 지도 오류는 대체하고 lm-* 오버레이 오류는 유지한다', () => {
  assert.equal(shouldFallbackFromMapError({ sourceId: 'basemap' }), true)
  assert.equal(shouldFallbackFromMapError({ sourceId: 'lm-route' }), false)
  assert.equal(shouldFallbackFromMapError({}), true)
})

test('압축 캠퍼스 지도 좌표를 GeoJSON으로 푼다', () => {
  const context = unpackCampusContext({
    o: [10, 20], u: 0.00001,
    buildings: [[1, 2, 3, 2, 3, 4]],
    roads: [[2, 0, 0, 1, 1]],
    paths: [[2, 3, 4, 5]],
  })
  assert.deepEqual(context.buildings.features[0].geometry.coordinates[0], [
    [10.00001, 20.00002], [10.00003, 20.00002], [10.00003, 20.00004], [10.00001, 20.00002],
  ])
  assert.deepEqual(context.roads.features[0].properties, { road_class: 2 })
  assert.deepEqual(context.roads.features[0].geometry.coordinates, [[10, 20], [10.00001, 20.00001]])
  assert.equal(context.paths.features[0].geometry.type, 'LineString')
})
