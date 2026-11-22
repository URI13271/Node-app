// guide.html: 주차장에서 목적 건물 입구까지 경로와 단계별 카메라를 보여준다.
import { getBuildings, getPlace, getWalkRoutes } from '../api.js'
import { fractionOnPath } from '../geo.js'
import { createMap, drawBuildings, drawMarkers, drawRoute, flyTo, renderLegend } from '../map.js'
import { $, escapeHtml, loadErrorMessage, param } from '../util.js'

const placeId = Number(param('id'))
const startAtStep = param('start') === '1'
const state = { place: null, buildings: null, routes: [], route: null, step: -1, error: '' }
const map = createMap($('#map'))
const routeSwitcher = $('#route-switcher')

function activeEntrance() {
  return state.place?.entrances?.find((item) => item.id === state.route?.entrance_id) || null
}

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

function completedFraction() {
  if (!state.route) return 0
  const steps = state.route.steps || []
  if (state.step < 0) return 0
  if (state.step >= steps.length) return 1
  return fractionOnPath(state.route.path.coordinates, steps[state.step].location.coordinates)
}

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

function render() {
  const steps = state.route?.steps || []
  const count = steps.length
  const step = state.step
  const segments = $('#step-seg')
  const number = $('#step-num')
  const text = $('#step-text')

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
  drawRoute(map, state.route, completedFraction())
  const view = routeView()
  if (view) flyTo(map, view)
}

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

$('#btn-prev').addEventListener('click', () => {
  state.step = Math.max(-1, state.step - 1)
  render()
})
$('#btn-next').addEventListener('click', () => {
  const count = state.route?.steps.length || 0
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

renderLegend($('#map-legend'), ['entrance', 'landmark', 'route'])
render()
load()
