"""
Admin API for wallet management, compliance, and regulatory oversight
Role-based access: regulators, aggregators, auditors, compliance officers
"""

from functools import wraps
from flask import Blueprint, request, jsonify, g
from flask_login import current_user, login_required
from datetime import datetime, timedelta

from app.extensions import db
from app.wallet.models.transaction import TransactionModel, TransactionStatus, TransactionType
from app.wallet.models.ledger import AccountModel, LedgerEntryModel
from app.wallet.models.audit import AuditLogModel
from app.wallet.models.fx import FXRateModel, FXTransactionModel
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
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
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
        "generated_at": datetime.utcnow().isoformat(),
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
        "checked_at": datetime.utcnow().isoformat()
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
        account.frozen_at = datetime.utcnow()
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
        "timestamp": datetime.utcnow().isoformat(),
    })


__all__ = ['admin_api_bp']
