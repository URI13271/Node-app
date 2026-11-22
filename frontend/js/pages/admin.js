// admin.html: API 계약을 지키며 경로 안내 단계를 편집한다.
import { checkAdminKey, getBuildings, getPlace, getPlaces, getWalkRoutes, patchStep, replaceSteps } from '../api.js'
import { adminKey, drafts } from '../admin-store.js'
import { checkDraft, cleanInstruction } from '../draft-checks.js'
import { fractionOnPath, pointAlong } from '../geo.js'
import { createMap, drawBuildings, drawDraftSteps, drawMarkers, drawRoute, flyTo, renderLegend } from '../map.js'
import { $, escapeHtml, param, toast } from '../util.js'

const $keyForm = $('#key-form')
const $key = $('#admin-key')
const $keyStatus = $('#key-status')
const $keyClear = $('#btn-key-clear')
const $editor = $('#editor')
const $placeSelect = $('#place-select')
const $routeSelect = $('#route-select')
const $routeMeta = $('#route-meta')
const $stepList = $('#step-list')
const $status = $('#editor-status')
const $recovery = $('#draft-recovery')
const $map = $('#map')
const $warning = $('#warning-dialog')
const $conflict = $('#conflict-dialog')

const state = {
  key: null, map: null, places: [], place: null, route: null, routes: [], steps: [],
  activeStep: 0, saving: false, pendingDraft: null, conflictRoute: null, placeLoadId: 0,
}

function setMessage(element, message, kind = '') {
  element.textContent = message
  element.hidden = !message
  element.classList.toggle('notice-error', kind === 'error')
  element.classList.toggle('notice-success', kind === 'success')
}

function showKeyError(error) {
  if (error?.status === 401) return '관리자 키가 올바르지 않습니다.'
  if (error?.status === 429) {
    const seconds = error.retryAfter
    return seconds ? `요청이 잠겼습니다. ${Math.ceil(seconds / 60)}분 뒤 다시 시도하세요.` : '요청이 잠겼습니다. 10분 뒤 다시 시도하세요.'
  }
  return error?.message || '관리자 키를 확인하지 못했습니다.'
}

async function authenticate(key) {
  setMessage($keyStatus, '관리자 키를 확인하고 있습니다.')
  try {
    await checkAdminKey(key)
    state.key = key.trim()
    adminKey.set(state.key)
    $key.value = ''
    $keyForm.hidden = true
    $editor.hidden = false
    $keyClear.hidden = false
    if (!state.map) state.map = createMap($map)
    requestAnimationFrame(() => state.map?.resize())
    await loadPlaces()
    return true
  } catch (error) {
    if (error?.status === 401) adminKey.set(null)
    setMessage($keyStatus, showKeyError(error), 'error')
    return false
  }
}

async function loadPlaces() {
  setMessage($status, '장소 목록을 불러오는 중입니다.')
  try {
    const result = await getPlaces('', 100)
    state.places = result.items || []
    $placeSelect.innerHTML = state.places.map((place) => `<option value="${place.id}">${escapeHtml(place.name)}</option>`).join('')
    if (!state.places.length) {
      setMessage($status, '편집할 장소가 없습니다.', 'error')
      return
    }
    const saved = drafts.last()
    const requestedId = Number(param('id'))
    const preferred = state.places.find((item) => item.id === requestedId)
      || state.places.find((item) => item.id === saved?.placeId)
      || state.places[0]
    $placeSelect.value = String(preferred.id)
    await loadPlace(preferred.id, saved?.placeId === preferred.id ? saved.routeId : null)
  } catch (error) {
    setMessage($status, `장소 목록을 불러오지 못했습니다. ${error.message || ''}`, 'error')
  }
}

async function loadPlace(placeId, preferredRouteId = null) {
  const requestId = ++state.placeLoadId
  const place = state.places.find((item) => item.id === Number(placeId))
  if (!place) return
  state.place = null
  state.route = null
  state.routes = []
  state.steps = []
  $routeSelect.replaceChildren()
  $stepList.replaceChildren()
  $routeMeta.textContent = ''
  $('#btn-add-step').disabled = true
  $('#btn-save').disabled = true
  $('#btn-preview').href = '#'
  $('#btn-preview').setAttribute('aria-disabled', 'true')
  setMessage($status, '장소와 경로를 불러오는 중입니다.')
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
    $routeSelect.innerHTML = state.routes.map((route) => {
      const lot = state.place.parking_lots?.find((item) => item.id === route.parking_lot_id)
      const entrance = state.place.entrances?.find((item) => item.id === route.entrance_id)
      return `<option value="${route.id}">${escapeHtml(lot?.name || '주차장')} → ${escapeHtml(entrance?.name || '입구')} · ${Math.round(route.distance_m)}m</option>`
    }).join('')
    if (!state.routes.length) {
      setMessage($status, '이 장소에는 등록된 도보 경로가 없습니다.')
      drawRoute(state.map, null)
      drawDraftSteps(state.map, [])
      return
    }
    const route = state.routes.find((item) => item.id === Number(preferredRouteId)) || state.routes[0]
    $routeSelect.value = String(route.id)
    await selectRoute(route.id)
  } catch (error) {
    if (requestId !== state.placeLoadId) return
    setMessage($status, `장소 데이터를 불러오지 못했습니다. ${error.message || ''}`, 'error')
  }
}

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

function pathCoordinates() {
  return state.route?.path?.coordinates || []
}

function stepProgress(step) {
  return Math.round(fractionOnPath(pathCoordinates(), step.location.coordinates) * 1000)
}

function hasLocationOrOrderChange(step, index) {
  const original = state.route?.steps?.find((item) => item.id === step.id)
  if (!original) return true
  const originalPoint = original.location?.coordinates || []
  const point = step.location.coordinates
  return step.step_order !== original.step_order || point[0] !== originalPoint[0] || point[1] !== originalPoint[1]
}

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

function renderMeta() {
  if (!state.route) return
  const lot = state.place?.parking_lots?.find((item) => item.id === state.route.parking_lot_id)
  const entrance = state.place?.entrances?.find((item) => item.id === state.route.entrance_id)
  $routeMeta.textContent = `${lot?.name || '주차장'} → ${entrance?.name || '입구'} · ${Math.round(state.route.distance_m)}m · ${state.route.walk_time_min}분 · 버전 ${state.route.updated_at || '없음'}`
  $('#btn-preview').href = `/guide.html?${new URLSearchParams({ id: String(state.place.id), parking_lot_id: String(state.route.parking_lot_id), route: String(state.route.id) })}`
  $('#btn-preview').removeAttribute('aria-disabled')
}

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
    <label class="label" for="position-${index}">경로 위 위치 <span class="position-value">${(stepProgress(step) / 10).toFixed(1)}%</span></label>
    <input id="position-${index}" class="position-slider" type="range" min="0" max="1000" step="1" value="${stepProgress(step)}" data-field="position" aria-label="${index + 1}단계 위치를 경로 따라 이동" />
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
  $stepList.innerHTML = state.steps.map(stepCard).join('')
  state.steps.forEach((_, index) => {
    const textarea = $(`#ins-${index}`)
    const counter = $(`#cnt-${index}`)
    textarea.addEventListener('input', () => {
      state.steps[index].instruction = textarea.value
      bindCounter(textarea, counter)
      persistDraft()
    })
    bindCounter(textarea, counter)
  })
  updateMap()
}

function bindCounter(textarea, counter) {
  const length = textarea.value.length
  counter.textContent = `${length}/200`
  counter.classList.toggle('over', length > 200)
  counter.classList.toggle('empty-text', textarea.value.trim() === '')
}

function showDraftRecovery(draft) {
  state.pendingDraft = draft
  const stale = draft.version !== state.route.updated_at
  $recovery.innerHTML = `<b>${stale ? '서버 경로가 초안 저장 후 변경되었습니다.' : '저장하지 않은 초안이 있습니다.'}</b>
    <p>${escapeHtml(draft.savedAt || '')}${stale ? ' · 복원하면 최신 경로에 초안을 적용합니다.' : ''}</p>
    <div class="actions"><button class="btn btn-sm" type="button" data-action="restore-draft">초안 복원</button><button class="btn btn-sm" type="button" data-action="discard-draft">초안 삭제</button></div>`
  $recovery.hidden = false
}

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
  const coordinates = pathCoordinates()
  if (coordinates.length) flyTo(state.map, { center: coordinates[0], bearing: 0, pitch: 45, zoom: 17.5 })
  const draft = drafts.get(route.id)
  $recovery.hidden = true
  renderSteps()
  setMessage($status, '')
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

function currentErrors() {
  return checkDraft(state.steps, pathCoordinates())
}

function showValidation(issues) {
  const firstError = issues.find((item) => item.level === 'error')
  if (firstError?.step > 0) {
    $(`#ins-${firstError.step - 1}`)?.focus()
  }
  setMessage($status, issues.map((item) => item.message).join(' '), 'error')
}

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

function getAuthor() {
  let name = $('#updated-by').value.trim() || adminKey.getName()
  if (!name) name = window.prompt('저장 기록에 표시할 작성자 이름을 입력하세요.')?.trim() || ''
  if (name) {
    $('#updated-by').value = name
    adminKey.setName(name)
  }
  return name
}

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
    $warning.innerHTML = `<section class="sheet-panel"><h2 id="warning-title">경로 검토</h2><p>다음 내용을 확인하고 전체 경로를 저장합니다.</p><ul>${warnings.map((item) => `<li>${escapeHtml(item.message)}</li>`).join('')}</ul><div class="actions"><button class="btn" data-action="cancel-warning">취소</button><button class="btn btn-primary" data-action="confirm-warning">계속 저장</button></div></section>`
    $warning.hidden = false
    return
  }
  const author = getAuthor()
  if (!author) {
    setMessage($status, '작성자 이름이 필요합니다.', 'error')
    $('#updated-by').focus()
    return
  }
  state.saving = true
  $('#btn-save').disabled = true
  setMessage($status, '전체 경로를 저장하고 있습니다.')
  const body = {
    expected_updated_at: expectedRoute.updated_at,
    updated_by: author,
    steps: serializedSteps(),
  }
  try {
    const saved = await replaceSteps(state.route.id, body, state.key)
    acceptSavedRoute(saved)
    drafts.clear(saved.id)
    setMessage($status, '전체 경로를 저장했습니다.', 'success')
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

function showApiError(error) {
  const details = error?.details || []
  const text = details.length ? details.map((item) => item.message || `${item.field}: ${item.reason}`).join(' ') : error?.message || '저장에 실패했습니다.'
  setMessage($status, `저장하지 못했습니다. ${text}`, 'error')
  const fieldMatch = details[0]?.field?.match(/steps\[(\d+)\]\.instruction/)
  if (fieldMatch) $(`#ins-${Number(fieldMatch[1])}`)?.focus()
}

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

async function openConflict(error, baseRoute) {
  persistDraft()
  try {
    state.conflictRoute = await fetchLatest()
  } catch {
    state.conflictRoute = null
  }
  const latest = state.conflictRoute
  if (!latest) {
    setMessage($status, '다른 수정이 감지되었지만 최신 버전을 불러오지 못했습니다. 다시 불러와 주세요.', 'error')
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
  $conflict.innerHTML = `<section class="sheet-panel"><h2 id="conflict-title">다른 관리자가 먼저 수정했습니다</h2><p>현재 버전 ${escapeHtml(latest.updated_at)}</p><div class="conflict-list">${comparison}</div>
    <div class="actions"><button class="btn" data-action="restore-latest">최신으로 되돌리기</button><button class="btn btn-primary" data-action="overwrite-latest">내 수정으로 덮어쓰기</button></div></section>`
  $conflict.dataset.baseVersion = baseRoute.updated_at || ''
  $conflict.dataset.errorMessage = error?.message || ''
  $conflict.hidden = false
}

async function patchOne(index) {
  const step = state.steps[index]
  if (!step?.id || hasLocationOrOrderChange(step, index)) {
    setMessage($status, '위치나 단계 순서가 바뀐 경우에는 전체 저장(PUT)을 사용하세요.', 'error')
    return
  }
  const author = getAuthor()
  if (!author) return
  const otherStepsDirty = state.steps.some((item, itemIndex) => itemIndex !== index && differsFromOriginal(item))
  const invalid = checkDraft([step], pathCoordinates()).find((item) => item.level === 'error' && item.field !== 'steps')
  if (invalid) {
    setMessage($status, invalid.message, 'error')
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
    setMessage($status, `${index + 1}단계를 저장했습니다. 다른 수정 내용은 초안으로 남아 있습니다.`, 'success')
    if (otherStepsDirty) persistDraft()
    else setMessage($status, `${index + 1}단계를 저장했습니다.`, 'success')
  } catch (error) {
    if (error?.status === 409) await openConflict(error, state.route)
    else { persistDraft(); showApiError(error) }
  }
}

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

$keyForm.addEventListener('submit', async (event) => {
  event.preventDefault()
  if ($key.value.trim()) await authenticate($key.value)
})

$keyClear.addEventListener('click', () => {
  adminKey.set(null)
  state.key = null
  $editor.hidden = true
  $keyForm.hidden = false
  $keyClear.hidden = true
  setMessage($keyStatus, '관리자 키를 지웠습니다.')
  $key.focus()
})

$placeSelect.addEventListener('change', () => loadPlace(Number($placeSelect.value)))
$routeSelect.addEventListener('change', () => selectRoute(Number($routeSelect.value)))
$('#updated-by').addEventListener('input', () => adminKey.setName($('#updated-by').value))

$('#btn-add-step').addEventListener('click', () => {
  if (state.steps.length >= 30) return toast('안내 단계는 30개까지 추가할 수 있습니다.')
  const coordinates = pathCoordinates()
  const progress = state.steps.length ? Math.min(1, fractionOnPath(coordinates, state.steps.at(-1).location.coordinates) + 0.05) : 0
  const location = pointAlong(coordinates, progress) || coordinates[0] || state.place.location.coordinates
  state.steps.push({ id: null, step_order: state.steps.length + 1, instruction: '', landmark_id: null, location: { type: 'Point', coordinates }, camera: null })
  state.steps.at(-1).location.coordinates = [...location]
  state.activeStep = state.steps.length - 1
  persistDraft()
  renderSteps()
})

$('#btn-save').addEventListener('click', () => saveAll())

$stepList.addEventListener('input', (event) => {
  const target = event.target
  const card = target.closest('[data-index]')
  if (!card) return
  const index = Number(card.dataset.index)
  const field = target.dataset.field
  if (field === 'position') {
    const fraction = Number(target.value) / 1000
    const point = pointAlong(pathCoordinates(), fraction)
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

$stepList.addEventListener('focusin', (event) => {
  const card = event.target.closest('[data-index]')
  if (!card) return
  state.activeStep = Number(card.dataset.index)
  updateMap()
})

$stepList.addEventListener('change', (event) => {
  const target = event.target
  const card = target.closest('[data-index]')
  if (!card) return
  const field = target.dataset.field
  if (field && field !== 'position' && field !== 'instruction') changeField(field, Number(card.dataset.index), target)
})

$stepList.addEventListener('click', (event) => {
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

$recovery.addEventListener('click', (event) => {
  const action = event.target.closest('[data-action]')?.dataset.action
  if (!action || !state.pendingDraft) return
  if (action === 'restore-draft') {
    state.steps = state.pendingDraft.steps.map(normalizeStep)
    state.activeStep = 0
    persistDraft()
    renderSteps()
    setMessage($status, '초안을 복원했습니다. 저장 전에 내용을 확인하세요.')
  } else {
    drafts.clear(state.route.id)
    setMessage($status, '저장하지 않은 초안을 삭제했습니다.')
  }
  state.pendingDraft = null
  $recovery.hidden = true
})

$warning.addEventListener('click', (event) => {
  const action = event.target.closest('[data-action]')?.dataset.action
  if (action === 'cancel-warning' || event.target === $warning) $warning.hidden = true
  if (action === 'confirm-warning') {
    $warning.hidden = true
    saveAll(true)
  }
})

$conflict.addEventListener('click', async (event) => {
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
    setMessage($status, '서버 최신 버전으로 되돌렸습니다.')
    $conflict.hidden = true
    return
  }
  if (action === 'overwrite-latest') {
    const localSteps = state.steps.map((step) => ({ ...step, location: { type: 'Point', coordinates: [...step.location.coordinates] }, camera: step.camera ? { ...step.camera } : null }))
    const latest = state.conflictRoute
    state.route = latest
    state.routes = state.routes.map((item) => item.id === latest.id ? latest : item)
    state.steps = localSteps
    $conflict.hidden = true
    await saveAll(true, latest)
  }
})

$('#btn-preview').addEventListener('click', (event) => {
  if (!state.route) { event.preventDefault(); return }
})

function init() {
  renderLegend($('#map-legend'), ['entrance', 'landmark', 'route'])
  $('#updated-by').value = adminKey.getName()
  $('#btn-preview').href = '/guide.html'
  const existingKey = adminKey.get()
  if (existingKey) authenticate(existingKey)
}

init()
