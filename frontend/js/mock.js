// 가짜 응답(mock). 백엔드 없이 화면을 만들 때 쓴다. 백엔드가 실제 응답을 주기 시작하면 이 파일과 mock/ 폴더를 지운다.
//
// 켜기: 아무 화면 주소 뒤에 ?mock=1 을 붙여 한 번 연다 (예: /?mock=1). 그 탭에서는 계속 켜져 있다.
// 끄기: ?mock=0 을 붙여 연다. 켜져 있으면 화면 오른쪽 위에 "MOCK" 표시가 뜬다.
//
// 데이터: frontend/mock/ 의 JSON (API 명세서 v1.3 형식의 예시 응답, 가좌캠퍼스 장소 3곳).
// 관리자 저장(PUT, PATCH)은 이 탭의 sessionStorage 에 기억한다. 다른 화면으로 가도 유지되고, 탭을 닫으면 처음으로 돌아간다.
// 관리자 키: 아무 값이나 통과. 'wrong' 은 401, 'locked' 는 429(잠김)로 오류 화면을 시험할 수 있다.
// 개발자 도구 콘솔에서: majunggilMock.bump(경로id) → 다른 관리자가 먼저 저장한 것처럼 버전을 바꾼다 (409 화면 시험)
//                      majunggilMock.reset()      → 저장한 내용을 지우고 처음 데이터로
import { ApiError } from './api.js'

const MOCK_STORAGE_KEY = 'majunggil.mock'
const MOCK_EDITS_STORAGE_KEY = 'majunggil.mock.routes' // {routeId: route} 관리자가 저장한 경로

function storage() {
  try { return window.sessionStorage } catch { return null }
}

/** 주소의 ?mock=1 / ?mock=0 을 기억하고, 지금 mock 을 쓰는지 알려준다 */
export function isMockMode() {
  if (typeof window === 'undefined') return false
  const s = storage()
  const q = new URLSearchParams(location.search).get('mock')
  try {
    if (q === '1') s?.setItem(MOCK_STORAGE_KEY, '1')
    if (q === '0') s?.removeItem(MOCK_STORAGE_KEY)
    return s?.getItem(MOCK_STORAGE_KEY) === '1'
  } catch {
    return q === '1'
  }
}

function showBadge() {
  if (document.getElementById('mock-badge')) return
  const b = document.createElement('div')
  b.id = 'mock-badge'
  b.className = 'mock-badge'
  b.textContent = 'MOCK'
  b.title = '가짜 응답을 쓰는 중 (끄려면 주소에 ?mock=0)'
  document.body.appendChild(b)
}
if (typeof window !== 'undefined' && isMockMode()) {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', showBadge)
  else showBadge()
}

// ---- 도구 ----
const wait = (ms) => new Promise((r) => setTimeout(r, ms))
const err = (status, code, message, details = [], retryAfter = null) => new ApiError(status, code, message, details, 'mock', retryAfter)

async function file(rel) {
  const res = await fetch(`/mock/${rel}`, { cache: 'no-cache' })
  if (res.status === 404) throw err(404, 'NOT_FOUND', '장소를 찾을 수 없습니다.')
  if (!res.ok) throw err(500, 'INTERNAL', `mock 파일을 읽지 못했습니다: ${rel}`)
  return res.json()
}

/** 서버처럼 마이크로초까지 있는 버전 문자열. 예: 2026-11-12T05:54:08.124567Z */
function stamp() {
  const micro = String(Math.floor(Math.random() * 1e6)).padStart(6, '0')
  return new Date().toISOString().slice(0, 19) + '.' + micro + 'Z'
}

function edits() {
  try { return JSON.parse(storage()?.getItem(MOCK_EDITS_STORAGE_KEY) || '{}') } catch { return {} }
}
function saveEdit(route) {
  const all = edits()
  all[route.id] = route
  try { storage()?.setItem(MOCK_EDITS_STORAGE_KEY, JSON.stringify(all)) } catch { /* 저장 못 해도 이번 응답은 돌려준다 */ }
}

/** 장소의 경로 목록 (관리자 저장 내용을 덮어씀) */
async function routesOf(placeId) {
  const data = await file(`places/${placeId}/walk-routes.json`)
  const ed = edits()
  return data.items.map((r) => ed[r.id] || r)
}

/** 경로 id → {placeId, route}. 장소 목록을 돌며 찾는다 */
async function findRoute(routeId) {
  const places = await file('places.json')
  for (const p of places.items) {
    const route = (await routesOf(p.id)).find((r) => r.id === routeId)
    if (route) return { placeId: p.id, route }
  }
  throw err(404, 'NOT_FOUND', '경로를 찾을 수 없습니다.')
}

async function findStep(stepId) {
  const places = await file('places.json')
  for (const p of places.items) {
    for (const route of await routesOf(p.id)) {
      const step = route.steps.find((s) => s.id === stepId)
      if (step) return { placeId: p.id, route, step }
    }
  }
  throw err(404, 'NOT_FOUND', '단계를 찾을 수 없습니다.')
}

function checkKey(key) {
  if (!key) throw err(401, 'UNAUTHORIZED', '관리자 키가 맞지 않습니다.')
  if (key === 'wrong') throw err(401, 'UNAUTHORIZED', '관리자 키가 맞지 않습니다.')
  if (key === 'locked') {
    throw err(429, 'RATE_LIMITED', '관리자 키를 여러 번 틀려 잠시 막혔습니다.',
      [{ field: 'header.X-Admin-Key', reason: 'locked', message: '같은 IP에서 키를 연속 5회 틀려 10분 동안 막혔습니다.' }], 600)
  }
}

function conflict(route) {
  return err(409, 'CONFLICT', '다른 관리자가 먼저 저장했습니다. 최신 내용을 확인하세요.',
    [{ field: 'expected_updated_at', reason: 'stale', message: `현재 버전: ${route.updated_at}` }])
}

async function landmarkRef(placeId, landmarkId) {
  if (landmarkId == null) return null
  const place = await file(`places/${placeId}.json`)
  const lm = place.landmarks.find((l) => l.id === landmarkId)
  if (!lm) throw err(400, 'INVALID_INPUT', '입력값을 확인하세요.', [{ field: 'landmark_id', reason: 'not_in_place', message: '이 장소의 랜드마크가 아닙니다.' }])
  return { id: lm.id, name: lm.name }
}

const DEFAULT_STEP_CAMERA = { bearing: 0, pitch: 55, zoom: 18.5 }

// ---- 요청 처리 ----

/** api.js 의 request() 와 같은 모양: 성공하면 본문, 실패하면 ApiError */
export async function mockRequest(path, opt = {}) {
  await wait(150) // 불러오는 중 화면이 보이도록
  const url = new URL(path, 'http://mock')
  const parts = url.pathname.split('/').filter(Boolean) // ['places', '1', 'walk-routes']
  const method = opt.method || 'GET'
  const q = url.searchParams

  if (method === 'GET' && parts[0] === 'places') {
    if (parts.length === 1) {
      const term = (q.get('q') || '').trim()
      if (term.length > 50) throw err(400, 'INVALID_INPUT', '입력값을 확인하세요.', [{ field: 'query.q', reason: 'too_long', message: '검색어는 50자 이하로 입력하세요.' }])
      const limit = Number(q.get('limit') || 20), offset = Number(q.get('offset') || 0)
      const all = (await file('places.json')).items.filter((p) => p.name.toLowerCase().includes(term.toLowerCase()))
      return { total: all.length, limit, offset, items: all.slice(offset, offset + limit) }
    }
    const id = Number(parts[1])
    if (!(id >= 1)) throw err(400, 'INVALID_INPUT', '입력값을 확인하세요.', [{ field: 'id', reason: 'out_of_range', message: 'id 는 1 이상이어야 합니다.' }])
    if (parts.length === 2) return file(`places/${id}.json`)
    if (parts[2] === 'buildings') return file(`places/${id}/buildings.json`)
    if (parts[2] === 'walk-routes') {
      const lot = q.get('parking_lot_id')
      const items = await routesOf(id)
      return { items: lot ? items.filter((r) => r.parking_lot_id === Number(lot)) : items }
    }
  }

  if (parts[0] === 'admin') {
    checkKey(opt.adminKey)
    if (method === 'GET' && parts[1] === 'me') return { role: 'admin' }

    if (method === 'PUT' && parts[1] === 'walk-routes' && parts[3] === 'steps') {
      const { placeId, route } = await findRoute(Number(parts[2]))
      const body = opt.body || {}
      if (body.expected_updated_at !== route.updated_at) throw conflict(route)
      const steps = Array.isArray(body.steps) ? body.steps : []
      if (steps.length < 2) throw err(400, 'INVALID_INPUT', '입력값을 확인하세요.', [{ field: 'steps', reason: 'too_few_steps', message: '단계는 2개 이상이어야 합니다.' }])
      let nextId = Math.max(0, ...Object.values(edits()).flatMap((r) => r.steps.map((s) => s.id)), ...route.steps.map((s) => s.id)) + 1000
      const out = []
      for (const s of [...steps].sort((a, b) => a.step_order - b.step_order)) {
        out.push({
          id: nextId++, step_order: s.step_order, instruction: String(s.instruction || '').trim(),
          landmark: await landmarkRef(placeId, s.landmark_id), location: s.location,
          camera: s.camera || DEFAULT_STEP_CAMERA, camera_is_default: !s.camera,
        })
      }
      const saved = { ...route, steps: out, updated_at: stamp() }
      saveEdit(saved)
      return saved
    }

    if (method === 'PATCH' && parts[1] === 'walk-route-steps') {
      const { placeId, route, step } = await findStep(Number(parts[2]))
      const body = opt.body || {}
      if (body.expected_updated_at != null && body.expected_updated_at !== route.updated_at) throw conflict(route)
      const next = { ...step }
      if ('instruction' in body) next.instruction = String(body.instruction || '').trim()
      if ('landmark_id' in body) next.landmark = await landmarkRef(placeId, body.landmark_id)
      if ('camera' in body) { next.camera = body.camera || DEFAULT_STEP_CAMERA; next.camera_is_default = !body.camera }
      const saved = { ...route, steps: route.steps.map((s) => (s.id === step.id ? next : s)), updated_at: stamp() }
      saveEdit(saved)
      return { ...next, walk_route_id: saved.id, walk_route_updated_at: saved.updated_at }
    }
  }

  throw err(404, 'NOT_FOUND', `mock 에 없는 요청입니다: ${method} ${url.pathname}`)
}

// 개발자 도구 콘솔용
if (typeof window !== 'undefined') {
  window.majunggilMock = {
    async bump(routeId) {
      const { route } = await findRoute(Number(routeId))
      const steps = route.steps.map((s, i) => (i === 0 ? { ...s, instruction: `(다른 관리자 수정) ${s.instruction}` } : s))
      saveEdit({ ...route, steps, updated_at: stamp() })
      return '경로 버전을 바꿨습니다. 지금 저장하면 409 가 납니다.'
    },
    reset() {
      try { storage()?.removeItem(MOCK_EDITS_STORAGE_KEY) } catch { /* 무시 */ }
      return '관리자 저장 내용을 지웠습니다.'
    },
  }
}
