# 1. 기반 이미지 설정
# --------------------
# 가볍고 안정적인 Python 3.11-slim 버전을 사용합니다.
FROM python:3.11-slim

# 2. 환경 변수 설정
# -------------------
# 파이썬이 .pyc 파일을 생성하지 않도록 하고 (PYTHONDONTWRITEBYTECODE),
# 로그 출력이 버퍼링 없이 즉시 표시되도록 설정합니다 (PYTHONUNBUFFERED).
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt update && apt install -y --no-install-recommends postgresql-client && rm -rf /var/lib/apt/lists/*


# 3. 비루트 사용자 생성 (보안 강화)
# ---------------------------------
# Debian 기반 이미지에 맞는 --system 옵션을 사용하여 사용자를 생성합니다.
RUN addgroup --system appgroup && adduser --system --ingroup appgroup --no-create-home appuser

# 4. 의존성 설치
# --------------
# 먼저 requirements.txt 파일만 복사하여 의존성을 설치합니다.
# 이렇게 하면 소스 코드가 변경될 때마다 매번 의존성을 새로 설치하지 않고,
# Docker 캐시를 활용하여 빌드 속도를 높일 수 있습니다.
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 소스 코드 복사 및 권한 설정
# ------------------------------
# 나머지 애플리케이션 코드를 복사하고, 생성된 사용자가 파일에 접근할 수 있도록
# /app 디렉토리 전체의 소유권을 변경합니다.
COPY . .

# ⭐️ 로그 디렉토리를 생성하고 권한을 설정합니다.
RUN mkdir -p /app/logs && chown -R appuser:appgroup /app/logs

RUN chown -R appuser:appgroup /app

# 6. 사용자 전환
# -------------
# 이제부터는 appuser 권한으로 명령을 실행합니다.
USER appuser

# 7. 애플리케이션 실행
# --------------------
# Gunicorn을 사용하여 Django 애플리케이션을 실행합니다.
# --timeout을 600초로 설정하여 복잡한 요청 처리 시 워커가 종료되는 것을 방지합니다.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--timeout", "600", "invest.wsgi:application"]
