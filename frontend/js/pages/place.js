// place.html: 장소 정보, 지도, 주차장 경로, 내비 연결, 도착 판정.
import { getBuildings, getPlace, getWalkRoutes } from '../api.js'
import { createMap, drawBuildings, drawMarkers, flyTo, renderLegend } from '../map.js'
import { checkArrival, clearTrip, loadTrip, naviLinks, saveTrip } from '../navi.js'
import { $, CATEGORY_LABEL, escapeHtml, loadErrorMessage, param } from '../util.js'

const placeId = Number(param('id'))
const state = { place: null, buildings: null, routes: [], trip: null, map: null }
const placeInfo = $('#place-info')
const parkingList = $('#parking-list')
const naviSheet = $('#navi-sheet')
const arrivalBox = $('#arrival-check')

function routeForParking(parkingLotId) {
  return state.routes.find((route) => route.parking_lot_id === parkingLotId) || null
}

function guideUrl(route, { start = false } = {}) {
  if (!route) return '#'
  const query = new URLSearchParams({ id: String(placeId), parking_lot_id: String(route.parking_lot_id), route: String(route.id) })
  if (start) query.set('start', '1')
  return `/guide.html?${query}`
}

function renderPlace() {
  const place = state.place
  if (!place) return
  const category = CATEGORY_LABEL[place.category] || '기타'
  const attributions = (place.attributions || []).map(escapeHtml).join(' · ')
  placeInfo.innerHTML = `
    <article class="place-summary card">
      <div class="place-heading"><h1>${escapeHtml(place.name)}</h1><span class="chip">${escapeHtml(category)}</span></div>
      ${place.address ? `<p class="place-address">${escapeHtml(place.address)}</p>` : ''}
      ${place.description ? `<p class="place-description">${escapeHtml(place.description)}</p>` : ''}
      <div class="place-meta">
        <span>입구 ${place.entrances?.length || 0}곳</span>
        <span>주차장 ${place.parking_lots?.length || 0}곳</span>
        ${place.last_verified_at ? `<span>확인 ${escapeHtml(place.last_verified_at.slice(0, 10))}</span>` : ''}
      </div>
      ${attributions ? `<p class="map-attribution-note">건물 데이터: ${attributions}</p>` : ''}
    </article>`

  const routesByLot = new Map()
  for (const route of state.routes) routesByLot.set(route.parking_lot_id, (routesByLot.get(route.parking_lot_id) || 0) + 1)
  const parkingLots = [...(place.parking_lots || [])].sort((a, b) => a.priority - b.priority)
  parkingList.innerHTML = parkingLots.length ? parkingLots.map((lot) => {
    const route = routeForParking(lot.id)
    const routeCount = routesByLot.get(lot.id) || 0
    const details = [
      lot.capacity == null ? '' : `주차 ${lot.capacity}대`,
      lot.is_free == null ? '' : lot.is_free ? '무료' : '유료',
      lot.description || '',
    ].filter(Boolean).map(escapeHtml).join(' · ')
    return `<li class="card parking-card">
      <div class="parking-heading"><b>${escapeHtml(lot.name)}</b>${lot.id === place.navigation_target?.parking_lot_id ? '<span class="chip">내비 목적지</span>' : ''}</div>
      ${details ? `<p class="parking-detail">${details}</p>` : ''}
      ${routeCount
        ? `<a class="btn btn-sm parking-route" href="${guideUrl(route)}">입구까지 3D 안내${routeCount > 1 ? ` · 경로 ${routeCount}개` : ''}</a>`
        : '<p class="parking-route-empty">입구까지 도보 경로를 준비 중입니다.</p>'}
    </li>`
  }).join('') : '<li class="empty">등록된 주차장이 없습니다.</li>'

  const navButton = $('#btn-navi')
  navButton.disabled = !place.navigation_target
  const preferred = routeForParking(place.navigation_target?.parking_lot_id)
  const route = preferred || state.routes[0] || null
  const guideButton = $('#btn-guide')
  const unavailable = state.routes.length === 0
  guideButton.href = guideUrl(route)
  guideButton.setAttribute('aria-disabled', String(unavailable))
  $('#route-notice').hidden = !unavailable
  if (route) guideButton.href = guideUrl(route)
}

function renderNaviSheet() {
  const target = state.place?.navigation_target
  const links = naviLinks(target)
  if (!links.length) {
    naviSheet.innerHTML = '<section class="sheet-panel"><p class="notice">내비 목적지를 확인할 수 없습니다.</p><button class="btn" data-action="close-navi">닫기</button></section>'
    return
  }
  naviSheet.innerHTML = `<section class="sheet-panel" role="document">
    <div class="sheet-handle" aria-hidden="true"></div>
    <h2>어느 앱으로 갈까요?</h2>
    <p class="sheet-description">목적지는 건물이 아니라 <b>${escapeHtml(target.name)}</b>입니다. 주차한 뒤 이 화면으로 돌아오세요.</p>
    <ul class="list navi-options">${links.map((link) => `<li><a class="card navi-option" data-navi="${link.id}" href="${escapeHtml(link.url)}"><b>${escapeHtml(link.name)}</b><span>${escapeHtml(link.url)}</span></a></li>`).join('')}</ul>
    <p class="sheet-footnote">앱별 링크 형식은 기기와 설치 상태에 따라 달라질 수 있습니다. 앱이 열리지 않으면 내비 앱에서 목적지를 검색하세요.</p>
    <button class="btn sheet-close" data-action="close-navi">닫기</button>
  </section>`
}

function openNaviSheet() {
  if (!state.place?.navigation_target) return
  renderNaviSheet()
  naviSheet.hidden = false
  naviSheet.querySelector('.sheet-close')?.focus()
}

function closeNaviSheet() {
  naviSheet.hidden = true
  $('#btn-navi').focus()
}

function destinationRoute(parkingLotId) {
  return routeForParking(parkingLotId) || state.routes[0] || null
}

function finishTrip() {
  const route = destinationRoute(state.trip?.parkingLotId)
  clearTrip()
  state.trip = null
  if (route) location.href = guideUrl(route, { start: true })
  else {
    arrivalBox.innerHTML = '<p>주차장 도착을 확인했습니다. 이 주차장부터 안내하는 도보 경로는 아직 준비되지 않았습니다.</p>'
    arrivalBox.hidden = false
  }
}

function renderArrivalMessage(message, actions = true) {
  arrivalBox.innerHTML = `<p>${escapeHtml(message)}</p>${actions ? `<div class="actions"><button class="btn" data-action="check-arrival">다시 확인</button><button class="btn btn-primary" data-action="arrived-manually">주차장에 도착했어요</button></div>` : ''}`
  arrivalBox.hidden = false
}

function showTripReturn() {
  const trip = loadTrip()
  if (!trip || Number(trip.placeId) !== placeId) return
  state.trip = trip
  renderArrivalMessage('내비 앱에서 돌아오셨나요? 주차장에 도착했는지 확인해 보세요.')
  arrivalBox.querySelector('[data-action="arrived-manually"]')?.remove()
  const actions = arrivalBox.querySelector('.actions')
  if (actions) actions.innerHTML = '<button class="btn btn-primary" data-action="check-arrival">현재 위치로 확인</button>'
}

async function checkArrivalNow() {
  if (!state.place?.navigation_target) return
  renderArrivalMessage('현재 위치를 확인하고 있습니다.', false)
  const result = await checkArrival(state.place.navigation_target, state.place.arrival_radius_m)
  if (result.kind === 'arrived') {
    finishTrip()
    return
  }
  if (result.kind === 'far') {
    renderArrivalMessage(`아직 주차장에서 ${result.distanceM}m 떨어져 있습니다.`)
    return
  }
  renderArrivalMessage('위치를 확인하지 못했습니다. 권한을 허용하거나 실내·GPS 환경을 확인하세요.')
}

async function init() {
  if (!Number.isInteger(placeId) || placeId < 1) {
    placeInfo.innerHTML = '<p class="notice" role="status">주소에 올바른 장소 번호가 없습니다.</p>'
    return
  }
  state.map = createMap($('#map'))
  renderLegend($('#map-legend'))
  placeInfo.innerHTML = '<p class="empty" role="status">장소 정보를 불러오는 중입니다.</p>'

  try {
    state.place = await getPlace(placeId)
  } catch (error) {
    placeInfo.innerHTML = `<div class="notice" role="status"><p>${escapeHtml(loadErrorMessage(error))}</p><a class="btn btn-sm" href="/">홈으로</a></div>`
    $('#btn-guide').setAttribute('aria-disabled', 'true')
    $('#btn-navi').disabled = true
    return
  }

  renderPlace()
  drawMarkers(state.map, state.place)
  flyTo(state.map, { center: state.place.location.coordinates, ...state.place.camera })
  const [buildingResult, routeResult] = await Promise.allSettled([getBuildings(placeId), getWalkRoutes(placeId)])
  if (buildingResult.status === 'fulfilled') {
    state.buildings = buildingResult.value
    drawBuildings(state.map, state.buildings)
  }
  if (routeResult.status === 'fulfilled') state.routes = routeResult.value.items || []
  else $('#route-notice').textContent = loadErrorMessage(routeResult.reason)
  renderPlace()
  showTripReturn()
}

$('#btn-navi').addEventListener('click', openNaviSheet)
naviSheet.addEventListener('click', (event) => {
  if (event.target === naviSheet || event.target.closest('[data-action="close-navi"]')) {
    closeNaviSheet()
    return
  }
  const link = event.target.closest('[data-navi]')
  if (link && state.place?.navigation_target) {
    saveTrip({ placeId, parkingLotId: state.place.navigation_target.parking_lot_id })
  }
})
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && !naviSheet.hidden) closeNaviSheet()
})
arrivalBox.addEventListener('click', (event) => {
  if (event.target.closest('[data-action="check-arrival"]')) checkArrivalNow()
  if (event.target.closest('[data-action="arrived-manually"]')) finishTrip()
})

init()
