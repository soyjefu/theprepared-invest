#!/bin/sh
# wait-for-postgres.sh

set -e

host="$1"
shift
# exec a command at the end
cmd="$@"

# PGPASSWORD 환경 변수를 사용하여 psql 명령어 실행
# -c '\q' 옵션은 간단한 연결 테스트 후 바로 종료하는 명령어입니다.
until PGPASSWORD=$POSTGRES_PASSWORD psql -h "$host" -U "$POSTGRES_USER" -d "$POSTGRES_DB_I" -c '\q'; do
  >&2 echo "Postgres is unavailable - sleeping"
  sleep 1
done

>&2 echo "Postgres is up - executing command"
exec $cmd