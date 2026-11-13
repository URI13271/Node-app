# 빌드 위치는 저장소 맨 위 폴더다 (화면 파일 frontend/ 도 이미지에 넣기 위해).
#   docker compose build                       (docker-compose.yml 에 context: . 로 적혀 있음)
#   docker build -f backend/Dockerfile .        (직접 빌드할 때)
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/scripts ./scripts
# 배포 형태: FastAPI 하나가 API 와 화면 파일을 모두 내보낸다 (CSP, no-cache 헤더도 FastAPI 가 붙인다)
COPY frontend ./frontend
ENV FRONTEND_DIR=/app/frontend
EXPOSE 8000
# --proxy-headers 는 FORWARDED_ALLOW_IPS(기본 127.0.0.1)에 적힌 프록시가 보낸 X-Forwarded-For 만 믿는다.
# "*" 로 두면 누구나 X-Forwarded-For 를 바꿔 보내 IP 기준 제한(관리자 5회 잠금, 분당 요청 수)을 우회한다.
# 운영에서 리버스 프록시 뒤에 둘 때만 그 프록시 IP를 넣는다. 예: docker run -e FORWARDED_ALLOW_IPS=10.0.0.5
ENV FORWARDED_ALLOW_IPS=127.0.0.1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
