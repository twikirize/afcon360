"""replace RoomCategory with RoomType in room model

Revision ID: 6e9dbae2ac1a
Revises: 07c931b46c36
Create Date: 2026-07-26 21:29:42.709221

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '6e9dbae2ac1a'
down_revision = '07c931b46c36'
branch_labels = None
depends_on = None


def upgrade():
    # ============================================================
    # STEP 1: Drop the foreign key constraint from accommodation_rooms FIRST
    # This removes the dependency on accommodation_room_categories
    # ============================================================
    with op.batch_alter_table('accommodation_rooms', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('accommodation_rooms_category_id_fkey'), type_='foreignkey')

    # ============================================================
    # STEP 2: Drop indexes on the old table (cleanup before dropping)
    # ============================================================
    with op.batch_alter_table('accommodation_room_categories', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('idx_room_category_active'))
        batch_op.drop_index(batch_op.f('idx_room_category_property'))
        batch_op.drop_index(batch_op.f('ix_accommodation_room_categories_created_at'))
        batch_op.drop_index(batch_op.f('ix_accommodation_room_categories_is_active'))
        batch_op.drop_index(batch_op.f('ix_accommodation_room_categories_is_deleted'))
        batch_op.drop_index(batch_op.f('ix_accommodation_room_categories_updated_at'))

    # ============================================================
    # STEP 3: Drop the old table (now safe because FK is gone)
    # ============================================================
    op.drop_table('accommodation_room_categories')

    # ============================================================
    # STEP 4: Modify accommodation_rooms - add new column, drop old column
    # ============================================================
    with op.batch_alter_table('accommodation_rooms', schema=None) as batch_op:
        # Add new room_type_id column (nullable initially)
        batch_op.add_column(sa.Column('room_type_id', sa.BigInteger(), nullable=True))

        # Drop old index on category_id
        batch_op.drop_index(batch_op.f('idx_room_category'))

        # Create new index on room_type_id
        batch_op.create_index('idx_room_room_type', ['room_type_id'], unique=False)

        # Add new foreign key to accommodation_room_types
        batch_op.create_foreign_key(
            batch_op.f('accommodation_rooms_room_type_id_fkey'),
            'accommodation_room_types',
            ['room_type_id'],
            ['id'],
            ondelete='RESTRICT'
        )

        # Drop the old category_id column (FK already dropped in Step 1)
        batch_op.drop_column('category_id')

    # ============================================================
    # STEP 5: Populate room_type_id for existing rooms
    # All rooms had category_id=2, which maps to RoomType.id=5 (DELUXE KING)
    # ============================================================
    op.execute("UPDATE accommodation_rooms SET room_type_id = 5 WHERE room_type_id IS NULL")

    # ============================================================
    # STEP 6: Make room_type_id NOT NULL after populating
    # ============================================================
    with op.batch_alter_table('accommodation_rooms', schema=None) as batch_op:
        batch_op.alter_column('room_type_id', nullable=False)

    # ============================================================
    # STEP 7: Other unrelated migrations (content_flags, user_nonces)
    # ============================================================
    with op.batch_alter_table('content_flags', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_content_flags_risk_score'))
        batch_op.create_index(batch_op.f('ix_content_flags_risk_score'), ['risk_score'], unique=False)

    with op.batch_alter_table('user_nonces', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_nonces_nonce'))
        batch_op.create_index(batch_op.f('ix_user_nonces_nonce'), ['nonce'], unique=True)


def downgrade():
    # ============================================================
    # STEP 1: Reverse user_nonces change
    # ============================================================
    with op.batch_alter_table('user_nonces', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_nonces_nonce'))
        batch_op.create_index(batch_op.f('ix_user_nonces_nonce'), ['nonce'], unique=False)

    # ============================================================
    # STEP 2: Reverse content_flags change
    # ============================================================
    with op.batch_alter_table('content_flags', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_content_flags_risk_score'))
        batch_op.create_index(batch_op.f('ix_content_flags_risk_score'), ['risk_score', 'status'], unique=False)

    # ============================================================
    # STEP 3: Reverse accommodation_rooms changes
    # ============================================================
    with op.batch_alter_table('accommodation_rooms', schema=None) as batch_op:
        # Add back category_id column
        batch_op.add_column(sa.Column('category_id', sa.BIGINT(), autoincrement=False, nullable=True))

        # Drop the new FK constraint
        batch_op.drop_constraint(batch_op.f('accommodation_rooms_room_type_id_fkey'), type_='foreignkey')

        # Drop the new index
        batch_op.drop_index('idx_room_room_type')

        # Recreate old index on category_id
        batch_op.create_index(batch_op.f('idx_room_category'), ['category_id'], unique=False)

        # Drop the room_type_id column
        batch_op.drop_column('room_type_id')

    # ============================================================
    # STEP 4: Recreate accommodation_room_categories table
    # ============================================================
    op.create_table('accommodation_room_categories',
        sa.Column('id', sa.BIGINT(), autoincrement=True, nullable=False),
        sa.Column('property_id', sa.BIGINT(), autoincrement=False, nullable=False),
        sa.Column('name', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
        sa.Column('description', sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column('short_code', sa.VARCHAR(length=20), autoincrement=False, nullable=True),
        sa.Column('max_guests', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('bedrooms', sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column('beds', sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column('bathrooms', sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column('base_price_per_night', sa.NUMERIC(precision=10, scale=2), autoincrement=False, nullable=False),
        sa.Column('currency', sa.VARCHAR(length=3), autoincrement=False, nullable=True),
        sa.Column('cleaning_fee', sa.NUMERIC(precision=10, scale=2), autoincrement=False, nullable=True),
        sa.Column('is_active', sa.BOOLEAN(), autoincrement=False, nullable=False),
        sa.Column('is_deleted', sa.BOOLEAN(), autoincrement=False, nullable=False),
        sa.Column('deleted_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(), server_default=sa.text('now()'), autoincrement=False, nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(), server_default=sa.text('now()'), autoincrement=False, nullable=False),
        sa.CheckConstraint('base_price_per_night >= 0::numeric', name=op.f('ck_category_price_positive')),
        sa.CheckConstraint('max_guests >= 1', name=op.f('ck_category_guests_min')),
        sa.ForeignKeyConstraint(['property_id'], ['accommodation_properties.id'], name=op.f('accommodation_room_categories_property_id_fkey'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('accommodation_room_categories_pkey')),
        sa.UniqueConstraint('property_id', 'name', name=op.f('uq_category_per_property'))
    )

    # ============================================================
    # STEP 5: Recreate indexes on accommodation_room_categories
    # ============================================================
    with op.batch_alter_table('accommodation_room_categories', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('idx_room_category_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('idx_room_category_property'), ['property_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_accommodation_room_categories_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_accommodation_room_categories_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_accommodation_room_categories_is_deleted'), ['is_deleted'], unique=False)
        batch_op.create_index(batch_op.f('ix_accommodation_room_categories_updated_at'), ['updated_at'], unique=False)

    # ============================================================
    # STEP 6: Recreate the foreign key constraint on accommodation_rooms
    # ============================================================
    with op.batch_alter_table('accommodation_rooms', schema=None) as batch_op:
        batch_op.create_foreign_key(
            batch_op.f('accommodation_rooms_category_id_fkey'),
            'accommodation_room_categories',
            ['category_id'],
            ['id'],
            ondelete='RESTRICT'
        )
