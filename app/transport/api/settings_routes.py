# app/transport/api/settings_routes.py
"""
AFCON360 Transport — Settings REST API
Admin-controlled feature flags and configuration.
All writes are audited. Sensitive settings are protected.
Cache is invalidated on every write.
"""
from flask import request
from flask_restful import Resource
from app.extensions import db, cache
from app.transport.models import TransportSetting
from app.admin.routes import admin_required
from app.transport.utils.helpers import paginate, filter_query, sort_query
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

SETTING_SORT_FIELDS = ["key", "category", "updated_at", "is_public", "is_advanced"]

# Settings that cannot be changed via the API (must be set via env/deploy)
PROTECTED_KEYS = {
    "environment",
    "data_encryption_enabled",
}


def _setting_or_404(setting_id):
    return TransportSetting.query.filter_by(
        id=setting_id, is_deleted=False
    ).first_or_404()


def _invalidate_cache(key):
    """Invalidate the cached value for a setting key."""
    try:
        cache.delete(f"transport:setting:{key}")
    except Exception:
        pass  # Cache miss is not fatal


# ===========================================================================
# Settings List
# ===========================================================================

class SettingsListResource(Resource):
    """GET /api/transport/settings  — list all settings (admin: all, public: public only)
       POST /api/transport/settings — create a new setting (admin only)
    """

    def get(self):
        """
        List settings.
        Non-admin callers only see settings where is_public=True.
        Admin callers see everything.
        """
        from flask_login import current_user
        is_admin = (
            current_user.is_authenticated
            and hasattr(current_user, "has_global_role")
            and current_user.has_global_role("admin")
        )

        query = TransportSetting.query.filter_by(is_deleted=False)

        if not is_admin:
            query = query.filter_by(is_public=True)

        filters = {
            "category":    request.args.get("category"),
            "subcategory": request.args.get("subcategory"),
            "data_type":   request.args.get("data_type"),
            "is_public":   request.args.get("is_public", type=bool),
            "is_advanced": request.args.get("is_advanced", type=bool),
        }
        query = filter_query(query, TransportSetting, filters)
        query = sort_query(query, TransportSetting, SETTING_SORT_FIELDS)
        result = paginate(query)

        serializer = "to_dict" if is_admin else "to_safe_dict"

        return {
            "success": True,
            "data": {
                "items": [getattr(s, serializer)() for s in result["items"]],
                "total":    result["total"],
                "page":     result["page"],
                "per_page": result["per_page"],
                "pages":    result["pages"],
            },
        }

    @admin_required
    def post(self):
        """Create a new transport setting"""
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        required = ["key", "value", "name", "category", "data_type"]
        missing = [f for f in required if f not in data]
        if missing:
            return {"success": False, "error": f"Missing fields: {missing}"}, 400

        if TransportSetting.query.filter_by(key=data["key"], is_deleted=False).first():
            return {"success": False, "error": f"Setting '{data['key']}' already exists"}, 409

        try:
            setting = TransportSetting(
                key=data["key"],
                value=data["value"],
                name=data["name"],
                category=data["category"],
                data_type=data["data_type"],
                description=data.get("description"),
                subcategory=data.get("subcategory"),
                default_value=data.get("default_value", data["value"]),
                is_public=data.get("is_public", False),
                is_advanced=data.get("is_advanced", False),
                requires_restart=data.get("requires_restart", False),
                allowed_values=data.get("allowed_values"),
                validation_rules=data.get("validation_rules"),
            )
            db.session.add(setting)
            db.session.commit()
            logger.info(f"Setting created: key={setting.key}")
            return {"success": True, "data": setting.to_dict()}, 201

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating setting: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500


# ===========================================================================
# Setting Detail (by ID)
# ===========================================================================

class SettingDetailResource(Resource):
    """GET/PUT/DELETE /api/transport/settings/<setting_id>"""

    def get(self, setting_id):
        """Get setting by ID"""
        setting = _setting_or_404(setting_id)
        return {"success": True, "data": setting.to_dict()}

    @admin_required
    def put(self, setting_id):
        """Update a setting value with full audit trail"""
        setting = _setting_or_404(setting_id)
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        # Block protected settings
        if setting.key in PROTECTED_KEYS:
            return {
                "success": False,
                "error": f"Setting '{setting.key}' is protected and cannot be changed via API. "
                         f"Set it via environment variables or deployment config.",
            }, 403

        if "value" not in data:
            return {"success": False, "error": "value is required"}, 400

        from flask_login import current_user
        old_value = setting.value
        new_value = data["value"]

        # Record in modification history
        history_entry = {
            "old_value": old_value,
            "new_value": new_value,
            "changed_at": datetime.now(timezone.utc).isoformat(),
            "changed_by": getattr(current_user, "id", None),
        }
        setting.modification_history = (setting.modification_history or []) + [history_entry]
        setting.value = new_value
        setting.last_modified_by = getattr(current_user, "id", None)

        # Update other meta if provided
        for field in ["name", "description", "is_public", "is_advanced"]:
            if field in data:
                setattr(setting, field, data[field])

        try:
            db.session.commit()
            _invalidate_cache(setting.key)
            logger.info(
                f"Setting updated: key={setting.key}, "
                f"old={old_value}, new={new_value}"
            )
            return {
                "success": True,
                "data": setting.to_dict(),
                "requires_restart": setting.requires_restart,
            }
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating setting {setting_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500

    @admin_required
    def delete(self, setting_id):
        """Soft delete a setting (only non-core settings)"""
        setting = _setting_or_404(setting_id)

        if setting.key in PROTECTED_KEYS:
            return {
                "success": False,
                "error": f"Cannot delete protected setting: {setting.key}"
            }, 403

        setting.is_deleted = True
        setting.deleted_at = datetime.now(timezone.utc)

        try:
            db.session.commit()
            _invalidate_cache(setting.key)
            logger.info(f"Setting deleted: key={setting.key}")
            return {"success": True, "message": f"Setting '{setting.key}' deleted"}
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting setting {setting_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500


# ===========================================================================
# Setting by Key
# ===========================================================================

class SettingByKeyResource(Resource):
    """GET/PUT /api/transport/settings/key/<key>"""

    def get(self, key):
        """
        Get a setting by its key.
        More ergonomic for frontend feature-flag checks.
        Returns the value directly for public settings.
        """
        setting = TransportSetting.query.filter_by(
            key=key, is_deleted=False
        ).first()

        if not setting:
            return {"success": False, "error": f"Setting '{key}' not found"}, 404

        from flask_login import current_user
        is_admin = (
            current_user.is_authenticated
            and hasattr(current_user, "has_global_role")
            and current_user.has_global_role("admin")
        )

        if not setting.is_public and not is_admin:
            return {"success": False, "error": "Access denied"}, 403

        return {
            "success": True,
            "data": {
                "key": setting.key,
                "value": setting.value,
                "data_type": setting.data_type,
                "category": setting.category,
                "description": setting.description,
            },
        }

    @admin_required
    def put(self, key):
        """Update a setting by key — shorthand for the detail PUT endpoint"""
        setting = TransportSetting.query.filter_by(
            key=key, is_deleted=False
        ).first()

        if not setting:
            return {"success": False, "error": f"Setting '{key}' not found"}, 404

        if key in PROTECTED_KEYS:
            return {
                "success": False,
                "error": f"Setting '{key}' is protected",
            }, 403

        data = request.get_json()
        if not data or "value" not in data:
            return {"success": False, "error": "value is required"}, 400

        from flask_login import current_user
        old_value = setting.value
        setting.value = data["value"]
        setting.last_modified_by = getattr(current_user, "id", None)
        setting.modification_history = (setting.modification_history or []) + [{
            "old_value": old_value,
            "new_value": data["value"],
            "changed_at": datetime.now(timezone.utc).isoformat(),
            "changed_by": getattr(current_user, "id", None),
        }]

        try:
            db.session.commit()
            _invalidate_cache(key)
            logger.info(f"Setting '{key}' updated via key endpoint: {old_value} → {data['value']}")
            return {
                "success": True,
                "data": {"key": key, "value": setting.value},
                "requires_restart": setting.requires_restart,
            }
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating setting by key '{key}': {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500
