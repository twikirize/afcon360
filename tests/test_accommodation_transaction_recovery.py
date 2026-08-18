"""Regression checks for accommodation read-route transaction recovery."""

from pathlib import Path


def test_guest_detail_resets_failed_transaction_before_property_lookup():
    source = Path("app/accommodation/routes.py").read_text(encoding="utf-8")
    route_start = source.index("def guest_detail(identifier):")
    route_body = source[route_start:source.index("\n\n@accommodation_bp.route", route_start + 1)]

    assert route_body.index("db.session.rollback()") < route_body.index(
        "property_data = search_service.get_property_by_identifier(identifier)"
    )
    assert "Room-type lookup failed" in route_body


def test_guest_detail_recovers_from_property_serialization_failure_at_route_boundary():
    source = Path("app/accommodation/routes.py").read_text(encoding="utf-8")
    route_start = source.index("def guest_detail(identifier):")
    route_body = source[route_start:source.index("\n\n@accommodation_bp.route", route_start + 1)]

    serialization_start = route_body.index("property_data = search_service.get_property_by_identifier(identifier)")
    media_start = route_body.index("gallery_media = [")
    room_start = route_body.index("# Resolve the default room type")
    serialization_section = route_body[serialization_start:media_start]
    media_section = route_body[media_start:room_start]

    assert "logger.exception(\"Property serialization failed" in serialization_section
    assert "db.session.rollback()" in serialization_section
    assert "logger.exception(\"Property media serialization failed" in media_section
    assert "db.session.rollback()" in media_section
    assert "gallery_media = []" in media_section


def test_global_error_handler_rolls_back_before_audit_write():
    source = Path("app/__init__.py").read_text(encoding="utf-8")
    handler_start = source.index("def handle_exception(e):")
    handler_body = source[handler_start:source.index("\n    # ------------------------------------------------------------------", handler_start)]

    assert handler_body.index("db.session.rollback()") < handler_body.index("AuditLog.log(")