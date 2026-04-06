"""
app/wallet/api/audit_api.py
API endpoints for audit log queries.
Access restricted to auditor, compliance_officer, super_admin, owner roles.
"""

from flask import Blueprint, request, jsonify, current_app, Response
from flask_login import login_required, current_user
from datetime import datetime
from decimal import Decimal

from app.auth.policy import can
from app.wallet.services.audit_query_service import AuditQueryService
from app.wallet.exceptions import WalletError

audit_bp = Blueprint('audit_api', __name__, url_prefix='/api/admin/audit')


def require_audit_access(required_permission: str = "audit.view"):
    """Decorator to check audit access permission."""

    def decorator(f):
        from functools import wraps
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not can(current_user, required_permission):
                # Check for specific roles as fallback
                user_roles = [getattr(r.role, 'name', '') for r in getattr(current_user, "roles", []) if
                              hasattr(r, "role")]
                allowed_roles = ["auditor", "compliance_officer", "super_admin", "owner"]
                if not any(role in allowed_roles for role in user_roles):
                    return jsonify({
                        "status": "error",
                        "code": "UNAUTHORIZED",
                        "message": f"Audit access requires {required_permission} permission"
                    }), 403
            return f(*args, **kwargs)

        return decorated_function

    return decorator


# ============================================================================
# FINANCIAL AUDIT ENDPOINTS
# ============================================================================

@audit_bp.route('/financial', methods=['GET'])
@login_required
@require_audit_access("audit.view")
def get_financial_logs():
    """
    Query financial audit logs.

    GET /api/admin/audit/financial?user_id=123&status=completed&page=1&per_page=50
    """
    try:
        user_id = request.args.get('user_id', type=int)
        transaction_type = request.args.get('transaction_type')
        status = request.args.get('status')
        aml_flagged = request.args.get('aml_flagged')
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        min_amount = request.args.get('min_amount')
        max_amount = request.args.get('max_amount')
        currency = request.args.get('currency')
        payment_provider = request.args.get('payment_provider')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        sort_by = request.args.get('sort_by', 'created_at')
        sort_order = request.args.get('sort_order', 'desc')

        if aml_flagged is not None:
            aml_flagged = aml_flagged.lower() == 'true'

        start_date = None
        end_date = None
        if start_date_str:
            start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
        if end_date_str:
            end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))

        min_amount_dec = Decimal(min_amount) if min_amount else None
        max_amount_dec = Decimal(max_amount) if max_amount else None

        service = AuditQueryService()
        result = service.query_financial_logs(
            user_id=user_id,
            transaction_type=transaction_type,
            status=status,
            aml_flagged=aml_flagged,
            start_date=start_date,
            end_date=end_date,
            min_amount=min_amount_dec,
            max_amount=max_amount_dec,
            currency=currency,
            payment_provider=payment_provider,
            page=page,
            per_page=min(per_page, 500),
            sort_by=sort_by,
            sort_order=sort_order
        )

        return jsonify({"status": "success", "data": result})

    except Exception as e:
        current_app.logger.error(f"Error querying financial logs: {e}")
        return jsonify({"status": "error", "code": "INTERNAL_ERROR", "message": str(e)}), 500


# ============================================================================
# SECURITY EVENT ENDPOINTS
# ============================================================================

@audit_bp.route('/security', methods=['GET'])
@login_required
@require_audit_access("audit.view")
def get_security_events():
    """
    Query security event logs.

    GET /api/admin/audit/security?severity=CRITICAL&page=1
    """
    try:
        user_id = request.args.get('user_id', type=int)
        event_type = request.args.get('event_type')
        severity = request.args.get('severity')
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)

        start_date = None
        end_date = None
        if start_date_str:
            start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
        if end_date_str:
            end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))

        service = AuditQueryService()
        result = service.query_security_events(
            user_id=user_id,
            event_type=event_type,
            severity=severity,
            start_date=start_date,
            end_date=end_date,
            page=page,
            per_page=min(per_page, 500)
        )

        return jsonify({"status": "success", "data": result})

    except Exception as e:
        current_app.logger.error(f"Error querying security events: {e}")
        return jsonify({"status": "error", "code": "INTERNAL_ERROR", "message": str(e)}), 500


# ============================================================================
# API LOG ENDPOINTS
# ============================================================================

@audit_bp.route('/api', methods=['GET'])
@login_required
@require_audit_access("audit.view")
def get_api_logs():
    """
    Query API call logs.

    GET /api/admin/audit/api?service_name=flutterwave&page=1
    """
    try:
        service_name = request.args.get('service_name')
        status = request.args.get('status')
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)

        start_date = None
        end_date = None
        if start_date_str:
            start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
        if end_date_str:
            end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))

        service = AuditQueryService()
        result = service.query_api_logs(
            service_name=service_name,
            status=status,
            start_date=start_date,
            end_date=end_date,
            page=page,
            per_page=min(per_page, 500)
        )

        return jsonify({"status": "success", "data": result})

    except Exception as e:
        current_app.logger.error(f"Error querying API logs: {e}")
        return jsonify({"status": "error", "code": "INTERNAL_ERROR", "message": str(e)}), 500


# ============================================================================
# DATA ACCESS LOG ENDPOINTS (GDPR)
# ============================================================================

@audit_bp.route('/data-access', methods=['GET'])
@login_required
@require_audit_access("audit.view")
def get_data_access_logs():
    """
    Query data access logs for GDPR compliance.

    GET /api/admin/audit/data-access?user_id=123&page=1
    """
    try:
        user_id = request.args.get('user_id', type=int)
        accessed_by = request.args.get('accessed_by', type=int)
        data_category = request.args.get('data_category')
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)

        start_date = None
        end_date = None
        if start_date_str:
            start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
        if end_date_str:
            end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))

        service = AuditQueryService()
        result = service.query_data_access_logs(
            user_id=user_id,
            accessed_by=accessed_by,
            data_category=data_category,
            start_date=start_date,
            end_date=end_date,
            page=page,
            per_page=min(per_page, 500)
        )

        return jsonify({"status": "success", "data": result})

    except Exception as e:
        current_app.logger.error(f"Error querying data access logs: {e}")
        return jsonify({"status": "error", "code": "INTERNAL_ERROR", "message": str(e)}), 500


# ============================================================================
# AML REVIEW ENDPOINTS
# ============================================================================

@audit_bp.route('/aml', methods=['GET'])
@login_required
@require_audit_access("aml.view")
def get_aml_transactions():
    """
    Get AML flagged transactions.

    GET /api/admin/audit/aml?requires_review=true&page=1
    """
    try:
        requires_review = request.args.get('requires_review', 'true')
        requires_review = requires_review.lower() == 'true'
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)

        service = AuditQueryService()
        result = service.get_aml_flagged_transactions(
            requires_review=requires_review,
            page=page,
            per_page=min(per_page, 500)
        )

        return jsonify({"status": "success", "data": result})

    except Exception as e:
        current_app.logger.error(f"Error getting AML transactions: {e}")
        return jsonify({"status": "error", "code": "INTERNAL_ERROR", "message": str(e)}), 500


@audit_bp.route('/aml/<int:transaction_id>/review', methods=['POST'])
@login_required
@require_audit_access("aml.review")
def review_aml_transaction(transaction_id):
    """
    Review an AML flagged transaction.

    POST /api/admin/audit/aml/123/review
    Body: {"approved": true, "notes": "Legitimate transaction"}
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "status": "error",
                "code": "INVALID_REQUEST",
                "message": "Request body is required"
            }), 400

        approved = data.get('approved', False)
        notes = data.get('notes', '')

        service = AuditQueryService()
        service.review_aml_flag(
            transaction_id=transaction_id,
            reviewer_id=current_user.id,
            approved=approved,
            notes=notes
        )

        return jsonify({
            "status": "success",
            "message": f"AML flag {'approved' if approved else 'rejected'} successfully"
        })

    except ValueError as e:
        return jsonify({"status": "error", "code": "NOT_FOUND", "message": str(e)}), 404
    except Exception as e:
        current_app.logger.error(f"Error reviewing AML transaction: {e}")
        return jsonify({"status": "error", "code": "INTERNAL_ERROR", "message": str(e)}), 500


# ============================================================================
# EXPORT ENDPOINT
# ============================================================================

@audit_bp.route('/export', methods=['GET'])
@login_required
@require_audit_access("audit.export")
def export_audit_data():
    """
    Export audit data to JSON or CSV.

    GET /api/admin/audit/export?type=financial&format=json&start_date=2024-01-01
    """
    try:
        log_type = request.args.get('type', 'financial')
        format_type = request.args.get('format', 'json')

        # Build filters from query params
        filters = {}
        if request.args.get('user_id'):
            filters['user_id'] = int(request.args.get('user_id'))
        if request.args.get('start_date'):
            filters['start_date'] = datetime.fromisoformat(request.args.get('start_date').replace('Z', '+00:00'))
        if request.args.get('end_date'):
            filters['end_date'] = datetime.fromisoformat(request.args.get('end_date').replace('Z', '+00:00'))
        if request.args.get('status'):
            filters['status'] = request.args.get('status')
        if request.args.get('transaction_type'):
            filters['transaction_type'] = request.args.get('transaction_type')

        service = AuditQueryService()
        export_data = service.export_audit_data(log_type, format_type, **filters)

        content_type = 'application/json' if format_type == 'json' else 'text/csv'
        filename = f"audit_{log_type}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.{format_type}"

        return Response(
            export_data,
            mimetype=content_type,
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )

    except Exception as e:
        current_app.logger.error(f"Error exporting audit data: {e}")
        return jsonify({"status": "error", "code": "INTERNAL_ERROR", "message": str(e)}), 500