"""Regression tests for jurisdiction-local AML deadlines and daily periods."""
from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from flask import Flask

from app.compliance.aml_regulatory_service import _resolve_aml_period_date, compute_due_date


@pytest.fixture
def aml_app():
    app = Flask(__name__)
    app.config["AML_APPROVED_WORKING_CALENDARS"] = {
        "UG": {
            "approved": True,
            "source": "Approved Uganda regulator calendar fixture",
            "approved_by": "compliance-test-approver",
            "approved_at": "2026-01-01",
            "version": "UG-2026-v1",
            "valid_from": "2026-01-01",
            "valid_until": "2026-12-31",
            "working_weekdays": [0, 1, 2, 3, 4],
            "public_holidays": ["2026-11-09"],
        },
        "US": {
            "approved": True,
            "source": "Approved US regulator calendar fixture",
            "approved_by": "compliance-test-approver",
            "approved_at": "2026-01-01",
            "version": "US-2026-v1",
            "valid_from": "2026-01-01",
            "valid_until": "2026-12-31",
            "working_weekdays": [0, 1, 2, 3, 4],
            "public_holidays": ["2026-03-09"],
        },
    }
    return app


def test_due_date_uses_jurisdiction_local_date_and_approved_holiday(aml_app):
    jurisdiction = SimpleNamespace(country_code="UG", timezone_name="Africa/Kampala", str_sla_working_days=1)
    suspicion = datetime(2026, 11, 6, 22, 30, tzinfo=timezone.utc)
    with aml_app.app_context():
        due = compute_due_date(suspicion, 1, jurisdiction)
    # Kampala is already Saturday at this instant. Monday is a holiday,
    # so the next working day is Tuesday 01:30 EAT.
    assert due == datetime(2026, 11, 9, 22, 30, tzinfo=timezone.utc)


def test_due_date_preserves_local_wall_time_across_dst(aml_app):
    jurisdiction = SimpleNamespace(country_code="US", timezone_name="America/New_York", str_sla_working_days=1)
    suspicion = datetime(2026, 3, 6, 23, 30, tzinfo=timezone.utc)
    with aml_app.app_context():
        due = compute_due_date(suspicion, 1, jurisdiction)
    # March 9 is an approved holiday. The next working day is Tuesday,
    # after New York has changed from EST to EDT.
    assert due == datetime(2026, 3, 10, 22, 30, tzinfo=timezone.utc)


def test_due_date_fails_closed_without_approved_calendar():
    app = Flask(__name__)
    app.config["AML_APPROVED_WORKING_CALENDARS"] = {}
    jurisdiction = SimpleNamespace(country_code="UG", timezone_name="Africa/Kampala", str_sla_working_days=2)
    with app.app_context(), pytest.raises(ValueError, match="No approved working-day calendar"):
        compute_due_date(datetime(2026, 11, 6, 12, tzinfo=timezone.utc), 2, jurisdiction)


def test_due_date_rejects_naive_suspicion_timestamp(aml_app):
    jurisdiction = SimpleNamespace(country_code="UG", timezone_name="Africa/Kampala", str_sla_working_days=1)
    with aml_app.app_context(), pytest.raises(ValueError, match="timezone-aware"):
        compute_due_date(datetime(2026, 11, 6, 12), 1, jurisdiction)


def test_aware_detection_datetime_is_converted_before_date_is_taken():
    instant = datetime(2026, 11, 7, 23, 30, tzinfo=timezone.utc)
    assert _resolve_aml_period_date(instant, ZoneInfo("Africa/Kampala")).isoformat() == "2026-11-08"


def test_naive_detection_datetime_is_rejected():
    with pytest.raises(ValueError, match="timezone offset"):
        _resolve_aml_period_date(datetime(2026, 11, 7, 23, 30), ZoneInfo("Africa/Kampala"))



def test_due_date_fails_when_approved_calendar_does_not_cover_deadline(aml_app):
    jurisdiction = SimpleNamespace(
        country_code="UG",
        timezone_name="Africa/Kampala",
        str_sla_working_days=2,
    )
    with aml_app.app_context():
        calendar = dict(aml_app.config["AML_APPROVED_WORKING_CALENDARS"]["UG"])
        calendar["valid_until"] = "2026-11-07"
        with pytest.raises(ValueError, match="does not cover"):
            compute_due_date(
                datetime(2026, 11, 6, 12, tzinfo=timezone.utc),
                2,
                jurisdiction,
                approved_calendar=calendar,
            )
