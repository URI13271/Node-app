// 여러 화면이 같이 쓰는 작은 도구.

/** 뼈대 전용. 아직 만들지 않은 함수가 부르면 바로 알 수 있게 오류를 던진다. 구현이 끝나면 지운다. */
export function todo(name) {
  throw new Error(`TODO: ${name}`)
}

/** CSS 선택자로 요소 하나 찾기. 예: $('#q') */
export const $ = (selector, root = document) => root.querySelector(selector)

/** 주소의 ?id=1 같은 값 읽기. 예: param('id') → '1' (없으면 null) */
export const param = (name) => new URLSearchParams(location.search).get(name)

/** 화면 아래 짧은 알림 (낭독기도 읽는다) */
export function toast(message, ms = 2500) {
  const el = $('#toast')
  if (!el) return
  el.textContent = message
  el.hidden = false
  clearTimeout(toast.timer)
  toast.timer = setTimeout(() => { el.hidden = true }, ms)
}

/** 입력이 멈춘 뒤 ms 만큼 지나면 fn 실행 (검색창 300ms) */
export function debounce(fn, ms) {
  let t
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms) }
}

/** 사용자 입력을 HTML 에 넣기 전에 꼭 거친다 (innerHTML 사용 시) */
export const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)

/** 장소 분류 → 화면 표기 */
export const CATEGORY_LABEL = {
  campus: '학교 시설', pension: '펜션', campsite: '캠핑장', temple: '사찰', restaurant: '맛집',
  trailhead: '등산로 입구', attraction: '관광지', other: '기타',
}

/**
 * 불러오기 실패를 사람이 읽을 문장으로 (프론트 작성 가이드 5.2 표)
 * @param {any} e  api.js 가 던진 ApiError (status, code, requestId)
 */
export function loadErrorMessage(e) {
  const status = e?.status
  if (status === 0) return '서버에 연결하지 못했습니다. 인터넷 연결을 확인하세요.'
  if (status === 404) return '찾을 수 없는 장소입니다.'
  if (status === 400) return e.message || '입력값을 확인하세요.'
  if (status === 429) return `요청이 너무 많습니다. ${e.retryAfter ? `${e.retryAfter}초 뒤 ` : ''}다시 시도하세요.`
  const id = e?.requestId && e.requestId !== 'mock' ? ` (요청 ID ${e.requestId})` : ''
  return `정보를 불러오지 못했습니다. 잠시 후 다시 시도하세요.${id}`
}

/**
 * 글자 수 표시: 입력할 때마다 counterEl 에 "n/max" 를 쓴다. 비었거나 넘으면 빨간색 (관리자 문장 1~200자)
 * textarea 에는 maxlength 도 같이 단다. 예: <textarea maxlength="200"> + <span class="counter">
 */
export function bindCharCounter(textarea, counterEl, max = 200) {
  const update = () => {
    const n = textarea.value.length // maxlength 와 같은 기준
    counterEl.textContent = `${n}/${max}`
    counterEl.classList.toggle('over', n > max)
    counterEl.classList.toggle('empty-text', textarea.value.trim() === '')
  }
  textarea.addEventListener('input', update)
  update()
  return update
}

// ---- 화면 오류 처리 ----
// 잡지 못한 오류가 나도 흰 화면 대신 알림을 띄운다. 모든 화면이 util.js 를 불러오므로 여기서 한 번만 등록한다.
// 뼈대의 todo() 오류도 여기서 알림으로 보인다.
function showError(err) {
  console.error('화면 오류', err)
  const msg = err && err.message ? err.message : String(err)
  toast(msg.startsWith('TODO:') ? `아직 만들지 않은 기능: ${msg.slice(5).trim()}` : '문제가 생겼습니다. 새로고침해 보세요.', 4000)
}
if (typeof window !== 'undefined') { // 브라우저에서만 (npm test 는 Node 에서 돌아 window 가 없다)
  window.addEventListener('error', (e) => showError(e.error || e.message))
  window.addEventListener('unhandledrejection', (e) => showError(e.reason))
}
