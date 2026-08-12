"""Regression tests for user-facing KYC upload validation failures."""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock

from flask import Flask, get_flashed_messages

from app.kyc import routes as kyc_routes
from app.kyc.routes import kyc_bp, verify_upload


def test_disallowed_document_type_redirects_with_validation_message(monkeypatch):
    """A rejected file type must not turn the upload form into a 500 response."""
    test_app = Flask(__name__)
    test_app.secret_key = "test-secret"
    test_app.register_blueprint(kyc_bp)

    fake_user = SimpleNamespace(id=1, public_id="user-public-id")
    query = MagicMock()
    query.filter_by.return_value.order_by.return_value.all.return_value = []
    monkeypatch.setattr(kyc_routes.KycRecord, "query", query)
    monkeypatch.setattr(kyc_routes, "current_user", fake_user)
    monkeypatch.setattr(kyc_routes, "_get_user_organisations", lambda: [])
    monkeypatch.setattr(kyc_routes, "is_acting_as_organization", lambda: False)
    monkeypatch.setattr(
        kyc_routes,
        "_save_uploaded_file",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("File type 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' is not allowed for kyc.")
        ),
    )

    handler = verify_upload
    while hasattr(handler, "__wrapped__"):
        handler = handler.__wrapped__

    with test_app.test_request_context(
        "/kyc/verify/upload",
        method="POST",
        data={
            "kyc_type": "individual",
            "id_type": "national_id",
            "id_number": "CM1234567890",
            "kyc_doc_file": (
                BytesIO(b"not-a-supported-document"),
                "identity.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        },
        content_type="multipart/form-data",
    ):
        response = handler()
        messages = get_flashed_messages(with_categories=True)

    assert response.status_code == 302
    assert any("not allowed" in message for _, message in messages)