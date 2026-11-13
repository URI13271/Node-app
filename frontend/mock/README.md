# mock/ (가짜 응답)

백엔드 없이 화면을 만들 때 쓰는 응답 파일이다. `js/mock.js` 가 읽는다.

## 쓰는 법

1. 백엔드를 켠다 (`uvicorn app.main:app --reload --port 8000`). 화면 파일을 내보내는 데만 쓰고 API 는 아직 501 이어도 된다.
2. `http://localhost:8000/?mock=1` 을 연다. 화면 오른쪽 위에 노란 **MOCK** 표시가 뜬다.
3. 같은 탭에서는 다른 화면으로 가도 계속 켜져 있다. 끄려면 주소에 `?mock=0`.

## 들어 있는 데이터

경상국립대 가좌캠퍼스 시연 장소 3곳 (API 명세서 v1.3 형식의 예시 응답)과, 경로 없는 화면 확인용 예시 1곳(id 4, mock 전용).

| 파일 | API |
|---|---|
| `places.json` | `GET /places` (검색어 q, limit, offset 은 mock.js 가 처리) |
| `places/{id}.json` | `GET /places/{id}` (id 1 중앙도서관, 2 학생회관, 3 교양학관, 4 경로 준비 중 예시) |
| `places/{id}/buildings.json` | `GET /places/{id}/buildings` |
| `places/{id}/walk-routes.json` | `GET /places/{id}/walk-routes` (parking_lot_id 거르기는 mock.js) |
| `admin/me.json` | `GET /admin/me` 응답 예시 |

관리자 저장(PUT, PATCH)은 파일을 바꾸지 않고 탭의 sessionStorage 에 기억한다. 버전(updated_at)이 다르면 서버처럼 409 를 준다.

## 오류 화면 시험

| 하고 싶은 것 | 방법 |
|---|---|
| 401 (키 틀림) | 관리자 키에 `wrong` |
| 429 (키 잠김) | 관리자 키에 `locked` |
| 404 (없는 장소) | `place.html?id=99` |
| 도보 경로가 없는 장소 | `place.html?id=4`, `guide.html?id=4` |
| 409 (다른 관리자가 먼저 저장) | 개발자 도구 콘솔에서 `majunggilMock.bump(경로id)` 뒤 저장 |
| 처음 데이터로 | 콘솔에서 `majunggilMock.reset()` |

## 지우는 때

백엔드가 네 API 를 실제로 돌려주기 시작하면 `mock/` 폴더, `js/mock.js`, `api.js` 의 mock 두 줄, `style.css` 의 `.mock-badge` 를 지운다.
