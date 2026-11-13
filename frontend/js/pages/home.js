// index.html (F-01 검색/홈). 입력 300ms 멈춘 뒤 GET /places?q= (API 명세서 6장)
// 상태 4가지: 검색어 없음(시연 장소 전체) / 검색 중 / 0건 / 결과 있음. 제목 줄(#result-title)은 aria-live 라 낭독기가 읽는다
import { getPlaces } from '../api.js'
import { $, CATEGORY_LABEL, debounce, escapeHtml, loadErrorMessage } from '../util.js'

// 1. 요소, 화면 상태
const input = $('#q')
const list = $('#place-list')
const title = $('#result-title')
let seq = 0 // 늦게 도착한 옛 응답을 버리려고 요청마다 번호를 붙인다

// 2. 그리기
function renderItems(q, data) {
  title.textContent = q ? `검색 결과 ${data.total}곳` : '시연 장소'
  list.innerHTML = data.items.length
    ? data.items.map((p) => `<li><a class="card place-item" href="/place.html?id=${p.id}">
        <b>${escapeHtml(p.name)}</b> <span class="chip">${escapeHtml(CATEGORY_LABEL[p.category] || '기타')}</span></a></li>`).join('')
    : `<li class="empty">“${escapeHtml(q)}”에 대한 결과가 없어요. 이름 일부만 넣어 보세요.</li>`
}

// 3. 불러오기
async function search(q) {
  const my = ++seq
  try {
    const data = await getPlaces(q)
    if (my !== seq) return // 더 새 검색이 있으면 버린다
    renderItems(q, data)
  } catch (e) {
    if (my !== seq) return
    title.textContent = '목록을 불러오지 못했습니다'
    list.innerHTML = `<li class="empty">${escapeHtml(loadErrorMessage(e))}</li>`
  }
}

// 4. 이벤트: 입력 즉시 "검색 중…", 300ms 멈추면 요청
const searchLater = debounce((q) => search(q), 300)
input.addEventListener('input', () => {
  const q = input.value.trim()
  title.textContent = q ? '검색 중…' : '시연 장소'
  searchLater(q)
})

// 5. 시작: 검색어 없이 시연 장소 전체
search('')
