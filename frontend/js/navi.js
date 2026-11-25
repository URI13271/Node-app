// 외부 내비 앱 연결 (F-04)과 도착 판정. 목적지는 건물이 아니라 navigation_target(주차장)이다.
// 현재 위치는 브라우저 안에서만 쓰고 서버로 보내지 않는다 (ADR-006, N-03).
import { distanceM } from './geo.js'

// 네이버지도 URL 스킴은 호출한 앱 이름(appname)을 요구한다
const NAVI_APP_NAME = 'com.majunggil.app'

/**
 * 내비 앱 링크 목록 → [{id: 'kakao'|'naver'|'tmap', name, url}]. 좌표가 없으면 빈 배열
 * [검증 필요] 앱별 URL 스킴 파라미터는 실제 기기에서 확인 후 확정한다 (MVP 범위 정의서 7장 미결 사항)
 */
export function naviLinks(target) {
  const { lng, lat } = target || {}
  if (!Number.isFinite(lng) || !Number.isFinite(lat)) return []
  const name = encodeURIComponent(target.name || '목적지')
  return [
    { id: 'kakao', name: '카카오맵', url: `kakaomap://route?ep=${lat},${lng}&by=CAR` },
    { id: 'naver', name: '네이버지도', url: `nmap://route/car?dlat=${lat}&dlng=${lng}&dname=${name}&appname=${NAVI_APP_NAME}` },
    { id: 'tmap', name: '티맵', url: `tmap://route?goalx=${lng}&goaly=${lat}&goalname=${name}` },
  ]
}

// ---- 진행 중 여행 ----
// 내비 앱으로 떠나기 전에 {placeId, parkingLotId, startedAt} 를 저장하고, 돌아오면 도착 판정에 쓴다.
// localStorage + 6시간 만료로 둔다. sessionStorage 는 내비 앱을 다녀오는 사이 모바일 브라우저가 탭을 정리하면 사라질 수 있다.
// 위치는 저장하지 않는다 (장소 id, 주차장 id, 시각만).
const TRIP_STORAGE_KEY = 'majunggil.trip'
export const TRIP_TTL_MS = 6 * 60 * 60 * 1000

export function saveTrip(trip) {
  try { localStorage.setItem(TRIP_STORAGE_KEY, JSON.stringify({ ...trip, startedAt: trip.startedAt || Date.now() })) } catch { /* 저장소를 사용할 수 없으면 도착 판정만 건너뛴다 */ }
}

/** 저장된 여행. 없거나 6시간이 지났거나 시각이 미래면 null (지난 것은 지운다) */
export function loadTrip(now = Date.now()) {
  try {
    const trip = JSON.parse(localStorage.getItem(TRIP_STORAGE_KEY) || 'null')
    if (!trip || !Number.isFinite(trip.startedAt) || now - trip.startedAt >= TRIP_TTL_MS || now < trip.startedAt) {
      clearTrip()
      return null
    }
    return trip
  } catch { return null }
}

export function clearTrip() {
  try { localStorage.removeItem(TRIP_STORAGE_KEY) } catch { /* 무시 */ }
}

/** Geolocation 결과({coords})나 {lat, lng} 객체에서 [경도, 위도]를 꺼낸다 */
function locationCoordinates(position) {
  const coords = position?.coords || position
  const lat = coords?.latitude ?? coords?.lat
  const lng = coords?.longitude ?? coords?.lng
  return Number.isFinite(lat) && Number.isFinite(lng) ? [lng, lat] : null
}

/** 현재 위치와 주차장 사이 거리로 arrived, far, unavailable을 판정한다. */
export function judgeArrival(position, target, radiusM) {
  const current = locationCoordinates(position)
  const destination = locationCoordinates(target)
  if (!current || !destination || !Number.isFinite(radiusM) || radiusM < 0) {
    return { kind: 'unavailable', distanceM: null }
  }
  const distance = distanceM(current, destination)
  return { kind: distance <= radiusM ? 'arrived' : 'far', distanceM: Math.round(distance) }
}

/** 사용자가 버튼을 누른 시점에만 위치 권한을 요청한다. */
export function checkArrival(target, radiusM) {
  const geolocation = globalThis.navigator?.geolocation
  if (!geolocation?.getCurrentPosition) return Promise.resolve({ kind: 'unavailable', distanceM: null })
  return new Promise((resolve) => {
    geolocation.getCurrentPosition(
      (position) => resolve(judgeArrival(position, target, radiusM)),
      () => resolve({ kind: 'unavailable', distanceM: null }),
      // 정확한 위치, 10초 제한, 이전 위치 재사용 안 함. 실패하면 unavailable
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 },
    )
  })
}
