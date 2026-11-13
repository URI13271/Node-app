// place.html?id=1 (F-01 상세, F-03 강조, F-04 내비)
import { getBuildings, getPlace, getWalkRoutes } from '../api.js'
import { createMap, renderLegend } from '../map.js'
import { naviLinks, loadTrip, checkArrival } from '../navi.js'
import { $, escapeHtml, loadErrorMessage, param } from '../util.js'

const placeId = Number(param('id'))

/** 도보 경로 유무에 따라 3D 안내 버튼과 안내 문구를 바꾼다 (경로가 없으면 버튼 비활성 + 이유 표시) */
function renderRouteState(routes) {
  const btn = $('#btn-guide')
  const none = routes.length === 0
  $('#route-notice').hidden = !none
  btn.setAttribute('aria-disabled', String(none))
  btn.href = none ? '#' : `/guide.html?id=${placeId}&parking_lot_id=${routes[0].parking_lot_id}`
  // TODO 3-1. #parking-list 의 주차장마다 이 경로 목록에 그 parking_lot_id 가 없으면 "입구까지 도보 경로 준비 중" 표시
}

async function init() {
  if (!(placeId >= 1)) { $('#place-info').textContent = '주소에 장소 번호(id)가 없습니다.'; return }
  const map = createMap($('#map'))
  renderLegend($('#map-legend'))
  // TODO 1. getPlace(placeId) → #place-info, #parking-list 그리기 (404 면 안내)
  // TODO 2. getBuildings(placeId) → 지도에 목적 건물 강조
  try {
    const routes = await getWalkRoutes(placeId)
    renderRouteState(routes.items)
  } catch (e) {
    $('#place-info').innerHTML = `<p class="notice" role="status">${escapeHtml(loadErrorMessage(e))}</p>`
    $('#btn-guide').setAttribute('aria-disabled', 'true')
  }
  // TODO 4. #btn-navi → #navi-sheet 에 naviLinks(place.navigation_target) 버튼
  // TODO 5. 도착 판정: loadTrip() 이 이 장소면 #arrival-check 에 "도착하셨나요?" + [위치로 확인] 버튼
  //   checkArrival 결과
  //   - arrived            → "주차장에 도착했어요" 안내 후 3D 안내로 (guide.html?...&start=1), clearTrip()
  //   - far                → "아직 주차장에서 {distanceM}m 떨어져 있어요" + [주차장에 도착했어요] 버튼
  //   - unavailable        → "위치를 확인하지 못했어요 (권한 거부, 실내, GPS 불안정)" + [주차장에 도착했어요] 버튼
  //   [주차장에 도착했어요] 를 누르면 위치 확인 없이 arrived 와 같게 진행한다. 시연 중 실내나 GPS 가 불안정해도 막히지 않게
}

init()
