// 단말 안에서만 쓰는 거리 계산. 위치는 서버로 보내지 않는다 (ADR-006, N-03).
// 좌표는 항상 [경도, 위도] 순서 배열이다. 예: [128.0985, 35.1534]

const EARTH_RADIUS_M = 6371008.8
const rad = (degrees) => (degrees * Math.PI) / 180
const fraction = (value) => Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0
const copyPoint = (point) => [point[0], point[1]]

/** 두 점 사이 거리(m): 지구가 둥근 점을 고려하는 하버사인 공식 */
export function distanceM([lng1, lat1], [lng2, lat2]) {
  const dLat = rad(lat2 - lat1)
  const dLng = rad(lng2 - lng1)
  const h = Math.sin(dLat / 2) ** 2
    + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dLng / 2) ** 2
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(Math.min(1, h)))
}

/** 경로에서 p 에 가장 가까운 꼭짓점 번호. 경로가 비어 있으면 -1 */
export function nearestVertex(path, p) {
  if (!path.length) return -1
  let nearest = 0
  let nearestDistance = distanceM(path[0], p)
  for (let i = 1; i < path.length; i += 1) {
    const distance = distanceM(path[i], p)
    if (distance < nearestDistance) {
      nearest = i
      nearestDistance = distance
    }
  }
  return nearest
}

/** 경로 전체 길이(m). 점이 하나뿐이거나 비어 있으면 0 */
export function pathLengthM(path) {
  let length = 0
  for (let i = 1; i < path.length; i += 1) length += distanceM(path[i - 1], path[i])
  return length
}

/** 경로 위 비율 t(0~1) 지점. 비어 있는 경로는 null */
export function pointAlong(path, t) {
  if (!path.length) return null
  if (path.length === 1) return copyPoint(path[0])

  const total = pathLengthM(path)
  if (total === 0) return copyPoint(path[0])

  const target = total * fraction(t)
  let travelled = 0
  for (let i = 1; i < path.length; i += 1) {
    const start = path[i - 1]
    const end = path[i]
    const segment = distanceM(start, end)
    if (travelled + segment >= target) {
      const part = segment === 0 ? 0 : (target - travelled) / segment
      return [start[0] + (end[0] - start[0]) * part, start[1] + (end[1] - start[1]) * part]
    }
    travelled += segment
  }
  return copyPoint(path.at(-1))
}

/** p 에서 경로에 수선을 내린 가장 가까운 지점까지의 진행 비율(0~1) */
export function fractionOnPath(path, p) {
  const total = pathLengthM(path)
  if (path.length < 2 || total === 0) return 0

  let travelled = 0
  let nearestDistance = Infinity
  let nearestFraction = 0
  for (let i = 1; i < path.length; i += 1) {
    const start = path[i - 1]
    const end = path[i]
    const segment = distanceM(start, end)
    if (segment === 0) continue

    // 캠퍼스처럼 작은 범위에서는 위경도를 지역 평면 좌표로 바꿔 수선 위치를 구한다.
    const cosLat = Math.cos(rad((start[1] + end[1]) / 2))
    const dx = rad(end[0] - start[0]) * cosLat
    const dy = rad(end[1] - start[1])
    const px = rad(p[0] - start[0]) * cosLat
    const py = rad(p[1] - start[1])
    const part = fraction((px * dx + py * dy) / (dx * dx + dy * dy))
    const projected = [start[0] + (end[0] - start[0]) * part, start[1] + (end[1] - start[1]) * part]
    const distance = distanceM(p, projected)
    if (distance < nearestDistance) {
      nearestDistance = distance
      nearestFraction = (travelled + segment * part) / total
    }
    travelled += segment
  }
  return nearestFraction
}

/** 경로 처음부터 비율 t 까지 자른 선. t 는 0~1 범위로 제한한다 */
export function pathUntil(path, t) {
  if (!path.length) return []
  if (path.length === 1 || pathLengthM(path) === 0) return path.map(copyPoint)

  const progress = fraction(t)
  if (progress === 0) return [copyPoint(path[0])]
  if (progress === 1) return path.map(copyPoint)

  const target = pathLengthM(path) * progress
  let travelled = 0
  for (let i = 1; i < path.length; i += 1) {
    const start = path[i - 1]
    const end = path[i]
    const segment = distanceM(start, end)
    if (travelled + segment >= target) {
      const part = segment === 0 ? 0 : (target - travelled) / segment
      const result = path.slice(0, i).map(copyPoint)
      result.push([start[0] + (end[0] - start[0]) * part, start[1] + (end[1] - start[1]) * part])
      return result
    }
    travelled += segment
  }
  return path.map(copyPoint)
}
