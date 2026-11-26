// place.html?id=1 (F-01 상세, F-03 목적 건물 강조, F-04 내비 연결, 도착 판정)
// 불러오는 API: GET /places/{id}, /places/{id}/buildings, /places/{id}/walk-routes
import { getBuildings, getPlace, getWalkRoutes } from '../api.js'
import { createMap, drawBuildings, drawMarkers, flyTo, renderLegend } from '../map.js'
import { checkArrival, clearTrip, loadTrip, naviLinks, saveTrip } from '../navi.js'
import { $, CATEGORY_LABEL, escapeHtml, loadErrorMessage, param } from '../util.js'

// 1. 주소 값, 화면 상태
const placeId = Number(param('id'))
// trip: 내비 앱으로 떠나기 전에 저장한 여행 (navi.js saveTrip). 돌아왔을 때 도착 판정에 쓴다
const state = { place: null, buildings: null, routes: [], trip: null, map: null }
const placeInfo = $('#place-info')
const parkingList = $('#parking-list')
const naviSheet = $('#navi-sheet')
const arrivalBox = $('#arrival-check')

// 2. 그리기

/** 이 주차장에서 출발하는 첫 도보 경로. 없으면 null */
function routeForParking(parkingLotId) {
  return state.routes.find((route) => route.parking_lot_id === parkingLotId) || null
}

/** 3D 안내 주소. start: true 면 개요를 건너뛰고 1단계부터 (도착 판정 뒤) */
function guideUrl(route, { start = false } = {}) {
  if (!route) return '#'
  const query = new URLSearchParams({ id: String(placeId), parking_lot_id: String(route.parking_lot_id), route: String(route.id) })
  if (start) query.set('start', '1')
  return `/guide.html?${query}`
}

/**
 * 장소 정보, 주차장 목록, 3D 안내 버튼을 그린다. 상세와 경로를 모두 받은 뒤 한 번 부른다
 * 주차장마다 도보 경로가 없으면 "입구까지 도보 경로를 준비 중" 을 보여 준다
 * 3D 안내 버튼은 내비 목적지 주차장의 경로를 먼저 고르고, 없으면 첫 경로. 경로가 하나도 없으면 비활성 + #route-notice
 */
function renderPlace() {
  const place = state.place
  if (!place) return
  const category = CATEGORY_LABEL[place.category] || '기타'
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
    </article>`

  const routesByLot = new Map()
  for (const route of state.routes) routesByLot.set(route.parking_lot_id, (routesByLot.get(route.parking_lot_id) || 0) + 1)
  // 주차장은 priority 순서. 내비 목적지 주차장(navigation_target)에는 "내비 목적지" 칩을 붙인다
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
}

// 3. 내비 연결 (F-04)

/** 내비 앱 선택 시트. 목적지는 건물이 아니라 navigation_target(주차장)이다 */
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
    <ul class="list navi-options">${links.map((link) => `<li><a class="card navi-option" data-navi="${link.id}" href="${escapeHtml(link.url)}"><b>${escapeHtml(link.name)}</b></a></li>`).join('')}</ul>
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

// 4. 도착 판정
// 내비 앱에서 돌아오면 loadTrip() 이 이 장소인지 보고 #arrival-check 를 띄운다. checkArrival 결과는 세 가지
//   - arrived      → 3D 안내 1단계로 (start=1), clearTrip()
//   - far          → 남은 거리 + [주차장에 도착했어요] 버튼
//   - unavailable  → 위치를 못 받음 (권한 거부, 실내, GPS 불안정) + [주차장에 도착했어요] 버튼
// [주차장에 도착했어요] 는 위치 확인 없이 arrived 와 같게 진행한다. 시연 중 실내나 GPS 가 불안정해도 막히지 않게 (N-03)

/** 도착한 주차장의 경로. 없으면 첫 경로 */
function destinationRoute(parkingLotId) {
  return routeForParking(parkingLotId) || state.routes[0] || null
}

/** 도착 처리: 여행 기록을 지우고 3D 안내 1단계로 간다. 경로가 없으면 안내 문구만 */
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

/** 이 장소로 떠났던 여행이 있으면 "돌아오셨나요?" 안내. 처음에는 위치 확인 버튼만 보여 준다 */
function showTripReturn() {
  const trip = loadTrip()
  if (!trip || Number(trip.placeId) !== placeId) return
  state.trip = trip
  renderArrivalMessage('내비 앱에서 돌아오셨나요? 주차장에 도착했는지 확인해 보세요.', false)
  arrivalBox.insertAdjacentHTML('beforeend', '<div class="actions"><button class="btn btn-primary" data-action="check-arrival">현재 위치로 확인</button></div>')
}

/** 버튼을 누른 순간에만 위치를 한 번 받는다. 위치는 서버로 보내지 않는다 (ADR-006) */
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

// 5. 불러오기
// 상세, 건물, 경로를 함께 받고 한 번만 그린다 (경로를 받기 전에 "준비 중"이 깜빡이지 않게)
// 장소 상세가 실패하면 홈 링크만 보여 주고 멈춘다. 건물, 경로는 실패해도 상세는 그대로 보여 준다
async function load() {
  if (!Number.isInteger(placeId) || placeId < 1) {
    placeInfo.innerHTML = '<p class="notice" role="status">주소에 올바른 장소 번호가 없습니다.</p>'
    return
  }
  state.map = createMap($('#map'))
  renderLegend($('#map-legend'))
  placeInfo.innerHTML = '<p class="empty" role="status">장소 정보를 불러오는 중입니다.</p>'

  const [placeResult, buildingResult, routeResult] = await Promise.allSettled([
    getPlace(placeId), getBuildings(placeId), getWalkRoutes(placeId),
  ])
  if (placeResult.status === 'rejected') {
    const error = placeResult.reason
    placeInfo.innerHTML = `<div class="notice" role="status"><p>${escapeHtml(loadErrorMessage(error))}</p><a class="btn btn-sm" href="/">홈으로</a></div>`
    $('#btn-guide').setAttribute('aria-disabled', 'true')
    $('#btn-navi').disabled = true
    return
  }

  state.place = placeResult.value
  drawMarkers(state.map, state.place)
  flyTo(state.map, { center: state.place.location.coordinates, ...state.place.camera })
  if (buildingResult.status === 'fulfilled') {
    state.buildings = buildingResult.value
    drawBuildings(state.map, state.buildings)
  }
  if (routeResult.status === 'fulfilled') state.routes = routeResult.value.items || []
  else $('#route-notice').textContent = loadErrorMessage(routeResult.reason)
  renderPlace()
  showTripReturn()
}

// 6. 이벤트
function bind() {
  $('#btn-navi').addEventListener('click', openNaviSheet)
  naviSheet.addEventListener('click', (event) => {
    if (event.target === naviSheet || event.target.closest('[data-action="close-navi"]')) {
      closeNaviSheet()
      return
    }
    const link = event.target.closest('[data-navi]')
    // 앱으로 떠나기 직전에 여행을 저장한다 (돌아오면 도착 판정)
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
}

// 7. 시작
bind()
load()
