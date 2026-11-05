#!/bin/bash
set -e

echo "🚀 AFCON360 container starting (role: ${CONTAINER_ROLE:-web})"

# ---------------------------------------------------------------------------
# Wait for PostgreSQL
# DB_USER defaults to 'israeli' to match base .env — prevents empty-user loop
# pg_isready does not authenticate, so no PGPASSWORD here; real connections
# resolve credentials from the libpq pgpass file, never from env.
# ---------------------------------------------------------------------------
until pg_isready -h "${DB_HOST:-db}" -U "${DB_USER:-israeli}" -d "${DB_NAME:-afcon360_prod}"; do
    echo "   Waiting for PostgreSQL at ${DB_HOST:-db}..."
    sleep 2
done
echo "✅ PostgreSQL ready"

# ---------------------------------------------------------------------------
# Wait for Redis
# ---------------------------------------------------------------------------
until nc -z "${REDIS_HOST:-redis}" "${REDIS_PORT:-6379}"; do
    echo "   Waiting for Redis at ${REDIS_HOST:-redis}:${REDIS_PORT:-6379}..."
    sleep 2
done
echo "✅ Redis ready"

# ---------------------------------------------------------------------------
# Startup env validation — fail fast before boot if critical vars are missing
# ---------------------------------------------------------------------------
REQUIRED_VARS="DATABASE_URL REDIS_URL SECRET_KEY SECURITY_SALT"
MISSING=""
for var in $REQUIRED_VARS; do
    if [ -z "${!var}" ]; then
        MISSING="$MISSING $var"
    fi
done
if [ -n "$MISSING" ]; then
    echo "❌ FATAL: Missing required environment variables:$MISSING"
    echo "   Check your .env.docker or .env.prod file and retry."
    exit 1
fi
echo "✅ Environment validation passed"

# ---------------------------------------------------------------------------
# Run migrations ONLY on the web container — never on celery/beat
# ---------------------------------------------------------------------------
if [ "${CONTAINER_ROLE}" = "web" ]; then
    echo "🔄 Running database migrations..."
    flask db upgrade
    echo "✅ Migrations complete"

    echo "🌱 Seeding roles and permissions..."
    flask seed-roles 2>/dev/null || echo "ℹ️  Seed skipped (already seeded or not available)"
else
    echo "⏭️  Skipping migrations (role: ${CONTAINER_ROLE})"
fi

# ---------------------------------------------------------------------------
# Start the correct process based on CONTAINER_ROLE
# ---------------------------------------------------------------------------
case "$1" in
    gunicorn)
        echo "🌐 Starting Gunicorn (workers: ${GUNICORN_WORKERS:-2})..."
        exec gunicorn \
            --bind 0.0.0.0:5000 \
            --workers "${GUNICORN_WORKERS:-2}" \
            --threads "${GUNICORN_THREADS:-2}" \
            --timeout "${GUNICORN_TIMEOUT:-120}" \
            --access-logfile - \
            --error-logfile - \
            "app:create_app()"
        ;;
    celery)
        echo "⚙️  Starting Celery worker (concurrency: ${CELERY_CONCURRENCY:-1})..."
        # Compose may pass "celery -A ... worker ..." as the command. Preserve
        # those explicit arguments instead of silently discarding queue,
        # prefetch, and process-recycling flags.
        if [ "$#" -gt 1 ]; then
            shift
            exec celery "$@"
        fi

        queue_args=()
        if [ -n "${CELERY_QUEUES:-}" ]; then
            queue_args=(-Q "${CELERY_QUEUES}")
        fi
        exec celery -A app.celery_app worker \
            --loglevel=info \
            --concurrency="${CELERY_CONCURRENCY:-1}" \
            --prefetch-multiplier="${CELERY_PREFETCH_MULTIPLIER:-1}" \
            --max-tasks-per-child="${CELERY_MAX_TASKS_PER_CHILD:-50}" \
            "${queue_args[@]}"
        ;;
    celery-beat)
        echo "🕐 Starting Celery Beat..."
        if [ "$#" -gt 1 ]; then
            shift
            exec celery -A app.celery_app beat --loglevel=info "$@"
        fi
        exec celery -A app.celery_app beat --loglevel=info
        ;;
    *)
        exec "$@"
        ;;
esac
