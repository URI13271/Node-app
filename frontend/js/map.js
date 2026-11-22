// MapLibre 지도와 지도 오버레이. 지도 데이터와 위치 계산은 브라우저 안에서만 처리한다.
import { pathUntil } from './geo.js'

export const DEFAULT_BASEMAP_URL = 'https://tiles.openfreemap.org/styles/liberty'
export const BASEMAP_TIMEOUT_MS = 8000
export const CAMPUS_CONTEXT_URL = '/data/osm_context_gnu.json'
export const CAMPUS_CONTEXT_BOUNDS = [128.0948, 35.1505, 128.1022, 35.1558]
export const CONTEXT_ATTRIBUTION = '© OpenMapTiles © OpenStreetMap contributors (저장해 둔 캠퍼스 지도)'

export const ATTRIBUTION_OPTIONS = {
  compact: true,
  customAttribution: '<a href="/about.html">출처 전체</a>',
}

const mapStates = new WeakMap()
const EMPTY_COLLECTION = () => ({ type: 'FeatureCollection', features: [] })
const MARKER_KINDS = ['parking', 'entrance', 'landmark']

/** 출처 표기 위치. 3D 안내 화면에서는 카드가 겹치지 않도록 위에 둔다. */
export function attributionPosition(container) {
  return container.classList.contains('map-full') ? 'top-right' : 'bottom-right'
}

export function shouldFallbackOnTimeout({ loaded, fallback }) {
  return !loaded && !fallback
}

export function shouldFallbackFromMapError(event) {
  return !String(event?.sourceId || '').startsWith('lm-')
}

const pointArray = (flat, origin, unit, offset = 0) => {
  const coordinates = []
  for (let i = offset; i + 1 < flat.length; i += 2) {
    coordinates.push([
      Number((origin[0] + flat[i] * unit).toFixed(6)),
      Number((origin[1] + flat[i + 1] * unit).toFixed(6)),
    ])
  }
  return coordinates
}

function polygonCollection(polygons, origin, unit, name) {
  return {
    type: 'FeatureCollection',
    features: polygons.flatMap((flat, index) => {
      const ring = pointArray(flat, origin, unit)
      if (ring.length < 3) return []
      const first = ring[0], last = ring.at(-1)
      if (first[0] !== last[0] || first[1] !== last[1]) ring.push([...first])
      return [{
        type: 'Feature',
        id: `context-${name}-${index}`,
        geometry: { type: 'Polygon', coordinates: [ring] },
        properties: { kind: name },
      }]
    }),
  }
}

function lineCollection(lines, origin, unit, name) {
  return {
    type: 'FeatureCollection',
    features: lines.flatMap((line, index) => {
      const roadClass = name === 'roads' ? line[0] : null
      const coordinates = pointArray(line, origin, unit, name === 'roads' ? 1 : 0)
      if (coordinates.length < 2) return []
      return [{
        type: 'Feature',
        id: `context-${name}-${index}`,
        geometry: { type: 'LineString', coordinates },
        properties: name === 'roads' ? { road_class: roadClass } : { kind: name },
      }]
    }),
  }
}

/** 압축된 캠퍼스 좌표를 다섯 GeoJSON FeatureCollection으로 푼다. */
export function unpackCampusContext(context) {
  const origin = context?.o
  const unit = context?.u
  if (!Array.isArray(origin) || origin.length !== 2 || !Number.isFinite(unit) || unit <= 0) {
    throw new TypeError('캠퍼스 지도 형식이 올바르지 않습니다.')
  }
  return {
    green: polygonCollection(context.green || [], origin, unit, 'green'),
    water: polygonCollection(context.water || [], origin, unit, 'water'),
    buildings: polygonCollection(context.buildings || [], origin, unit, 'buildings'),
    roads: lineCollection(context.roads || [], origin, unit, 'roads'),
    paths: lineCollection(context.paths || [], origin, unit, 'paths'),
  }
}

export async function loadCampusContext() {
  const response = await fetch(CAMPUS_CONTEXT_URL, { cache: 'force-cache' })
  if (!response.ok) throw new Error('저장된 캠퍼스 지도를 불러오지 못했습니다.')
  return unpackCampusContext(await response.json())
}

export const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()

function fallbackStyle(context) {
  const color = (name) => cssVar(name)
  return {
    version: 8,
    sources: {
      'context-green': { type: 'geojson', data: context.green },
      'context-water': { type: 'geojson', data: context.water },
      'context-buildings': { type: 'geojson', data: context.buildings, attribution: CONTEXT_ATTRIBUTION },
      'context-roads': { type: 'geojson', data: context.roads },
      'context-paths': { type: 'geojson', data: context.paths },
    },
    layers: [
      { id: 'base-background', type: 'background', paint: { 'background-color': color('--map-ground') } },
      { id: 'base-green', type: 'fill', source: 'context-green', paint: { 'fill-color': color('--map-grass'), 'fill-opacity': 0.9 } },
      { id: 'base-water', type: 'fill', source: 'context-water', paint: { 'fill-color': color('--map-water'), 'fill-opacity': 0.95 } },
      { id: 'base-context-buildings', type: 'fill', source: 'context-buildings', paint: { 'fill-color': color('--map-ctx-bldg'), 'fill-outline-color': color('--map-bldg') } },
      { id: 'base-roads-casing', type: 'line', source: 'context-roads', paint: { 'line-color': color('--map-road-edge'), 'line-width': ['match', ['get', 'road_class'], 2, 7, 1, 5, 3] } },
      { id: 'base-roads', type: 'line', source: 'context-roads', paint: { 'line-color': color('--map-road'), 'line-width': ['match', ['get', 'road_class'], 2, 5, 1, 3, 1] } },
      { id: 'base-paths', type: 'line', source: 'context-paths', paint: { 'line-color': color('--map-path'), 'line-width': 1.5, 'line-dasharray': [1.5, 1.5] } },
    ],
  }
}

function setMapNotice(state, message) {
  if (!state.notice) {
    state.notice = document.createElement('div')
    state.notice.className = 'map-notice'
    state.notice.setAttribute('role', 'status')
    state.container.appendChild(state.notice)
  }
  state.notice.textContent = message
  state.notice.hidden = !message
}

function addOrUpdateSource(map, id, data) {
  const source = map.getSource(id)
  if (source) source.setData(data)
  else map.addSource(id, { type: 'geojson', data })
}

function removeLayerAndSource(map, id) {
  if (map.getLayer(id)) map.removeLayer(id)
  if (map.getSource(id)) map.removeSource(id)
}

function updateMarkers(map, state) {
  for (const marker of state.markers) marker.remove()
  state.markers = []
  const place = state.place
  if (!place || !globalThis.maplibregl?.Marker) return

  const activeId = state.markerOptions.activeEntranceId
  const points = [
    ...(place.parking_lots || []).map((item) => ({ kind: 'parking', item })),
    ...(place.entrances || []).map((item) => ({ kind: 'entrance', item })),
    ...(place.landmarks || []).map((item) => ({ kind: 'landmark', item })),
  ]
  for (const { kind, item } of points) {
    const marker = new maplibregl.Marker({ element: markerElement(kind, item.name), anchor: 'bottom' })
      .setLngLat(item.location.coordinates)
      .addTo(map)
    if (kind === 'entrance' && activeId != null && item.id !== activeId) marker.getElement().style.opacity = '0.45'
    state.markers.push(marker)
  }
}

function updateDraftMarkers(map, state) {
  for (const marker of state.stepMarkers) marker.remove()
  state.stepMarkers = []
  if (!globalThis.maplibregl?.Marker) return
  for (const [index, step] of state.draftSteps.entries()) {
    const coordinates = step.location?.coordinates
    if (!Array.isArray(coordinates) || coordinates.length !== 2) continue
    const element = document.createElement('div')
    element.className = `mk-step${index === state.activeStepIndex ? ' selected' : ''}`
    element.textContent = String(index + 1)
    element.setAttribute('aria-label', `${index + 1}단계`)
    state.stepMarkers.push(new maplibregl.Marker({ element, anchor: 'center' }).setLngLat(coordinates).addTo(map))
  }
}

function renderStoredLayers(map) {
  const state = mapStates.get(map)
  if (!state || !map.isStyleLoaded()) return

  if (state.buildings) {
    addOrUpdateSource(map, 'lm-buildings', state.buildings)
    if (!map.getLayer('lm-buildings')) {
      map.addLayer({
        id: 'lm-buildings', type: 'fill-extrusion', source: 'lm-buildings',
        paint: {
          'fill-extrusion-color': ['case', ['boolean', ['get', 'is_target'], false], cssVar('--target'), cssVar('--map-bldg')],
          'fill-extrusion-height': ['max', ['get', 'render_height_m'], 1],
          'fill-extrusion-base': 0,
          'fill-extrusion-opacity': 0.92,
        },
      })
    }
  } else removeLayerAndSource(map, 'lm-buildings')

  const path = state.route?.path?.coordinates
  const fullRoute = Array.isArray(path) && path.length >= 2
    ? { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'LineString', coordinates: path }, properties: {} }] }
    : EMPTY_COLLECTION()
  const donePath = Array.isArray(path) && path.length >= 2 && state.doneFraction > 0
    ? pathUntil(path, state.doneFraction)
    : []
  const doneRoute = donePath.length >= 2
    ? { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'LineString', coordinates: donePath }, properties: {} }] }
    : EMPTY_COLLECTION()

  addOrUpdateSource(map, 'lm-route', fullRoute)
  addOrUpdateSource(map, 'lm-route-done', doneRoute)
  if (!map.getLayer('lm-route')) {
    map.addLayer({ id: 'lm-route', type: 'line', source: 'lm-route', paint: { 'line-color': cssVar('--accent'), 'line-width': 5, 'line-opacity': 0.9 } })
  }
  if (!map.getLayer('lm-route-done')) {
    map.addLayer({ id: 'lm-route-done', type: 'line', source: 'lm-route-done', paint: { 'line-color': cssVar('--muted'), 'line-width': 6, 'line-opacity': 0.72 } })
  }
  updateMarkers(map, state)
  updateDraftMarkers(map, state)
}

async function switchToFallback(map) {
  const state = mapStates.get(map)
  if (!state || state.fallback || state.switching) return
  state.switching = true
  clearTimeout(state.timeout)
  let context
  try { context = await loadCampusContext() } catch { context = null }
  const empty = { green: EMPTY_COLLECTION(), water: EMPTY_COLLECTION(), buildings: EMPTY_COLLECTION(), roads: EMPTY_COLLECTION(), paths: EMPTY_COLLECTION() }
  const style = fallbackStyle(context || empty)
  state.fallback = true
  map.once('style.load', () => {
    state.switching = false
    state.loaded = true
    setMapNotice(state, context ? '저장된 캠퍼스 지도를 표시하고 있습니다.' : '지도 데이터를 불러오지 못했습니다.')
    renderStoredLayers(map)
    map.resize()
  })
  map.setStyle(style)
}

/** MapLibre 지도를 만든다. 외부 지도가 실패하면 저장된 캠퍼스 지도로 전환한다. */
export function createMap(container, view = {}) {
  if (!container) return null
  const maplibre = globalThis.maplibregl
  if (!maplibre?.Map) {
    container.textContent = '이 브라우저에서는 지도를 표시할 수 없습니다.'
    container.setAttribute('role', 'status')
    return null
  }

  try {
    const map = new maplibre.Map({
      container,
      style: DEFAULT_BASEMAP_URL,
      center: view.center || [128.0989, 35.1532],
      zoom: view.zoom ?? 16,
      bearing: view.bearing ?? 0,
      pitch: view.pitch ?? 45,
      attributionControl: false,
      maxPitch: 85,
    })
    const state = {
      container, loaded: false, fallback: false, switching: false, timeout: null,
      buildings: null, route: null, doneFraction: 0, place: null, markerOptions: {}, markers: [],
      draftSteps: [], activeStepIndex: 0, stepMarkers: [], notice: null,
    }
    mapStates.set(map, state)
    map.addControl(new maplibre.NavigationControl({ showCompass: true, showZoom: true, visualizePitch: true }), 'top-left')
    map.addControl(new maplibre.AttributionControl(ATTRIBUTION_OPTIONS), attributionPosition(container))
    map.on('style.load', () => renderStoredLayers(map))
    map.on('load', () => {
      state.loaded = true
      clearTimeout(state.timeout)
      renderStoredLayers(map)
    })
    map.on('error', (event) => {
      if (!state.fallback && shouldFallbackFromMapError(event)) switchToFallback(map)
    })
    state.timeout = setTimeout(() => {
      if (shouldFallbackOnTimeout(state)) switchToFallback(map)
    }, BASEMAP_TIMEOUT_MS)
    return map
  } catch {
    container.textContent = '지도를 시작하지 못했습니다. 브라우저의 그래픽 기능을 확인해 주세요.'
    container.setAttribute('role', 'status')
    return null
  }
}

/** 건물 GeoJSON을 높이와 목적 건물 강조 색으로 표시한다. */
export function drawBuildings(map, buildings) {
  const state = map && mapStates.get(map)
  if (!state) return
  state.buildings = buildings || EMPTY_COLLECTION()
  renderStoredLayers(map)
}

/** 전체 경로와 진행한 구간을 그린다. doneFraction은 0~1이다. */
export function drawRoute(map, route, doneFraction = 0) {
  const state = map && mapStates.get(map)
  if (!state) return
  state.route = route || null
  state.doneFraction = Number.isFinite(doneFraction) ? Math.min(1, Math.max(0, doneFraction)) : 0
  renderStoredLayers(map)
}

/** 주차장, 입구, 랜드마크를 표시한다. 선택한 입구 외에는 흐리게 표시한다. */
export function drawMarkers(map, place, options = {}) {
  const state = map && mapStates.get(map)
  if (!state) return
  state.place = place || null
  state.markerOptions = options
  if (map.isStyleLoaded()) updateMarkers(map, state)
}

/** 관리자 지도에 초안 단계를 번호로 표시한다. */
export function drawDraftSteps(map, steps, activeStepIndex = 0) {
  const state = map && mapStates.get(map)
  if (!state) return
  state.draftSteps = Array.isArray(steps) ? steps : []
  state.activeStepIndex = activeStepIndex
  if (map.isStyleLoaded()) updateDraftMarkers(map, state)
}

// 색과 모양을 함께 써서 색만으로 구분하지 않는다.
export const MARKER_ICON = {
  parking: '<svg class="mk-icon" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true"><rect class="park edge" x="1.5" y="1.5" width="21" height="21" rx="4"/><text class="fg" x="12" y="17" text-anchor="middle" font-size="14" font-weight="700">P</text></svg>',
  entrance: '<svg class="mk-icon" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true"><path class="ent edge" d="M12 1 L23 12 L12 23 L1 12Z"/><rect class="fg" x="9" y="7" width="6" height="10" rx="1"/></svg>',
  landmark: '<svg class="mk-icon" width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><circle class="lm edge" cx="10" cy="10" r="8.5"/><circle class="fg" cx="10" cy="10" r="3"/></svg>',
  target: '<svg class="mk-icon" width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><rect class="tgt" x="2" y="4" width="14" height="10" rx="1"/></svg>',
  route: '<svg class="mk-icon" width="22" height="18" viewBox="0 0 22 18" aria-hidden="true"><path class="route" d="M2 9 H20" stroke-width="4" stroke-linecap="round" fill="none"/></svg>',
}

export function markerElement(kind, label = '') {
  const el = document.createElement('div')
  el.className = `mk mk-${kind}`
  el.innerHTML = MARKER_ICON[kind] || ''
  if (label) {
    const text = document.createElement('span')
    text.className = 'mk-label'
    text.textContent = label
    el.appendChild(text)
  }
  return el
}

export function renderLegend(container, kinds = ['parking', 'entrance', 'target', 'route']) {
  const name = { parking: '주차장', entrance: '입구', landmark: '랜드마크', target: '목적 건물', route: '도보 경로' }
  container.innerHTML = kinds.filter((kind) => name[kind]).map((kind) => `<span>${MARKER_ICON[kind]}${name[kind]}</span>`).join('')
}

/** 카메라 이동. 사용자가 움직임 줄이기를 켰으면 즉시 이동한다. */
export function flyTo(map, view) {
  if (!map || !view) return
  const camera = { center: view.center, bearing: view.bearing, pitch: view.pitch, zoom: view.zoom }
  const reduceMotion = globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  if (reduceMotion) map.jumpTo(camera)
  else map.flyTo({ ...camera, essential: false, duration: 700 })
}
