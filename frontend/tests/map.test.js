// js/map.js 중 DOM 없이 도는 규칙 단위 테스트 (대체 지도 전환, 프론트 작성 가이드 7.2)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  BASEMAP_TIMEOUT_MS, ATTRIBUTION_OPTIONS, CONTEXT_ATTRIBUTION, attributionPosition,
  createBasemapWatch, isBasemapError, decodeCampusContext, campusStyle, flyTo,
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

/** 가짜 시계: setTimeout 을 기억만 하고, tick(ms) 로 시간을 흘린다 */
function fakeTimers() {
  let now = 0, id = 0
  const jobs = new Map()
  return {
    setTimeout(fn, ms) { jobs.set(++id, { at: now + ms, fn }); return id },
    clearTimeout(k) { jobs.delete(k) },
    tick(ms) {
      now += ms
      for (const [k, j] of [...jobs]) if (j.at <= now) { jobs.delete(k); j.fn() }
    },
  }
}

test('배경 지도 스타일이 8초 안에 안 오면 저장해 둔 캠퍼스 지도로 바꾼다', () => {
  // 1) 8초 동안 load 가 없으면 'timeout' 으로 한 번만 바꾼다
  const timers = fakeTimers()
  const calls = []
  const watch = createBasemapWatch((r) => calls.push(r), { timers })
  timers.tick(BASEMAP_TIMEOUT_MS - 1) // 7.999초: 아직
  assert.deepEqual(calls, [])
  timers.tick(1)                      // 8초: 바꾼다
  assert.deepEqual(calls, ['timeout'])
  assert.equal(watch.fallen, true)
  assert.equal(watch.error({ sourceId: 'openmaptiles' }), false) // 이미 바꿨으면 다시 바꾸지 않는다
  assert.deepEqual(calls, ['timeout'])

  // 2) 8초 안에 load 가 오면 바꾸지 않는다
  const t2 = fakeTimers()
  const calls2 = []
  const w2 = createBasemapWatch((r) => calls2.push(r), { timers: t2 })
  t2.tick(3000)
  w2.loaded()
  t2.tick(10000)
  assert.deepEqual(calls2, [])
  assert.equal(w2.fallen, false)
})

test('배경 지도 타일 오류는 대체 지도로 바꾸고, 우리 레이어(lm-*) 오류는 바꾸지 않는다', () => {
  // 판단 규칙 (styleLoaded = 배경 지도 load 이벤트를 받았는가)
  assert.equal(isBasemapError({ sourceId: 'openmaptiles' }, true), true)   // 배경 지도 타일 오류 (load 뒤 인터넷 끊김)
  assert.equal(isBasemapError({ sourceId: 'lm-route' }, true), false)      // 우리 레이어
  assert.equal(isBasemapError({ sourceId: 'lm-buildings' }, false), false) // 우리 레이어는 load 전이라도 아니다
  assert.equal(isBasemapError({ error: new Error('style') }, false), true) // sourceId 없음 + load 전 = 스타일 주소 실패
  assert.equal(isBasemapError({ error: new Error('Layer already exists') }, true), false) // load 뒤 = 우리 코드 오류

  // 감시와 함께: lm- 오류는 무시, 배경 타일 오류는 'error' 로 바로 (8초를 기다리지 않음)
  const timers = fakeTimers()
  const calls = []
  const watch = createBasemapWatch((r) => calls.push(r), { timers })
  watch.loaded()
  assert.equal(watch.error({ sourceId: 'lm-route' }), false)
  assert.deepEqual(calls, [])
  assert.equal(watch.error({ sourceId: 'openmaptiles' }), true)
  assert.deepEqual(calls, ['error'])
})

test('loadCampusContext: 원점 + 정수 x 단위 → [경도, 위도]', () => {
  // 검산: 원점 [128.09, 35.14], 단위 0.00001도
  //   x=10 → 128.09 + 10 x 0.00001 = 128.0901,  y=20 → 35.14 + 20 x 0.00001 = 35.1402
  //   x=3, y=7 → 128.09003, 35.14007 (소수 6자리 반올림이라 0.1+0.2 같은 부동소수 꼬리가 없다)
  const raw = {
    o: [128.09, 35.14], u: 0.00001,
    buildings: [[0, 0, 10, 0, 10, 20]],            // 닫히지 않은 다각형 → 첫 점으로 닫는다
    green: [[0, 0, 3, 7, 0, 7, 0, 0]],              // 이미 닫힌 다각형 → 그대로
    water: [],
    roads: [[2, 0, 0, 3, 7]],                        // 첫 값 2 = 간선 등급
    paths: [[10, 20, 3, 7]],
  }
  const c = decodeCampusContext(raw)
  for (const k of ['green', 'water', 'buildings', 'roads', 'paths']) assert.equal(c[k].type, 'FeatureCollection')

  assert.deepEqual(c.buildings.features[0].geometry, {
    type: 'Polygon',
    coordinates: [[[128.09, 35.14], [128.0901, 35.14], [128.0901, 35.1402], [128.09, 35.14]]],
  })
  assert.equal(c.green.features[0].geometry.coordinates[0].length, 4)
  assert.deepEqual(c.green.features[0].geometry.coordinates[0][1], [128.09003, 35.14007])
  assert.equal(c.water.features.length, 0)
  assert.deepEqual(c.roads.features[0].properties, { grade: 2 })
  assert.deepEqual(c.roads.features[0].geometry, { type: 'LineString', coordinates: [[128.09, 35.14], [128.09003, 35.14007]] })
  assert.deepEqual(c.paths.features[0].geometry.coordinates, [[128.0901, 35.1402], [128.09003, 35.14007]])

  // 실제 파일: 첫 건물 첫 점 (493, 1580) → [128.09 + 0.00493, 35.14 + 0.0158] = [128.09493, 35.1558]
  const real = decodeCampusContext(JSON.parse(readFileSync(new URL('../data/osm_context_gnu.json', import.meta.url), 'utf8')))
  assert.deepEqual(real.buildings.features[0].geometry.coordinates[0][0], [128.09493, 35.1558])
  assert.equal(real.buildings.features.length, 94)
})

test('대체 지도 스타일: 소스, 레이어 id 는 lm- 로 시작하고 출처 표기와 토큰 색을 쓴다', () => {
  const ctx = decodeCampusContext({ o: [128.09, 35.14], u: 0.00001, buildings: [], green: [], water: [], roads: [], paths: [] })
  const style = campusStyle(ctx, (name) => `color(${name})`)
  assert.equal(style.version, 8)
  for (const id of Object.keys(style.sources)) {
    assert.ok(id.startsWith('lm-'), id)
    assert.equal(style.sources[id].attribution, CONTEXT_ATTRIBUTION)
  }
  for (const l of style.layers) assert.ok(l.id.startsWith('lm-'), l.id)
  assert.equal(style.glyphs, undefined) // 글자 레이어 없음 → 외부 글꼴 주소 없음 (CSP)
  assert.equal(style.layers[0].paint['background-color'], 'color(--map-ground)')
})

test('flyTo: 동작 줄이기를 켜면 jumpTo, 아니면 flyTo. 빈 칸은 넘기지 않는다', () => {
  const calls = []
  const map = { flyTo: (v) => calls.push(['fly', v]), jumpTo: (v) => calls.push(['jump', v]) }
  const view = { center: [128.0994, 35.1532], bearing: 168.2, pitch: 60, zoom: 17.5 }

  flyTo(map, view) // Node 에는 matchMedia 가 없다 → 동작 줄이기 아님
  flyTo(map, { zoom: 18, bearing: undefined })
  globalThis.matchMedia = (q) => ({ matches: q === '(prefers-reduced-motion: reduce)' })
  try { flyTo(map, view) } finally { delete globalThis.matchMedia }
  flyTo(null, view) // 지도를 못 만든 화면(null)에서도 오류 없이 넘어간다

  assert.deepEqual(calls, [['fly', view], ['fly', { zoom: 18 }], ['jump', view]])
})
