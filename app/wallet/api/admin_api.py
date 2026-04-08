"""
app/wallet/api/admin_api.py
Admin API endpoints for wallet management.
Uses UUID-based user identification for external exposure.
"""

from flask import Blueprint, request, jsonify, current_app, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from decimal import Decimal
from datetime import datetime

from app.auth.policy import can
from app.wallet.middleware.kill_switch import wallet_enabled, require_wallet_enabled
from app.wallet.services.wallet_service import WalletService
from app.wallet.services.wallet_admin_service import WalletAdminService
from app.wallet.services.payout_service import PayoutService
from app.wallet.exceptions import (
    WalletNotFoundError,
    WalletFrozenError,
    WalletError
)
from app.identity.models.user import User

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
# CORE ENDPOINTS
# ============================================================================

@admin_wallet_bp.route('/toggle', methods=['POST'])
@login_required
@require_admin()
def toggle_wallet():
    """Toggle wallet module ON/OFF."""
    data = request.get_json()
    enabled = data.get('enabled')

    if enabled is None:
        return jsonify({
            "status": "error",
            "code": "VALIDATION_ERROR",
            "message": "enabled field required (true/false)"
        }), 400

    current_app.config["MODULE_FLAGS"]["wallet"] = enabled
    current_app.logger.warning(
        f"Wallet module {'ENABLED' if enabled else 'DISABLED'} by admin user {current_user.user_id}"
    )

    return jsonify({
        "status": "success",
        "data": {
            "wallet_enabled": enabled,
            "message": f"Wallet module {'enabled' if enabled else 'disabled'} successfully"
        }
    })


@admin_wallet_bp.route('/status', methods=['GET'])
@login_required
def wallet_status():
    """Get current wallet module status."""
    enabled = wallet_enabled()
    return jsonify({
        "status": "success",
        "data": {
            "wallet_enabled": enabled,
            "timestamp": datetime.utcnow().isoformat()
        }
    })


@admin_wallet_bp.route('/users/<string:user_id>/balance', methods=['GET'])
@login_required
@require_admin()
def get_user_balance(user_id):
    """Get balance for any user by UUID."""
    try:
        user = User.query.filter_by(user_id=user_id).first_or_404()
        service = WalletService()
        balance = service.get_balance(user.id) # Internal logic uses BigInt id

        return jsonify({
            "status": "success",
            "data": {
                "user_id": user.user_id,
                "balance": balance
            }
        })
    except Exception as e:
        current_app.logger.error(f"Admin balance error for user {user_id}: {e}")
        return jsonify({"status": "error", "message": "Unable to retrieve balance"}), 500


@admin_wallet_bp.route('/users/<string:user_id>/transactions', methods=['GET'])
@login_required
@require_admin()
def get_user_transactions(user_id):
    """Get transaction history for any user by UUID."""
    try:
        user = User.query.filter_by(user_id=user_id).first_or_404()
        limit = min(request.args.get('limit', 50, type=int), 100)
        offset = request.args.get('offset', 0, type=int)
        transaction_type = request.args.get('type')

        service = WalletService()
        result = service.get_transaction_history(
            user_id=user.id, # Internal logic uses BigInt id
            limit=limit,
            offset=offset,
            transaction_type=transaction_type
        )

        return jsonify({
            "status": "success",
            "data": {
                "user_id": user.user_id,
                **result
            }
        })
    except Exception as e:
        current_app.logger.error(f"Admin transactions error for user {user_id}: {e}")
        return jsonify({"status": "error", "message": "Unable to retrieve transactions"}), 500


# ============================================================================
# WALLET MANAGEMENT
# ============================================================================

@admin_wallet_bp.route('/wallets', methods=['GET'])
@login_required
@require_admin()
def list_wallets():
    """List all wallets with pagination and filters."""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 50, type=int), 100)
        search = request.args.get('search')
        status = request.args.get('status')
        verified = request.args.get('verified', '').lower() == 'true' if 'verified' in request.args else None
        frozen = request.args.get('frozen', '').lower() == 'true' if 'frozen' in request.args else None

        admin_service = WalletAdminService()
        result = admin_service.list_all_wallets(
            page=page, per_page=per_page, search=search,
            status=status, verified=verified, frozen=frozen
        )

        return jsonify({"status": "success", "data": result})
    except Exception as e:
        current_app.logger.error(f"Error listing wallets: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_wallet_bp.route('/wallets/<string:user_id>', methods=['GET'])
@login_required
@require_admin()
def get_wallet_details(user_id):
    """Get detailed wallet information by User UUID."""
    try:
        user = User.query.filter_by(user_id=user_id).first_or_404()
        admin_service = WalletAdminService()
        result = admin_service.get_wallet_details(user.id) # Internal BigInt

        return jsonify({"status": "success", "data": result})
    except WalletNotFoundError as e:
        return jsonify({"status": "error", "message": str(e)}), 404
    except Exception as e:
        current_app.logger.error(f"Error getting wallet details for user {user_id}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_wallet_bp.route('/wallets/<string:user_id>/freeze', methods=['POST'])
@login_required
@require_admin()
def freeze_wallet(user_id):
    """Freeze a wallet using User UUID."""
    try:
        user = User.query.filter_by(user_id=user_id).first_or_404()
        data = request.get_json() or {}
        reason = data.get('reason', '').strip()
        if not reason:
            return jsonify({"status": "error", "message": "Reason required"}), 400

        admin_service = WalletAdminService()
        admin_service.freeze_wallet(
            user_id=user.id,
            admin_user_id=current_user.id,
            reason=reason,
            notes=data.get('notes', '')
        )

        return jsonify({
            "status": "success",
            "message": f"Wallet for user {user_id} frozen",
            "data": {"user_id": user.user_id, "reason": reason}
        })
    except WalletNotFoundError as e:
        return jsonify({"status": "error", "message": str(e)}), 404
    except Exception as e:
        current_app.logger.error(f"Error freezing wallet for user {user_id}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_wallet_bp.route('/wallets/<string:user_id>/unfreeze', methods=['POST'])
@login_required
@require_admin()
def unfreeze_wallet(user_id):
    """Unfreeze a wallet using User UUID."""
    try:
        user = User.query.filter_by(user_id=user_id).first_or_404()
        data = request.get_json() or {}
        admin_service = WalletAdminService()
        admin_service.unfreeze_wallet(
            user_id=user.id,
            admin_user_id=current_user.id,
            reason=data.get('reason', '')
        )
        return jsonify({"status": "success", "message": f"Wallet for user {user_id} unfrozen"})
    except WalletNotFoundError as e:
        return jsonify({"status": "error", "message": str(e)}), 404
    except Exception as e:
        current_app.logger.error(f"Error unfreezing wallet for user {user_id}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_wallet_bp.route('/wallets/<string:user_id>/adjust', methods=['POST'])
@login_required
@require_admin()
def adjust_balance(user_id):
    """Manually adjust wallet balance using User UUID."""
    try:
        user = User.query.filter_by(user_id=user_id).first_or_404()
        data = request.get_json() or {}
        amount = Decimal(str(data.get('amount', '0')))
        currency = data.get('currency', 'USD').upper()
        reason = data.get('reason', '').strip()

        if not reason:
            return jsonify({"status": "error", "message": "Reason required"}), 400

        admin_service = WalletAdminService()
        result = admin_service.adjust_balance(
            user_id=user.id,
            admin_user_id=current_user.id,
            amount=amount,
            currency=currency,
            reason=reason,
            notes=data.get('notes', '')
        )

        return jsonify({"status": "success", "data": result})
    except WalletNotFoundError as e:
        return jsonify({"status": "error", "message": str(e)}), 404
    except Exception as e:
        current_app.logger.error(f"Error adjusting balance for user {user_id}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_wallet_bp.route('/stats/detailed', methods=['GET'])
@login_required
@require_admin()
def get_detailed_wallet_stats():
    """Get comprehensive system statistics."""
    try:
        admin_service = WalletAdminService()
        return jsonify({"status": "success", "data": admin_service.get_wallet_stats()})
    except Exception as e:
        current_app.logger.error(f"Error getting wallet stats: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_wallet_bp.route('/control', methods=['GET'])
@login_required
@require_admin()
def wallet_control():
    """Render wallet control page."""
    return render_template('admin/wallet_control.html')


# ============================================================================
# PAYOUT MANAGEMENT
# ============================================================================

@admin_wallet_bp.route('/payouts', methods=['GET'], endpoint="admin_list_payouts")
@login_required
@require_admin()
def admin_list_payouts():
    """List all payout requests for admin review."""
    status = request.args.get('status')
    limit = request.args.get('limit', 50, type=int)

    payout_service = PayoutService()
    requests = payout_service.list_requests(status=status, limit=limit)

    return render_template('admin_payouts.html', requests=requests)


@admin_wallet_bp.route('/payouts/<int:req_id>/process', methods=['POST'], endpoint="admin_process_payout")
@login_required
@require_admin()
def admin_process_payout(req_id):
    """Process a payout request (approve/reject/mark_paid)."""
    action = request.form.get('action')
    notes = request.form.get('notes', '')

    payout_service = PayoutService()

    try:
        if action == 'approve':
            payout_service.approve_request(req_id, current_user.id, notes)
            flash(f"Payout request #{req_id} approved.", "success")
        elif action == 'reject':
            reason = notes or "Rejected by admin"
            payout_service.reject_request(req_id, current_user.id, reason)
            flash(f"Payout request #{req_id} rejected.", "warning")
        elif action == 'mark_paid':
            payout_service.mark_as_paid(req_id, current_user.id, notes=notes)
            flash(f"Payout request #{req_id} marked as paid.", "success")
        else:
            flash("Invalid action specified.", "danger")
    except Exception as e:
        flash(f"Error processing payout: {str(e)}", "danger")

    return redirect(url_for('admin_wallet_api.admin_list_payouts'))
