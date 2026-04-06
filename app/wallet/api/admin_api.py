"""
app/wallet/api/admin_api.py
Admin API endpoints for wallet management.
"""

from flask import Blueprint, request, jsonify, current_app, render_template
from flask_login import login_required, current_user
from decimal import Decimal
from datetime import datetime

from app.auth.policy import can
from app.wallet.middleware.kill_switch import wallet_enabled, require_wallet_enabled
from app.wallet.services.wallet_service import WalletService
from app.wallet.services.wallet_admin_service import WalletAdminService
from app.wallet.exceptions import (
    WalletNotFoundError,
    WalletFrozenError,
    WalletError
)

admin_wallet_bp = Blueprint('admin_wallet_api', __name__, url_prefix='/api/admin/wallet')


def require_admin():
    """Decorator to check admin permission."""
    def decorator(f):
        from functools import wraps
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not can(current_user, 'system.manage'):
                return jsonify({
                    "status": "error",
                    "code": "UNAUTHORIZED",
                    "message": "Admin access required"
                }), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ============================================================================
# EXISTING ENDPOINTS (KEPT AS IS)
# ============================================================================

@admin_wallet_bp.route('/toggle', methods=['POST'])
@login_required
@require_admin()
def toggle_wallet():
    """
    Toggle wallet module ON/OFF.

    POST /api/admin/wallet/toggle
    Body: {"enabled": true} or {"enabled": false}

    This updates the runtime config. To make permanent, also update .env file.
    """
    data = request.get_json()
    enabled = data.get('enabled')

    if enabled is None:
        return jsonify({
            "status": "error",
            "code": "VALIDATION_ERROR",
            "message": "enabled field required (true/false)"
        }), 400

    # Update runtime config
    current_app.config["MODULE_FLAGS"]["wallet"] = enabled

    # Log the change
    current_app.logger.warning(
        f"Wallet module {'ENABLED' if enabled else 'DISABLED'} by admin user {current_user.id}"
    )

    return jsonify({
        "status": "success",
        "data": {
            "wallet_enabled": enabled,
            "message": f"Wallet module {'enabled' if enabled else 'disabled'} successfully",
            "persistent_note": "To make permanent, update ENABLE_WALLET in .env file"
        }
    })


@admin_wallet_bp.route('/status', methods=['GET'])
@login_required
def wallet_status():
    """
    Get current wallet module status.

    GET /api/admin/wallet/status

    Accessible to all authenticated users (not just admins) for UI display.
    """
    enabled = wallet_enabled()

    return jsonify({
        "status": "success",
        "data": {
            "wallet_enabled": enabled,
            "timestamp": datetime.utcnow().isoformat()
        }
    })


@admin_wallet_bp.route('/users/<int:user_id>/balance', methods=['GET'])
@login_required
@require_admin()
def get_user_balance(user_id):
    """
    Get balance for any user (admin only).

    GET /api/admin/wallet/users/123/balance
    """
    try:
        service = WalletService()
        balance = service.get_balance(user_id)

        return jsonify({
            "status": "success",
            "data": {
                "user_id": user_id,
                "balance": balance
            }
        })

    except Exception as e:
        current_app.logger.error(f"Admin balance error for user {user_id}: {e}")
        return jsonify({
            "status": "error",
            "code": "INTERNAL_ERROR",
            "message": "Unable to retrieve balance"
        }), 500


@admin_wallet_bp.route('/users/<int:user_id>/transactions', methods=['GET'])
@login_required
@require_admin()
def get_user_transactions(user_id):
    """
    Get transaction history for any user (admin only).

    GET /api/admin/wallet/users/123/transactions?limit=50&offset=0
    """
    try:
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        transaction_type = request.args.get('type')

        limit = min(limit, 100)

        service = WalletService()
        result = service.get_transaction_history(
            user_id=user_id,
            limit=limit,
            offset=offset,
            transaction_type=transaction_type
        )

        return jsonify({
            "status": "success",
            "data": {
                "user_id": user_id,
                **result
            }
        })

    except Exception as e:
        current_app.logger.error(f"Admin transactions error for user {user_id}: {e}")
        return jsonify({
            "status": "error",
            "code": "INTERNAL_ERROR",
            "message": "Unable to retrieve transactions"
        }), 500


# ============================================================================
# PHASE 2: NEW ADMIN WALLET MANAGEMENT ENDPOINTS
# ============================================================================

@admin_wallet_bp.route('/wallets', methods=['GET'])
@login_required
@require_admin()
def list_wallets():
    """
    List all wallets with pagination and filters.

    GET /api/admin/wallet/wallets?page=1&per_page=50&search=john&status=active&frozen=true
    """
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        search = request.args.get('search', None)
        status = request.args.get('status', None)
        verified = request.args.get('verified', None)
        frozen = request.args.get('frozen', None)
        sort_by = request.args.get('sort_by', 'created_at')
        sort_order = request.args.get('sort_order', 'desc')

        # Convert string params to boolean
        if verified is not None:
            verified = verified.lower() == 'true'
        if frozen is not None:
            frozen = frozen.lower() == 'true'

        # Limit per_page
        per_page = min(per_page, 100)

        admin_service = WalletAdminService()
        result = admin_service.list_all_wallets(
            page=page,
            per_page=per_page,
            search=search,
            status=status,
            verified=verified,
            frozen=frozen,
            sort_by=sort_by,
            sort_order=sort_order
        )

        return jsonify({
            "status": "success",
            "data": result
        })

    except Exception as e:
        current_app.logger.error(f"Error listing wallets: {e}")
        return jsonify({
            "status": "error",
            "code": "INTERNAL_ERROR",
            "message": str(e)
        }), 500


@admin_wallet_bp.route('/wallets/<int:user_id>', methods=['GET'])
@login_required
@require_admin()
def get_wallet_details(user_id):
    """
    Get detailed wallet information for a specific user.

    GET /api/admin/wallet/wallets/123
    """
    try:
        admin_service = WalletAdminService()
        result = admin_service.get_wallet_details(user_id)

        return jsonify({
            "status": "success",
            "data": result
        })

    except WalletNotFoundError as e:
        return jsonify({
            "status": "error",
            "code": "NOT_FOUND",
            "message": str(e)
        }), 404
    except Exception as e:
        current_app.logger.error(f"Error getting wallet details for user {user_id}: {e}")
        return jsonify({
            "status": "error",
            "code": "INTERNAL_ERROR",
            "message": str(e)
        }), 500


@admin_wallet_bp.route('/wallets/<int:user_id>/freeze', methods=['POST'])
@login_required
@require_admin()
def freeze_wallet(user_id):
    """
    Freeze a wallet, preventing all transactions.

    POST /api/admin/wallet/wallets/123/freeze
    Body: {"reason": "Suspicious activity", "notes": "Optional notes"}
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "status": "error",
                "code": "INVALID_REQUEST",
                "message": "Request body is required"
            }), 400

        reason = data.get('reason', '').strip()
        if not reason:
            return jsonify({
                "status": "error",
                "code": "VALIDATION_ERROR",
                "message": "Reason is required to freeze a wallet"
            }), 400

        notes = data.get('notes', '')

        admin_service = WalletAdminService()
        admin_service.freeze_wallet(
            user_id=user_id,
            admin_user_id=current_user.id,
            reason=reason,
            notes=notes
        )

        return jsonify({
            "status": "success",
            "message": f"Wallet for user {user_id} has been frozen",
            "data": {
                "user_id": user_id,
                "reason": reason,
                "frozen_at": datetime.utcnow().isoformat()
            }
        })

    except WalletNotFoundError as e:
        return jsonify({
            "status": "error",
            "code": "NOT_FOUND",
            "message": str(e)
        }), 404
    except WalletFrozenError as e:
        return jsonify({
            "status": "error",
            "code": "ALREADY_FROZEN",
            "message": str(e)
        }), 409
    except Exception as e:
        current_app.logger.error(f"Error freezing wallet for user {user_id}: {e}")
        return jsonify({
            "status": "error",
            "code": "INTERNAL_ERROR",
            "message": str(e)
        }), 500


@admin_wallet_bp.route('/wallets/<int:user_id>/unfreeze', methods=['POST'])
@login_required
@require_admin()
def unfreeze_wallet(user_id):
    """
    Unfreeze a wallet, restoring transaction capabilities.

    POST /api/admin/wallet/wallets/123/unfreeze
    Body: {"reason": "Issue resolved"}
    """
    try:
        data = request.get_json() or {}
        reason = data.get('reason', '')

        admin_service = WalletAdminService()
        admin_service.unfreeze_wallet(
            user_id=user_id,
            admin_user_id=current_user.id,
            reason=reason
        )

        return jsonify({
            "status": "success",
            "message": f"Wallet for user {user_id} has been unfrozen"
        })

    except WalletNotFoundError as e:
        return jsonify({
            "status": "error",
            "code": "NOT_FOUND",
            "message": str(e)
        }), 404
    except WalletError as e:
        return jsonify({
            "status": "error",
            "code": "NOT_FROZEN",
            "message": str(e)
        }), 409
    except Exception as e:
        current_app.logger.error(f"Error unfreezing wallet for user {user_id}: {e}")
        return jsonify({
            "status": "error",
            "code": "INTERNAL_ERROR",
            "message": str(e)
        }), 500


@admin_wallet_bp.route('/wallets/<int:user_id>/adjust', methods=['POST'])
@login_required
@require_admin()
def adjust_balance(user_id):
    """
    Manually adjust wallet balance.

    POST /api/admin/wallet/wallets/123/adjust
    Body: {
        "amount": "100.00",
        "currency": "USD",
        "reason": "Refund for overcharge",
        "notes": "Customer was charged twice"
    }

    Note: Positive amount adds funds, negative amount deducts funds.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "status": "error",
                "code": "INVALID_REQUEST",
                "message": "Request body is required"
            }), 400

        amount_str = data.get('amount')
        currency = data.get('currency', '').upper()
        reason = data.get('reason', '').strip()
        notes = data.get('notes', '')

        if not amount_str:
            return jsonify({
                "status": "error",
                "code": "VALIDATION_ERROR",
                "message": "Amount is required"
            }), 400

        if not reason:
            return jsonify({
                "status": "error",
                "code": "VALIDATION_ERROR",
                "message": "Reason is required for balance adjustment"
            }), 400

        try:
            amount = Decimal(str(amount_str))
        except:
            return jsonify({
                "status": "error",
                "code": "VALIDATION_ERROR",
                "message": "Invalid amount format"
            }), 400

        admin_service = WalletAdminService()
        result = admin_service.adjust_balance(
            user_id=user_id,
            admin_user_id=current_user.id,
            amount=amount,
            currency=currency,
            reason=reason,
            notes=notes
        )

        return jsonify({
            "status": "success",
            "message": f"Balance adjusted by {amount} {currency}",
            "data": result
        })

    except WalletNotFoundError as e:
        return jsonify({
            "status": "error",
            "code": "NOT_FOUND",
            "message": str(e)
        }), 404
    except WalletFrozenError as e:
        return jsonify({
            "status": "error",
            "code": "WALLET_FROZEN",
            "message": str(e)
        }), 403
    except ValueError as e:
        return jsonify({
            "status": "error",
            "code": "VALIDATION_ERROR",
            "message": str(e)
        }), 400
    except Exception as e:
        current_app.logger.error(f"Error adjusting balance for user {user_id}: {e}")
        return jsonify({
            "status": "error",
            "code": "INTERNAL_ERROR",
            "message": str(e)
        }), 500


@admin_wallet_bp.route('/stats/detailed', methods=['GET'])
@login_required
@require_admin()
def get_detailed_wallet_stats():
    """
    Get comprehensive wallet statistics for admin dashboard.

    GET /api/admin/wallet/stats/detailed
    """
    try:
        admin_service = WalletAdminService()
        result = admin_service.get_wallet_stats()

        return jsonify({
            "status": "success",
            "data": result
        })

    except Exception as e:
        current_app.logger.error(f"Error getting wallet stats: {e}")
        return jsonify({
            "status": "error",
            "code": "INTERNAL_ERROR",
            "message": str(e)
        }), 500


@admin_wallet_bp.route('/control', methods=['GET'])
@login_required
@require_admin()
def wallet_control():
    """Render wallet control page (kill switch)."""
    return render_template('admin/wallet_control.html')


# ============================================================================
# EXISTING STATS ENDPOINT (UPDATED TO USE NEW SERVICE)
# ============================================================================

@admin_wallet_bp.route('/stats', methods=['GET'])
@login_required
@require_admin()
def get_wallet_stats():
    """
    Get wallet system statistics (admin only).

    GET /api/admin/wallet/stats

    Note: For detailed statistics, use /stats/detailed
    """
    try:
        from app.wallet.models import Wallet as WalletModel, Transaction as TransactionModel
        from datetime import datetime, timedelta

        today = datetime.utcnow().date()
        today_start = datetime(today.year, today.month, today.day)

        # Total wallets
        total_wallets = WalletModel.query.count()

        # Total balances
        from app.extensions import db
        result = db.session.query(
            db.func.sum(WalletModel.balance_home).label('total_home'),
            db.func.sum(WalletModel.balance_local).label('total_local')
        ).first()

        total_home = result.total_home or 0
        total_local = result.total_local or 0

        # Active wallets today (with transactions)
        active_wallets = db.session.query(
            TransactionModel.wallet_id
        ).filter(
            TransactionModel.created_at >= today_start
        ).distinct().count()

        # Transactions today
        transactions_today = TransactionModel.query.filter(
            TransactionModel.created_at >= today_start
        ).count()

        # Volume today
        volume_result = db.session.query(
            db.func.sum(TransactionModel.amount).filter(
                TransactionModel.type.in_(['deposit', 'send'])
            ).label('volume_home')
        ).filter(
            TransactionModel.created_at >= today_start,
            TransactionModel.currency == 'USD'
        ).first()

        return jsonify({
            "status": "success",
            "data": {
                "total_wallets": total_wallets,
                "total_balance_home": str(total_home),
                "total_balance_local": str(total_local),
                "active_wallets_today": active_wallets,
                "transactions_today": transactions_today,
                "volume_today_home": str(volume_result.volume_home or 0),
                "timestamp": datetime.utcnow().isoformat()
            }
        })

    except Exception as e:
        current_app.logger.error(f"Wallet stats error: {e}")
        return jsonify({
            "status": "error",
            "code": "INTERNAL_ERROR",
            "message": "Unable to retrieve statistics"
        }), 500