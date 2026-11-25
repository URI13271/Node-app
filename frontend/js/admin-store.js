// 관리자 키, 작성자 이름, 저장하지 못한 초안 보관 (설계서 2.7.1).
// sessionStorage 에만 둔다. 탭을 닫으면 사라지고 쿠키를 쓰지 않는다.
// 사생활 보호 모드에서는 저장소 접근이 예외를 던질 수 있어 읽고 쓸 때 모두 try/catch 로 감싼다.
const ADMIN_KEY_STORAGE_KEY = 'majunggil.admin.key'
const ADMIN_NAME_STORAGE_KEY = 'majunggil.admin.name'
const LAST_DRAFT_STORAGE_KEY = 'majunggil.draft.last'
const DRAFT_STORAGE_KEY_PREFIX = 'majunggil.draft.'

function storage() {
  try { return globalThis.sessionStorage || null } catch { return null }
}

function read(key) {
  try { return storage()?.getItem(key) ?? null } catch { return null }
}

/** 값이 비면 지운다. 저장했으면 true */
function write(key, value) {
  try {
    const store = storage()
    if (!store) return false
    if (value == null || value === '') store.removeItem(key)
    else store.setItem(key, value)
    return true
  } catch { return false }
}

/** 관리자 키와 작성자 이름(updated_by). set(null) 이나 빈 값은 지운다 */
export const adminKey = {
  get() { return read(ADMIN_KEY_STORAGE_KEY) },
  set(value) { return write(ADMIN_KEY_STORAGE_KEY, String(value || '').trim() || null) },
  getName() { return read(ADMIN_NAME_STORAGE_KEY) || '' },
  setName(value) { return write(ADMIN_NAME_STORAGE_KEY, String(value || '').trim() || null) },
}

function draftKey(routeId) {
  return `${DRAFT_STORAGE_KEY_PREFIX}${routeId}`
}

/**
 * 초안 {placeId, routeId, version, steps, savedAt} 를 경로별 키로 보관하고, 마지막 위치 {placeId, routeId} 를 따로 둔다
 * version 은 서버가 준 route.updated_at 문자열 그대로 둔다 (마이크로초까지 있음. Date 로 바꾸면 저장할 때 409)
 */
export const drafts = {
  save(draft) {
    if (!draft || !Number.isFinite(Number(draft.routeId))) return false
    const value = { ...draft, savedAt: draft.savedAt || new Date().toISOString() }
    if (!write(draftKey(draft.routeId), JSON.stringify(value))) return false
    write(LAST_DRAFT_STORAGE_KEY, JSON.stringify({ placeId: draft.placeId, routeId: draft.routeId }))
    return true
  },
  get(routeId) {
    try {
      const value = JSON.parse(read(draftKey(routeId)) || 'null')
      return value && Number(value.routeId) === Number(routeId) ? value : null
    } catch { return null }
  },
  last() {
    try {
      const value = JSON.parse(read(LAST_DRAFT_STORAGE_KEY) || 'null')
      return value && Number.isFinite(Number(value.placeId)) && Number.isFinite(Number(value.routeId))
        ? { placeId: Number(value.placeId), routeId: Number(value.routeId) }
        : null
    } catch { return null }
  },
  clear(routeId) {
    try { storage()?.removeItem(draftKey(routeId)) } catch { return false }
    const last = this.last()
    if (last?.routeId === Number(routeId)) write(LAST_DRAFT_STORAGE_KEY, null)
    return true
  },
}
