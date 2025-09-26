#!/bin/bash

# 마이그레이션 실행
docker compose exec invest_app python manage.py makemigrations
docker compose exec invest_app python manage.py migrate

# 스태틱 파일 수집
docker compose exec invest_app python manage.py collectstatic --no-input