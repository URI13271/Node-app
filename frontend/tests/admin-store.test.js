import { test } from 'node:test'
import assert from 'node:assert/strict'
import { adminKey, drafts } from '../js/admin-store.js'

const previousStorage = Object.getOwnPropertyDescriptor(globalThis, 'sessionStorage')
const values = new Map()
Object.defineProperty(globalThis, 'sessionStorage', {
  configurable: true,
  value: {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  },
})

test.after(() => {
  if (previousStorage) Object.defineProperty(globalThis, 'sessionStorage', previousStorage)
  else delete globalThis.sessionStorage
})

test('관리자 키와 작성자 이름은 sessionStorage에서 읽고 지운다', () => {
  adminKey.set(' sample-key ')
  adminKey.setName('  홍길동  ')
  assert.equal(adminKey.get(), 'sample-key')
  assert.equal(adminKey.getName(), '홍길동')
  adminKey.set(null)
  adminKey.setName('')
  assert.equal(adminKey.get(), null)
  assert.equal(adminKey.getName(), '')
})

test('초안을 경로별로 보관하고 마지막 경로와 버전을 유지한다', () => {
  const draft = { placeId: 1, routeId: 5, version: '2026-11-12T05:54:08.124567Z', steps: [] }
  assert.equal(drafts.save(draft), true)
  assert.deepEqual(drafts.get(5), { ...draft, savedAt: drafts.get(5).savedAt })
  assert.deepEqual(drafts.last(), { placeId: 1, routeId: 5 })
  drafts.clear(5)
  assert.equal(drafts.get(5), null)
  assert.equal(drafts.last(), null)
})

test('sessionStorage 접근 실패를 처리한다', () => {
  Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, get() { throw new Error('blocked') } })
  try {
    assert.equal(adminKey.get(), null)
    assert.equal(adminKey.set('key'), false)
    assert.equal(drafts.save({ routeId: 1 }), false)
  } finally {
    Object.defineProperty(globalThis, 'sessionStorage', {
      configurable: true,
      value: {
        getItem: (key) => values.get(key) ?? null,
        setItem: (key, value) => values.set(key, String(value)),
        removeItem: (key) => values.delete(key),
      },
    })
  }
})
