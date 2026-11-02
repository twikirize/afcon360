#!/usr/bin/env bash
#
# AFCON360 Oracle pre-release audit — READ ONLY.
#
# Run on the Oracle host from /opt/afcon360:
#   bash scripts/ops/pre_release_readonly_audit.sh
#
# This script does not restart or stop containers, apply migrations, change
# Redis configuration, read environment-file contents, or write to PostgreSQL.
# It reports only non-secret runtime metadata. Review all output before release.
#
set -uo pipefail

ROOT="${AFCON360_ROOT:-/opt/afcon360}"
WEB_CONTAINER="${AFCON360_WEB_CONTAINER:-afcon360_web}"
DB_CONTAINER="${AFCON360_DB_CONTAINER:-afcon360_db}"
REDIS_CONTAINER="${AFCON360_REDIS_CONTAINER:-afcon360_redis}"

section() {
    printf '\n===== %s =====\n' "$1"
}

container_exists() {
    docker inspect "$1" >/dev/null 2>&1
}

container_summary() {
    local name="$1"
    if ! container_exists "$name"; then
        printf '%s: NOT FOUND\n' "$name"
        return
    fi
    docker inspect --format \
        '{{.Name}} image={{.Config.Image}} state={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}} started={{.State.StartedAt}}' \
        "$name" 2>/dev/null | sed 's#^/##'
    docker inspect --format \
        '{{range .Config.Labels}}{{if or (eq .Name "com.docker.compose.project") (eq .Name "com.docker.compose.service")}}{{println .Name "=" .Value}}{{end}}{{end}}' \
        "$name" 2>/dev/null
}

section "HOST AND CHECKOUT"
hostname
date -u '+utc_time=%Y-%m-%dT%H:%M:%SZ'
whoami
printf 'working_directory='
pwd
if [ -d "$ROOT/.git" ]; then
    cd "$ROOT" || exit 1
    printf 'checkout='
    git rev-parse --short=12 HEAD 2>/dev/null || true
    git log -1 --format='last_commit=%h %s' 2>/dev/null || true
    git status --short --branch 2>/dev/null || true
    printf '\nserver-only files (names only; contents not read):\n'
    for f in .env.docker.runtime .env.runtime docker-compose.prod.yml; do
        if [ -e "$f" ]; then
            stat -c '%n size=%s bytes modified=%y' "$f" 2>/dev/null || printf '%s exists\n' "$f"
        else
            printf '%s: not present\n' "$f"
        fi
    done
else
    printf 'checkout directory not found: %s\n' "$ROOT"
fi

section "DISK AND HOST CAPACITY"
df -h / /opt 2>/dev/null || df -h 2>/dev/null
free -h 2>/dev/null || true
uptime 2>/dev/null || true

section "CONTAINER INVENTORY"
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || true

section "EXPECTED SERVICE CONTAINERS"
container_summary "$WEB_CONTAINER"
container_summary "$DB_CONTAINER"
container_summary "$REDIS_CONTAINER"

section "UNHEALTHY / UNIDENTIFIED CONTAINERS"
docker ps -a --filter health=unhealthy --format '{{.Names}} image={{.Image}} status={{.Status}}' 2>/dev/null || true

section "WEB CONTAINER DATABASE TARGET (CREDENTIALS REDACTED)"
if container_exists "$WEB_CONTAINER"; then
    docker inspect "$WEB_CONTAINER" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null |
    python3 -c '
import sys
from urllib.parse import urlsplit

allowed = {"APP_ENV", "FLASK_ENV", "DB_HOST", "DB_PORT", "DB_NAME"}
uri_keys = {"DATABASE_URL", "SQLALCHEMY_DATABASE_URI", "REDIS_URL"}

for raw in sys.stdin:
    raw = raw.rstrip("\n")
    if "=" not in raw:
        continue
    key, value = raw.split("=", 1)
    if key in allowed:
        print(f"{key}={value}")
    elif key in uri_keys:
        try:
            parsed = urlsplit(value)
            if key == "REDIS_URL":
                print(
                    f"{key}: scheme={parsed.scheme} host={parsed.hostname} "
                    f"port={parsed.port or \'default\'} database={parsed.path.lstrip(\'/\')}"
                )
            else:
                print(
                    f"{key}: scheme={parsed.scheme} host={parsed.hostname} "
                    f"port={parsed.port or \'default\'} database={parsed.path.lstrip(\'/\')}"
                )
        except Exception:
            print(f"{key}: set (target could not be parsed; value suppressed)")
' || true
else
    printf 'web container missing; target not inspected\n'
fi

section "POSTGRESQL SERVER AND SCHEMA METADATA"
if container_exists "$DB_CONTAINER"; then
    docker exec "$DB_CONTAINER" sh -lc '
        PGUSER="${POSTGRES_USER:-postgres}"
        PGDATABASE="${POSTGRES_DB:-postgres}"
        export PGUSER PGDATABASE
        psql -X -v ON_ERROR_STOP=1 -Atc "
            SELECT '''server_version=''' || current_setting('''server_version''');
            SELECT '''database=''' || current_database();
            SELECT '''database_size=''' || pg_size_pretty(pg_database_size(current_database()));
            SELECT '''public_base_tables=''' || count(*)
              FROM information_schema.tables
             WHERE table_schema = '''public''' AND table_type = '''BASE TABLE''';
            SELECT '''public_enum_types=''' || count(*)
              FROM pg_type t
              JOIN pg_namespace n ON n.oid = t.typnamespace
             WHERE n.nspname = '''public''' AND t.typtype = '''e''';
            SELECT '''alembic_version_table=''' || coalesce(to_regclass('''public.alembic_version''')::text, '''missing''');
        "
        if psql -X -Atc "SELECT to_regclass('''public.alembic_version''') IS NOT NULL" | grep -qx t; then
            psql -X -v ON_ERROR_STOP=1 -Atc \
              "SELECT '''alembic_revisions=''' || coalesce(string_agg(version_num, ''',''' ORDER BY version_num), '''none''') FROM alembic_version;"
        fi
    ' 2>&1 || true
else
    printf 'database container missing; PostgreSQL metadata not available\n'
fi

section "REDIS MEMORY, EVICTION AND PERSISTENCE"
if container_exists "$REDIS_CONTAINER"; then
    docker exec "$REDIS_CONTAINER" sh -lc '
        echo "-- CONFIG --"
        redis-cli CONFIG GET maxmemory maxmemory-policy appendonly appendfsync 2>&1
        echo "-- MEMORY --"
        redis-cli INFO memory 2>&1 | grep -E "^(used_memory_human|maxmemory|maxmemory_human|mem_fragmentation_ratio):" || true
        echo "-- STATS --"
        redis-cli INFO stats 2>&1 | grep -E "^(evicted_keys|keyspace_hits|keyspace_misses):" || true
        echo "-- PERSISTENCE --"
        redis-cli INFO persistence 2>&1 | grep -E "^(loading|rdb_last_save_time|rdb_last_bgsave_status|aof_enabled|aof_last_bgrewrite_status):" || true
    ' 2>&1 || true
else
    printf 'Redis container missing; runtime metadata not available\n'
fi

section "COMPOSE SERVICE NAMES (NO CONFIG VALUES)"
if [ -d "$ROOT" ] && [ -f "$ROOT/docker-compose.prod.yml" ]; then
    cd "$ROOT" || exit 1
    docker compose -f docker-compose.prod.yml config --services 2>&1 || true
else
    printf 'docker-compose.prod.yml not found; no Compose config was evaluated\n'
fi

section "END OF READ-ONLY AUDIT"
printf '%s\n' 'No application, database, Redis, container or host configuration was changed by this script.'
