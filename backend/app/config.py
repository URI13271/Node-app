"""환경 변수 (설계서 2.2.2). 값은 .env 또는 실행 환경에서 읽는다."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "1.0.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ENV: str = "local"  # local | prod
    DATABASE_URL: str = "postgresql+psycopg://majunggil_app:app_local_only@localhost:5432/majunggil"
    MIGRATION_DATABASE_URL: str = "postgresql+psycopg://majunggil_owner:owner_local_only@localhost:5432/majunggil"
    ADMIN_KEY: str = Field(default="", description="32자 이상. 비어 있으면 관리자 API는 항상 401")
    ALLOWED_ORIGINS: str = ""  # 쉼표 구분. 같은 도메인 배포면 비워 둔다
    DEFAULT_ARRIVAL_RADIUS_M: int = 150
    LOG_LEVEL: str = "INFO"
    # HTML 프론트 폴더. 비우면 저장소의 ../frontend 를 쓴다. 폴더가 없으면 화면은 내보내지 않는다 (API만)
    FRONTEND_DIR: str = ""
    # 보안 정책(CSP) 적용 방식. report-only: 막지 않고 위반만 기록 / enforce: 실제로 막음 / off: 헤더 없음
    # 비우면 ENV 로 정한다: local → report-only, prod → enforce. 전환 기준은 frontend/README.md "CSP 운영"
    CSP_MODE: str = ""
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5
    DB_POOL_TIMEOUT_S: float = 3.0
    DB_STATEMENT_TIMEOUT_MS: int = 2000  # 조회
    DB_ADMIN_STATEMENT_TIMEOUT_MS: int = 5000  # 관리자 저장
    DB_LOCK_TIMEOUT_MS: int = 3000
    # 요청 횟수 제한 (API 명세서 1.9)
    RATE_LIMIT_PUBLIC_PER_MIN: int = 300
    RATE_LIMIT_ADMIN_PER_MIN: int = 60
    ADMIN_FAIL_LIMIT: int = 5
    ADMIN_LOCK_S: int = 600

    @property
    def is_prod(self) -> bool:
        return self.ENV == "prod"

    @property
    def csp_mode(self) -> str:
        mode = (self.CSP_MODE or ("enforce" if self.is_prod else "report-only")).strip().lower()
        if mode not in ("report-only", "enforce", "off"):
            raise ValueError(f"CSP_MODE 는 report-only, enforce, off 중 하나여야 합니다: {self.CSP_MODE!r}")
        return mode

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
