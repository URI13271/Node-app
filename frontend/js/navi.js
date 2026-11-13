// 외부 내비 앱 연결 (F-04)과 도착 판정. 목적지는 건물이 아니라 navigation_target(주차장)이다.
// [검증 필요] 앱별 URL 스킴 파라미터는 실제 앱에서 확인 후 확정한다 (MVP 범위 정의서 7장 미결 사항).
import { todo } from './util.js'

/** 내비 앱 링크 목록 → [{id: 'kakao'|'naver'|'tmap', name, url}] */
export function naviLinks(target) { return todo('naviLinks') }

// ---- 진행 중 여행 ----
// 내비 앱으로 떠나기 전에 {placeId, parkingLotId, startedAt} 를 저장하고, 돌아오면 도착 판정에 쓴다.
// localStorage + 6시간 만료로 둔다. sessionStorage 는 내비 앱을 다녀오는 사이 모바일 브라우저가 탭을 정리하면 사라질 수 있다.
// 위치는 저장하지 않는다 (장소 id, 주차장 id, 시각만. ADR-006, N-03).
const TRIP_KEY = 'majunggil.trip'
export const TRIP_TTL_MS = 6 * 60 * 60 * 1000

export function saveTrip(trip) {
  try { localStorage.setItem(TRIP_KEY, JSON.stringify({ ...trip, startedAt: trip.startedAt || Date.now() })) } catch { /* 저장 못 하면 도착 판정만 건너뛴다 */ }
}

/** 저장된 여행. 없거나 6시간이 지났으면 null (지난 것은 지운다) */
export function loadTrip(now = Date.now()) {
  try {
    const t = JSON.parse(localStorage.getItem(TRIP_KEY) || 'null')
    if (!t || !(now - t.startedAt < TRIP_TTL_MS)) { clearTrip(); return null }
    return t
  } catch { return null }
}

export function clearTrip() {
  try { localStorage.removeItem(TRIP_KEY) } catch { /* 무시 */ }
}

/** 현재 위치 pos 와 목적지 거리가 radiusM 이하면 도착 → {kind: 'arrived'|'far'|'unavailable', distanceM} */
export function judgeArrival(pos, target, radiusM) { return todo('judgeArrival') }

/** TODO: navigator.geolocation 으로 현재 위치를 한 번 받아 judgeArrival */
export function checkArrival(target, radiusM) { return todo('checkArrival') }
