#!/bin/bash
# Convenience script to create database tables using the lazy table creator
# Usage: ./create_tables.sh

cd "$(dirname "$0")"

echo "Creating database tables with lazy dependency resolution..."
docker compose exec web python scripts/lazy_table_creator.py

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Tables created successfully!"
    echo "You can now restart your application: docker compose restart"
else
    echo ""
    echo "⚠️ Some tables may still be missing. Run the script again or check logs."
fi
