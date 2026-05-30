#!/bin/bash
# Quick database inspection tool

cd "$(dirname "$0")"

case "$1" in
    --docs)
        echo "Generating database documentation..."
        docker compose exec web python scripts/table_inspector.py --docs
        ;;
    --export)
        echo "Exporting schema to JSON..."
        docker compose exec web python scripts/table_inspector.py --export
        ;;
    --monitor)
        echo "Checking for schema changes..."
        docker compose exec web python scripts/table_monitor.py --check
        ;;
    --report)
        echo "Generating table report..."
        docker compose exec web python scripts/table_monitor.py --report
        ;;
    --init-monitor)
        echo "Initializing table monitor..."
        docker compose exec web python scripts/table_monitor.py --init
        ;;
    --detail)
        echo "Detailed table inspection..."
        docker compose exec web python scripts/table_inspector.py --detail
        ;;
    *)
        echo "AFCON360 Database Inspector"
        echo ""
        echo "Usage: ./inspect_db.sh [OPTION]"
        echo ""
        echo "Options:"
        echo "  --docs        Generate markdown documentation"
        echo "  --export      Export schema to JSON"
        echo "  --monitor     Check for new/removed tables"
        echo "  --report      Show registered tables by module"
        echo "  --init-monitor Initialize table monitor state"
        echo "  --detail      Show detailed table information"
        echo ""
        echo "Examples:"
        echo "  ./inspect_db.sh --report"
        echo "  ./inspect_db.sh --monitor"
        echo "  ./inspect_db.sh --docs"
        ;;
esac
