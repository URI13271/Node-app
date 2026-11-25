import { test } from 'node:test'
import assert from 'node:assert/strict'
import { clearTrip, judgeArrival, loadTrip, naviLinks, saveTrip, TRIP_TTL_MS } from '../js/navi.js'

test('naviLinks: 카카오맵, 네이버지도, 티맵 목적지 링크를 만든다', () => {
  const links = naviLinks({ name: '경상국립대 도서관', lng: 128.1, lat: 35.15 })
  assert.deepEqual(links.map((link) => link.id), ['kakao', 'naver', 'tmap'])
  assert.match(links[0].url, /ep=35\.15,128\.1/)
  assert.match(links[1].url, /dname=%EA%B2%BD%EC%83%81%EA%B5%AD%EB%A6%BD%EB%8C%80%20%EB%8F%84%EC%84%9C%EA%B4%80/)
  assert.match(links[2].url, /goalx=128\.1&goaly=35\.15/)
  assert.deepEqual(naviLinks(null), [])
})

test('judgeArrival: 반경 안은 도착, 바깥은 거리와 함께 far', () => {
  const target = { lng: 128.1, lat: 35.15 }
  assert.deepEqual(judgeArrival({ coords: { longitude: 128.1, latitude: 35.15 } }, target, 20), { kind: 'arrived', distanceM: 0 })
  const result = judgeArrival({ longitude: 128.1, latitude: 35.151 }, target, 20)
  assert.equal(result.kind, 'far')
  assert.ok(result.distanceM > 100)
})

test('judgeArrival: 위치나 목적지가 없으면 unavailable', () => {
  assert.deepEqual(judgeArrival(null, { lng: 128.1, lat: 35.15 }, 20), { kind: 'unavailable', distanceM: null })
  assert.deepEqual(judgeArrival({ lat: 35.15, lng: 128.1 }, null, 20), { kind: 'unavailable', distanceM: null })
})

test('여행 정보는 저장소에 두고 6시간 뒤 만료한다', () => {
  const values = new Map()
  globalThis.localStorage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  }
  try {
    saveTrip({ placeId: 3, parkingLotId: 4, startedAt: 1000 })
    assert.deepEqual(loadTrip(1001), { placeId: 3, parkingLotId: 4, startedAt: 1000 })
    assert.equal(loadTrip(1000 + TRIP_TTL_MS), null)
    clearTrip()
  } finally {
    delete globalThis.localStorage
  }
})
