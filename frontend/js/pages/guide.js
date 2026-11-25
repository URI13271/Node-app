// guide.html?id=1&parking_lot_id=&route=&start=1 (F-02~F-05 3D 안내)
// 주차장에서 목적 건물 입구까지 경로와 단계별 카메라를 보여 준다. start=1 이면 개요를 건너뛰고 1단계부터
import { getBuildings, getPlace, getWalkRoutes } from '../api.js'
import { fractionOnPath } from '../geo.js'
import { createMap, drawBuildings, drawMarkers, drawRoute, flyTo, renderLegend } from '../map.js'
import { $, escapeHtml, loadErrorMessage, param } from '../util.js'

// 1. 주소 값, 화면 상태
const placeId = Number(param('id'))
const startAtStep = param('start') === '1'
// step: -1 도착 방향 개요, 0..n-1 단계, n 도착 완료
const state = { place: null, buildings: null, routes: [], route: null, step: -1, error: '' }
const map = createMap($('#map'))
const routeSwitcher = $('#route-switcher')

// 2. 그리기: state 만 보고 카드와 지도를 바꾼다

/** 고른 경로의 도착 입구 */
function activeEntrance() {
  return state.place?.entrances?.find((item) => item.id === state.route?.entrance_id) || null
}

/**
 * 지금 단계의 카메라. 서버 camera 에는 center 가 없어 위치와 합친다
 *   개요 → 출발 주차장 camera, 단계 → steps[i].camera, 도착 → 입구 위치 + 마지막 단계 camera
 */
function routeView() {
  const place = state.place
  const route = state.route
  if (!place || !route) return null
  const steps = route.steps || []
  if (state.step < 0) {
    const parking = place.parking_lots?.find((item) => item.id === route.parking_lot_id)
    return parking ? { center: parking.location.coordinates, ...parking.camera } : { center: place.location.coordinates, ...place.camera }
  }
  if (state.step < steps.length) {
    const step = steps[state.step]
    return { center: step.location.coordinates, ...step.camera }
  }
  const entrance = activeEntrance()
  const camera = steps.at(-1)?.camera || place.camera
  return { center: entrance?.location.coordinates || place.location.coordinates, ...camera }
}

/** 지나온 구간 비율(0~1): 현재 단계 지점을 경로 선에 내린 위치. 개요는 0, 도착은 1 */
function completedFraction() {
  if (!state.route) return 0
  const steps = state.route.steps || []
  if (state.step < 0) return 0
  if (state.step >= steps.length) return 1
  return fractionOnPath(state.route.path.coordinates, steps[state.step].location.coordinates)
}

/** 경로가 2개 이상이면 "주차장 → 입구" 칩으로 고르게 한다 */
function renderRouteSwitcher() {
  if (!state.place || state.routes.length < 2) {
    routeSwitcher.hidden = true
    routeSwitcher.replaceChildren()
    return
  }
  routeSwitcher.innerHTML = state.routes.map((route) => {
    const lot = state.place.parking_lots?.find((item) => item.id === route.parking_lot_id)
    const entrance = state.place.entrances?.find((item) => item.id === route.entrance_id)
    const label = `${lot?.name || '주차장'} → ${entrance?.name || '입구'} ${Math.round(route.distance_m)}m`
    return `<button class="route-chip ${route.id === state.route?.id ? 'selected' : ''}" data-route-id="${route.id}" aria-pressed="${route.id === state.route?.id}">${escapeHtml(label)}</button>`
  }).join('')
  routeSwitcher.hidden = false
}

function renderSummary() {
  const summary = $('#guide-summary')
  const place = state.place
  if (!place) {
    summary.textContent = state.error || '안내 정보를 불러오는 중입니다.'
    return
  }
  if (!state.route) {
    summary.innerHTML = `<b>${escapeHtml(place.name)}</b><span>도보 경로 안내를 준비 중입니다.</span>`
    return
  }
  const parking = place.parking_lots?.find((item) => item.id === state.route.parking_lot_id)
  const entrance = activeEntrance()
  summary.innerHTML = `<b>${escapeHtml(place.name)}</b><span>${escapeHtml(parking?.name || '주차장')}에서 ${escapeHtml(entrance?.name || '입구')}까지 · 약 ${Math.round(state.route.distance_m)}m · ${state.route.walk_time_min}분</span>`
}

/** 진행 막대, 큰 번호와 문장, 버튼, 지도를 한 번에 맞춘다 */
function render() {
  const steps = state.route?.steps || []
  const count = steps.length
  const step = state.step
  const segments = $('#step-seg')
  const number = $('#step-num')
  const text = $('#step-text')

  // 진행 막대: 단계 수만큼 칸, 지나온 단계까지 .on
  segments.innerHTML = steps.map((_, index) => `<i class="${index <= step ? 'on' : ''}"></i>`).join('')
  if (state.error) {
    number.textContent = ''
    text.textContent = state.error
  } else if (!state.place) {
    number.textContent = ''
    text.textContent = '안내 정보를 불러오는 중입니다.'
  } else if (!state.route) {
    number.textContent = ''
    text.textContent = '이 장소는 아직 도보 경로 안내가 준비되지 않았습니다.'
  } else if (!count) {
    number.textContent = ''
    text.textContent = '안내 단계가 아직 등록되지 않았습니다.'
  } else if (step < 0) {
    number.textContent = '개요'
    text.textContent = `주차장에서 입구까지 ${Math.round(state.route.distance_m)}m, 걸어서 약 ${state.route.walk_time_min}분입니다. 단계 ${count}개.`
  } else if (step < count) {
    const current = steps[step]
    number.innerHTML = `${step + 1}<small> / ${count}</small>`
    text.textContent = current.landmark ? `${current.instruction} (랜드마크: ${current.landmark.name})` : current.instruction
  } else {
    number.textContent = '도착'
    text.textContent = `${activeEntrance()?.name || '입구'}에 도착했습니다.`
  }

  // 버튼: 개요에서는 이전 비활성, 마지막 단계에서는 "다음" 대신 "도착", 도착 완료에서는 완료 버튼 묶음
  const done = !!state.route && count > 0 && step >= count
  $('#step-actions').hidden = done
  $('#done-actions').hidden = !done
  $('#btn-prev').disabled = !state.route || step < 0
  $('#btn-next').disabled = !state.route || count === 0
  $('#btn-next').textContent = !state.route ? '다음' : step < 0 ? '안내 시작' : step === count - 1 ? '도착' : '다음'

  renderRouteSwitcher()
  renderSummary()
  const attributions = state.place?.attributions || []
  const attribution = $('#guide-attribution')
  attribution.textContent = attributions.length ? `건물 데이터: ${attributions.join(' · ')}` : ''
  attribution.hidden = !attributions.length
  // 지도: 경로 선과 지나온 구간, 단계 카메라
  drawRoute(map, state.route, completedFraction())
  const view = routeView()
  if (view) flyTo(map, view)
}

// 3. 불러오기
// 장소 상세가 실패하면 오류만 보여 준다. 건물은 실패해도 안내는 계속한다
async function load() {
  if (!Number.isInteger(placeId) || placeId < 1) {
    state.error = '주소에 올바른 장소 번호가 없습니다.'
    render()
    return
  }
  const [placeResult, buildingResult, routeResult] = await Promise.allSettled([
    getPlace(placeId), getBuildings(placeId), getWalkRoutes(placeId),
  ])
  if (placeResult.status === 'rejected') {
    state.error = loadErrorMessage(placeResult.reason)
    render()
    return
  }
  state.place = placeResult.value
  if (buildingResult.status === 'fulfilled') {
    state.buildings = buildingResult.value
    drawBuildings(map, state.buildings)
  }
  drawMarkers(map, state.place)
  renderLegend($('#map-legend'), ['entrance', 'landmark', 'route'])
  $('#btn-detail').href = `/place.html?id=${placeId}`

  if (routeResult.status === 'rejected') {
    state.error = loadErrorMessage(routeResult.reason)
    render()
    return
  }
  state.routes = routeResult.value.items || []
  // 처음 경로 고르기: route → parking_lot_id → 첫 경로
  const routeId = Number(param('route'))
  const parkingLotId = Number(param('parking_lot_id'))
  state.route = state.routes.find((route) => route.id === routeId)
    || state.routes.find((route) => route.parking_lot_id === parkingLotId)
    || state.routes[0]
    || null
  state.step = startAtStep && state.route ? 0 : -1
  if (state.route && !state.route.steps?.length) state.error = '안내 단계가 아직 등록되지 않았습니다.'
  render()
}

// 4. 이벤트
$('#btn-prev').addEventListener('click', () => {
  state.step = Math.max(-1, state.step - 1)
  render()
})
$('#btn-next').addEventListener('click', () => {
  const count = state.route?.steps.length || 0
  // 마지막 단계(n-1)에서 누르면 n = 도착 완료
  state.step = Math.min(count, state.step + 1)
  render()
})
routeSwitcher.addEventListener('click', (event) => {
  const button = event.target.closest('[data-route-id]')
  if (!button) return
  const route = state.routes.find((item) => item.id === Number(button.dataset.routeId))
  if (!route) return
  state.route = route
  state.step = -1
  state.error = ''
  render()
})

// 5. 시작
renderLegend($('#map-legend'), ['entrance', 'landmark', 'route'])
render()
load()
