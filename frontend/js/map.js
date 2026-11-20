// 3D 지도 (MapLibre). 화면 HTML 에서 maplibre-gl.js 를 먼저 불러야 전역 maplibregl 이 생긴다.
// 배경 지도: OpenFreeMap "liberty" (키, 가입 없음, SLA 없음) [검증 필요: 이용 조건 변경 여부]
// 배경 지도 주소를 바꾸면 backend/app/frontend.py 의 CSP 허용 주소도 같이 바꾼다.
import { todo, toast } from './util.js'

export const DEFAULT_BASEMAP_URL = 'https://tiles.openfreemap.org/styles/liberty'
export const BASEMAP_TIMEOUT_MS = 8000 // 이 시간 안에 배경 지도가 안 오면 저장해 둔 캠퍼스 지도로 바꾼다
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
 * @param ctx   decodeCampusContext 결과
 * @param color 토큰 이름 → 색 값 함수. 화면에서는 cssVar (다크 모드 자동)
 */
export function campusStyle(ctx, color) {
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
      { id: 'lm-ctx-road-edge', type: 'line', source: 'lm-ctx-roads', layout: round,
        paint: { 'line-color': color('--map-road-edge'), 'line-width': ['match', ['get', 'grade'], 2, 9, 1, 6, 4] } },
      { id: 'lm-ctx-road', type: 'line', source: 'lm-ctx-roads', layout: round,
        paint: { 'line-color': color('--map-road'), 'line-width': ['match', ['get', 'grade'], 2, 7, 1, 4.5, 2.5] } },
      { id: 'lm-ctx-path', type: 'line', source: 'lm-ctx-paths',
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
export function isBasemapError(event, styleLoaded) {
  const id = event?.sourceId
  if (typeof id === 'string' && id.startsWith('lm-')) return false
  if (id) return true
  return !styleLoaded
}

/**
 * 배경 지도 감시. timeoutMs 안에 loaded() 가 안 오거나 배경 지도 오류가 나면 onFallback(이유) 를 한 번만 부른다.
 * @param {(reason: 'timeout' | 'error') => void} onFallback
 * @param {{timeoutMs?: number, timers?: {setTimeout: Function, clearTimeout: Function}}} [opt]  timers 는 테스트용 가짜 시계
 */
export function createBasemapWatch(onFallback, { timeoutMs = BASEMAP_TIMEOUT_MS, timers = globalThis } = {}) {
  let styleLoaded = false
  let fallen = false
  let timer = null
  const fall = (reason) => {
    if (fallen) return
    fallen = true
    timers.clearTimeout(timer)
    onFallback(reason)
  }
  timer = timers.setTimeout(() => { if (!styleLoaded) fall('timeout') }, timeoutMs)
  return {
    /** 배경 지도 load 이벤트 */
    loaded() { styleLoaded = true; timers.clearTimeout(timer) },
    /** 지도 error 이벤트. 이번 오류로 대체 지도로 바꾸면 true */
    error(event) {
      if (fallen || !isBasemapError(event, styleLoaded)) return false
      fall('error')
      return true
    },
    get fallen() { return fallen },
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
 * 대체 지도로 바꾼 뒤 우리 레이어(lm-*)를 다시 그리기 위한 기록. setStyle 은 레이어를 모두 지운다.
 * 4단계 drawBuildings, drawRoute 가 마지막 데이터로 다시 그리는 함수를 넣는다: lastDraw.get(map).route = () => ...
 * (마커는 DOM 이라 스타일을 바꿔도 남는다)
 */
const lastDraw = new WeakMap()

/** 지도 자리에 안내 문구 (지도를 만들 수 없을 때) */
function showMapNotice(container, text) {
  const p = document.createElement('p')
  p.className = 'notice'
  p.setAttribute('role', 'status')
  p.textContent = text
  container.replaceChildren(p)
}

/** 저장해 둔 캠퍼스 지도로 바꾼다. 바꾼 뒤 lastDraw 에 기록된 우리 레이어를 다시 그린다 */
async function switchToCampusMap(map, reason) {
  let ctx
  try {
    ctx = await loadCampusContext()
  } catch (e) {
    console.warn('저장해 둔 캠퍼스 지도를 불러오지 못했습니다', e)
    toast('지도를 불러오지 못했습니다. 인터넷 연결을 확인하세요.', 4000)
    return
  }
  map.once('style.load', () => { for (const redraw of Object.values(lastDraw.get(map) || {})) redraw() })
  map.setStyle(campusStyle(ctx, cssVar), { diff: false })
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
  // 나침반: 지도를 돌리면 북쪽을 가리키고, 누르면 북쪽으로 되돌린다. 확대 버튼은 손가락 확대가 있어 뺀다
  map.addControl(new maplibregl.NavigationControl({ showZoom: false, visualizePitch: true }), 'top-right')
  map.addControl(new maplibregl.AttributionControl(ATTRIBUTION_OPTIONS), attributionPosition(container))

  loadCampusContext().catch(() => {}) // 미리 받아 둔다 (약 18KB). 인터넷이 끊긴 뒤에도 바로 바꿀 수 있게
  const watch = createBasemapWatch((reason) => switchToCampusMap(map, reason))
  map.once('load', () => watch.loaded())
  map.on('error', (ev) => {
    if (!watch.error(ev)) console.warn('지도 오류', ev.sourceId || '', ev.error) // 우리 레이어 오류, 전환 뒤 오류는 기록만
  })
  return map
}

/** 건물(2.5D), 목적 건물 강조, 주차장 레이어 그리기 (F-02, F-03) */
export function drawBuildings(map, buildings) { todo('drawBuildings') }
/** 도보 경로 선, 지나온 구간 (F-04) */
export function drawRoute(map, route, doneFraction = 0) { todo('drawRoute') }
/**
 * 입구, 주차장, 랜드마크 마커. TODO: place.entrances, parking_lots, landmarks 마다
 *   new maplibregl.Marker({ element: markerElement('entrance', e.name), anchor: 'bottom' }).setLngLat(e.location.coordinates).addTo(map)
 *   options.activeEntranceId 가 있으면 다른 입구는 흐리게 (el.style.opacity = .45)
 */
export function drawMarkers(map, place, options = {}) { todo('drawMarkers') }

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
/** 카메라 이동 {center: [경도, 위도], bearing, pitch, zoom}. "동작 줄이기"를 켠 사용자에게는 jumpTo (움직임 없이 바로) */
export function flyTo(map, view) {
  if (!map || !view) return
  const camera = cameraOf(view)
  if (prefersReducedMotion()) map.jumpTo(camera)
  else map.flyTo(camera)
}
