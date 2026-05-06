"""
Admin API for wallet management, compliance, and regulatory oversight
Role-based access: regulators, aggregators, auditors, compliance officers
"""

from functools import wraps
from flask import Blueprint, request, jsonify, g
from flask_login import current_user, login_required
from datetime import datetime, timezone, timedelta

from app.extensions import db
from app.wallet.models.transaction import TransactionModel, TransactionStatus, TransactionType
from app.wallet.models.ledger import AccountModel, LedgerEntryModel
from app.wallet.models.audit import AuditLogModel
from app.wallet.models.fx import FXRateModel, FXTransactionModel
from app.wallet.models.payout import PayoutRequest
from app.wallet.services.wallet_service import WalletService
from app.wallet.services.compliance_engine import check_transaction, get_country_requirements
from app.wallet.services.regulatory_reporting import generate_str_report, generate_ctr_report
from app.wallet.services.payment_gateway import get_provider_status

admin_api_bp = Blueprint('wallet_admin_api', __name__, url_prefix='/api/admin/wallet')


def require_any_role(*roles):
    """Decorator to require any of the specified roles"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({"error": "Authentication required"}), 401
            
            if not any(current_user.has_role(role) for role in roles):
                return jsonify({"error": f"Requires one of roles: {roles}"}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ============== REGULATOR APIs ==============

@admin_api_bp.route('/regulator/dashboard', methods=['GET'])
@login_required
@require_any_role('regulator', 'central_bank', 'financial_authority')
def regulator_dashboard():
    """Regulator dashboard with system-wide statistics"""
    
    # Total system volume
    total_volume = db.session.query(
        db.func.sum(LedgerEntryModel.amount)
    ).filter(LedgerEntryModel.entry_type == 'CREDIT').scalar() or 0
    
    # Active users
    active_users = db.session.query(
        db.func.count(db.distinct(AccountModel.user_id))
    ).scalar()
    
    # Transaction statistics (last 30 days)
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    
    txn_stats = db.session.query(
        db.func.count(TransactionModel.id).label('total'),
        db.func.sum(TransactionModel.amount).label('volume'),
        db.func.avg(TransactionModel.amount).label('average'),
    ).filter(
        TransactionModel.created_at >= thirty_days_ago
    ).first()
    
    # Currency breakdown
    currency_stats = db.session.query(
        TransactionModel.currency,
        db.func.count(TransactionModel.id).label('count'),
        db.func.sum(TransactionModel.amount).label('volume')
    ).filter(
        TransactionModel.created_at >= thirty_days_ago,
        TransactionModel.status == TransactionStatus.COMPLETED
    ).group_by(TransactionModel.currency).all()
    
    frozen_accounts = db.session.query(
        db.func.count(AccountModel.id)
    ).filter(AccountModel.is_frozen == True).scalar()
    
    return jsonify({
        "system_overview": {
            "total_volume_all_time": float(total_volume),
            "active_users": active_users,
            "frozen_accounts": frozen_accounts
        },
        "last_30_days": {
            "total_transactions": txn_stats.total or 0,
            "total_volume": float(txn_stats.volume or 0),
            "average_transaction": float(txn_stats.average or 0),
        },
        "currency_breakdown": [
            {
                "currency": curr,
                "transactions": count,
                "volume": float(volume)
            }
            for curr, count, volume in currency_stats
        ]
    })


@admin_api_bp.route('/regulator/transactions', methods=['GET'])
@login_required
@require_any_role('regulator', 'central_bank', 'financial_authority')
def regulator_transaction_search():
    """Search all transactions (regulator view)"""
    
    user_id = request.args.get('user_id', type=int)
    min_amount = request.args.get('min_amount', type=float)
    max_amount = request.args.get('max_amount', type=float)
    currency = request.args.get('currency')
    
    query = TransactionModel.query
    
    if user_id:
        query = query.filter(TransactionModel.user_id == user_id)
    if min_amount:
        query = query.filter(TransactionModel.amount >= min_amount)
    if max_amount:
        query = query.filter(TransactionModel.amount <= max_amount)
    if currency:
        query = query.filter(TransactionModel.currency == currency)
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    pagination = query.order_by(TransactionModel.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        "transactions": [
            {
                "id": str(tx.id),
                "user_id": tx.user_id,
                "type": tx.tx_type.value,
                "status": tx.status.value,
                "amount": float(tx.amount),
                "currency": tx.currency,
            }
            for tx in pagination.items
        ],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": pagination.total,
            "pages": pagination.pages
        }
    })


@admin_api_bp.route('/regulator/reports/str', methods=['POST'])
@login_required
@require_any_role('regulator', 'compliance_officer', 'financial_authority')
def generate_str():
    """Generate Suspicious Transaction Report"""
    data = request.get_json()
    country_code = data.get('country_code', 'NG')
    days = data.get('days', 7)
    
    report = generate_str_report(country_code, days)
    
    return jsonify({
        "report_type": "STR",
        "country": country_code,
        "period_days": days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data": report
    })


# ============== AUDITOR APIs ==============

@admin_api_bp.route('/auditor/reconciliation', methods=['GET'])
@login_required
@require_any_role('auditor', 'regulator')
def auditor_reconciliation():
    """Reconciliation report - verify all debits equal credits"""
    
    totals = db.session.query(
        LedgerEntryModel.entry_type,
        db.func.sum(LedgerEntryModel.amount).label('total'),
        db.func.count(LedgerEntryModel.id).label('count')
    ).group_by(LedgerEntryModel.entry_type).all()
    
    debit_total = sum(t.total for t in totals if t.entry_type.value == 'DEBIT') or 0
    credit_total = sum(t.total for t in totals if t.entry_type.value == 'CREDIT') or 0
    
    is_balanced = abs(float(debit_total) - float(credit_total)) < 0.01
    
    return jsonify({
        "reconciliation_status": "balanced" if is_balanced else "imbalance_detected",
        "total_debits": float(debit_total),
        "total_credits": float(credit_total),
        "difference": float(debit_total) - float(credit_total),
        "checked_at": datetime.now(timezone.utc).isoformat()
    })


# ============== COMPLIANCE APIs ==============

@admin_api_bp.route('/compliance/freeze-account', methods=['POST'])
@login_required
@require_any_role('compliance_officer', 'admin', 'super_admin')
def compliance_freeze_account():
    """Freeze account for compliance reasons"""
    data = request.get_json()
    account_id = data.get('account_id')
    reason = data.get('reason')
    
    if not account_id or not reason:
        return jsonify({"error": "account_id and reason required"}), 400
    
    try:
        account = AccountModel.query.get(account_id)
        if not account:
            return jsonify({"error": "Account not found"}), 404
        
        account.is_frozen = True
        account.frozen_reason = reason
        account.frozen_at = datetime.now(timezone.utc)
        account.frozen_by = current_user.id
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": f"Account {account_id} frozen"
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# ============== SYSTEM ADMIN APIs ==============

@admin_api_bp.route('/system/payment-providers', methods=['GET'])
@login_required
@require_any_role('admin', 'super_admin', 'owner')
def system_payment_providers():
    """Get payment provider status"""
    status = get_provider_status()
    
    return jsonify({
        "payment_providers": status,
        "configured_count": sum(1 for v in status.values() if v),
        "total_providers": len(status)
    })


@admin_api_bp.route('/system/health', methods=['GET'])
def system_health():
    """Public health check endpoint"""
    
    try:
        db.session.execute('SELECT 1')
        db_healthy = True
    except:
        db_healthy = False
    
    return jsonify({
        "status": "healthy" if db_healthy else "unhealthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ============== ADMIN PAYOUT APIs ==============

@admin_api_bp.route('/payouts', methods=['GET'])
@login_required
@require_any_role('admin', 'super_admin', 'compliance_officer')
def admin_list_payouts():
    """List all payout requests (admin view)."""
    status = request.args.get('status')
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)

    query = PayoutRequest.query.filter(PayoutRequest.is_deleted == False)
    if status:
        query = query.filter(PayoutRequest.status == status)

    total = query.count()
    payouts = query.order_by(PayoutRequest.created_at.desc()).limit(limit).offset(offset).all()

    return jsonify({
        "status": "success",
        "data": [
            {
                "id": p.id,
                "request_ref": p.request_ref,
                "agent_id": p.agent_id,
                "amount": float(p.amount),
                "currency": p.currency,
                "method": p.payment_method,
                "status": p.status,
                "requested_at": p.created_at.isoformat() if p.created_at else None,
                "approved_by": p.approved_by,
                "approved_at": p.approved_at.isoformat() if p.approved_at else None,
                "paid_by": p.paid_by,
                "paid_at": p.paid_at.isoformat() if p.paid_at else None,
                "notes": p.notes,
            }
            for p in payouts
        ],
        "pagination": {
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    })


@admin_api_bp.route('/payouts/<int:req_id>/process', methods=['POST'])
@login_required
@require_any_role('admin', 'super_admin', 'compliance_officer')
def admin_process_payout(req_id):
    """Approve, reject, or mark paid a payout request."""
    data = request.get_json() or {}
    action = data.get('action') or request.form.get('action')
    notes = data.get('notes') or request.form.get('notes', '')

    if action not in ('approve', 'reject', 'mark_paid'):
        return jsonify({"error": "action must be one of: approve, reject, mark_paid"}), 400

    payout = PayoutRequest.query.get(req_id)
    if not payout or payout.is_deleted:
        return jsonify({"error": "Payout request not found"}), 404

    try:
        if action == 'approve':
            if payout.status != 'pending':
                return jsonify({"error": f"Cannot approve payout with status: {payout.status}"}), 400
            payout.status = 'approved'
            payout.approved_by = current_user.id
            payout.approved_at = datetime.now(timezone.utc)
            payout.notes = (payout.notes or '') + f"\n[Approved by admin {current_user.id}] {notes}"

        elif action == 'reject':
            if payout.status not in ('pending', 'approved'):
                return jsonify({"error": f"Cannot reject payout with status: {payout.status}"}), 400
            payout.status = 'rejected'
            payout.rejection_reason = notes
            payout.notes = (payout.notes or '') + f"\n[Rejected by admin {current_user.id}] {notes}"

        elif action == 'mark_paid':
            if payout.status != 'approved':
                return jsonify({"error": f"Cannot mark as paid with status: {payout.status}"}), 400
            payout.status = 'paid'
            payout.paid_by = current_user.id
            payout.paid_at = datetime.now(timezone.utc)
            payout.notes = (payout.notes or '') + f"\n[Marked paid by admin {current_user.id}] {notes}"

        db.session.commit()
        return jsonify({
            "status": "success",
            "message": f"Payout {action}d successfully",
            "payout": {
                "id": payout.id,
                "request_ref": payout.request_ref,
                "status": payout.status,
            }
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Admin payout process error: {e}")
        return jsonify({"error": str(e)}), 500


# ============== ADMIN WALLET APIs ==============

@admin_api_bp.route('/wallets', methods=['GET'])
@login_required
@require_any_role('admin', 'super_admin', 'auditor', 'regulator')
def list_wallets():
    """List all wallets with basic info."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    search = request.args.get('search', '')

    query = AccountModel.query
    if search:
        query = query.filter(
            db.or_(
                AccountModel.user_id.ilike(f"%{search}%"),
            )
        )

    pagination = query.order_by(AccountModel.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        "status": "success",
        "data": [
            {
                "id": str(a.id),
                "user_id": a.user_id,
                "currency": a.currency,
                "is_frozen": a.is_frozen,
                "frozen_reason": a.frozen_reason,
                "frozen_at": a.frozen_at.isoformat() if a.frozen_at else None,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "updated_at": a.updated_at.isoformat() if a.updated_at else None,
            }
            for a in pagination.items
        ],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": pagination.total,
            "pages": pagination.pages,
        }
    })


__all__ = ['admin_api_bp']
