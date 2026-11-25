// 3D 지도 (MapLibre). 화면 HTML 에서 maplibre-gl.js 를 먼저 불러야 전역 maplibregl 이 생긴다.
// 배경 지도: OpenFreeMap "liberty" (키, 가입 없음, SLA 없음) [검증 필요: 이용 조건 변경 여부]
// 배경 지도 주소를 바꾸면 backend/app/frontend.py 의 CSP 허용 주소도 같이 바꾼다.
import { pathUntil } from './geo.js'
import { toast } from './util.js'

export const DEFAULT_BASEMAP_URL = 'https://tiles.openfreemap.org/styles/liberty'
export const BASEMAP_TIMEOUT_MS = 8000 // 이 시간 안에 배경 지도가 안 오면 저장해 둔 캠퍼스 지도로 바꾼다
// 배경 지도가 뜬 뒤에는 타일 오류가 이 시간 안에 이 횟수만큼 쌓여야 바꾼다 (타일 1장의 일시 오류로 지도 전체를 바꾸지 않게)
export const TILE_ERROR_LIMIT = 3
export const TILE_ERROR_WINDOW_MS = 5000
export const CAMPUS_CONTEXT_URL = '/data/osm_context_gnu.json' // 저장해 둔 캠퍼스 지도 (형식은 data/README.md)
export const CAMPUS_CONTEXT_BOUNDS = [128.0948, 35.1505, 128.1022, 35.1558] // [서, 남, 동, 북]
export const CONTEXT_ATTRIBUTION = '© OpenMapTiles © OpenStreetMap contributors (저장해 둔 캠퍼스 지도)'  // 대체 지도 source 의 attribution 에 넣어야 모서리에 표시된다

// 지도 출처 표기 (OSM ODbL, OpenFreeMap 조건). 배경 지도 스타일에 든 출처는 MapLibre 가 자동으로 모은다.
// compact: 처음에는 펼쳐 보이고, 지도를 끌면 (i) 버튼으로 접힌다 (MapLibre 4.7.1 동작, 배포 파일에서 확인).
// 전체 목록은 정적 정보 페이지 about.html. 이 링크 문자열은 MapLibre 가 innerHTML 로 넣으므로 서버 글자를 섞지 않는다.
export const ATTRIBUTION_OPTIONS = {
  compact: true,
  customAttribution: '<a href="/about.html">출처 전체</a>',
}

/** 출처 표기 위치. 3D 안내 화면(.map-full)은 아래 안내 카드가 덮으므로 오른쪽 위 */
export function attributionPosition(container) {
  return container.classList.contains('map-full') ? 'top-right' : 'bottom-right'
}

// ---- 저장해 둔 캠퍼스 지도 (대체 지도) ----

/** 시작 시점을 안 줬을 때 보여 줄 곳: 저장해 둔 캠퍼스 지도 범위의 가운데 */
export const DEFAULT_VIEW = {
  center: [(CAMPUS_CONTEXT_BOUNDS[0] + CAMPUS_CONTEXT_BOUNDS[2]) / 2, (CAMPUS_CONTEXT_BOUNDS[1] + CAMPUS_CONTEXT_BOUNDS[3]) / 2],
  zoom: 16, pitch: 45, bearing: 0,
}

const round6 = (v) => Math.round(v * 1e6) / 1e6

/**
 * 저장 형식(data/README.md)을 GeoJSON 묶음으로 푼다. DOM 없이 도는 계산 함수 (tests/map.test.js)
 * 실제 좌표 = [o[0] + x * u, o[1] + y * u], 소수 6자리 반올림. 좌표는 [경도, 위도]
 * @returns {{green, water, buildings, roads, paths}} 각각 GeoJSON FeatureCollection
 */
export function decodeCampusContext(raw) {
  const [ox, oy] = raw.o
  const u = raw.u
  const points = (nums) => {
    const out = []
    for (let i = 0; i + 1 < nums.length; i += 2) out.push([round6(ox + nums[i] * u), round6(oy + nums[i + 1] * u)])
    return out
  }
  const ring = (nums) => {
    const pts = points(nums)
    const a = pts[0], z = pts[pts.length - 1]
    if (pts.length && (a[0] !== z[0] || a[1] !== z[1])) pts.push([...a]) // 닫히지 않은 다각형은 닫는다 (GeoJSON 규칙)
    return pts
  }
  const fc = (features) => ({ type: 'FeatureCollection', features })
  const feature = (geometry, properties = {}) => ({ type: 'Feature', properties, geometry })
  const polygons = (list = []) => fc(list.map((nums) => feature({ type: 'Polygon', coordinates: [ring(nums)] })))
  return {
    green: polygons(raw.green),
    water: polygons(raw.water),
    buildings: polygons(raw.buildings),
    // 도로: 첫 값은 등급 (2 간선, 1 동네 길, 0 단지 안 길)
    roads: fc((raw.roads || []).map(([grade, ...nums]) => feature({ type: 'LineString', coordinates: points(nums) }, { grade }))),
    paths: fc((raw.paths || []).map((nums) => feature({ type: 'LineString', coordinates: points(nums) }))),
  }
}

let contextPromise = null
/**
 * 저장해 둔 캠퍼스 지도를 받아 GeoJSON 묶음 {green, water, buildings, roads, paths} 으로 푼다.
 * 서버 API 가 아닌 같은 서버의 정적 파일이라 api.js 를 거치지 않는다.
 * 한 번 받으면 다시 받지 않는다 (실패하면 다음 호출에서 다시 시도)
 */
export function loadCampusContext() {
  contextPromise ||= fetch(CAMPUS_CONTEXT_URL)
    .then((res) => { if (!res.ok) throw new Error(`캠퍼스 지도 ${res.status}`); return res.json() })
    .then(decodeCampusContext)
    .catch((e) => { contextPromise = null; throw e })
  return contextPromise
}

/**
 * 대체 지도 스타일 (MapLibre style spec). 글자 레이어가 없어 glyphs 주소가 필요 없다 (CSP 추가 없음).
 * 소스, 레이어 id 는 lm-ctx-* (우리 레이어 접두 lm-). 출처 표기는 소스 attribution 으로 모서리에 뜬다.
 * 레이어 id 는 소스 id 와 같게, 같은 소스의 보조 레이어는 꼬리를 붙인다 (lm-ctx-roads, lm-ctx-roads-edge)
 * @param ctx   decodeCampusContext 결과
 * @param color 토큰 이름 → 색 값 함수. 화면에서는 cssVar
 *              (전환하는 순간의 테마 색을 읽는다. 전환 뒤 다크 모드를 바꿔도 지도 색은 그대로)
 */
export function campusContextStyle(ctx, color) {
  const src = (data) => ({ type: 'geojson', data, attribution: CONTEXT_ATTRIBUTION })
  const round = { 'line-cap': 'round', 'line-join': 'round' }
  return {
    version: 8,
    sources: {
      'lm-ctx-green': src(ctx.green), 'lm-ctx-water': src(ctx.water), 'lm-ctx-roads': src(ctx.roads),
      'lm-ctx-paths': src(ctx.paths), 'lm-ctx-buildings': src(ctx.buildings),
    },
    layers: [
      { id: 'lm-ctx-bg', type: 'background', paint: { 'background-color': color('--map-ground') } },
      { id: 'lm-ctx-green', type: 'fill', source: 'lm-ctx-green', paint: { 'fill-color': color('--map-grass') } },
      { id: 'lm-ctx-water', type: 'fill', source: 'lm-ctx-water', paint: { 'fill-color': color('--map-water') } },
      { id: 'lm-ctx-roads-edge', type: 'line', source: 'lm-ctx-roads', layout: round,
        paint: { 'line-color': color('--map-road-edge'), 'line-width': ['match', ['get', 'grade'], 2, 9, 1, 6, 4] } },
      { id: 'lm-ctx-roads', type: 'line', source: 'lm-ctx-roads', layout: round,
        paint: { 'line-color': color('--map-road'), 'line-width': ['match', ['get', 'grade'], 2, 7, 1, 4.5, 2.5] } },
      { id: 'lm-ctx-paths', type: 'line', source: 'lm-ctx-paths',
        paint: { 'line-color': color('--map-path'), 'line-width': 1.2, 'line-dasharray': [2, 2] } },
      { id: 'lm-ctx-buildings', type: 'fill', source: 'lm-ctx-buildings', paint: { 'fill-color': color('--map-ctx-bldg') } },
    ],
  }
}

// ---- 대체 지도 전환 판단 (DOM, 지도 객체 없이 테스트) ----

/**
 * 지도 error 이벤트가 배경 지도 쪽 오류인가.
 * - sourceId 가 lm- 로 시작: 우리 레이어 오류 → 아니다 (배경을 바꿔도 고쳐지지 않는다)
 * - 그 밖의 sourceId (배경 지도 타일, 소스): 그렇다
 * - sourceId 없음: 스타일을 아직 못 받았으면(스타일 주소 실패) 그렇다. 받은 뒤라면 우리 코드 오류로 본다
 */
export function isBasemapError(event, basemapLoaded) {
  const id = event?.sourceId
  if (typeof id === 'string' && id.startsWith('lm-')) return false
  if (id) return true
  return !basemapLoaded
}

/**
 * 배경 지도 감시. onFallback(이유) 를 한 번만 부른다.
 * - load 전: timeoutMs 안에 onLoad() 가 안 오면 'timeout', 배경 지도 오류가 나면 바로 'error'
 * - load 뒤: 배경 지도 타일 오류가 tileErrorWindowMs 안에 tileErrorLimit 번 쌓이거나, 오프라인이면 'error'
 * @param {(reason: 'timeout' | 'error') => void} onFallback
 * @param {object} [opt]
 * @param {number} [opt.timeoutMs]
 * @param {number} [opt.tileErrorLimit]     load 뒤 전환에 필요한 타일 오류 횟수
 * @param {number} [opt.tileErrorWindowMs]  그 횟수를 세는 시간 폭
 * @param {{setTimeout: Function, clearTimeout: Function}} [opt.timers]  테스트용 가짜 시계
 * @param {() => number} [opt.now]         현재 시각(ms). 테스트용
 * @param {() => boolean} [opt.isOffline]  오프라인인가. 테스트용
 */
export function createBasemapWatch(onFallback, {
  timeoutMs = BASEMAP_TIMEOUT_MS,
  tileErrorLimit = TILE_ERROR_LIMIT,
  tileErrorWindowMs = TILE_ERROR_WINDOW_MS,
  timers = globalThis,
  now = () => Date.now(),
  isOffline = () => globalThis.navigator?.onLine === false,
} = {}) {
  let basemapLoaded = false
  let usingFallback = false
  let timer = null
  let tileErrors = [] // load 뒤 배경 지도 타일 오류 시각
  const fallBack = (reason) => {
    if (usingFallback) return
    usingFallback = true
    timers.clearTimeout(timer)
    onFallback(reason)
  }
  const arm = () => { timer = timers.setTimeout(() => { if (!basemapLoaded) fallBack('timeout') }, timeoutMs) }
  arm()
  return {
    /** 배경 지도 load 이벤트 */
    onLoad() { basemapLoaded = true; timers.clearTimeout(timer) },
    /** 지도 error 이벤트. 이번 오류로 대체 지도로 바꾸면 true */
    onError(event) {
      if (usingFallback || !isBasemapError(event, basemapLoaded)) return false
      if (basemapLoaded && !isOffline()) {
        const t = now()
        tileErrors = tileErrors.filter((at) => t - at < tileErrorWindowMs)
        tileErrors.push(t)
        if (tileErrors.length < tileErrorLimit) return false
      }
      fallBack('error')
      return true
    },
    /**
     * 전환을 취소하고 다시 감시한다. 대체 지도로 바꾸기 직전에 배경 지도가 떴거나,
     * 저장해 둔 캠퍼스 지도를 받지 못해 배경 지도를 그대로 둘 때 부른다
     */
    resume() {
      usingFallback = false
      tileErrors = []
      if (!basemapLoaded) arm() // 아직 배경 지도가 안 떴으면 대기 시간을 다시 잰다
    },
    get usingFallback() { return usingFallback },
    /** 배경 지도 load 이벤트를 받았는가 */
    get basemapLoaded() { return basemapLoaded },
  }
}

/** CSS 변수 값 읽기. 지도 색은 css/style.css 토큰에서 가져온다. 예: cssVar('--entrance') */
export const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()

/** 사용자가 "동작 줄이기"를 켰는가 (Node 테스트처럼 matchMedia 가 없으면 false) */
const prefersReducedMotion = () =>
  typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches

/** view 에서 값이 있는 카메라 칸만 고른다 ({center: [경도, 위도], bearing, pitch, zoom}) */
function cameraOf(view = {}) {
  const out = {}
  for (const k of ['center', 'bearing', 'pitch', 'zoom']) if (view[k] != null) out[k] = view[k]
  return out
}

/**
 * 우리 레이어(lm-*)를 다시 그리기 위한 기록. 지도마다 {이름: 다시 그리는 함수}.
 * 스타일이 준비될 때(style.load: 처음 배경 지도, 대체 지도로 바꾼 뒤) 모두 다시 부른다. setStyle 은 레이어를 모두 지운다.
 * (마커는 DOM 이라 스타일을 바꿔도 남는다)
 */
const lastDraw = new WeakMap()

/**
 * 레이어를 더할 수 있는 지도. style.load 에서 넣고, 대체 지도로 바꾸기 직전에 뺀다.
 * map.isStyleLoaded() 는 지도가 뜬 뒤에도 타일을 받는 동안 false 라서, 그 값으로 판단하면 단계 전환 때 경로 선이 안 바뀐다
 */
const styleReady = new WeakSet()

/** 지도 자리에 안내 문구 (지도를 만들 수 없을 때) */
function showMapNotice(container, text) {
  const p = document.createElement('p')
  p.className = 'notice'
  p.setAttribute('role', 'status')
  p.textContent = text
  container.replaceChildren(p)
}

const CAMPUS_CONTEXT_RETRY_MS = 10000 // 캠퍼스 지도를 못 받았을 때 다시 감시하기까지 (오류마다 재시도, 안내가 반복되지 않게)

/**
 * 저장해 둔 캠퍼스 지도로 바꾼다. 바꾼 뒤 lastDraw 에 기록된 우리 레이어를 다시 그린다.
 * 캠퍼스 지도를 받는 동안 배경 지도가 떴으면 바꾸지 않는다 (이미 뜬 배경 지도를 덮어쓰지 않게)
 */
async function switchToCampusContext(map, reason, watch) {
  let ctx
  try {
    ctx = await loadCampusContext()
  } catch (e) {
    console.warn('저장해 둔 캠퍼스 지도를 불러오지 못했습니다', e)
    setTimeout(() => watch.resume(), CAMPUS_CONTEXT_RETRY_MS) // 배경 지도는 그대로 두고, 잠시 뒤 다시 감시한다 (다음 전환 때 캠퍼스 지도를 다시 받는다)
    toast(reason === 'timeout'
      ? '지도를 받는 데 시간이 걸리고 있습니다. 잠시 기다려 주세요.'
      : '지도를 불러오지 못했습니다. 인터넷 연결을 확인하세요.', 4000)
    return
  }
  if (reason === 'timeout' && watch.basemapLoaded) { watch.resume(); return } // 기다리는 사이 배경 지도가 떴다
  styleReady.delete(map) // 새 스타일이 준비될 때까지 레이어를 더하지 않는다 (style.load 에서 다시 그림)
  map.setStyle(campusContextStyle(ctx, cssVar), { diff: false })
  toast(reason === 'timeout'
    ? '배경 지도가 늦어 저장해 둔 캠퍼스 지도로 보여 드려요.'
    : '배경 지도를 받지 못해 저장해 둔 캠퍼스 지도로 보여 드려요.', 4000)
}

/**
 * 지도 만들기. 배경 지도(OpenFreeMap)가 BASEMAP_TIMEOUT_MS 안에 뜨지 않거나 배경 지도 오류가 나면
 * 저장해 둔 캠퍼스 지도로 바꾼다. 나침반(NavigationControl)과 출처 표기를 붙인다.
 * 지도를 만들 수 없으면(WebGL 없음, 라이브러리 못 받음) 지도 자리에 안내 문구를 넣고 null 을 돌려준다.
 * @param {HTMLElement} container  예: document.getElementById('map')
 * @param {{center?: number[], bearing?: number, pitch?: number, zoom?: number}} [view]  처음 시점. 비면 DEFAULT_VIEW
 * @returns {object | null} maplibregl.Map
 */
export function createMap(container, view = {}) {
  if (typeof maplibregl === 'undefined') {
    showMapNotice(container, '지도 라이브러리를 불러오지 못했습니다. 새로고침해 보세요.')
    return null
  }
  let map
  try {
    map = new maplibregl.Map({
      container,
      style: DEFAULT_BASEMAP_URL,
      ...DEFAULT_VIEW,
      ...cameraOf(view),
      attributionControl: false, // 기본 표기 대신 아래 AttributionControl(ATTRIBUTION_OPTIONS)
    })
  } catch (e) { // WebGL 을 못 쓰는 기기, 브라우저
    console.warn('지도를 만들지 못했습니다', e)
    showMapNotice(container, '이 기기에서는 3D 지도를 표시할 수 없습니다. 안내 문장을 따라 이동하세요.')
    return null
  }
  lastDraw.set(map, {})
  map.on('style.load', () => {
    styleReady.add(map)
    for (const redraw of Object.values(lastDraw.get(map) || {})) redraw()
  })
  // 나침반: 지도를 돌리면 북쪽을 가리키고, 누르면 북쪽으로 되돌린다. 확대 버튼은 손가락 확대가 있어 뺀다
  map.addControl(new maplibregl.NavigationControl({ showZoom: false, visualizePitch: true }), 'top-right')
  map.addControl(new maplibregl.AttributionControl(ATTRIBUTION_OPTIONS), attributionPosition(container))

  loadCampusContext().catch(() => {}) // 미리 받아 둔다 (약 18KB). 인터넷이 끊긴 뒤에도 바로 바꿀 수 있게
  const watch = createBasemapWatch((reason) => switchToCampusContext(map, reason, watch))
  map.once('load', () => watch.onLoad())
  map.on('error', (event) => {
    if (!watch.onError(event)) console.warn('지도 오류', event.sourceId || '', event.error) // 우리 레이어 오류, 전환 뒤 오류는 기록만
  })
  return map
}

// ---- 우리 레이어와 마커 (F-02 ~ F-05) ----

const EMPTY_COLLECTION = () => ({ type: 'FeatureCollection', features: [] })
const lineCollection = (coordinates) => (Array.isArray(coordinates) && coordinates.length >= 2
  ? { type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates } }] }
  : EMPTY_COLLECTION())

/** 지도마다 마지막으로 그린 데이터. 스타일이 바뀌면 이 값으로 다시 그린다 */
const drawData = new WeakMap()
function dataOf(map) {
  if (!drawData.has(map)) drawData.set(map, { buildings: null, route: null, doneFraction: 0, markers: [], stepMarkers: [] })
  return drawData.get(map)
}

function setSource(map, id, data) {
  const source = map.getSource(id)
  if (source) source.setData(data)
  else map.addSource(id, { type: 'geojson', data })
}

/** 레이어를 다시 그리는 함수를 기록하고, 스타일이 준비돼 있으면 바로 그린다 */
function keepDrawing(map, name, draw) {
  if (!lastDraw.has(map)) lastDraw.set(map, {})
  lastDraw.get(map)[name] = draw
  if (styleReady.has(map)) draw()
}

/** 건물(2.5D), 목적 건물 강조 (F-02, F-03). buildings: GET /places/{id}/buildings 응답 (GeoJSON) */
export function drawBuildings(map, buildings) {
  if (!map) return
  dataOf(map).buildings = buildings || EMPTY_COLLECTION()
  keepDrawing(map, 'buildings', () => {
    setSource(map, 'lm-buildings', dataOf(map).buildings)
    if (map.getLayer('lm-buildings')) return
    map.addLayer({
      id: 'lm-buildings', type: 'fill-extrusion', source: 'lm-buildings',
      paint: {
        'fill-extrusion-color': ['case', ['boolean', ['get', 'is_target'], false], cssVar('--target'), cssVar('--map-bldg')],
        'fill-extrusion-height': ['max', ['get', 'render_height_m'], 1],
        'fill-extrusion-base': 0,
        'fill-extrusion-opacity': 0.92,
      },
    }, map.getLayer('lm-route') ? 'lm-route' : undefined) // 경로 선이 먼저 그려졌으면 그 아래에 둔다
  })
}

/** 도보 경로 선과 지나온 구간 (F-04). doneFraction 은 0~1 */
export function drawRoute(map, route, doneFraction = 0) {
  if (!map) return
  const data = dataOf(map)
  data.route = route || null
  data.doneFraction = Number.isFinite(doneFraction) ? Math.min(1, Math.max(0, doneFraction)) : 0
  keepDrawing(map, 'route', () => {
    const path = data.route?.path?.coordinates
    const done = Array.isArray(path) && path.length >= 2 && data.doneFraction > 0 ? pathUntil(path, data.doneFraction) : []
    setSource(map, 'lm-route', lineCollection(path))
    setSource(map, 'lm-route-done', lineCollection(done))
    if (!map.getLayer('lm-route')) {
      map.addLayer({ id: 'lm-route', type: 'line', source: 'lm-route', layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': cssVar('--accent'), 'line-width': 5, 'line-opacity': 0.9 } })
    }
    if (!map.getLayer('lm-route-done')) {
      map.addLayer({ id: 'lm-route-done', type: 'line', source: 'lm-route-done', layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': cssVar('--muted'), 'line-width': 6, 'line-opacity': 0.72 } })
    }
  })
}

/**
 * 주차장, 입구, 랜드마크 마커 (F-03). 마커는 DOM 이라 스타일을 바꿔도 남고, 지도가 뜨기 전에 더해도 된다.
 * options.activeEntranceId 가 있으면 다른 입구는 흐리게 표시한다
 */
export function drawMarkers(map, place, options = {}) {
  if (!map) return
  const data = dataOf(map)
  for (const marker of data.markers) marker.remove()
  data.markers = []
  if (!place) return
  const points = [
    ...(place.parking_lots || []).map((item) => ({ kind: 'parking', item })),
    ...(place.entrances || []).map((item) => ({ kind: 'entrance', item })),
    ...(place.landmarks || []).map((item) => ({ kind: 'landmark', item })),
  ]
  for (const { kind, item } of points) {
    const coordinates = item.location?.coordinates
    if (!Array.isArray(coordinates)) continue
    const el = markerElement(kind, item.name)
    if (kind === 'entrance' && options.activeEntranceId != null && item.id !== options.activeEntranceId) el.style.opacity = '0.45'
    data.markers.push(new maplibregl.Marker({ element: el, anchor: 'bottom' }).setLngLat(coordinates).addTo(map))
  }
}

/** 관리자 지도에 초안 단계를 번호로 표시한다. activeStepIndex 단계는 크게 */
export function drawDraftSteps(map, steps, activeStepIndex = 0) {
  if (!map) return
  const data = dataOf(map)
  for (const marker of data.stepMarkers) marker.remove()
  data.stepMarkers = []
  for (const [index, step] of (Array.isArray(steps) ? steps : []).entries()) {
    const coordinates = step.location?.coordinates
    if (!Array.isArray(coordinates) || coordinates.length !== 2) continue
    const el = document.createElement('div')
    el.className = `mk-step${index === activeStepIndex ? ' selected' : ''}`
    el.textContent = String(index + 1)
    el.setAttribute('aria-label', `${index + 1}단계`)
    data.stepMarkers.push(new maplibregl.Marker({ element: el, anchor: 'center' }).setLngLat(coordinates).addTo(map))
  }
}

// ---- 마커와 범례 모양 (색 + 모양을 함께 써서 색만으로 구분하지 않는다) ----
// 색은 css/style.css 의 .mk-icon 규칙이 토큰(--parking, --entrance ...)으로 칠한다
export const MARKER_ICON = {
  parking: '<svg class="mk-icon" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true"><rect class="park edge" x="1.5" y="1.5" width="21" height="21" rx="4"/><text class="fg" x="12" y="17" text-anchor="middle" font-size="14" font-weight="700">P</text></svg>',
  entrance: '<svg class="mk-icon" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true"><path class="ent edge" d="M12 1 L23 12 L12 23 L1 12Z"/><rect class="fg" x="9" y="7" width="6" height="10" rx="1"/></svg>',
  landmark: '<svg class="mk-icon" width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><circle class="lm edge" cx="10" cy="10" r="8.5"/><circle class="fg" cx="10" cy="10" r="3"/></svg>',
  target: '<svg class="mk-icon" width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><rect class="tgt" x="2" y="4" width="14" height="10" rx="1"/></svg>',
  route: '<svg class="mk-icon" width="22" height="18" viewBox="0 0 22 18" aria-hidden="true"><path class="route" d="M2 9 H20" stroke-width="4" stroke-linecap="round" fill="none"/></svg>',
}

/** 지도 마커 요소 (아이콘 + 이름표). kind: 'parking' | 'entrance' | 'landmark' */
export function markerElement(kind, label = '') {
  const el = document.createElement('div')
  el.className = `mk mk-${kind}`
  el.innerHTML = MARKER_ICON[kind]
  if (label) {
    const t = document.createElement('span')
    t.className = 'mk-label'
    t.textContent = label // 서버 글자는 textContent 로
    el.appendChild(t)
  }
  return el
}

/** 범례 그리기. container 예: <div id="map-legend" class="legend" aria-label="지도 범례"> */
export function renderLegend(container, kinds = ['parking', 'entrance', 'target', 'route']) {
  const name = { parking: '주차장', entrance: '입구', landmark: '랜드마크', target: '목적 건물', route: '도보 경로' }
  container.innerHTML = kinds.map((k) => `<span>${MARKER_ICON[k]}${name[k]}</span>`).join('')
}
/**
 * 카메라 이동 {center: [경도, 위도], bearing, pitch, zoom}. "동작 줄이기"를 켠 사용자에게는 jumpTo (움직임 없이 바로)
 * 서버의 steps[].camera 에는 center 가 없다 (위치는 steps[].location). 넘길 때 합친다:
 *   flyTo(map, { center: step.location.coordinates, ...step.camera })
 */
export function flyTo(map, view) {
  if (!map || !view) return
  const camera = cameraOf(view)
  if (prefersReducedMotion()) map.jumpTo(camera)
  else map.flyTo(camera)
}
