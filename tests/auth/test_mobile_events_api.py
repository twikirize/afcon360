from types import SimpleNamespace


def _authenticated_mobile_user(monkeypatch, user):
    from app.auth import mobile_api

    monkeypatch.setattr(
        mobile_api,
        "require_mobile_context",
        lambda expected_client=None: ({"user": user}, None),
    )


def test_native_events_list_is_bearer_authenticated_and_server_filtered(client, monkeypatch):
    from app.events.native_event_service import NativeEventService

    user = SimpleNamespace(id=901, public_id="native-event-user-901")
    _authenticated_mobile_user(monkeypatch, user)
    captured = {}

    def fake_list(**kwargs):
        captured.update(kwargs)
        return {"items": [{"public_id": "event-public-1", "name": "AFCON Fan Fest"}], "limit": 10, "offset": 0, "has_more": False}

    monkeypatch.setattr(NativeEventService, "list_events", fake_list)
    response = client.get(
        "/api/mobile/v1/events?q=AFCON&city=Kampala&category=sports&limit=10",
        headers={"Authorization": "Bearer native-events-test-token"},
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["items"][0]["public_id"] == "event-public-1"
    assert captured["query"] == "AFCON"
    assert captured["city"] == "Kampala"
    assert captured["category"] == "sports"
    assert captured["limit"] == 10


def test_native_event_detail_uses_public_id_and_returns_ticket_availability(client, monkeypatch):
    from app.events.native_event_service import NativeEventService

    user = SimpleNamespace(id=902, public_id="native-event-user-902")
    _authenticated_mobile_user(monkeypatch, user)
    captured = {}

    def fake_detail(public_id):
        captured["public_id"] = public_id
        return {
            "public_id": public_id,
            "name": "AFCON Fan Fest",
            "ticket_availability": [{"ticket_token": "signed-choice", "name": "Free Entry", "price": "0.00", "is_available_now": True}],
        }

    monkeypatch.setattr(NativeEventService, "get_event", fake_detail)
    response = client.get(
        "/api/mobile/v1/events/event-public-902",
        headers={"Authorization": "Bearer native-events-test-token"},
    )

    assert response.status_code == 200
    assert captured["public_id"] == "event-public-902"
    assert response.get_json()["data"]["ticket_availability"][0]["ticket_token"] == "signed-choice"


def test_native_free_ticket_registration_uses_bearer_user_and_signed_ticket(client, monkeypatch):
    from app.events.native_event_service import NativeEventService

    user = SimpleNamespace(id=903, public_id="native-event-user-903")
    _authenticated_mobile_user(monkeypatch, user)
    captured = {}

    def fake_register(owner, **kwargs):
        captured["owner"] = owner
        captured.update(kwargs)
        return {
            "registration_reference": "ER-AFCONFEST-0000903",
            "ticket_number": "TKT-AFCONFEST-0000903",
            "qr_code": "data:image/png;base64,AA==",
            "status": "confirmed",
            "payment_status": "free",
        }

    monkeypatch.setattr(NativeEventService, "register_free_ticket", fake_register)
    response = client.post(
        "/api/mobile/v1/events/event-public-903/registrations",
        json={"ticket_token": "signed-free-ticket-903"},
        headers={"Authorization": "Bearer native-events-test-token"},
    )

    assert response.status_code == 201
    assert captured["owner"] is user
    assert captured["event_public_id"] == "event-public-903"
    assert captured["ticket_token"] == "signed-free-ticket-903"
    assert response.get_json()["data"]["payment_status"] == "free"


def test_native_event_registration_rejects_missing_ticket_selection(client, monkeypatch):
    user = SimpleNamespace(id=904, public_id="native-event-user-904")
    _authenticated_mobile_user(monkeypatch, user)
    response = client.post(
        "/api/mobile/v1/events/event-public-904/registrations",
        json={},
        headers={"Authorization": "Bearer native-events-test-token"},
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "ticket_selection_required"


def test_native_event_paid_ticket_is_not_misrepresented_as_purchased(client, monkeypatch):
    from app.events.native_event_service import NativeEventError, NativeEventService

    user = SimpleNamespace(id=905, public_id="native-event-user-905")
    _authenticated_mobile_user(monkeypatch, user)

    def reject_paid(*args, **kwargs):
        raise NativeEventError(
            "paid_ticket_checkout_unavailable",
            "Native paid-ticket checkout is being completed; no Wallet debit has been made.",
            409,
        )

    monkeypatch.setattr(NativeEventService, "register_free_ticket", reject_paid)
    response = client.post(
        "/api/mobile/v1/events/event-public-905/registrations",
        json={"ticket_token": "signed-paid-ticket-905"},
        headers={"Authorization": "Bearer native-events-test-token"},
    )
    assert response.status_code == 409
    assert response.get_json()["code"] == "paid_ticket_checkout_unavailable"
    assert "no Wallet debit has been made" in response.get_json()["message"]


def test_native_event_ticket_history_is_scoped_to_bearer_user(client, monkeypatch):
    from app.events.native_event_service import NativeEventService

    user = SimpleNamespace(id=906, public_id="native-event-user-906")
    _authenticated_mobile_user(monkeypatch, user)
    captured = {}

    def fake_list(owner, **kwargs):
        captured["owner"] = owner
        captured.update(kwargs)
        return {"items": [{"registration_reference": "ER-EVENT-906"}], "limit": 5, "offset": 10}

    monkeypatch.setattr(NativeEventService, "list_registrations", fake_list)
    response = client.get(
        "/api/mobile/v1/events/registrations?limit=5&offset=10",
        headers={"Authorization": "Bearer native-events-test-token"},
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["items"][0]["registration_reference"] == "ER-EVENT-906"
    assert captured["owner"] is user
    assert captured["limit"] == 5
    assert captured["offset"] == 10


def test_native_event_ticket_detail_hides_other_users_registrations(client, monkeypatch):
    from app.events.native_event_service import NativeEventError, NativeEventService

    user = SimpleNamespace(id=907, public_id="native-event-user-907")
    _authenticated_mobile_user(monkeypatch, user)

    def not_found(*args, **kwargs):
        raise NativeEventError("registration_not_found", "Ticket registration not found.", 404)

    monkeypatch.setattr(NativeEventService, "get_registration", not_found)
    response = client.get(
        "/api/mobile/v1/events/registrations/ER-OTHER-USER-0001",
        headers={"Authorization": "Bearer native-events-test-token"},
    )
    assert response.status_code == 404
    assert response.get_json()["code"] == "registration_not_found"
