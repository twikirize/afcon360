#!/bin/bash
# =============================================================================
# AFCON360 - Docker Entrypoint
# Waits for PostgreSQL + Redis, runs migrations, starts correct process
# =============================================================================
set -e

echo "🚀 AFCON360 container starting (role: ${CONTAINER_ROLE:-web})..."

# ---------------------------------------------------------------------------
# Wait for PostgreSQL
# ---------------------------------------------------------------------------
DB_HOST_WAIT="${DB_HOST:-db}"
DB_PORT_WAIT="${DB_PORT:-5432}"
echo "⏳ Waiting for PostgreSQL at ${DB_HOST_WAIT}:${DB_PORT_WAIT}..."

until PGPASSWORD=${DB_PASS} pg_isready -h "${DB_HOST_WAIT}" -p "${DB_PORT_WAIT}" -U "${DB_USER}" 2>/dev/null; do
    echo "   PostgreSQL not ready — retrying in 2s..."
    sleep 2
done
echo "✅ PostgreSQL ready"

# ---------------------------------------------------------------------------
# Wait for Redis
# ---------------------------------------------------------------------------
REDIS_HOST_WAIT="${REDIS_HOST:-redis}"
REDIS_PORT_WAIT="${REDIS_PORT:-6379}"
echo "⏳ Waiting for Redis at ${REDIS_HOST_WAIT}:${REDIS_PORT_WAIT}..."

until nc -z "${REDIS_HOST_WAIT}" "${REDIS_PORT_WAIT}" 2>/dev/null; do
    echo "   Redis not ready — retrying in 2s..."
    sleep 2
done
echo "✅ Redis ready"

# ---------------------------------------------------------------------------
# Migrations + seed (only on web container)
# ---------------------------------------------------------------------------
if [ "${CONTAINER_ROLE}" = "web" ] || [ "$1" = "gunicorn" ]; then
    echo "🔄 Running database migrations..."
    flask db upgrade || echo "⚠️  Migrations failed (may already be up to date)"

    echo "🌱 Seeding roles and permissions..."
    flask seed-roles 2>/dev/null || echo "ℹ️  Seed skipped (already seeded or no changes)"
fi

# ---------------------------------------------------------------------------
# Start the correct process based on command
# ---------------------------------------------------------------------------
case "$1" in
    gunicorn)
        echo "🌐 Starting Gunicorn with ${GUNICORN_WORKERS:-2} workers..."
        exec gunicorn \
            --bind 0.0.0.0:5000 \
            --workers "${GUNICORN_WORKERS:-2}" \
            --threads "${GUNICORN_THREADS:-2}" \
            --timeout "${GUNICORN_TIMEOUT:-120}" \
            --keepalive 5 \
            --max-requests 1000 \
            --max-requests-jitter 100 \
            --access-logfile - \
            --error-logfile - \
            "app:create_app()"
        ;;

    celery)
        echo "⚙️  Starting Celery worker with concurrency ${CELERY_CONCURRENCY:-2}..."
        exec celery -A app.celery_app worker \
            --loglevel="${LOG_LEVEL:-warning}" \
            --concurrency="${CELERY_CONCURRENCY:-2}" \
            --max-tasks-per-child=100
        ;;

    celery-beat)
        echo "🕐 Starting Celery Beat..."
        exec celery -A app.celery_app beat \
            --loglevel="${LOG_LEVEL:-warning}" \
            --schedule=/tmp/celerybeat-schedule
        ;;

    *)
        exec "$@"
        ;;
esac