# 프론트엔드 (HTML, CSS, JavaScript)

빌드 도구 없이 HTML 파일을 그대로 쓴다. 설치할 것이 없다. 지도 라이브러리(MapLibre)도 `vendor/` 에 받아 두어서 인터넷 CDN 이 막혀도 지도 화면이 뜬다.

## 실행

백엔드를 켜면 이 폴더도 같은 주소로 열린다. 그래서 API를 부를 때 CORS 설정이 필요 없다.

```bash
cd ../backend
uvicorn app.main:app --reload --port 8000
```

브라우저에서 http://localhost:8000 을 연다. 파일을 고치면 브라우저 새로고침(F5)만 하면 된다.

HTML 파일을 더블클릭해서(`file://`) 열면 안 된다. `<script type="module">` 과 API 호출이 막힌다.

## 백엔드 없이 화면 만들기 (mock)

백엔드 API 가 아직 501 을 주는 동안에도 `http://localhost:8000/?mock=1` 로 열면 가짜 응답으로 화면이 동작한다.
같은 탭에서는 다른 화면으로 가도 유지되고, `?mock=0` 으로 끈다. 켜져 있으면 오른쪽 위에 노란 MOCK 표시가 뜬다.
데이터와 오류 시험 방법은 `mock/README.md`. 화면 코드는 mock 이든 실제 서버든 똑같이 `js/api.js` 함수만 부른다.

## 파일

| 파일 | 화면, 역할 |
|---|---|
| `index.html` + `js/pages/home.js` | 검색/홈 (F-01) |
| `place.html` + `js/pages/place.js` | 장소 상세, 내비 연결 (F-01, F-03, F-04). 주소 `place.html?id=1` |
| `guide.html` + `js/pages/guide.js` | 3D 안내 (F-02~F-05). 주소 `guide.html?id=1` |
| `admin.html` + `js/pages/admin.js` | 관리자 문장 작성 (F-06, N-04) |
| `404.html` | 없는 주소 |
| `about.html` | 서비스 정보, 출처 전체 목록 (정적, 스크립트 없음). 홈과 장소 상세 아래 링크, 지도 출처의 "출처 전체" 링크로 들어온다 |
| `css/style.css` | 공용 스타일. 색은 맨 위 변수(`--accent` 등)만 쓴다 |
| `js/api.js` | 서버 API 호출 (구현됨). 화면 파일은 fetch 를 직접 쓰지 않고 여기 함수만 부른다 |
| `js/mock.js`, `mock/` | 가짜 응답. 백엔드가 완성되면 지운다 |
| `js/map.js` | MapLibre 3D 지도 |
| `js/geo.js` | 거리, 경로 계산 |
| `js/navi.js` | 내비 앱 링크, 도착 판정 |
| `js/admin-store.js`, `js/draft-checks.js` | 관리자 키, 초안 보관과 검사 |
| `js/util.js` | `$`, `param`, `toast`, `debounce`, `escapeHtml`, `todo`, 화면 오류 알림 |
| `vendor/maplibre-gl-4.7.1/` | MapLibre GL JS 원본 파일 (BSD-3 라이선스 동봉). 고치지 않는다 |
| `data/osm_context_gnu.json` | 저장해 둔 캠퍼스 지도 (형식은 `data/README.md`) |
| `tests/` | DOM 없이 도는 함수의 단위 테스트 |
| `package.json` | 설치할 패키지 없음. `npm test` 실행용 |

## 테스트

Node.js 20 이상이 있으면 `frontend` 폴더에서 `npm test` (설치 없이 `node --test` 를 돌린다). `js/geo.js`, `js/draft-checks.js`, `js/map.js` 의 계산 함수가 대상이다. 함수를 만들면 `tests/*.test.js` 의 `test.todo` 를 실제 테스트로 바꾼다.

## 정해 둔 것

| 항목 | 결정 | 이유 |
|---|---|---|
| 오류 형식 | 서버 오류는 항상 `{"error": {code, message, request_id, details}}`. 입력 오류도 400 `INVALID_INPUT` | api.js 가 한 가지 형식만 다루면 된다 |
| 도보 경로 캐시 | `If-None-Match`, 304 를 JS 에서 다루지 않는다. 브라우저 캐시에 맡긴다. 관리자 편집만 `cache: 'no-store'` | 서버가 `no-cache` + ETag 를 보내므로 브라우저가 알아서 재검증한다 |
| 파일 캐시 | 서버가 모든 화면 파일에 `Cache-Control: no-cache` 를 붙인다 | 배포 직후 옛 JS 와 새 JS 가 섞이지 않게 |
| 보안 정책(CSP) | 서버가 HTML 에 붙인다 (`backend/app/frontend.py`). 허용: 자기 주소, Google Fonts, tiles.openfreemap.org, worker 는 blob:. 개발 중에는 Report-Only (막지 않고 기록만) | 아래 "CSP 운영" |
| 화면 오류 | 잡지 못한 오류는 `util.js` 가 알림으로 띄운다 | 흰 화면 대신 안내 |
| 경로 버전 `updated_at` | 받은 문자열 그대로 `expected_updated_at` 에 넣는다. `new Date()` 금지 | 마이크로초가 잘려 항상 409 |
| 진행 중 여행 | localStorage + 6시간 만료 (`js/navi.js` 구현됨) | 내비 앱을 다녀오는 사이 탭이 정리돼도 남게. 위치는 저장 안 함 |
| 휴대폰 시험 | HTTPS 필요. `../README.md` "휴대폰에서 시험하기" | 위치 API 는 HTTPS 에서만 동작 |
| 접근성 | `:focus-visible` 외곽선, `.btn` 높이 44px 이상(뒤로 등 아이콘 버튼은 `.btn-icon` 44x44), "동작 줄이기" 존중, 노치 여백(safe-area), 마커와 범례는 색 + 모양 | 휴대폰 한 손 조작, 키보드, 색 구분이 어려운 사용자. `.btn-sm` 은 보조 버튼에만 |
| 지도 출처 표기 | 지도 모서리에 항상 표시 (`ATTRIBUTION_OPTIONS`, compact). 처음엔 펼쳐 보이고 지도를 끌면 (i) 로 접힌다. 3D 안내 화면만 오른쪽 위, 나머지는 오른쪽 아래. 전체 목록은 `about.html` | OSM(ODbL), OpenFreeMap 출처 표기 조건. 별도 페이지만으로는 부족 |
| 3D 안내 카드 | 진행 막대 + 큰 번호(`2 / 4`), 마지막 단계에서 "도착", 개요에서 이전 비활성 | 지금 몇 단계인지 한눈에 |
| 경로 없는 장소 | 버튼 비활성 + "아직 도보 경로 안내가 준비되지 않았어요" 안내 | 왜 못 누르는지 알려 준다 |
| 도착 판정 실패 | `far`, `unavailable` 이면 "주차장에 도착했어요" 버튼으로 직접 진행 | 실내, GPS 불안정에서도 시연이 막히지 않게 |

## CSP 운영

개발 중에는 막지 않고 기록만 한다(Report-Only). 처음부터 막으면 초보 팀원이 기능보다 보안 오류를 푸는 데 시간을 쓰게 되고, 배포 직전에 처음 켜면 그동안 쌓인 위반이 한꺼번에 터지기 때문이다.

| 단계 | 설정 | 동작 |
|---|---|---|
| 개발 (`ENV=local`, 기본) | `CSP_MODE` 비움 → report-only | 아무것도 막지 않는다. 위반은 브라우저 콘솔에 표시되고 서버 터미널에 `WARNING:csp:csp_violation ...` 로 남는다 |
| 배포 전 점검 | `CSP_MODE=enforce` 로 켜고 화면 전체를 한 번씩 써 본다 | 실제로 막아 본다. 깨지는 곳을 고친다 |
| 운영 (`ENV=prod`) | `CSP_MODE` 비움 → enforce | 정책 밖 스크립트, 이미지, 요청을 막는다 |
| 급한 문제 | `CSP_MODE=report-only` 로 잠시 되돌림 | 원인을 고친 뒤 다시 enforce |

서버 로그 예: `WARNING:csp:csp_violation script-src-attr blocked=inline page=guide.html source=:3`
(위반 규칙, 막힌 주소, 화면, 파일:줄. 쿼리 문자열은 남기지 않는다)

**위반이 찍히면 바로 고친다.** 막지 않는다고 미뤄 두면 배포 전 점검에서 한꺼번에 고쳐야 한다. 자주 나오는 원인:

| 로그의 규칙 | 원인 | 고치는 법 |
|---|---|---|
| `script-src-elem blocked=inline` | HTML 안에 `<script>...</script>` 를 직접 씀 | `js/` 파일로 옮기고 `<script type="module" src="...">` |
| `script-src-attr blocked=inline` | `onclick="..."` 같은 HTML 속성 | `addEventListener('click', ...)` |
| `img-src`, `connect-src`, `font-src` + 외부 주소 | 허용 목록에 없는 외부 주소 | 정말 필요한지 팀에서 정한 뒤 `backend/app/frontend.py` 의 `CSP` 에 주소 추가 |
| `script-src blocked=https://...` | CDN 스크립트 | `vendor/` 에 파일을 받아 두고 그 경로로 불러오기 |

배포 전 점검 체크리스트:
1. 개발 서버 로그에 `csp_violation` 이 더 나오지 않는지 확인
2. `CSP_MODE=enforce` 로 띄우고 화면 4개(검색, 상세, 3D 안내, 관리자)와 지도 대체 전환을 모두 써 보기
3. 브라우저 콘솔에 `Refused` 또는 `violates the following Content Security Policy` 가 없는지 확인

## 규칙

- 화면마다 HTML 1개 + JS 1개. 공용 기능은 `js/` 바로 아래 파일에 만들고 `import` 해서 쓴다.
- 서버에서 받은 글자를 `innerHTML` 에 넣을 때는 `escapeHtml()` 을 거친다. 글자만 넣을 때는 `textContent` 를 쓴다.
- 숨기고 보이기는 `hidden` 속성으로 한다 (`el.hidden = true`).
- `todo('이름')` 이 남은 곳이 할 일이다. `grep -rn "TODO" .` 로 찾는다.
- 뼈대 전용 (구현 후 삭제): 각 HTML 의 `<section class="skeleton">`, `<nav class="skeleton-nav">`, `style.css` 맨 아래 뼈대 전용 블록, `util.js` 의 `todo`.
