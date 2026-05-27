#!/bin/bash
set -e

echo "🚀 AFCON360 container starting (role: ${CONTAINER_ROLE:-web})"

# Wait for PostgreSQL
until PGPASSWORD=${DB_PASS} pg_isready -h ${DB_HOST:-db} -U ${DB_USER}; do
    echo "   Waiting for PostgreSQL..."
    sleep 2
done
echo "✅ PostgreSQL ready"

# Wait for Redis
until nc -z ${REDIS_HOST:-redis} ${REDIS_PORT:-6379}; do
    echo "   Waiting for Redis..."
    sleep 2
done
echo "✅ Redis ready"

# ONLY run migrations if this is the web container
if [ "${CONTAINER_ROLE}" = "web" ]; then
    echo "🔄 Running database migrations (web container only)..."
    flask db upgrade
    echo "✅ Migrations complete"
    
    echo "🌱 Seeding roles and permissions..."
    flask seed-roles 2>/dev/null || echo "ℹ️  Seed skipped"
else
    echo "⏭️  Skipping migrations (role: ${CONTAINER_ROLE})"
fi

# Start the correct process
case "$1" in
    gunicorn)
        echo "🌐 Starting Gunicorn..."
        exec gunicorn --bind 0.0.0.0:5000 --workers 2 --threads 2 "app:create_app()"
        ;;
    celery)
        echo "⚙️  Starting Celery worker..."
        exec celery -A app.celery_app worker --loglevel=info --concurrency=2
        ;;
    celery-beat)
        echo "🕐 Starting Celery Beat..."
        exec celery -A app.celery_app beat --loglevel=info
        ;;
    *)
        exec "$@"
        ;;
esac
