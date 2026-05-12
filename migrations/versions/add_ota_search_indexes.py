"""Add OTA-grade search and performance indexes"""
from alembic import op

def upgrade():
    # Full-text search — check 'accommodation_properties' is the actual table name
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_properties_fts
        ON accommodation_properties
        USING gin(
            to_tsvector('english',
                coalesce(title, '') || ' ' ||
                coalesce(description, '') || ' ' ||
                coalesce(city, '') || ' ' ||
                coalesce(country, '')
            )
        );
    """)
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_properties_city_lower
        ON accommodation_properties (lower(city), lower(country))
        WHERE is_active = TRUE;
    """)
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_properties_price_rating
        ON accommodation_properties (base_price_per_night ASC, overall_rating DESC NULLS LAST)
        WHERE is_active = TRUE;
    """)
    # Booking date range queries
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bookings_property_dates
        ON accommodation_bookings (property_id, check_in_date, check_out_date)
        WHERE status NOT IN ('cancelled', 'rejected');
    """)

def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_properties_fts;")
    op.execute("DROP INDEX IF EXISTS idx_properties_city_lower;")
    op.execute("DROP INDEX IF EXISTS idx_properties_price_rating;")
    op.execute("DROP INDEX IF EXISTS idx_bookings_property_dates;")
