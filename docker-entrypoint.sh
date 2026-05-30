#!/bin/bash
set -e

echo "🚀 AFCON360 container starting (role: ${CONTAINER_ROLE:-web})"

# ---------------------------------------------------------------------------
# Wait for PostgreSQL
# DB_USER defaults to 'israeli' to match base .env — prevents empty-user loop
# ---------------------------------------------------------------------------
until PGPASSWORD="${DB_PASS}" pg_isready -h "${DB_HOST:-db}" -U "${DB_USER:-israeli}" -d "${DB_NAME:-afcon360_prod}"; do
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
        echo "⚙️  Starting Celery worker (concurrency: ${CELERY_CONCURRENCY:-2})..."
        exec celery -A app.celery_app worker \
            --loglevel=info \
            --concurrency="${CELERY_CONCURRENCY:-2}"
        ;;
    celery-beat)
        echo "🕐 Starting Celery Beat..."
        exec celery -A app.celery_app beat --loglevel=info
        ;;
    *)
        exec "$@"
        ;;
esac
