// js/map.js 중 DOM 없이 도는 규칙 단위 테스트 (대체 지도 전환, 프론트 작성 가이드 7.2)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  BASEMAP_TIMEOUT_MS, TILE_ERROR_LIMIT, TILE_ERROR_WINDOW_MS, ATTRIBUTION_OPTIONS, CONTEXT_ATTRIBUTION, attributionPosition,
  createBasemapWatch, isBasemapError, decodeCampusContext, campusContextStyle, flyTo,
} from '../js/map.js'

test('배경 지도 대기 시간은 8초', () => {
  assert.equal(BASEMAP_TIMEOUT_MS, 8000)
})

test('출처 표기는 접을 수 있게 두고 정보 페이지로 연결한다', () => {
  assert.equal(ATTRIBUTION_OPTIONS.compact, true)
  assert.match(ATTRIBUTION_OPTIONS.customAttribution, /href="\/about"/)
})

test('출처 위치: 3D 안내 화면은 오른쪽 위, 나머지는 오른쪽 아래', () => {
  const box = (cls) => ({ classList: { contains: (c) => c === cls } })
  assert.equal(attributionPosition(box('map-full')), 'top-right')
  assert.equal(attributionPosition(box('map-preview')), 'bottom-right')
})

/** 가짜 시계: setTimeout 을 기억만 하고, tick(ms) 로 시간을 흘린다. now() 는 흘린 시간 */
function fakeTimers() {
  let now = 0, id = 0
  const jobs = new Map()
  return {
    now: () => now,
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
  assert.equal(watch.usingFallback, true)
  assert.equal(watch.onError({ sourceId: 'openmaptiles' }), false) // 이미 바꿨으면 다시 바꾸지 않는다
  assert.deepEqual(calls, ['timeout'])

  // 2) 8초 안에 load 가 오면 바꾸지 않는다
  const t2 = fakeTimers()
  const calls2 = []
  const w2 = createBasemapWatch((r) => calls2.push(r), { timers: t2 })
  t2.tick(3000)
  w2.onLoad()
  t2.tick(10000)
  assert.deepEqual(calls2, [])
  assert.equal(w2.usingFallback, false)
})

test('배경 지도 타일 오류는 대체 지도로 바꾸고, 우리 레이어(lm-*) 오류는 바꾸지 않는다', () => {
  // 판단 규칙 (basemapLoaded = 배경 지도 load 이벤트를 받았는가)
  assert.equal(isBasemapError({ sourceId: 'openmaptiles' }, true), true)   // 배경 지도 타일 오류 (load 뒤 인터넷 끊김)
  assert.equal(isBasemapError({ sourceId: 'lm-route' }, true), false)      // 우리 레이어
  assert.equal(isBasemapError({ sourceId: 'lm-buildings' }, false), false) // 우리 레이어는 load 전이라도 아니다
  assert.equal(isBasemapError({ error: new Error('style') }, false), true) // sourceId 없음 + load 전 = 스타일 주소 실패
  assert.equal(isBasemapError({ error: new Error('Layer already exists') }, true), false) // load 뒤 = 우리 코드 오류

  // load 전: 배경 지도 오류는 'error' 로 바로 (8초를 기다리지 않음)
  const t0 = fakeTimers()
  const calls0 = []
  const w0 = createBasemapWatch((r) => calls0.push(r), { timers: t0, now: t0.now, isOffline: () => false })
  assert.equal(w0.onError({ sourceId: 'openmaptiles' }), true)
  assert.deepEqual(calls0, ['error'])

  // load 뒤: lm- 오류는 무시, 배경 타일 오류는 5초 안에 3번 쌓여야 바꾼다
  const timers = fakeTimers()
  const calls = []
  const watch = createBasemapWatch((r) => calls.push(r), { timers, now: timers.now, isOffline: () => false })
  watch.onLoad()
  assert.equal(watch.onError({ sourceId: 'lm-route' }), false)
  for (let i = 1; i < TILE_ERROR_LIMIT; i++) {
    assert.equal(watch.onError({ sourceId: 'openmaptiles' }), false) // 1, 2번째: 타일 1장의 일시 오류일 수 있다
    timers.tick(1000)
  }
  assert.deepEqual(calls, [])
  assert.equal(watch.onError({ sourceId: 'openmaptiles' }), true)  // 3번째 (5초 안)
  assert.deepEqual(calls, ['error'])
})

test('load 뒤 타일 오류: 띄엄띄엄 나면 바꾸지 않고, 오프라인이면 바로 바꾼다', () => {
  // 5초 넘게 간격을 두고 나는 오류는 쌓이지 않는다
  const timers = fakeTimers()
  const calls = []
  const watch = createBasemapWatch((r) => calls.push(r), { timers, now: timers.now, isOffline: () => false })
  watch.onLoad()
  for (let i = 0; i < 10; i++) {
    assert.equal(watch.onError({ sourceId: 'openmaptiles' }), false)
    timers.tick(TILE_ERROR_WINDOW_MS / 2 + 1) // 2.5초 남짓마다 1번 → 5초 폭 안에는 늘 2번 이하
  }
  assert.deepEqual(calls, [])

  // 오프라인: 첫 오류에 바로 바꾼다
  let offline = false
  const t2 = fakeTimers()
  const calls2 = []
  const w2 = createBasemapWatch((r) => calls2.push(r), { timers: t2, now: t2.now, isOffline: () => offline })
  w2.onLoad()
  assert.equal(w2.onError({ sourceId: 'openmaptiles' }), false)
  offline = true
  assert.equal(w2.onError({ sourceId: 'openmaptiles' }), true)
  assert.deepEqual(calls2, ['error'])
})

test('resume: 전환을 취소하고 다시 감시한다', () => {
  // load 전에 취소하면 대기 시간을 다시 잰다 (캠퍼스 지도를 못 받아 배경 지도를 기다리는 경우)
  const timers = fakeTimers()
  const calls = []
  const watch = createBasemapWatch((r) => calls.push(r), { timers, now: timers.now, isOffline: () => false })
  timers.tick(BASEMAP_TIMEOUT_MS)
  assert.deepEqual(calls, ['timeout'])
  watch.resume()
  assert.equal(watch.usingFallback, false)
  timers.tick(BASEMAP_TIMEOUT_MS - 1)
  assert.deepEqual(calls, ['timeout'])
  timers.tick(1)
  assert.deepEqual(calls, ['timeout', 'timeout'])

  // load 뒤에 취소하면 (캠퍼스 지도를 받는 사이 배경 지도가 뜬 경우) 시계는 다시 걸지 않고 오류 횟수는 0부터
  const t2 = fakeTimers()
  const calls2 = []
  const w2 = createBasemapWatch((r) => calls2.push(r), { timers: t2, now: t2.now, isOffline: () => false })
  t2.tick(BASEMAP_TIMEOUT_MS)
  w2.onLoad()
  assert.equal(w2.basemapLoaded, true)
  w2.resume()
  t2.tick(BASEMAP_TIMEOUT_MS * 2)
  assert.deepEqual(calls2, ['timeout'])
  for (let i = 1; i < TILE_ERROR_LIMIT; i++) assert.equal(w2.onError({ sourceId: 'openmaptiles' }), false)
  assert.equal(w2.onError({ sourceId: 'openmaptiles' }), true)
  assert.deepEqual(calls2, ['timeout', 'error'])
})

test('decodeCampusContext: 원점 + 정수 x 단위 → [경도, 위도]', () => {
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
  assert.ok(real.buildings.features.length > 0) // 건물 수는 데이터를 새로 받으면 바뀌므로 개수는 고정하지 않는다
})

test('대체 지도 스타일: 소스, 레이어 id 는 lm- 로 시작하고 출처 표기와 토큰 색을 쓴다', () => {
  const ctx = decodeCampusContext({ o: [128.09, 35.14], u: 0.00001, buildings: [], green: [], water: [], roads: [], paths: [] })
  const style = campusContextStyle(ctx, (name) => `color(${name})`)
  assert.equal(style.version, 8)
  for (const id of Object.keys(style.sources)) {
    assert.ok(id.startsWith('lm-'), id)
    assert.equal(style.sources[id].attribution, CONTEXT_ATTRIBUTION)
  }
  for (const l of style.layers) {
    assert.ok(l.id.startsWith('lm-'), l.id)
    if (l.source) assert.ok(l.id === l.source || l.id.startsWith(`${l.source}-`), `${l.id} 는 소스 ${l.source} 이름을 따른다`)
  }
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

test('drawRoute, drawBuildings: 스타일 준비 전에는 기록만 하고 style.load 에서 그린다. 그 뒤에는 바로 갱신한다', async () => {
  const { mock } = await import('node:test')
  const { createMap, drawBuildings, drawRoute } = await import('../js/map.js')
  mock.timers.enable({ apis: ['setTimeout'] }) // 배경 지도 8초 감시가 테스트를 붙잡지 않게
  const saved = { maplibregl: globalThis.maplibregl, document: globalThis.document, getComputedStyle: globalThis.getComputedStyle }
  const calls = []
  class FakeMap {
    constructor() { this.handlers = {}; this.sources = {}; this.layers = [] }
    on(event, fn) { (this.handlers[event] ||= []).push(fn) }
    once(event, fn) { this.on(event, fn) }
    emit(event) { for (const fn of this.handlers[event] || []) fn({}) }
    addControl() {}
    isStyleLoaded() { return false } // 타일을 받는 중에는 false 다. 이 값에 기대지 않아야 한다
    getSource(id) { return this.sources[id] }
    addSource(id, spec) { this.sources[id] = { data: spec.data, attribution: spec.attribution, setData(d) { this.data = d; calls.push(['setData', id]) } } }
    getLayer(id) { return this.layers.find((l) => l.id === id) }
    addLayer(layer, beforeId) { calls.push(['addLayer', layer.id, beforeId]); const i = beforeId ? this.layers.findIndex((l) => l.id === beforeId) : -1; i < 0 ? this.layers.push(layer) : this.layers.splice(i, 0, layer) }
  }
  globalThis.maplibregl = { Map: FakeMap, NavigationControl: class {}, AttributionControl: class {} }
  globalThis.document = { documentElement: {} }
  globalThis.getComputedStyle = () => ({ getPropertyValue: () => '#000' })
  try {
    const map = createMap({ classList: { contains: () => false } })
    const route = { path: { type: 'LineString', coordinates: [[128.1, 35.15], [128.101, 35.15], [128.102, 35.15]] } }

    drawRoute(map, route, 0.5)
    assert.equal(calls.length, 0, '스타일 준비 전에는 레이어를 더하지 않는다')

    map.emit('style.load')
    assert.deepEqual(map.layers.map((l) => l.id), ['lm-route', 'lm-route-done'])
    assert.equal(map.sources['lm-route-done'].data.features[0].geometry.coordinates.length, 2, '절반 지점까지 자른 선')

    calls.length = 0
    drawRoute(map, route, 1)
    assert.deepEqual(calls, [['setData', 'lm-route'], ['setData', 'lm-route-done']], 'isStyleLoaded 가 false 여도 바로 갱신')

    drawBuildings(map, { type: 'FeatureCollection', features: [], attributions: ['© OpenStreetMap contributors', '공공 건물 데이터'] })
    assert.deepEqual(map.layers.map((l) => l.id), ['lm-buildings', 'lm-route', 'lm-route-done'], '건물은 경로 선 아래')
    assert.equal(map.sources['lm-buildings'].attribution, '건물: © OpenStreetMap contributors, 공공 건물 데이터', '건물 출처는 (i) 출처 표기로')
  } finally {
    Object.assign(globalThis, saved)
    mock.timers.reset()
  }
})

test('buildingAttribution: 건물 출처를 (i) 표기 문자열로. 없으면 빈 문자열, HTML 특수문자는 바꾼다', async () => {
  const { buildingAttribution } = await import('../js/map.js')
  assert.equal(buildingAttribution({ attributions: ['© OpenStreetMap contributors', '직접 조사'] }), '건물: © OpenStreetMap contributors, 직접 조사')
  assert.equal(buildingAttribution({ attributions: [] }), '')
  assert.equal(buildingAttribution(null), '')
  assert.equal(buildingAttribution({ attributions: ['<b>x</b>'] }), '건물: &lt;b&gt;x&lt;/b&gt;')
})

test('collapseAttribution: 펼쳐진 compact 출처 표기만 접는다', async () => {
  const { collapseAttribution, ATTRIBUTION_AUTO_COLLAPSE_MS } = await import('../js/map.js')
  assert.ok(ATTRIBUTION_AUTO_COLLAPSE_MS >= 3000, '읽을 시간은 남긴다')
  const classes = new Set(['maplibregl-ctrl-attrib', 'maplibregl-compact', 'maplibregl-compact-show'])
  const el = { classList: { remove: (c) => classes.delete(c) } }
  const box = (found) => ({ querySelector: (sel) => (found && sel.split('.').filter(Boolean).every((c) => classes.has(c)) ? el : null) })
  assert.equal(collapseAttribution(box(true)), true)
  assert.equal(classes.has('maplibregl-compact-show'), false)
  assert.equal(collapseAttribution(box(true)), false, '이미 접혔으면 그대로')
  assert.equal(collapseAttribution(box(false)), false)
  assert.equal(collapseAttribution(null), false)
})
