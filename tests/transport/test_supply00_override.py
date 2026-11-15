        staticmethod(lambda key, default=False: True),
    )

    uid = uuid.uuid4().hex[:8]
    user_id = _create_user(app, f"drv_T8_{uid}")
    from app.identity.models.roles_permission import get_or_create_role
    from app.identity.models.user import UserRole
    with app.app_context():
        owner_role = get_or_create_role('owner', level=1)
        db.session.add(UserRole(user_id=user_id, role_id=owner_role.id))
        db.session.commit()

    from flask_login import login_user
    with app.test_request_context():
        with app.app_context():
            login_user(db.session.get(User, user_id))
            result = get_provider_service().register_driver(
                user_id, _driver_data(uid)
            )
        assert result['success'] is True
        drv_id = result['data']['driver_id']
    with app.app_context():
        drv = db.session.get(DriverProfile, drv_id)
        assert drv.is_online is False
        assert drv.is_available is True
        assert drv.compliance_status == ComplianceStatus.APPROVED

    # See T7: clear participations before deleting the User (check constraint).
    with app.app_context():
        from app.identity.models.provider_participation import ProviderParticipation
        ProviderParticipation.query.filter_by(user_id=user_id).delete(
            synchronize_session=False
        )
        db.session.commit()

    _delete(app, (DriverProfile, drv_id), (User, user_id))


# ============================================================================
# T9: admin enables override -> (T, F) + metadata
# ============================================================================
def test_T9_admin_enables_override_populates_metadata(app, admin_client):
    user_id, drv_id, veh_id, hist_id = _make_matchable_driver(app, "drv_T9")
    with app.app_context():
        drv = db.session.get(DriverProfile, drv_id)
        drv.is_online = False
        drv.is_available = False
        drv.compliance_status = ComplianceStatus.PENDING_REVIEW
        db.session.commit()

    resp = admin_client.post(
        _admin_override_url(app, drv_id),
        json={"enabled": True, "reason": "test T9"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["driver_code"] == _driver_code(app, drv_id)
    assert "driver_id" not in body
    assert "driver_id" not in body["data"]
    assert "admin_online_override_by" not in body["data"]
    assert body["data"]["is_available"] is True
    assert body["data"]["is_online"] is False

    with app.app_context():
        drv = db.session.get(DriverProfile, drv_id)
        assert drv.is_available is True
        ov = (drv.driver_metadata or {}).get("admin_online_override")
        assert ov and ov["enabled"] is True
        assert ov["reason"] == "test T9"
        assert ov["by"] is not None
        assert ov["at"] is not None

    _delete(
        app,
        (DriverVehicleHistory, hist_id),
        (DriverProfile, drv_id),
        (Vehicle, veh_id),
        (User, user_id),
    )

