# 마중길(majunggil) 뼈대 (개발 시작용)

마중길 개발 뼈대다. 폴더 구조, 파일 이름, 함수 시그니처, API 경로, 화면을 정해 두고 구현은 `TODO` 로 비워 둔 코드다.
설계 근거는 `../doc/아키텍처_스켈레톤_v1.1.md`, API는 `../doc/요구사항/API 명세서_v1.3.md`, 테이블은 `../doc/요구사항/테이블 정의서_v1.1.md` 를 본다.

```
majunggil/
├─ backend/            FastAPI (api → services → repositories, domain 은 순수 규칙)
├─ frontend/           HTML + CSS + JavaScript (빌드 없음, MapLibre 는 vendor/ 에 포함). 백엔드가 같은 주소로 내보낸다
│                      mock/ 가짜 응답으로 백엔드 없이 화면 개발 (?mock=1)
├─ patches/            비워 둔 DDL, 시드, DTO 를 채우는 패치 (적용 전)
├─ .github/workflows/  자동 검사 (ruff, pytest, node --test)
├─ infra/db-init/      DB 첫 기동 SQL (앱 계정, UTC)
├─ docs/               구조도(diagrams), 화면 캡처(screens)
└─ docker-compose.yml  majunggil-db (PostGIS), majunggil-api
```

## 남긴 것과 비운 것

| 구분 | 남김 | 비움 (TODO) |
|---|---|---|
| 설정 | pyproject, requirements, Dockerfile, docker-compose, .env.example, config.py | 없음 |
| 백엔드 API | 엔드포인트 7개의 경로, 쿼리, 경로 변수 | 본문. 호출하면 501 `NOT_IMPLEMENTED` |
| 백엔드 계층 | domain, schemas, services, repositories 의 공개 함수와 클래스 이름, 시그니처, 설명 첫 줄, 설계 상수 | 함수 본문(`NotImplementedError`), DTO 필드, 테이블 정의, 미들웨어, 오류 처리기 대부분 |
| DB | 마이그레이션 파일 이름, 앱 계정 SQL | 테이블 DDL |
| 스크립트 | migrate, load_seed, build_walk_routes 진입점 | 본문, 시드 데이터 |
| 프론트 화면 | HTML 4개 + 404, 화면 틀(검색창, 지도 자리, 안내 카드, 키 입력 등), 색 토큰과 공용 버튼 스타일 | 화면 동작(할 일 목록과 TODO 주석으로 대체), 지도, 마커 스타일 |
| 프론트 모듈 | js/ 공용 파일의 함수 이름과 설명 (api, map, geo, navi, admin-store, draft-checks, util) | 본문(`todo()` 호출), 저장해 둔 캠퍼스 지도 |
| 테스트 | 테스트 폴더 구조, 통합 테스트 건너뛰기 규칙 | 기존 테스트. 뼈대 확인 테스트만 있음 |

뼈대 전용 부분은 구현이 끝나면 지운다: `backend/tests/unit/test_skeleton.py` 의 501 검사, `app/core/errors.py` 의 `NOT_IMPLEMENTED`, 프론트 각 HTML 의 `skeleton` 블록과 `util.js` 의 `todo` (자세한 목록은 `frontend/README.md`).

## 실행

Python 은 3.12 를 쓴다 (`backend/.python-version`, Dockerfile 과 같음). 3.14 에서는 pydantic-core 설치용 파일(휠)이 없어 설치가 실패할 수 있다. 3.13 까지는 동작한다.

```bash
cd backend
# 방법 1: uv 가 있으면 (3.12 를 알아서 받아 준다)
uv venv -p 3.12 .venv
# 방법 2: Windows 에 Python 3.12 가 설치돼 있으면
py -3.12 -m venv .venv

.venv\Scripts\activate                               # macOS, Linux: source .venv/bin/activate
python --version                                      # 3.12.x 인지 확인
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

이미 3.14 로 만든 `.venv` 가 있으면 폴더를 지우고 위 방법으로 다시 만든다.

| 주소 | 내용 |
|---|---|
| http://localhost:8000 | 프론트 화면 (frontend/ 의 HTML). 고치면 새로고침만 |
| http://localhost:8000/docs | API 문서 (Swagger) |
| http://localhost:8000/health | 상태 (DB 없이 뜬다. db: unchecked) |

프론트는 설치, 빌드가 없다. 같은 주소로 열리므로 API 호출에 CORS 설정이 필요 없다. 다른 폴더의 화면을 쓰려면 `.env` 에 `FRONTEND_DIR` 을 넣는다.

```bash
pytest   # 45개 통과, 25개 건너뜀 (건너뛴 것은 test_http_layer.py: 백엔드 단계 9 완료 기준)
```

## 남은 일 찾기

```bash
grep -rn "TODO" backend/app backend/scripts frontend
```

권장 순서 (프론트와 백엔드를 동시에):

1. 착수 전 (1~2일): `patches/` 의 두 패치 검토 후 적용 (DDL, 시드, DTO). `patches/README.md`
2. 백엔드: migrate, load_seed → tables.py → repositories → domain(단위 테스트) → services → api
   프론트: `?mock=1` 로 화면 4개 만들기 (`frontend/mock/README.md`). `js/api.js` 는 이미 동작한다
3. 백엔드 API 가 실제 응답을 주면 `?mock=0` 으로 바꿔 확인 → `frontend/mock/`, `js/mock.js` 삭제
4. 통합 테스트 (`TEST_DATABASE_URL`), CI integration 작업 켜기

## 정해 둔 것 (검토 v1.0 반영)

| 항목 | 결정 |
|---|---|
| /api 아래 없는 경로 | JSON 404 `NOT_FOUND` (화면 404.html 이 아님). `app/frontend.py` |
| 오류 형식 | 검증 오류 400 `INVALID_INPUT`, 404, 405 처리기를 미리 구현. DB 오류(503), 그 밖의 예외(500)는 TODO |
| Python 버전 | 3.12 (`.python-version`, `pyproject.toml` 은 3.12 이상 3.14 미만) |
| 프록시 IP | Dockerfile 에서 `--forwarded-allow-ips "*"` 를 뺐다. 기본 127.0.0.1, 운영에서만 `FORWARDED_ALLOW_IPS` 에 프록시 IP |
| MapLibre | CDN 대신 `frontend/vendor/` 에 4.7.1 원본을 둔다 |
| 보안 정책(CSP) | 개발(`ENV=local`)은 Report-Only로 위반만 기록(`POST /csp-report` → 서버 로그), 운영(`ENV=prod`)은 차단. `CSP_MODE` 로 바꿀 수 있다. 전환 기준은 `frontend/README.md` "CSP 운영" |
| 화면 파일 캐시, 도보 경로 ETag | `frontend/README.md` "정해 둔 것" |

## 정해 둔 것 (검토 v1.1 반영)

| 항목 | 결정 |
|---|---|
| 배포 형태 | FastAPI 하나가 API 와 화면 파일을 모두 내보낸다. Docker 이미지에 `frontend/` 를 넣는다 (맨 위 폴더에서 빌드, `docker-compose.yml` 의 `context: .`). HTTPS 용 프록시를 두면 모든 경로를 그대로 넘기고 정적 파일을 직접 주지 않는다 (CSP, no-cache 헤더가 빠지므로). API 명세서 v1.3 1.10 |
| DDL, 시드, DTO | 비워 둔 채로 두고, 테이블 정의서 v1.1, API 명세서 v1.3 로 확정된 내용을 `patches/` 로 준비했다. 검토 후 적용 |
| 백엔드 없이 화면 개발 | `frontend/mock/` + `js/mock.js`. `?mock=1` 로 켬. 관리자 저장, 409, 401, 429 도 흉내 낸다 |
| HTTP 오류 | 401, 413, 429 같은 HTTP 예외는 상태 코드를 그대로 두고 오류 형식만 맞춘다 (`CODE_BY_STATUS`) |
| HEAD 요청 | `/health` 는 HEAD 도 받는다 (모니터링용). `/api` 는 GET 만, HEAD 는 405 |
| CSP 위반 보고 | 8KB 넘으면 읽다가 멈춤, 로그 값의 제어 문자(줄바꿈)는 `?` 로 바꿈 (가짜 로그 줄 방지) |
| 경로 버전(updated_at) | 마이크로초까지 있는 문자열. 프론트는 `Date` 로 바꾸지 않고 받은 그대로 보낸다 (바꾸면 항상 409). mock 도 같은 형식이라 실수가 mock 단계에서 드러난다 |
| 도보 경로 ETag | 랜드마크를 바꾸면 그 장소 경로의 updated_at 도 올린다 (`scripts/load_seed.py` 규칙) |
| 진행 중 여행 | localStorage + 6시간 만료 (`js/navi.js`). 위치는 저장하지 않는다 |
| 휴대폰 실기 테스트 | 아래 "휴대폰에서 시험하기" (cloudflared 임시 HTTPS 주소) |
| CI | `.github/workflows/ci.yml`: ruff, pytest, node --test. 통합 테스트 작업은 migrate, load_seed 구현 뒤 주석 해제 |

## 휴대폰에서 시험하기

위치 확인(도착 판정, F-04)은 브라우저가 HTTPS 또는 localhost 에서만 허용한다. 같은 와이파이의 `http://192.168.x.x:8000` 으로 열면 위치 권한을 묻지도 않는다.
팀 공용 방법은 **cloudflared 임시 터널**로 정한다. 휴대폰에 인증서를 설치할 필요가 없고, 가입 없이 HTTPS 주소가 바로 나온다.

```bash
# 1) 설치 (한 번): Windows  winget install --id Cloudflare.cloudflared
#                  macOS    brew install cloudflared
# 2) 백엔드를 켠 상태에서
cloudflared tunnel --url http://localhost:8000
# 3) 출력되는 https://<임의 이름>.trycloudflare.com 주소를 휴대폰에서 연다 (?mock=1 도 된다)
```

- 이 주소는 터널을 켜 둔 동안 **인터넷 누구나** 열 수 있다. 시험이 끝나면 Ctrl+C 로 끈다. 주소를 단톡방 등에 올리지 않는다.
- 터널을 쓸 때는 `.env` 의 `ADMIN_KEY` 를 기본값이 아닌 긴 값으로 바꾼다.
- cloudflared 는 내 PC(127.0.0.1)에서 접속하므로 `FORWARDED_ALLOW_IPS` 기본값(127.0.0.1)으로 실제 휴대폰 IP 가 기록된다.
- 이용 조건(무료 임시 터널의 제한)은 바뀔 수 있다 [검증 필요: 시험 전 Cloudflare 문서 확인].

## 정해 둔 것 (팀원 백엔드 보완 반영, 2026-11-14)

출처: 팀원 보완 `../backend_supplement.patch`. 뼈대에 맞는 것만 옮겼다.

| 항목 | 결정 |
|---|---|
| 관리자 키 검사 순서 | `app/api/admin_route.py` 의 `AdminRoute` 가 본문 해석 전에 `require_admin` 을 부른다. 키 없이 깨진 JSON → 401 (400 아님). 라우터 `dependencies` 에 `require_admin` 을 넣지 않는다 (실패 횟수 두 번) |
| Swagger 관리자 키 칸 | 관리자 라우터에 `Security(APIKeyHeader("X-Admin-Key", auto_error=False))` 를 표시용으로 둔다. `/docs` 의 Authorize 에 키 칸이 보이고, 실패 횟수는 세지 않는다 |
| Content-Length | `app/core/http.py` `declared_length()`. 정수가 아니거나 음수면 400 `INVALID_INPUT` (500 이 나가지 않게). `/csp-report` 도 같은 함수를 쓴다 |
| 운영 관리자 키 | `ENV=prod` 에서 `ADMIN_KEY` 가 1~31자면 시작하지 않는다. 비어 있으면 관리자 API 가 꺼진 채로 뜬다 (항상 401) |
| HTTP 계층 테스트 | `tests/unit/test_http_layer.py` (25개) 는 단계 9 전까지 건너뛴다. 지금 확인 가능한 것은 `tests/unit/test_http_now.py` (17개) |
| 프록시 신뢰 | 이미 반영돼 있음 (위 "프록시 IP") |
