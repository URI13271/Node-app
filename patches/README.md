# patches/

뼈대에서 비워 둔 것 중, 문서(테이블 정의서 v1.1, API 명세서 v1.3)로 이미 확정돼 있어서 비울 이유가 없는 두 묶음을 채우는 패치다.
아직 적용하지 않았다. 먼저 차이를 보고 적용한다.

| 파일 | 내용 | 바뀌는 파일 |
|---|---|---|
| `01_ddl_seed.patch` | 테이블 DDL(001, 002 와 되돌리기), 가좌캠퍼스 시드(`scripts/seeds/gnu-gajwa`, osm 3개 포함 11개), 통합 테스트 고정 데이터(`tests/fixtures/seed_campus`), 통합 테스트 준비 코드(`tests/conftest.py`, `tests/integration/conftest.py`), `app/db.py` 의 제약 이름 규칙 | 26개 |
| `02_schemas.patch` | DTO 필드 (`app/schemas/*.py` 5개, API 명세서 v1.3 형식) | 5개 |

두 패치는 서로 겹치지 않아서 하나만, 또는 어느 순서로 적용해도 된다. 근거 문서: 테이블 정의서 v1.1, API 명세서 v1.3.

## 1. 차이 보기 (적용 전)

```bash
cd majunggil
git apply --stat patches/01_ddl_seed.patch     # 파일별 줄 수
git apply --stat patches/02_schemas.patch
```

`.patch` 파일을 VS Code 로 열면 줄마다 `-`(지워질 줄, 빨강) `+`(들어갈 줄, 초록)로 보인다. `02_schemas.patch` 는 짧아서 처음부터 끝까지 읽어 볼 만하다.

## 2. 적용

```bash
git apply --check patches/01_ddl_seed.patch    # 문제없으면 아무것도 출력하지 않는다
git apply patches/01_ddl_seed.patch
git apply patches/02_schemas.patch
```

- 저장소(git)가 아닌 폴더에서도 `git apply` 는 동작한다. git 이 없으면 `patch -p1 < patches/01_ddl_seed.patch`.
- `--check` 에서 실패하면 해당 파일을 이미 고친 것이다. 그 파일만 빼고 적용하려면 `git apply --exclude=backend/app/db.py patches/01_ddl_seed.patch` 처럼 쓴다.
- `02_schemas.patch` 에서 `new blank line at EOF` 경고가 나와도 적용은 된다.
- `has type 100755, expected 100644` 경고는 파일 권한 표시 차이라 무시해도 된다 (Windows 폴더를 리눅스에서 열 때 나옴).

## 3. 적용 뒤 확인

```bash
cd backend
pytest              # 45개 통과, 25개 건너뜀 그대로여야 한다 (통합 테스트는 DB 가 없으면 건너뜀)
ruff check app scripts tests
```

시험한 결과 (2026-11-12, Python 3.13): 두 패치 모두 적용 후 pytest 27 통과, ruff 통과. 2026-11-14 HTTP 계층 테스트 추가 후 다시 확인: 45 통과, 25 건너뜀. `frontend/mock/` 응답 9개가 패치된 DTO(PlaceDetail, WalkRouteListOut, BuildingCollection) 검증을 모두 통과했다.

## 4. 되돌리기

```bash
git apply -R patches/02_schemas.patch
git apply -R patches/01_ddl_seed.patch
```

## 적용 뒤 할 일

- `app/repositories/tables.py` 는 비어 있다. DDL 을 보고 채운다 (`tests/integration/test_schema.py` 가 실제 DB와 비교).
- `scripts/migrate.py`, `scripts/load_seed.py` 를 구현하면 통합 테스트(`TEST_DATABASE_URL` 설정 시)와 CI integration 작업을 켤 수 있다.
- 적용이 끝나면 이 폴더는 지워도 된다.
