// 외부 내비 연결과 도착 판정. 현재 위치는 브라우저 안에서만 사용한다.
import { distanceM } from './geo.js'

const NAVI_APP_NAME = 'com.majunggil.app'

/** 카카오맵, 네이버지도, 티맵 목적지 링크 */
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

// 여행 정보는 내비 앱을 다녀온 뒤 복귀 판정에 쓰고, 위치 정보는 보관하지 않는다.
const TRIP_KEY = 'majunggil.trip'
export const TRIP_TTL_MS = 6 * 60 * 60 * 1000

export function saveTrip(trip) {
  try { localStorage.setItem(TRIP_KEY, JSON.stringify({ ...trip, startedAt: trip.startedAt || Date.now() })) } catch { /* 저장소를 사용할 수 없으면 도착 판정만 건너뛴다 */ }
}

export function loadTrip(now = Date.now()) {
  try {
    const trip = JSON.parse(localStorage.getItem(TRIP_KEY) || 'null')
    if (!trip || !Number.isFinite(trip.startedAt) || now - trip.startedAt >= TRIP_TTL_MS || now < trip.startedAt) {
      clearTrip()
      return null
    }
    return trip
  } catch { return null }
}

export function clearTrip() {
  try { localStorage.removeItem(TRIP_KEY) } catch { /* 무시 */ }
}

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
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 },
    )
  })
}
