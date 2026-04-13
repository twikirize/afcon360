from datetime import datetime, timedelta
from sqlalchemy import func
from app.extensions import db
from app.identity.models import User, UserRole
from app.identity.models.organisation import Organisation
from app.identity.models.roles_permission import Role
from app.admin.owner.models import OwnerAuditLog
from app.admin.owner.utils import get_system_health
from app.identity.services import load_user_roles
from app.utils.transactions import transactional
from app.profile.models import get_profile_by_user

def user_to_dict(user):
    """Convert User model to dictionary to prevent lazy loading issues"""
    if not user: return None
    return {
        'id': user.id,
        'user_id': user.user_id,
        'username': user.username,
        'email': user.email,
        'is_verified': user.is_verified,
        'is_active': user.is_active,
        'created_at': user.created_at
    }

@transactional("Load owner dashboard data")
def get_owner_dashboard_data(user_id: int):
    """
    Fetch all owner dashboard info, including platform stats,
    RBAC roles, and system health.
    This will roll back if any part fails and logs detailed errors.
    """
    # Load RBAC roles using the nested identity service call
    user_roles = load_user_roles(user_id)

    # Platform stats
    total_users = User.query.count()
    verified_users = User.query.filter_by(is_verified=True).count()
    active_users = User.query.filter_by(is_active=True).count()
    new_users_today = User.query.filter(
        User.created_at >= datetime.utcnow().date()
    ).count()

    # Organisation stats
    total_orgs = Organisation.query.count()
    active_orgs = Organisation.query.filter_by(is_active=True).count()
    pending_orgs = Organisation.query.filter_by(verification_status='pending').count()

    # Role stats
    total_roles = Role.query.count()

    # Get super admins
    super_admin_role = Role.query.filter_by(name='super_admin').first()
    super_admins_list = []
    if super_admin_role:
        super_admins_list = User.query.join(User.roles).filter(
            UserRole.role_id == super_admin_role.id
        ).all()

    super_admins = [user_to_dict(u) for u in super_admins_list]

    # Get regular users (not super admin, not owner)
    owner_role = Role.query.filter_by(name='owner').first()
    regular_users_list = []
    if super_admin_role and owner_role:
        regular_users_list = User.query.filter(
            ~User.roles.any(UserRole.role_id.in_([
                super_admin_role.id,
                owner_role.id
            ]))
        ).order_by(User.username).limit(20).all()

    regular_users = [user_to_dict(u) for u in regular_users_list]

    # Recent signups
    recent_users_list = User.query.order_by(User.created_at.desc()).limit(10).all()
    recent_users = [user_to_dict(u) for u in recent_users_list]

    # System health
    health = get_system_health()

    # Recent audit logs
    recent_logs = OwnerAuditLog.query.order_by(
        OwnerAuditLog.created_at.desc()
    ).limit(10).all()

    # Detach logs from session to avoid lazy loading issues
    logs_data = []
    for log in recent_logs:
        logs_data.append({
            'id': log.id,
            'action': log.action,
            'category': log.category,
            'status': log.status,
            'created_at': log.created_at,
            'details': log.details
        })

    # User growth chart data (last 7 days)
    dates = []
    counts = []
    for i in range(6, -1, -1):
        date = (datetime.utcnow() - timedelta(days=i)).date()
        count = User.query.filter(
            func.date(User.created_at) == date
        ).count()
        dates.append(date.strftime('%a'))
        counts.append(count)

    return {
        "user_roles": user_roles,
        "total_users": total_users,
        "verified_users": verified_users,
        "active_users": active_users,
        "new_users_today": new_users_today,
        "total_orgs": total_orgs,
        "active_orgs": active_orgs,
        "pending_orgs": pending_orgs,
        "total_roles": total_roles,
        "super_admins": super_admins,
        "regular_users": regular_users,
        "recent_users": recent_users,
        "recent_logs": logs_data,
        "health": health,
        "chart_labels": dates,
        "chart_data": counts
    }
