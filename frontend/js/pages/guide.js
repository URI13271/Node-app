// guide.html?id=1&parking_lot_id=&route=&start=1 (F-02~F-05 3D 안내)
import { getBuildings, getPlace, getWalkRoutes } from '../api.js'
import { createMap, drawBuildings, drawMarkers, drawRoute, flyTo, renderLegend } from '../map.js'
import { $, loadErrorMessage, param } from '../util.js'

// 1. 주소 값, 화면 상태
const placeId = Number(param('id'))
const state = {
  place: null,
  route: null,  // 고른 도보 경로 (steps 포함)
  step: -1,     // -1: 도착 방향 개요, 0..n-1: 단계, n: 도착 완료
  error: '',
}

// 2. 그리기: state 만 보고 카드를 바꾼다
function render() {
  const steps = state.route?.steps || []
  const n = steps.length
  const { step } = state

  // 진행 막대: 단계 수만큼 칸, 지나온 단계까지 .on
  $('#step-seg').innerHTML = steps.map((_, k) => `<i class="${k <= step ? 'on' : ''}"></i>`).join('')

  // 큰 번호와 문장
  const num = $('#step-num')
  const text = $('#step-text')
  if (state.error) {
    num.textContent = ''
    text.textContent = state.error
  } else if (!state.route) {
    num.textContent = ''
    text.textContent = state.place ? '이 장소는 아직 도보 경로 안내가 준비되지 않았어요.' : '불러오는 중'
  } else if (step < 0) {
    num.textContent = '개요'
    text.textContent = `주차장에서 입구까지 ${Math.round(state.route.distance_m)}m, 걸어서 약 ${state.route.walk_time_min}분. 단계 ${n}개`
  } else if (step < n) {
    const s = steps[step]
    num.innerHTML = `${step + 1}<small> / ${n}</small>`
    text.textContent = s.landmark ? `${s.instruction} (랜드마크: ${s.landmark.name})` : s.instruction
  } else {
    num.textContent = '도착'
    text.textContent = '입구에 도착했습니다.'
  }

  // 버튼: 개요에서는 이전 비활성, 마지막 단계에서는 "다음" 대신 "도착", 도착 완료에서는 완료 버튼 묶음
  const done = !!state.route && step >= n
  $('#step-actions').hidden = done
  $('#done-actions').hidden = !done
  $('#btn-prev').disabled = !state.route || step < 0
  $('#btn-next').disabled = !state.route
  $('#btn-next').textContent = !state.route ? '다음' : step < 0 ? '안내 시작' : step === n - 1 ? '도착' : '다음'

  // TODO 3. 지도 시점: step < 0 → 출발 주차장 camera, 0..n-1 → steps[step].camera, n → 입구 위치. flyTo(map, ...)
  //         지나온 구간: drawRoute(map, state.route, fractionOnPath(path, 현재 단계 지점))
}

// 3. 불러오기
async function load() {
  if (!(placeId >= 1)) { state.error = '주소에 장소 번호(id)가 없습니다.'; render(); return }
  try {
    const [place, , routes] = await Promise.all([getPlace(placeId), getBuildings(placeId), getWalkRoutes(placeId)])
    state.place = place
    // 처음 경로 고르기: route → parking_lot_id → 첫 경로
    const routeId = Number(param('route')), lotId = Number(param('parking_lot_id'))
    state.route = routes.items.find((r) => r.id === routeId)
      || routes.items.find((r) => r.parking_lot_id === lotId)
      || routes.items[0] || null
    state.step = param('start') === '1' && state.route ? 0 : -1
    $('#btn-detail').href = `/place.html?id=${placeId}`
    // TODO 3. createMap 뒤 drawBuildings(map, buildings), drawRoute(map, state.route), drawMarkers(map, place, {activeEntranceId: state.route?.entrance_id})
  } catch (e) {
    state.error = loadErrorMessage(e)
  }
  render()
}

// 4. 이벤트
function bind() {
  $('#btn-prev').addEventListener('click', () => { state.step = Math.max(-1, state.step - 1); render() })
  $('#btn-next').addEventListener('click', () => {
    const n = state.route?.steps.length || 0
    state.step = Math.min(n, state.step + 1) // 마지막 단계(n-1)에서 누르면 n = 도착 완료
    render()
  })
}

// 5. 시작
const map = createMap($('#map')) // TODO 3 에서 drawBuildings, drawRoute, drawMarkers, flyTo 에 넘긴다
renderLegend($('#map-legend'), ['entrance', 'landmark', 'route'])
bind()
render()
load()
