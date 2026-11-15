            },
        }

# ===========================================================================
# SUPPLY-00 -- admin online override
# ===========================================================================

class DriverAdminOnlineOverrideResource(Resource):
    """POST /api/transport/drivers/<string:driver_code>/admin-online-override.

    The public driver code is resolved to the internal profile ID inside
    this resource. Internal database IDs are not part of the API contract.
    """

    @transport_admin_required
    def post(self, driver_code):
        from app.auth.helpers import has_global_role
        from app.transport.models import DriverProfile
        from app.transport.services.provider_service import get_provider_service
        from app.utils.exceptions import (
            NotFoundError as _NotFound,
            ValidationError as _Validation,
        )

        if not has_global_role(current_user, "owner", "super_admin", "admin", "transport_admin"):
            return {"success": False, "error": "not authorized"}, 403

        driver = DriverProfile.query.filter_by(
            driver_code=driver_code,
            is_deleted=False,
        ).first()
        if driver is None:
            return {"success": False, "error": "driver not found"}, 404

        data = request.get_json(silent=True) or {}
        raw_enabled = data.get("enabled")
        if raw_enabled is None:
            return {"success": False, "error": "enabled is required"}, 400

        # Safe boolean parsing
        try:
            enabled = parse_bool(str(raw_enabled))
        except ValueError as e:
            return {"success": False, "error": str(e)}, 400

        reason = (data.get("reason") or "").strip()[:200]

        try:
            result = get_provider_service().set_admin_online_override(
                driver_id=driver.id,
                enabled=enabled,
                actor_user_id=current_user.id,
                reason=reason,
            )
            response = dict(result) if isinstance(result, dict) else {"result": result}
            for private_key in ("driver_id", "user_id", "admin_user_id", "admin_online_override_by"):
                response.pop(private_key, None)

            data_payload = response.get("data")
            if isinstance(data_payload, dict):
                data_payload = dict(data_payload)
                for private_key in ("driver_id", "user_id", "admin_user_id", "admin_online_override_by"):
                    data_payload.pop(private_key, None)
                response["data"] = data_payload

            response["driver_code"] = driver_code
            return response, 200
        except _NotFound:
            return {"success": False, "error": "driver not found"}, 404
        except _Validation as e:
            return {"success": False, "error": str(e)}, 422
        except Exception as e:
            db.session.rollback()
            logger.error(
                f"admin override error for driver {driver_code}: {e}",
                exc_info=True,
            )
            return {"success": False, "error": "could not set override"}, 500
