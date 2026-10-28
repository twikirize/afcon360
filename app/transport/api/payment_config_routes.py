"""
AFCON360 Transport - Payment Method Configuration API
Super admin/owner controlled payment method configuration with country-aware rules.
All writes are audited and require transport.settings permission.
"""
from flask import request
from flask_login import login_required
from flask_restful import Resource
from app.extensions import db
from app.auth.decorators import admin_required, require_super_admin, require_admin_or_owner
from app.transport.services.payment_config import (
    get_payment_config_service,
    DEFAULT_PAYMENT_METHODS,
)
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


# Permission check for transport settings
def _require_transport_settings_permission():
    """Check if current user has transport.settings permission"""
    from flask_login import current_user
    if not current_user.is_authenticated:
        return False
    if hasattr(current_user, "has_global_role"):
        return current_user.has_global_role("owner", "super_admin", "admin")
    return False


class PaymentMethodsConfigResource(Resource):
    """GET/PUT /api/transport/payment-methods/config

    GET: List all configured payment methods (admin sees all, public sees enabled only)
    PUT: Update payment method configuration (super admin/owner only)
    """

    @login_required
    def get(self):
        """Get payment methods configuration"""
        from flask_login import current_user
        is_admin = _require_transport_settings_permission()

        config_service = get_payment_config_service()
        methods = config_service.get_all_methods()

        # For non-admin, only return enabled methods
        if not is_admin:
            methods = [m for m in methods if m.enabled]

        return {
            "success": True,
            "data": {
                "methods": [m.to_dict() for m in methods],
                "total": len(methods),
            },
        }

    @require_super_admin
    def put(self):
        """Update payment method configuration (super admin/owner only)"""
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        if "methods" not in data:
            return {"success": False, "error": "methods array is required"}, 400

        try:
            config_service = get_payment_config_service()
            from flask_login import current_user

            result = config_service.update_configuration(
                methods=data["methods"],
                actor_user_id=current_user.id,
            )

            logger.info(f"Payment methods config updated by user {current_user.id}")
            return {
                "success": True,
                "data": result,
                "message": "Payment methods configuration updated successfully",
            }

        except ValueError as e:
            return {"success": False, "error": str(e)}, 400
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating payment methods config: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500


class PaymentMethodsDefaultsResource(Resource):
    """POST /api/transport/payment-methods/config/seed-defaults

    Seed default payment method configuration (super admin/owner only)
    """

    @require_super_admin
    def post(self):
        """Seed default payment methods configuration"""
        try:
            config_service = get_payment_config_service()
            from flask_login import current_user

            result = config_service.seed_defaults(actor_user_id=current_user.id)

            logger.info(f"Payment methods defaults seeded by user {current_user.id}")
            return {
                "success": True,
                "data": result,
                "message": "Default payment methods configuration seeded",
            }

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error seeding payment methods defaults: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500


class PaymentMethodsAvailableResource(Resource):
    """GET /api/transport/payment-methods/available

    Get payment methods available for the current user (country-aware)
    """

    @login_required
    def get(self):
        """Get available payment methods for current user"""
        from flask_login import current_user

        config_service = get_payment_config_service()
        methods = config_service.get_methods_for_country(
            country_code=None,  # Will be detected from user
            user_has_wallet=False,  # Will be detected from user
        )

        # Also get default method
        default_method = config_service.get_default_method()

        return {
            "success": True,
            "data": {
                "methods": [m.to_dict() for m in methods],
                "default_method": default_method.to_dict() if default_method else None,
                "total": len(methods),
            },
        }


class PaymentMethodDetailResource(Resource):
    """GET/PUT /api/transport/payment-methods/config/<method_code>

    Get or update a specific payment method configuration
    """

    @login_required
    def get(self, method_code):
        """Get a specific payment method configuration"""
        from flask_login import current_user
        is_admin = _require_transport_settings_permission()

        config_service = get_payment_config_service()
        methods = config_service.get_all_methods()

        method = next((m for m in methods if m.code == method_code), None)
        if not method:
            return {"success": False, "error": f"Payment method '{method_code}' not found"}, 404

        # Non-admin can only see enabled methods
        if not is_admin and not method.enabled:
            return {"success": False, "error": "Payment method not available"}, 404

        return {"success": True, "data": method.to_dict()}

    @require_super_admin
    def put(self, method_code):
        """Update a specific payment method"""
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        config_service = get_payment_config_service()
        methods = config_service.get_all_methods()

        # Find and update the method
        method_idx = next((i for i, m in enumerate(methods) if m.code == method_code), None)
        if method_idx is None:
            return {"success": False, "error": f"Payment method '{method_code}' not found"}, 404

        # Update allowed fields
        allowed_fields = ["enabled", "default", "label", "description", "countries", "metadata"]
        method = methods[method_idx]
        for field in allowed_fields:
            if field in data:
                setattr(method, field, data[field])

        # Save updated configuration
        try:
            from flask_login import current_user
            result = config_service.update_configuration(
                methods=[m.to_dict() for m in methods],
                actor_user_id=current_user.id,
            )
            return {"success": True, "data": result, "message": f"Payment method '{method_code}' updated"}
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating payment method {method_code}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500


class PaymentMethodToggleResource(Resource):
    """POST /api/transport/payment-methods/config/<method_code>/toggle

    Enable/disable a payment method quickly
    """

    @require_super_admin
    def post(self, method_code):
        """Toggle a payment method on/off"""
        data = request.get_json() or {}
        enabled = data.get("enabled", True)

        config_service = get_payment_config_service()
        methods = config_service.get_all_methods()

        method = next((m for m in methods if m.code == method_code), None)
        if not method:
            return {"success": False, "error": f"Payment method '{method_code}' not found"}, 404

        method.enabled = enabled

        try:
            from flask_login import current_user
            result = config_service.update_configuration(
                methods=[m.to_dict() for m in methods],
                actor_user_id=current_user.id,
            )
            return {"success": True, "data": result, "message": f"Payment method '{method_code}' {'enabled' if enabled else 'disabled'}"}
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error toggling payment method {method_code}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500