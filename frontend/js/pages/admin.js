// admin.html (F-06 단계 문장 편집, N-04 관리자 키)
// 흐름: 키 확인 → 장소, 경로 고르기 → 단계 편집 → 저장 전 검사 → PUT(전체) 또는 PATCH(한 단계) → 409 면 비교 화면
import { checkAdminKey, getBuildings, getPlace, getPlaces, getWalkRoutes, patchStep, replaceSteps } from '../api.js'
import { adminKey, drafts } from '../admin-store.js'
import { checkDraft, cleanInstruction } from '../draft-checks.js'
import { fractionOnPath, pointAlong } from '../geo.js'
import { createMap, drawBuildings, drawDraftSteps, drawMarkers, drawRoute, flyTo, renderLegend } from '../map.js'
import { $, bindCharCounter, escapeHtml, param, toast } from '../util.js'

// 1. 화면 요소, 상태
const keyForm = $('#key-form')
const keyInput = $('#admin-key')
const keyStatus = $('#key-status')
const keyClearButton = $('#btn-key-clear')
const editor = $('#editor')
const placeSelect = $('#place-select')
const routeSelect = $('#route-select')
const routeMeta = $('#route-meta')
const stepList = $('#step-list')
const editorStatus = $('#editor-status')
const draftRecovery = $('#draft-recovery')
const mapContainer = $('#map')
const warningDialog = $('#warning-dialog')
const conflictDialog = $('#conflict-dialog')

// route.updated_at 은 서버가 준 문자열 그대로 둔다 (마이크로초까지 있어 Date 로 바꾸면 저장할 때 409)
// placeLoadId: 장소를 빠르게 바꿀 때 늦게 온 옛 응답을 버리기 위한 번호
const state = {
  key: null, map: null, places: [], place: null, route: null, routes: [], steps: [],
  activeStep: 0, saving: false, pendingDraft: null, conflictRoute: null, placeLoadId: 0,
}

// 2. 관리자 키 (N-04)

/** 상태 문구. kind: '' | 'error' | 'success' */
function setMessage(element, message, kind = '') {
  element.textContent = message
  element.hidden = !message
  element.classList.toggle('notice-error', kind === 'error')
  element.classList.toggle('notice-success', kind === 'success')
}

/** 401 은 키 오류, 429 는 같은 IP 5회 실패 뒤 10분 잠금 (Retry-After 초를 분으로 바꿔 보여 준다) */
function showKeyError(error) {
  if (error?.status === 401) return '관리자 키가 올바르지 않습니다.'
  if (error?.status === 429) {
    const seconds = error.retryAfter
    return seconds ? `요청이 잠겼습니다. ${Math.ceil(seconds / 60)}분 뒤 다시 시도하세요.` : '요청이 잠겼습니다. 10분 뒤 다시 시도하세요.'
  }
  return error?.message || '관리자 키를 확인하지 못했습니다.'
}

/** 키를 /admin/me 로 확인하고 편집기를 연다. 401 이면 저장해 둔 키를 지운다 */
async function authenticate(key) {
  setMessage(keyStatus, '관리자 키를 확인하고 있습니다.')
  try {
    await checkAdminKey(key)
    state.key = key.trim()
    adminKey.set(state.key)
    keyInput.value = ''
    keyForm.hidden = true
    editor.hidden = false
    keyClearButton.hidden = false
    if (!state.map) state.map = createMap(mapContainer)
    requestAnimationFrame(() => state.map?.resize())
    await loadPlaces()
    return true
  } catch (error) {
    if (error?.status === 401) adminKey.set(null)
    setMessage(keyStatus, showKeyError(error), 'error')
    return false
  }
}

// 3. 장소, 경로 불러오기

/** 장소 목록. 주소 ?id= 또는 마지막 초안의 장소를 먼저 고른다 */
async function loadPlaces() {
  setMessage(editorStatus, '장소 목록을 불러오는 중입니다.')
  try {
    const result = await getPlaces('', 100)
    state.places = result.items || []
    placeSelect.innerHTML = state.places.map((place) => `<option value="${place.id}">${escapeHtml(place.name)}</option>`).join('')
    if (!state.places.length) {
      setMessage(editorStatus, '편집할 장소가 없습니다.', 'error')
      return
    }
    const saved = drafts.last()
    const requestedId = Number(param('id'))
    const preferred = state.places.find((item) => item.id === requestedId)
      || state.places.find((item) => item.id === saved?.placeId)
      || state.places[0]
    placeSelect.value = String(preferred.id)
    await loadPlace(preferred.id, saved?.placeId === preferred.id ? saved.routeId : null)
  } catch (error) {
    setMessage(editorStatus, `장소 목록을 불러오지 못했습니다. ${error.message || ''}`, 'error')
  }
}

/** 장소 상세, 건물, 경로를 불러온다. 경로는 캐시를 무시한다 (fresh: 항상 서버 최신본) */
async function loadPlace(placeId, preferredRouteId = null) {
  const requestId = ++state.placeLoadId
  const place = state.places.find((item) => item.id === Number(placeId))
  if (!place) return
  state.place = null
  state.route = null
  state.routes = []
  state.steps = []
  routeSelect.replaceChildren()
  stepList.replaceChildren()
  routeMeta.textContent = ''
  $('#btn-add-step').disabled = true
  $('#btn-save').disabled = true
  $('#btn-preview').href = '#'
  $('#btn-preview').setAttribute('aria-disabled', 'true')
  setMessage(editorStatus, '장소와 경로를 불러오는 중입니다.')
  try {
    const [detailResult, buildingResult, routesResult] = await Promise.allSettled([
      getPlace(place.id), getBuildings(place.id), getWalkRoutes(place.id, null, { fresh: true }),
    ])
    if (requestId !== state.placeLoadId) return
    if (detailResult.status === 'rejected') throw detailResult.reason
    state.place = detailResult.value
    if (buildingResult.status === 'fulfilled') drawBuildings(state.map, buildingResult.value)
    drawMarkers(state.map, state.place)
    renderLegend($('#map-legend'), ['entrance', 'landmark', 'route'])
    if (routesResult.status === 'rejected') throw routesResult.reason
    state.routes = routesResult.value.items || []
    routeSelect.innerHTML = state.routes.map((route) => {
      const lot = state.place.parking_lots?.find((item) => item.id === route.parking_lot_id)
      const entrance = state.place.entrances?.find((item) => item.id === route.entrance_id)
      return `<option value="${route.id}">${escapeHtml(lot?.name || '주차장')} → ${escapeHtml(entrance?.name || '입구')} · ${Math.round(route.distance_m)}m</option>`
    }).join('')
    if (!state.routes.length) {
      setMessage(editorStatus, '이 장소에는 등록된 도보 경로가 없습니다.')
      drawRoute(state.map, null)
      drawDraftSteps(state.map, [])
      return
    }
    const route = state.routes.find((item) => item.id === Number(preferredRouteId)) || state.routes[0]
    routeSelect.value = String(route.id)
    await selectRoute(route.id)
  } catch (error) {
    if (requestId !== state.placeLoadId) return
    setMessage(editorStatus, `장소 데이터를 불러오지 못했습니다. ${error.message || ''}`, 'error')
  }
}

// 4. 단계 편집 상태

/** 서버 단계 → 편집용 단계. 서버 기본 카메라(camera_is_default)는 null(자동 카메라)로 바꾼다 */
function normalizeStep(step, index) {
  const coordinates = step.location?.coordinates || step.location
  return {
    id: step.id ?? null,
    step_order: index + 1,
    instruction: step.instruction || '',
    landmark_id: step.landmark?.id ?? step.landmark_id ?? null,
    location: { type: 'Point', coordinates: Array.isArray(coordinates) ? [...coordinates] : [0, 0] },
    camera: step.camera && !step.camera_is_default ? { bearing: step.camera.bearing, pitch: step.camera.pitch, zoom: step.camera.zoom } : null,
  }
}

function snapshot(route) {
  return (route.steps || []).map(normalizeStep)
}

function routePath() {
  return state.route?.path?.coordinates || []
}

/** 경로 위 진행 위치 0~1000 (위치 슬라이더 값) */
function stepSliderValue(step) {
  return Math.round(fractionOnPath(routePath(), step.location.coordinates) * 1000)
}

/** 위치나 순서가 바뀌었나. 바뀌었으면 PATCH 로는 저장할 수 없고 PUT 을 써야 한다 */
function hasLocationOrOrderChange(step, index) {
  const original = state.route?.steps?.find((item) => item.id === step.id)
  if (!original) return true
  const originalPoint = original.location?.coordinates || []
  const point = step.location.coordinates
  return step.step_order !== original.step_order || point[0] !== originalPoint[0] || point[1] !== originalPoint[1]
}

/** 서버 원본과 다른 단계인가 (한 단계 PATCH 뒤 다른 수정이 남았는지 볼 때) */
function differsFromOriginal(step) {
  const original = state.route?.steps?.find((item) => item.id === step.id)
  if (!original) return true
  const baseline = normalizeStep(original, original.step_order - 1)
  const a = step.location.coordinates
  const b = baseline.location.coordinates
  return step.step_order !== baseline.step_order || step.instruction !== baseline.instruction
    || Number(step.landmark_id || 0) !== Number(baseline.landmark_id || 0)
    || a[0] !== b[0] || a[1] !== b[1]
    || JSON.stringify(step.camera) !== JSON.stringify(baseline.camera)
}

/** 초안 {placeId, routeId, version(서버 updated_at), steps}. 편집할 때마다, 저장에 실패하면 sessionStorage 에 남긴다 */
function draftPayload() {
  return {
    placeId: state.place?.id,
    routeId: state.route?.id,
    version: state.route?.updated_at,
    steps: state.steps.map((step) => ({ ...step, location: { type: 'Point', coordinates: [...step.location.coordinates] }, camera: step.camera ? { ...step.camera } : null })),
  }
}

function persistDraft() {
  if (state.route && state.place) drafts.save(draftPayload())
}

function updateMap() {
  if (!state.route) return
  drawRoute(state.map, state.route)
  drawDraftSteps(state.map, state.steps, state.activeStep)
}

// 5. 그리기
function renderMeta() {
  if (!state.route) return
  const lot = state.place?.parking_lots?.find((item) => item.id === state.route.parking_lot_id)
  const entrance = state.place?.entrances?.find((item) => item.id === state.route.entrance_id)
  routeMeta.textContent = `${lot?.name || '주차장'} → ${entrance?.name || '입구'} · ${Math.round(state.route.distance_m)}m · ${state.route.walk_time_min}분 · 버전 ${state.route.updated_at || '없음'}`
  $('#btn-preview').href = `/guide.html?${new URLSearchParams({ id: String(state.place.id), parking_lot_id: String(state.route.parking_lot_id), route: String(state.route.id) })}`
  $('#btn-preview').removeAttribute('aria-disabled')
}

/** 단계 카드. 지점은 경로 선 위 비율(슬라이더)로만 옮긴다 (서버는 경로에서 30m 넘게 떨어진 지점을 400 으로 거부) */
function stepCard(step, index) {
  const camera = step.camera || { bearing: '', pitch: '', zoom: '' }
  const point = step.location.coordinates
  const options = (state.place?.landmarks || []).map((item) => `<option value="${item.id}" ${Number(step.landmark_id) === item.id ? 'selected' : ''}>${escapeHtml(item.name)}</option>`).join('')
  const patchable = step.id != null && !hasLocationOrOrderChange(step, index)
  return `<li class="step-card" data-index="${index}">
    <div class="step-card-heading"><h2>${index + 1}단계</h2><div class="step-order-actions">
      <button class="btn btn-sm" type="button" data-action="up" aria-label="${index + 1}단계 위로" ${index === 0 ? 'disabled' : ''}>↑</button>
      <button class="btn btn-sm" type="button" data-action="down" aria-label="${index + 1}단계 아래로" ${index === state.steps.length - 1 ? 'disabled' : ''}>↓</button>
      <button class="btn btn-sm" type="button" data-action="delete">삭제</button>
    </div></div>
    <label class="label" for="ins-${index}">안내 문장 <span id="cnt-${index}" class="counter"></span></label>
    <textarea id="ins-${index}" class="input step-instruction" rows="2" maxlength="200" data-field="instruction">${escapeHtml(step.instruction)}</textarea>
    <label class="label" for="landmark-${index}">랜드마크</label>
    <select id="landmark-${index}" class="input" data-field="landmark"><option value="">없음</option>${options}</select>
    <label class="label" for="position-${index}">경로 위 위치 <span class="position-value">${(stepSliderValue(step) / 10).toFixed(1)}%</span></label>
    <input id="position-${index}" class="position-slider" type="range" min="0" max="1000" step="1" value="${stepSliderValue(step)}" data-field="position" aria-label="${index + 1}단계 위치를 경로 따라 이동" />
    <p class="coordinate-note">${point[1].toFixed(6)}, ${point[0].toFixed(6)}</p>
    <label class="camera-auto"><input type="checkbox" data-field="camera-auto" ${step.camera ? '' : 'checked'} /> 자동 카메라</label>
    <div class="camera-fields" ${step.camera ? '' : 'hidden'}>
      <label class="label">방향 <input class="input" type="number" min="0" max="359.9" step="0.1" value="${escapeHtml(camera.bearing)}" data-field="bearing" /></label>
      <label class="label">기울기 <input class="input" type="number" min="0" max="85" step="0.1" value="${escapeHtml(camera.pitch)}" data-field="pitch" /></label>
      <label class="label">확대 <input class="input" type="number" min="0" max="22" step="0.1" value="${escapeHtml(camera.zoom)}" data-field="zoom" /></label>
    </div>
    <button class="btn btn-sm patch-step" type="button" data-action="patch" ${patchable ? '' : 'disabled'}>이 단계만 PATCH 저장</button>
  </li>`
}

function renderSteps() {
  stepList.innerHTML = state.steps.map(stepCard).join('')
  state.steps.forEach((_, index) => {
    const textarea = $(`#ins-${index}`)
    const counter = $(`#cnt-${index}`)
    bindCharCounter(textarea, counter) // 글자 수 표시 (util.js, maxlength 200 과 같은 기준)
    textarea.addEventListener('input', () => {
      state.steps[index].instruction = textarea.value
      persistDraft()
    })
  })
  updateMap()
}

/** 저장하지 않은 초안이 있으면 복원, 삭제를 묻는다. 초안 저장 뒤 서버 버전이 바뀌었으면 그 사실도 알린다 */
function showDraftRecovery(draft) {
  state.pendingDraft = draft
  const stale = draft.version !== state.route.updated_at
  draftRecovery.innerHTML = `<b>${stale ? '서버 경로가 초안 저장 후 변경되었습니다.' : '저장하지 않은 초안이 있습니다.'}</b>
    <p>${escapeHtml(draft.savedAt || '')}${stale ? ' · 복원하면 최신 경로에 초안을 적용합니다.' : ''}</p>
    <div class="actions"><button class="btn btn-sm" type="button" data-action="restore-draft">초안 복원</button><button class="btn btn-sm" type="button" data-action="discard-draft">초안 삭제</button></div>`
  draftRecovery.hidden = false
}

/** 경로를 고르면 서버 단계로 편집 상태를 만들고, 다른 초안이 있으면 복원 안내를 띄운다 */
async function selectRoute(routeId) {
  const route = state.routes.find((item) => item.id === Number(routeId))
  if (!route) return
  state.route = route
  state.steps = snapshot(route)
  state.activeStep = 0
  $('#btn-add-step').disabled = false
  $('#btn-save').disabled = false
  state.pendingDraft = null
  renderMeta()
  const coordinates = routePath()
  if (coordinates.length) flyTo(state.map, { center: coordinates[0], bearing: 0, pitch: 45, zoom: 17.5 })
  const draft = drafts.get(route.id)
  draftRecovery.hidden = true
  renderSteps()
  setMessage(editorStatus, '')
  if (draft && draft.version !== route.updated_at || draft && JSON.stringify(draft.steps) !== JSON.stringify(state.steps)) showDraftRecovery(draft)
}

function moveStep(from, to) {
  if (to < 0 || to >= state.steps.length) return
  const [step] = state.steps.splice(from, 1)
  state.steps.splice(to, 0, step)
  state.steps.forEach((item, index) => { item.step_order = index + 1 })
  state.activeStep = to
  persistDraft()
  renderSteps()
}

// 6. 저장 (PUT, PATCH, 409)
function currentErrors() {
  return checkDraft(state.steps, routePath())
}

function showValidation(issues) {
  const firstError = issues.find((item) => item.level === 'error')
  if (firstError?.step > 0) {
    $(`#ins-${firstError.step - 1}`)?.focus()
  }
  setMessage(editorStatus, issues.map((item) => item.message).join(' '), 'error')
}

/** API 명세 3.7 StepIn 모양으로 바꾼다. 자동 카메라는 camera: null (서버 기본 카메라) */
function serializedSteps() {
  return state.steps.map((step, index) => ({
    step_order: index + 1,
    instruction: cleanInstruction(step.instruction),
    landmark_id: step.landmark_id == null || step.landmark_id === '' ? null : Number(step.landmark_id),
    location: { type: 'Point', coordinates: [...step.location.coordinates] },
    camera: step.camera ? {
      bearing: Number(step.camera.bearing), pitch: Number(step.camera.pitch), zoom: Number(step.camera.zoom),
    } : null,
  }))
}

/** updated_by 에 넣을 작성자 이름. 비어 있으면 저장 전에 묻는다 */
function getAuthor() {
  let name = $('#updated-by').value.trim() || adminKey.getName()
  if (!name) name = window.prompt('저장 기록에 표시할 작성자 이름을 입력하세요.')?.trim() || ''
  if (name) {
    $('#updated-by').value = name
    adminKey.setName(name)
  }
  return name
}

/**
 * 전체 저장 (PUT). 오류가 있으면 막고, 경고만 있으면 확인 대화상자를 띄운다
 * overwrite: 경고를 확인했거나 409 에서 "내 수정으로 덮어쓰기" 를 고른 경우
 * expectedRoute: expected_updated_at 으로 보낼 버전. 409 뒤에는 서버 최신본
 */
async function saveAll(overwrite = false, expectedRoute = state.route) {
  if (!state.route || state.saving) return
  const issues = currentErrors()
  if (issues.some((item) => item.level === 'error')) {
    persistDraft()
    showValidation(issues.filter((item) => item.level === 'error'))
    return
  }
  const warnings = issues.filter((item) => item.level === 'warning')
  if (warnings.length && !overwrite) {
    warningDialog.innerHTML = `<section class="sheet-panel"><h2 id="warning-title">경로 검토</h2><p>다음 내용을 확인하고 전체 경로를 저장합니다.</p><ul>${warnings.map((item) => `<li>${escapeHtml(item.message)}</li>`).join('')}</ul><div class="actions"><button class="btn" data-action="cancel-warning">취소</button><button class="btn btn-primary" data-action="confirm-warning">계속 저장</button></div></section>`
    warningDialog.hidden = false
    return
  }
  const author = getAuthor()
  if (!author) {
    setMessage(editorStatus, '작성자 이름이 필요합니다.', 'error')
    $('#updated-by').focus()
    return
  }
  state.saving = true
  $('#btn-save').disabled = true
  setMessage(editorStatus, '전체 경로를 저장하고 있습니다.')
  const body = {
    expected_updated_at: expectedRoute.updated_at,
    updated_by: author,
    steps: serializedSteps(),
  }
  try {
    const saved = await replaceSteps(state.route.id, body, state.key)
    acceptSavedRoute(saved)
    drafts.clear(saved.id)
    setMessage(editorStatus, '전체 경로를 저장했습니다.', 'success')
  } catch (error) {
    if (error?.status === 409) {
      await openConflict(error, expectedRoute)
    } else {
      persistDraft()
      showApiError(error)
    }
  } finally {
    state.saving = false
    $('#btn-save').disabled = false
  }
}

/** 저장 응답(경로 전체, 새 updated_at)을 새 기준으로 삼는다 */
function acceptSavedRoute(route) {
  const index = state.routes.findIndex((item) => item.id === route.id)
  if (index >= 0) state.routes[index] = route
  else state.routes.push(route)
  state.route = route
  state.steps = snapshot(route)
  state.activeStep = Math.min(state.activeStep, Math.max(0, state.steps.length - 1))
  renderMeta()
  renderSteps()
}

/** 400 details[].field (예: steps[2].instruction)로 그 단계 문장 칸에 초점을 옮긴다 */
function showApiError(error) {
  const details = error?.details || []
  const text = details.length ? details.map((item) => item.message || `${item.field}: ${item.reason}`).join(' ') : error?.message || '저장에 실패했습니다.'
  setMessage(editorStatus, `저장하지 못했습니다. ${text}`, 'error')
  const fieldMatch = details[0]?.field?.match(/steps\[(\d+)\]\.instruction/)
  if (fieldMatch) $(`#ins-${Number(fieldMatch[1])}`)?.focus()
}

/** 409 비교용 서버 최신본 (캐시 무시) */
async function fetchLatest() {
  const result = await getWalkRoutes(state.place.id, null, { fresh: true })
  return (result.items || []).find((item) => item.id === state.route.id) || null
}

function stepSummary(step) {
  if (!step) return '단계 없음'
  const landmarkId = step.landmark?.id ?? step.landmark_id
  const landmark = state.place?.landmarks?.find((item) => item.id === Number(landmarkId))?.name
  const point = step.location?.coordinates || step.location
  const position = Array.isArray(point) ? `${point[1].toFixed(6)}, ${point[0].toFixed(6)}` : '위치 없음'
  const camera = step.camera && !step.camera_is_default
    ? `카메라 ${step.camera.bearing}° / ${step.camera.pitch}° / ${step.camera.zoom}x`
    : '자동 카메라'
  return [step.instruction || '문장 없음', landmark ? `랜드마크 ${landmark}` : '랜드마크 없음', position, camera].join(' · ')
}

/** 409 비교 화면: 단계마다 서버 최신과 내 수정을 나란히 놓고, 다른 단계는 .diff 로 표시한다 */
async function openConflict(error, baseRoute) {
  persistDraft()
  try {
    state.conflictRoute = await fetchLatest()
  } catch {
    state.conflictRoute = null
  }
  const latest = state.conflictRoute
  if (!latest) {
    setMessage(editorStatus, '다른 수정이 감지되었지만 최신 버전을 불러오지 못했습니다. 다시 불러와 주세요.', 'error')
    return
  }
  const serverSteps = snapshot(latest)
  const localSteps = state.steps
  const count = Math.max(serverSteps.length, localSteps.length)
  const comparison = Array.from({ length: count }, (_, index) => {
    const server = stepSummary(serverSteps[index])
    const local = stepSummary(localSteps[index])
    const changed = server !== local
    return `<div class="cmp-row ${changed ? 'diff' : ''}"><span>${index + 1}단계</span><div class="cmp"><div><b>서버 최신</b><br>${escapeHtml(server)}</div><div><b>내 수정</b><br>${escapeHtml(local)}</div></div></div>`
  }).join('')
  conflictDialog.innerHTML = `<section class="sheet-panel"><h2 id="conflict-title">다른 관리자가 먼저 수정했습니다</h2><p>현재 버전 ${escapeHtml(latest.updated_at)}</p><div class="conflict-list">${comparison}</div>
    <div class="actions"><button class="btn" data-action="restore-latest">최신으로 되돌리기</button><button class="btn btn-primary" data-action="overwrite-latest">내 수정으로 덮어쓰기</button></div></section>`
  conflictDialog.dataset.baseVersion = baseRoute.updated_at || ''
  conflictDialog.dataset.errorMessage = error?.message || ''
  conflictDialog.hidden = false
}

/** 한 단계만 저장 (PATCH). 문장, 랜드마크, 카메라만 바꿀 수 있고 위치나 순서가 바뀌었으면 PUT 으로 안내한다 */
async function patchOne(index) {
  const step = state.steps[index]
  if (!step?.id || hasLocationOrOrderChange(step, index)) {
    setMessage(editorStatus, '위치나 단계 순서가 바뀐 경우에는 전체 저장(PUT)을 사용하세요.', 'error')
    return
  }
  const author = getAuthor()
  if (!author) return
  const otherStepsDirty = state.steps.some((item, itemIndex) => itemIndex !== index && differsFromOriginal(item))
  const invalid = checkDraft([step], routePath()).find((item) => item.level === 'error' && item.field !== 'steps')
  if (invalid) {
    setMessage(editorStatus, invalid.message, 'error')
    return
  }
  const camera = step.camera ? {
    bearing: Number(step.camera.bearing), pitch: Number(step.camera.pitch), zoom: Number(step.camera.zoom),
  } : null
  try {
    const updated = await patchStep(step.id, {
      expected_updated_at: state.route.updated_at,
      updated_by: author,
      instruction: cleanInstruction(step.instruction),
      landmark_id: step.landmark_id == null || step.landmark_id === '' ? null : Number(step.landmark_id),
      camera,
    }, state.key)
    const previous = state.route.steps.find((item) => item.id === step.id)
    Object.assign(previous, {
      instruction: updated.instruction,
      landmark: updated.landmark,
      camera: updated.camera,
      camera_is_default: updated.camera_is_default,
    })
    state.route.updated_at = updated.walk_route_updated_at
    state.routes = state.routes.map((item) => item.id === state.route.id ? state.route : item)
    drafts.clear(state.route.id)
    renderMeta()
    renderSteps()
    setMessage(editorStatus, `${index + 1}단계를 저장했습니다. 다른 수정 내용은 초안으로 남아 있습니다.`, 'success')
    if (otherStepsDirty) persistDraft()
    else setMessage(editorStatus, `${index + 1}단계를 저장했습니다.`, 'success')
  } catch (error) {
    if (error?.status === 409) await openConflict(error, state.route)
    else { persistDraft(); showApiError(error) }
  }
}

/** 랜드마크, 자동 카메라, 카메라 칸 입력을 편집 상태에 반영하고 초안을 남긴다 */
function changeField(field, index, target) {
  const step = state.steps[index]
  if (!step) return
  if (field === 'landmark') step.landmark_id = target.value || null
  else if (field === 'camera-auto') step.camera = target.checked ? null : { bearing: '', pitch: '', zoom: '' }
  else if (['bearing', 'pitch', 'zoom'].includes(field)) {
    if (!step.camera) step.camera = { bearing: '', pitch: '', zoom: '' }
    step.camera[field] = target.value === '' ? '' : Number(target.value)
  }
  persistDraft()
  if (field === 'camera-auto') renderSteps()
  else {
    const patchButton = target.closest('.step-card')?.querySelector('[data-action="patch"]')
    if (patchButton) patchButton.disabled = hasLocationOrOrderChange(step, index)
    updateMap()
  }
}

// 7. 이벤트
function bind() {
  keyForm.addEventListener('submit', async (event) => {
    event.preventDefault()
    if (keyInput.value.trim()) await authenticate(keyInput.value)
  })

  keyClearButton.addEventListener('click', () => {
    adminKey.set(null)
    state.key = null
    editor.hidden = true
    keyForm.hidden = false
    keyClearButton.hidden = true
    setMessage(keyStatus, '관리자 키를 지웠습니다.')
    keyInput.focus()
  })

  placeSelect.addEventListener('change', () => loadPlace(Number(placeSelect.value)))
  routeSelect.addEventListener('change', () => selectRoute(Number(routeSelect.value)))
  $('#updated-by').addEventListener('input', () => adminKey.setName($('#updated-by').value))

  // 새 단계는 마지막 단계보다 경로 5% 앞 지점에 둔다 (최대 30개)
  $('#btn-add-step').addEventListener('click', () => {
    if (state.steps.length >= 30) return toast('안내 단계는 30개까지 추가할 수 있습니다.')
    const coordinates = routePath()
    const progress = state.steps.length ? Math.min(1, fractionOnPath(coordinates, state.steps.at(-1).location.coordinates) + 0.05) : 0
    const location = pointAlong(coordinates, progress) || coordinates[0] || state.place.location.coordinates
    state.steps.push({ id: null, step_order: state.steps.length + 1, instruction: '', landmark_id: null, location: { type: 'Point', coordinates }, camera: null })
    state.steps.at(-1).location.coordinates = [...location]
    state.activeStep = state.steps.length - 1
    persistDraft()
    renderSteps()
  })

  $('#btn-save').addEventListener('click', () => saveAll())

  // 위치 슬라이더는 움직일 때마다 경로 위 점으로 옮긴다. 문장 칸은 renderSteps 에서 따로 듣는다
  stepList.addEventListener('input', (event) => {
    const target = event.target
    const card = target.closest('[data-index]')
    if (!card) return
    const index = Number(card.dataset.index)
    const field = target.dataset.field
    if (field === 'position') {
      const fraction = Number(target.value) / 1000
      const point = pointAlong(routePath(), fraction)
      if (point) state.steps[index].location.coordinates = point
      card.querySelector('.position-value').textContent = `${(fraction * 100).toFixed(1)}%`
      const coordinates = state.steps[index].location.coordinates
      card.querySelector('.coordinate-note').textContent = `${coordinates[1].toFixed(6)}, ${coordinates[0].toFixed(6)}`
      const patchButton = card.querySelector('[data-action="patch"]')
      if (patchButton) patchButton.disabled = hasLocationOrOrderChange(state.steps[index], index)
      persistDraft()
      updateMap()
    } else if (field && field !== 'instruction') changeField(field, index, target)
  })

  stepList.addEventListener('focusin', (event) => {
    const card = event.target.closest('[data-index]')
    if (!card) return
    state.activeStep = Number(card.dataset.index)
    updateMap()
  })

  stepList.addEventListener('change', (event) => {
    const target = event.target
    const card = target.closest('[data-index]')
    if (!card) return
    const field = target.dataset.field
    if (field && field !== 'position' && field !== 'instruction') changeField(field, Number(card.dataset.index), target)
  })

  stepList.addEventListener('click', (event) => {
    const button = event.target.closest('[data-action]')
    if (!button) return
    const card = button.closest('[data-index]')
    const index = Number(card?.dataset.index)
    if (button.dataset.action === 'up') moveStep(index, index - 1)
    if (button.dataset.action === 'down') moveStep(index, index + 1)
    if (button.dataset.action === 'delete') {
      state.steps.splice(index, 1)
      state.steps.forEach((item, position) => { item.step_order = position + 1 })
      state.activeStep = Math.min(index, state.steps.length - 1)
      persistDraft()
      renderSteps()
    }
    if (button.dataset.action === 'patch') patchOne(index)
  })

  draftRecovery.addEventListener('click', (event) => {
    const action = event.target.closest('[data-action]')?.dataset.action
    if (!action || !state.pendingDraft) return
    if (action === 'restore-draft') {
      state.steps = state.pendingDraft.steps.map(normalizeStep)
      state.activeStep = 0
      persistDraft()
      renderSteps()
      setMessage(editorStatus, '초안을 복원했습니다. 저장 전에 내용을 확인하세요.')
    } else {
      drafts.clear(state.route.id)
      setMessage(editorStatus, '저장하지 않은 초안을 삭제했습니다.')
    }
    state.pendingDraft = null
    draftRecovery.hidden = true
  })

  warningDialog.addEventListener('click', (event) => {
    const action = event.target.closest('[data-action]')?.dataset.action
    if (action === 'cancel-warning' || event.target === warningDialog) warningDialog.hidden = true
    if (action === 'confirm-warning') {
      warningDialog.hidden = true
      saveAll(true)
    }
  })

  // 409 대화상자: "최신으로 되돌리기" 는 서버 최신본으로 편집 상태를 바꾸고,
  // "내 수정으로 덮어쓰기" 는 최신 updated_at 으로 내 수정을 다시 PUT 한다
  conflictDialog.addEventListener('click', async (event) => {
    const action = event.target.closest('[data-action]')?.dataset.action
    if (!action || !state.conflictRoute) return
    if (action === 'restore-latest') {
      const latest = state.conflictRoute
      state.route = latest
      state.routes = state.routes.map((item) => item.id === latest.id ? latest : item)
      state.steps = snapshot(latest)
      state.activeStep = 0
      drafts.clear(latest.id)
      renderMeta()
      renderSteps()
      setMessage(editorStatus, '서버 최신 버전으로 되돌렸습니다.')
      conflictDialog.hidden = true
      return
    }
    if (action === 'overwrite-latest') {
      const localSteps = state.steps.map((step) => ({ ...step, location: { type: 'Point', coordinates: [...step.location.coordinates] }, camera: step.camera ? { ...step.camera } : null }))
      const latest = state.conflictRoute
      state.route = latest
      state.routes = state.routes.map((item) => item.id === latest.id ? latest : item)
      state.steps = localSteps
      conflictDialog.hidden = true
      await saveAll(true, latest)
    }
  })

  $('#btn-preview').addEventListener('click', (event) => {
    if (!state.route) { event.preventDefault(); return }
  })
}

// 8. 불러오기: 저장해 둔 키가 있으면 바로 확인하고 장소 목록을 불러온다
function load() {
  renderLegend($('#map-legend'), ['entrance', 'landmark', 'route'])
  $('#updated-by').value = adminKey.getName()
  $('#btn-preview').href = '/guide.html'
  const existingKey = adminKey.get()
  if (existingKey) authenticate(existingKey)
}

// 9. 시작
bind()
load()
