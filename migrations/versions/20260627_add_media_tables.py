# migrations/versions/20260627_add_media_tables.py
"""Add media and media_processing_jobs tables

Revision ID: 20260627_add_media
Revises: ab6dd422c152
Create Date: 2026-06-27
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '20260627_add_media_tables'
down_revision = 'ab6dd422c152'
branch_labels = None
depends_on = None


def upgrade():
    # Check if tables already exist
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if 'media' not in existing_tables:
        op.create_table(
            'media',
            sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column('public_id', sa.String(64), nullable=False),
            sa.Column('module', sa.String(50), nullable=False),
            sa.Column('entity_id', sa.String(64), nullable=False),
            sa.Column('uploaded_by', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('media_type', sa.String(50), nullable=False, server_default='photo'),
            sa.Column('storage_key', sa.String(500), nullable=True),
            sa.Column('storage_backend', sa.String(20), nullable=False, server_default='local'),
            sa.Column('video_url', sa.String(500), nullable=True),
            sa.Column('original_filename', sa.String(255), nullable=True),
            sa.Column('file_size', sa.Integer(), nullable=True),
            sa.Column('mime_type', sa.String(100), nullable=True),
            sa.Column('sha256_hash', sa.String(64), nullable=True),
            sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('urls', sa.JSON(), nullable=False, server_default='{}'),
            sa.Column('caption', sa.String(300), nullable=True),
            sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('is_cover', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('is_public', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('public_id', name='uq_media_public_id'),
            sa.Index('ix_media_module_entity', 'module', 'entity_id'),
            sa.Index('ix_media_status', 'status'),
            sa.Index('ix_media_sha256', 'sha256_hash'),
            sa.Index('ix_media_is_deleted', 'is_deleted'),
        )

    if 'media_processing_jobs' not in existing_tables:
        op.create_table(
            'media_processing_jobs',
            sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column('public_id', sa.String(64), nullable=False),
            sa.Column('media_id', sa.BigInteger(), sa.ForeignKey('media.id', ondelete='CASCADE'), nullable=False),
            sa.Column('celery_task_id', sa.String(64), nullable=True),
            sa.Column('job_type', sa.String(50), nullable=False),
            sa.Column('status', sa.String(20), nullable=False, server_default='queued'),
            sa.Column('started_at', sa.DateTime(), nullable=True),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.Column('error', sa.Text(), nullable=True),
            sa.Column('result', sa.JSON(), nullable=True),
            sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint('id'),
            sa.Index('ix_mpj_celery_task', 'celery_task_id'),
            sa.Index('ix_mpj_media_id', 'media_id'),
        )


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if 'media_processing_jobs' in existing_tables:
        op.drop_table('media_processing_jobs')
    if 'media' in existing_tables:
        op.drop_table('media')
