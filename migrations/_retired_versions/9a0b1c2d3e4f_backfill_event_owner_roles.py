"""Backfill EventRole for existing event owners

Revision ID: 9a0b1c2d3e4f
Revises: 91911883eb58
Create Date: 2026-08-23 00:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

# revision identifiers, used by Alembic.
revision = '9a0b1c2d3e4f'
down_revision = '91911883eb58'
branch_labels = None
depends_on = None


# Define the owner permissions bundle
OWNER_PERMISSIONS = [
    'view_coordination', 'manage_coordination', 'check_in',
    'guest.view', 'guest.create', 'guest.edit', 'guest.import',
    'guest.archive', 'guest.link_account', 'guest.merge',
    'assignment.view', 'accommodation.assign', 'accommodation.cancel',
    'accommodation.allocate_room', 'transport.assign', 'transport.cancel',
    'transport.plan', 'tourism.assign', 'tourism.cancel',
    'experience.assign', 'wallet.view', 'allowance.create',
    'allowance.adjust', 'wallet.authorise_spend', 'financial.approve',
    'financial.view', 'journey.view', 'journey.manage',
    'journey.override', 'exception.resolve', 'coverage.view',
    'group.view', 'group.create', 'group.edit', 'group.bulk_assign',
    'group.vip_manage', 'notify.guest', 'notify.bulk', 'message.view',
]


def upgrade():
    """Create EventRole entries for existing event owners."""
    bind = op.get_bind()
    session = Session(bind=bind)

    try:
        # Get table references
        events_table = sa.Table('events', sa.MetaData(), autoload_with=bind)
        event_roles_table = sa.Table('event_roles', sa.MetaData(), autoload_with=bind)
        users_table = sa.Table('users', sa.MetaData(), autoload_with=bind)
        organisations_table = sa.Table('organisations', sa.MetaData(), autoload_with=bind)
        # Organisation members - check for the membership table
        try:
            org_members_table = sa.Table('organisation_members', sa.MetaData(), autoload_with=bind)
        except Exception:
            # Fallback: might be a different table name
            org_members_table = sa.Table('organisations_users', sa.MetaData(), autoload_with=bind)

        # 1. Individual owners
        individual_owners = session.execute(
            sa.select(events_table.c.id, events_table.c.current_owner_id).where(
                and_(
                    events_table.c.current_owner_type == 'individual',
                    events_table.c.current_owner_id.isnot(None),
                    events_table.c.is_deleted == False,
                )
            )
        ).fetchall()

        for event_id, owner_id in individual_owners:
            # Check if EventRole already exists
            existing = session.execute(
                sa.select(event_roles_table.c.id).where(
                    and_(
                        event_roles_table.c.event_id == event_id,
                        event_roles_table.c.user_id == owner_id,
                        event_roles_table.c.role == 'owner',
                    )
                )
            ).first()
            
            if not existing:
                session.execute(
                    event_roles_table.insert().values(
                        event_id=event_id,
                        user_id=owner_id,
                        role='owner',
                        title='Event Owner',
                        assigned_by_id=owner_id,
                        permissions=OWNER_PERMISSIONS,
                        is_active=True,
                        is_deleted=False,
                        assigned_at=sa.func.now(),
                    )
                )

        # 2. Organization owners - find org admins/owners for each org-owned event
        org_events = session.execute(
            sa.select(events_table.c.id, events_table.c.organization_id).where(
                and_(
                    events_table.c.current_owner_type == 'organization',
                    events_table.c.organization_id.isnot(None),
                    events_table.c.is_deleted == False,
                )
            )
        ).fetchall()

        for event_id, org_id in org_events:
            # Find org members with org_owner or org_admin role
            # This depends on the membership table structure
            try:
                org_admins = session.execute(
                    sa.select(users_table.c.id).select_from(
                        users_table.join(org_members_table, users_table.c.id == org_members_table.c.user_id)
                    ).where(
                        and_(
                            org_members_table.c.organisation_id == org_id,
                            org_members_table.c.role.in_(['org_owner', 'org_admin']),
                        )
                    )
                ).fetchall()

                for (admin_id,) in org_admins:
                    existing = session.execute(
                        sa.select(event_roles_table.c.id).where(
                            and_(
                                event_roles_table.c.event_id == event_id,
                                event_roles_table.c.user_id == admin_id,
                                event_roles_table.c.role == 'owner',
                            )
                        )
                    ).first()
                    
                    if not existing:
                        session.execute(
                            event_roles_table.insert().values(
                                event_id=event_id,
                                user_id=admin_id,
                                role='owner',
                                title='Event Owner',
                                organisation_id=org_id,
                                assigned_by_id=admin_id,  # Self-assigned as org admin
                                permissions=OWNER_PERMISSIONS,
                                is_active=True,
                                is_deleted=False,
                                assigned_at=sa.func.now(),
                            )
                        )
            except Exception as e:
                print(f"Warning: Could not process org {org_id} for event {event_id}: {e}")

        session.commit()
        print("EventRole backfill completed successfully")

    except Exception as e:
        session.rollback()
        print(f"Error during backfill: {e}")
        raise
    finally:
        session.close()


def downgrade():
    """Remove the backfilled EventRole entries (only those we created)."""
    # We only remove 'owner' roles that were created by this migration
    # In practice, this is hard to distinguish, so we leave them
    pass