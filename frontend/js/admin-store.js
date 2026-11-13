// 관리자 키와 저장하지 못한 초안 보관 (설계서 2.7.1, 검토 v1.2 3장).
// sessionStorage 에만 둔다. 탭을 닫으면 사라지고 쿠키를 쓰지 않는다. 읽고 쓸 때 try/catch 로 감싼다.

export const adminKey = {
  get() { return null },   // TODO
  set(value) {},           // TODO (null 이면 지움)
  getName() { return null },
  setName(value) {},
}

/**
 * 초안 {placeId, routeId, version, steps, savedAt} 를 경로별로 보관
 * version 은 서버가 준 route.updated_at 문자열 그대로 둔다 (마이크로초까지 있음. Date 로 바꾸면 저장할 때 409)
 */
export const drafts = {
  save(draft) {},          // TODO
  get(routeId) { return null },
  last() { return null },  // 마지막으로 보관한 {placeId, routeId}
  clear(routeId) {},
}
