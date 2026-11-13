// js/map.js 중 DOM 없이 도는 규칙 단위 테스트 (대체 지도 전환, 프론트 작성 가이드 7.2)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { BASEMAP_TIMEOUT_MS, ATTRIBUTION_OPTIONS, attributionPosition } from '../js/map.js'

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

test.todo('배경 지도 스타일이 8초 안에 안 오면 저장해 둔 캠퍼스 지도로 바꾼다')
test.todo('배경 지도 타일 오류는 대체 지도로 바꾸고, 우리 레이어(lm-*) 오류는 바꾸지 않는다')
test.todo('loadCampusContext: 원점 + 정수 x 단위 → [경도, 위도]')
