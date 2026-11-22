// 관리자 정보와 저장하지 못한 초안은 탭이 닫히면 사라지는 sessionStorage에만 둔다.
const ADMIN_KEY = 'majunggil.admin.key'
const ADMIN_NAME = 'majunggil.admin.name'
const LAST_DRAFT = 'majunggil.draft.last'
const DRAFT_PREFIX = 'majunggil.draft.'

function storage() {
  try { return globalThis.sessionStorage || null } catch { return null }
}

function read(key) {
  try { return storage()?.getItem(key) ?? null } catch { return null }
}

function write(key, value) {
  try {
    const store = storage()
    if (!store) return false
    if (value == null || value === '') store.removeItem(key)
    else store.setItem(key, value)
    return true
  } catch { return false }
}

export const adminKey = {
  get() { return read(ADMIN_KEY) },
  set(value) { return write(ADMIN_KEY, String(value || '').trim() || null) },
  getName() { return read(ADMIN_NAME) || '' },
  setName(value) { return write(ADMIN_NAME, String(value || '').trim() || null) },
}

function draftKey(routeId) {
  return `${DRAFT_PREFIX}${routeId}`
}

export const drafts = {
  save(draft) {
    if (!draft || !Number.isFinite(Number(draft.routeId))) return false
    const value = { ...draft, savedAt: draft.savedAt || new Date().toISOString() }
    if (!write(draftKey(draft.routeId), JSON.stringify(value))) return false
    write(LAST_DRAFT, JSON.stringify({ placeId: draft.placeId, routeId: draft.routeId }))
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
      const value = JSON.parse(read(LAST_DRAFT) || 'null')
      return value && Number.isFinite(Number(value.placeId)) && Number.isFinite(Number(value.routeId))
        ? { placeId: Number(value.placeId), routeId: Number(value.routeId) }
        : null
    } catch { return null }
  },
  clear(routeId) {
    try { storage()?.removeItem(draftKey(routeId)) } catch { return false }
    const last = this.last()
    if (last?.routeId === Number(routeId)) write(LAST_DRAFT, null)
    return true
  },
}
