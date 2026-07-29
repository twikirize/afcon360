"""
app/admin/owner/escrow_routes.py

Owner Escrow Account Management Routes
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app.admin.owner.decorators import owner_required
from app.extensions import db
from app.admin.owner.escrow_services import EscrowService, ESCROW_SERVICE_TYPES
from app.models.system_config import SystemConfig
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

escrow_bp = Blueprint('escrow', __name__)


def owner_login_required(f):
    return login_required(owner_required(f))


@escrow_bp.route('/escrow')
@owner_login_required
def escrow_index():
    """Escrow dashboard overview."""
    accounts = EscrowService.get_all_escrow_accounts()
    stats = EscrowService.get_service_stats()

    configs = SystemConfig.query.filter(SystemConfig.key.like('escrow_%')).all()
    settings = {c.key: c.value for c in configs}

    return render_template(
        'owner/escrow/index.html',
        accounts=accounts,
        stats=stats,
        service_types=ESCROW_SERVICE_TYPES,
        settings=settings
    )


@escrow_bp.route('/escrow/create', methods=['GET', 'POST'])
@owner_login_required
def escrow_create():
    """Create a new escrow account."""
    if request.method == 'GET':
        return render_template(
            'owner/escrow/create.html',
            service_types=ESCROW_SERVICE_TYPES
        )

    service_type = request.form.get('service_type')
    account_name = request.form.get('account_name', '').strip()
    description = request.form.get('description', '').strip()
    daily_limit = request.form.get('daily_limit', '1000000')
    monthly_limit = request.form.get('monthly_limit', '10000000')
    require_dual_auth = request.form.get('require_dual_auth') == 'on'

    if not service_type or service_type not in ESCROW_SERVICE_TYPES:
        flash('Please select a valid service type.', 'danger')
        return redirect(url_for('admin.owner.escrow_create'))

    success, account, error = EscrowService.create_escrow_account(
        service_type=service_type,
        created_by=current_user.id,
        account_name=account_name or None,
        description=description or None,
        daily_limit=Decimal(daily_limit) if daily_limit else None,
        monthly_limit=Decimal(monthly_limit) if monthly_limit else None,
        require_dual_auth=require_dual_auth
    )

    if success:
        flash(f'Escrow account created successfully: {account.account_number}', 'success')
        return redirect(url_for('admin.owner.escrow_detail', account_id=account.id))
    else:
        flash(f'Failed to create escrow account: {error}', 'danger')
        return redirect(url_for('admin.owner.escrow_create'))


@escrow_bp.route('/escrow/<uuid:account_id>')
@owner_login_required
def escrow_detail(account_id):
    """View escrow account details."""
    account = EscrowService.get_escrow_account(str(account_id))
    if not account:
        flash('Escrow account not found.', 'danger')
        return redirect(url_for('admin.owner.escrow_index'))

    balance = EscrowService.get_account_balance(str(account_id))
    transactions = EscrowService.get_account_transactions(str(account_id))

    service_info = {}
    if account.extra_data and account.extra_data.get('service_type'):
        service_info = ESCROW_SERVICE_TYPES.get(account.extra_data['service_type'], {})

    return render_template(
        'owner/escrow/detail.html',
        account=account,
        balance=balance,
        transactions=transactions,
        service_info=service_info
    )


@escrow_bp.route('/escrow/<uuid:account_id>/freeze', methods=['POST'])
@owner_login_required
def escrow_freeze(account_id):
    """Freeze an escrow account."""
    reason = request.form.get('reason', '').strip()
    if not reason:
        flash('Please provide a reason for freezing the account.', 'danger')
        return redirect(url_for('admin.owner.escrow_detail', account_id=account_id))

    success, message = EscrowService.freeze_account(
        account_id=str(account_id),
        reason=reason,
        frozen_by=current_user.id
    )

    if success:
        flash(f'Account frozen: {message}', 'warning')
    else:
        flash(f'Failed to freeze account: {message}', 'danger')

    return redirect(url_for('admin.owner.escrow_detail', account_id=account_id))


@escrow_bp.route('/escrow/<uuid:account_id>/unfreeze', methods=['POST'])
@owner_login_required
def escrow_unfreeze(account_id):
    """Unfreeze an escrow account."""
    success, message = EscrowService.unfreeze_account(
        account_id=str(account_id),
        unfrozen_by=current_user.id
    )

    if success:
        flash(f'Account unfrozen: {message}', 'success')
    else:
        flash(f'Failed to unfreeze account: {message}', 'danger')

    return redirect(url_for('admin.owner.escrow_detail', account_id=account_id))


@escrow_bp.route('/escrow/settings', methods=['GET', 'POST'])
@owner_login_required
def escrow_settings():
    """Configure escrow settings."""
    if request.method == 'POST':
        auto_release_days = request.form.get('auto_release_days', '2')
        min_balance_alert = request.form.get('min_balance_alert', '1000')
        require_dual_auth_default = request.form.get('require_dual_auth_default') == 'on'

        settings = {
            'escrow_auto_release_days': auto_release_days,
            'escrow_min_balance_alert': min_balance_alert,
            'escrow_require_dual_auth_default': 'true' if require_dual_auth_default else 'false'
        }

        for key, value in settings.items():
            config = SystemConfig.query.filter_by(key=key).first()
            if config:
                config.value = value
                config.updated_by = current_user.id
            else:
                config = SystemConfig(
                    key=key,
                    value=value,
                    description=f'Escrow system setting: {key}',
                    updated_by=current_user.id
                )
                db.session.add(config)

        db.session.commit()
        flash('Escrow settings updated successfully.', 'success')
        return redirect(url_for('admin.owner.escrow_settings'))

    configs = SystemConfig.query.filter(SystemConfig.key.like('escrow_%')).all()
    settings = {c.key: c.value for c in configs}

    return render_template(
        'owner/escrow/settings.html',
        settings=settings
    )


@escrow_bp.route('/escrow/transactions')
@owner_login_required
def escrow_transactions():
    """View all escrow transactions."""
    account_id = request.args.get('account_id')
    page = request.args.get('page', 1, type=int)
    per_page = 20

    from app.wallet.models.ledger import LedgerEntryModel

    query = LedgerEntryModel.query.filter_by(account_id=account_id) if account_id else LedgerEntryModel.query

    transactions = query.order_by(LedgerEntryModel.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    accounts = EscrowService.get_all_escrow_accounts()

    return render_template(
        'owner/escrow/transactions.html',
        transactions=transactions,
        accounts=accounts,
        selected_account_id=account_id
    )
