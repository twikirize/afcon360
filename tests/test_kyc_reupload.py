"""Tests for targeted KYC/KYB document re-upload requests."""

import pytest
from flask import Flask

from app.kyc.reupload import (
    clear_individual_reupload_request,
    clear_organisation_reupload_request,
    get_individual_reupload_request,
    get_organisation_reupload_requests,
    load_reupload_token,
    make_reupload_token,
    set_individual_reupload_request,
    set_organisation_reupload_request,
)


def test_individual_request_round_trip_and_clear():
    notes = set_individual_reupload_request(
        "existing compliance note",
        document_key="document",
        reason="The PDF is too dark to read.",
        requested_by=7,
    )

    request = get_individual_reupload_request(notes)
    assert request["document_key"] == "document"
    assert request["reason"] == "The PDF is too dark to read."
    assert request["requested_by"] == 7

    cleared = clear_individual_reupload_request(notes)
    assert get_individual_reupload_request(cleared) is None
    assert "existing compliance note" in cleared


def test_organisation_requests_support_multiple_document_targets():
    notes = set_organisation_reupload_request(
        None,
        document_id=11,
        document_type="tin_certificate",
        reason="The certificate is cropped.",
        requested_by=4,
    )
    notes = set_organisation_reupload_request(
        notes,
        document_id=12,
        document_type="trading_license",
        reason="Please provide a clearer scan.",
        requested_by=4,
    )

    requests = get_organisation_reupload_requests(notes)
    assert requests["11"]["document_type"] == "tin_certificate"
    assert requests["12"]["reason"] == "Please provide a clearer scan."

    cleared = clear_organisation_reupload_request(notes, document_id=11)
    remaining = get_organisation_reupload_requests(cleared)
    assert "11" not in remaining
    assert "12" in remaining


def test_reupload_token_is_bound_to_the_current_user():
    app = Flask(__name__)
    app.secret_key = "test-secret"

    with app.app_context():
        token = make_reupload_token(
            kind="individual",
            entity_id=19,
            owner_public_id="user-a",
            document_key="selfie",
        )

        payload = load_reupload_token(token, "user-a")
        assert payload["entity_id"] == 19
        assert payload["document_key"] == "selfie"

        with pytest.raises(ValueError):
            load_reupload_token(token, "user-b")


def test_invalid_reupload_document_key_is_rejected():
    with pytest.raises(ValueError):
        set_individual_reupload_request(
            None,
            document_key="passport_number",
            reason="Not a valid target.",
            requested_by=1,
        )