"""add_media_enhancements

Adds new columns to media table for enhanced security and UX:
- width, height, duration, thumbnail_url: media dimensions
- perceptual_hash: near-duplicate detection
- is_animated: animated WebP/GIF support
- upload_session_id: chunked upload support

Revision ID: 20260629_add_media_enhancements
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '20260629_add_media_enhancements'
down_revision = '20260627_add_media_tables'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to media table
    op.add_column('media', sa.Column('width', sa.Integer(), nullable=True))
    op.add_column('media', sa.Column('height', sa.Integer(), nullable=True))
    op.add_column('media', sa.Column('duration', sa.Integer(), nullable=True))
    op.add_column('media', sa.Column('thumbnail_url', sa.String(500), nullable=True))
    op.add_column('media', sa.Column('perceptual_hash', sa.String(64), nullable=True))
    op.add_column('media', sa.Column('is_animated', sa.Boolean(), server_default='false'))
    op.add_column('media', sa.Column('upload_session_id', sa.String(64), nullable=True))

    # Create indexes for new columns
    op.create_index('ix_media_perceptual_hash', 'media', ['perceptual_hash'])
    op.create_index('ix_media_upload_session', 'media', ['upload_session_id'])

    # Create media_settings table (single-row config table)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'media_settings' not in inspector.get_table_names():
        op.create_table(
            'media_settings',
            sa.Column('id', sa.BigInteger(), primary_key=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_by_id', sa.BigInteger(), nullable=True),
            sa.Column('virus_scan_enabled', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('content_moderation_enabled', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('perceptual_hash_enabled', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('perceptual_hash_threshold', sa.Integer(), nullable=False, server_default='6'),
            sa.Column('quota_enabled', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('user_quota_bytes', sa.BigInteger(), nullable=False, server_default=str(500 * 1024 * 1024)),
            sa.Column('host_quota_bytes', sa.BigInteger(), nullable=False, server_default=str(5 * 1024 * 1024 * 1024)),
            sa.Column('org_quota_bytes', sa.BigInteger(), nullable=False, server_default=str(10 * 1024 * 1024 * 1024)),
            sa.Column('webp_quality', sa.Integer(), nullable=False, server_default='75'),
            sa.Column('avif_quality', sa.Integer(), nullable=False, server_default='65'),
            sa.Column('jpeg_quality', sa.Integer(), nullable=False, server_default='82'),
            sa.Column('chunked_upload_enabled', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('chunk_size', sa.Integer(), nullable=False, server_default=str(5 * 1024 * 1024)),
            sa.Column('clamav_enabled', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('clamav_host', sa.String(255), nullable=True),
            sa.Column('clamav_port', sa.Integer(), nullable=True),
            sa.Column('signature_scan_enabled', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('moderation_strictness', sa.String(50), nullable=False, server_default='medium'),
            sa.Column('auto_reject_duplicates', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('max_files_per_upload', sa.Integer(), nullable=False, server_default='20'),
            sa.Column('allowed_extensions', sa.Text(), nullable=True),
            sa.Column('authorized_manager_roles', sa.Text(), nullable=False, server_default='[]'),
        )


def downgrade():
    # Drop media_settings table if it exists
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'media_settings' in inspector.get_table_names():
        op.drop_table('media_settings')

    # Remove indexes
    op.drop_index('ix_media_upload_session', table_name='media')
    op.drop_index('ix_media_perceptual_hash', table_name='media')

    # Remove columns
    op.drop_column('media', 'upload_session_id')
    op.drop_column('media', 'is_animated')
    op.drop_column('media', 'perceptual_hash')
    op.drop_column('media', 'thumbnail_url')
    op.drop_column('media', 'duration')
    op.drop_column('media', 'height')
    op.drop_column('media', 'width')
