-- Docker 첫 기동 때 한 번 실행 (postgis/postgis 이미지의 /docker-entrypoint-initdb.d)
-- 설계서 1.4.2: 애플리케이션 계정은 DDL 권한 없음, 세션 시간대 UTC
ALTER DATABASE majunggil SET timezone = 'UTC';
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE ROLE majunggil_app LOGIN PASSWORD 'app_local_only';
GRANT CONNECT ON DATABASE majunggil TO majunggil_app;
GRANT USAGE ON SCHEMA public TO majunggil_app;
-- 마이그레이션 계정(majunggil_owner)이 앞으로 만드는 테이블에 읽기, 쓰기 권한 자동 부여
ALTER DEFAULT PRIVILEGES FOR ROLE majunggil_owner IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO majunggil_app;
ALTER DEFAULT PRIVILEGES FOR ROLE majunggil_owner IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO majunggil_app;
