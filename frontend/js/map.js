// 3D 지도 (MapLibre). 화면 HTML 에서 maplibre-gl.js 를 먼저 불러야 전역 maplibregl 이 생긴다.
// 배경 지도: OpenFreeMap "liberty" (키, 가입 없음, SLA 없음) [검증 필요: 이용 조건 변경 여부]
// 배경 지도 주소를 바꾸면 backend/app/frontend.py 의 CSP 허용 주소도 같이 바꾼다.
import { todo } from './util.js'

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

/** 저장해 둔 캠퍼스 지도를 받아 GeoJSON 묶음 {green, water, buildings, roads, paths} 으로 푼다. TODO */
export async function loadCampusContext() { return todo('loadCampusContext') }

/** CSS 변수 값 읽기. 지도 색은 css/style.css 토큰에서 가져온다. 예: cssVar('--entrance') */
export const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()

/**
 * 지도 만들기. TODO: new maplibregl.Map, 배경 지도 → 대체 지도 전환, 나침반, 출처 표기
 *   출처: new maplibregl.Map({ ..., attributionControl: false }) 로 기본 표기를 끄고
 *         map.addControl(new maplibregl.AttributionControl(ATTRIBUTION_OPTIONS), attributionPosition(container))
 * @param {HTMLElement} container  예: document.getElementById('map')
 */
export function createMap(container) {
  container.innerHTML = '<div class="todo-box">createMap 구현 예정 (MapLibre 3D 지도)</div>'
  return null
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
/** 카메라 이동 {center: [경도, 위도], bearing, pitch, zoom} */
export function flyTo(map, view) { todo('flyTo') }
