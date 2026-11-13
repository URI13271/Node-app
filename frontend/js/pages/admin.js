// admin.html (F-06 문장 작성, N-04 관리자 키)
import { checkAdminKey, getPlaces, getWalkRoutes, patchStep, replaceSteps } from '../api.js'
import { adminKey, drafts } from '../admin-store.js'
import { checkDraft, instructionIssues } from '../draft-checks.js'
import { $, bindCharCounter, toast } from '../util.js'

$('#key-form').addEventListener('submit', async (e) => {
  e.preventDefault()
  // TODO 1. checkAdminKey(키) 성공 → adminKey.set, #key-form 숨기고 #editor 보이기
  //         401 → 키가 맞지 않음, 429(locked) → 10분 잠김 안내
  toast('관리자 키 확인은 아직 구현 전입니다.')
})

// TODO 2. getPlaces → #place-select, getWalkRoutes(관리자 편집은 캐시 무시) → #route-select
// TODO 3. 단계 목록 그리기, 편집 (문장, 랜드마크, 지점은 경로 선 위에서만, 카메라)
//   문장 칸은 maxlength 200 + 글자 수 표시 (서버 규칙 1~200자, 넘으면 400 too_long):
//     <label class="label" for="ins-1">1단계 문장 <span id="cnt-1" class="counter"></span></label>
//     <textarea id="ins-1" class="input" rows="2" maxlength="200"></textarea>
//     → bindCharCounter($('#ins-1'), $('#cnt-1'))   (util.js)
//   저장 전에는 instructionIssues(steps) (draft-checks.js) 로 빈 문장, 200자 초과를 막는다
// TODO 4. 저장 전 checkDraft, 실패한 초안은 drafts.save 로 보관
// TODO 5. replaceSteps(PUT) / patchStep(PATCH), 409 → #conflict-dialog 비교 화면
