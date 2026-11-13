// 서버 API 호출 (API 명세서 v1.3). 화면 파일은 fetch 를 직접 쓰지 않고 이 파일의 함수만 부른다.
// 응답 필드 이름은 서버와 같은 snake_case 를 그대로 쓴다.
//
// 가짜 응답(mock): 주소에 ?mock=1 을 붙여 한 번 열면 그 탭에서는 서버 대신 frontend/mock/ 의 JSON 을 쓴다 (?mock=0 으로 끔).
// 백엔드가 아직 501 을 주는 동안에도 화면을 만들 수 있다. 자세한 것은 mock/README.md.
import { isMockMode, mockRequest } from './mock.js'

const BASE = '/api/v1'

/** 서버가 보낸 오류 본문 {"error": {code, message, request_id, details}} 를 담는 오류 */
export class ApiError extends Error {
  constructor(status, code, message, details = [], requestId = null, retryAfter = null) {
    super(message)
    this.status = status         // 400, 401, 404, 409, 429 ...
    this.code = code             // INVALID_INPUT, CONFLICT ...
    this.details = details       // [{field, reason, message}]
    this.requestId = requestId
    this.retryAfter = retryAfter // 429 일 때 다시 시도할 초
  }
}

/**
 * 공통 요청. 성공하면 응답 본문(JSON)을 돌려주고, 실패하면 ApiError 를 던진다.
 * - 서버 오류는 항상 {"error": {code, message, request_id, details}} 한 가지 형식이다 (검증 오류도 400 INVALID_INPUT).
 * - 429 는 Retry-After 헤더를 retryAfter(초)로 넣는다.
 * - 304 는 직접 다루지 않는다. If-None-Match 를 붙이지 않고 브라우저 캐시에 맡긴다 (getWalkRoutes 설명).
 * @param {string} path  BASE 뒤 경로. 예: '/places?q=도서관'
 * @param {{method?: 'GET'|'PUT'|'PATCH', body?: any, adminKey?: string|null, cache?: RequestCache}} [opt]
 *   cache 는 fetch 의 cache 옵션 그대로 넘긴다. 관리자 편집 화면은 'no-store'
 */
export async function request(path, opt = {}) {
  if (isMockMode()) return mockRequest(path, opt)

  const headers = { 'X-Request-ID': crypto.randomUUID() }
  if (opt.body !== undefined) headers['Content-Type'] = 'application/json'
  if (opt.adminKey) headers['X-Admin-Key'] = opt.adminKey

  let res
  try {
    res = await fetch(BASE + path, {
      method: opt.method || 'GET',
      headers,
      body: opt.body !== undefined ? JSON.stringify(opt.body) : undefined,
      cache: opt.cache,
    })
  } catch {
    throw new ApiError(0, 'NETWORK', '서버에 연결하지 못했습니다. 인터넷 연결을 확인하세요.')
  }
  const data = await res.json().catch(() => null)
  if (res.ok) return data
  const e = data?.error
  const retry = Number(res.headers.get('Retry-After')) || null
  throw new ApiError(res.status, e?.code || 'INTERNAL', e?.message || '서버 오류가 발생했습니다.', e?.details || [], e?.request_id || null, retry)
}

/** 쿼리 문자열 만들기. null, undefined, 빈 문자열은 뺀다. 예: qs({q: '도서관', limit: 20}) → '?q=%EB%8F%84...&limit=20' */
export function qs(params) {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== '') p.set(k, String(v))
  const s = p.toString()
  return s ? `?${s}` : ''
}

// ---- 공개 API ----

/** GET /places?q=&limit=&offset= → {total, limit, offset, items} */
export function getPlaces(q = '', limit = 20, offset = 0) {
  return request(`/places${qs({ q: q.trim(), limit, offset })}`)
}

/** GET /places/{id} → 장소 상세 (입구, 주차장, 랜드마크, navigation_target, arrival_radius_m) */
export function getPlace(id) {
  return request(`/places/${id}`)
}

/** GET /places/{id}/buildings → 건물 GeoJSON {type, features, attributions} */
export function getBuildings(id) {
  return request(`/places/${id}/buildings`)
}

/**
 * GET /places/{id}/walk-routes?parking_lot_id= → {items}
 * 서버가 Cache-Control: no-cache 와 ETag 를 보내므로 브라우저가 알아서 재검증하고, 바뀌지 않았으면 캐시 본문으로 200 을 준다.
 * 그래서 ETag, If-None-Match, 304 를 JS 에서 다루지 않는다.
 * @param {{fresh?: boolean}} [opt]  관리자 편집 화면은 {fresh: true} → cache: 'no-store' (항상 서버 최신본)
 */
export function getWalkRoutes(id, parkingLotId = null, opt = {}) {
  return request(`/places/${id}/walk-routes${qs({ parking_lot_id: parkingLotId })}`, { cache: opt.fresh ? 'no-store' : undefined })
}

// ---- 관리자 API (헤더 X-Admin-Key) ----
// 경로 버전 updated_at 은 마이크로초까지 있는 문자열이다 (예: "2026-11-12T05:54:08.124567Z").
// new Date() 로 바꾸면 밀리초까지만 남아 저장할 때마다 409 가 난다. 받은 문자열 그대로 expected_updated_at 에 넣는다.

/** GET /admin/me → {role}. 키가 틀리면 401, 같은 IP 연속 5회면 429(details[0].reason === 'locked') */
export function checkAdminKey(key) {
  return request('/admin/me', { adminKey: key, cache: 'no-store' })
}

/**
 * PUT /admin/walk-routes/{routeId}/steps → 경로 전체 (새 updated_at 포함). 버전이 다르면 409 CONFLICT
 * @param {{expected_updated_at: string, updated_by: string, steps: Array<{step_order, instruction, landmark_id, location, camera}>}} body
 *   expected_updated_at: 받은 route.updated_at 문자열 그대로 (Date 로 바꾸지 않는다)
 */
export function replaceSteps(routeId, body, adminKey) {
  return request(`/admin/walk-routes/${routeId}/steps`, { method: 'PUT', body, adminKey })
}

/**
 * PATCH /admin/walk-route-steps/{stepId} → 단계 + walk_route_id + walk_route_updated_at. 보낸 키만 바꾼다 (null 은 지움)
 * @param {{updated_by: string, expected_updated_at?: string, instruction?: string, landmark_id?: number|null, camera?: object|null}} body
 */
export function patchStep(stepId, body, adminKey) {
  return request(`/admin/walk-route-steps/${stepId}`, { method: 'PATCH', body, adminKey })
}
