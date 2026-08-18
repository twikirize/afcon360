from datetime import date, timedelta
import pytest
from app.accommodation.services import host_service
from app.accommodation.services.host_service import HostService

class _FakeQuery:
    def __init__(self, scalar, is_blocked_query=False):
        self._scalar = scalar
        self._is_blocked_query = is_blocked_query
        self._has_booked_filter = False
        self._filters = []

    def filter(self, *args, **kwargs):
        for arg in args:
            self._filters.append(str(arg))
            if "reason" in str(arg) and "booked" in str(arg):
                self._has_booked_filter = True
        return self

    def scalar(self):
        print(f"FAKE QUERY: is_blocked={self._is_blocked_query}, has_booked_filter={self._has_booked_filter}, scalar={self._scalar}, filters={self._filters}")
        if self._is_blocked_query:
            if self._has_booked_filter:
                return 0
            return self._scalar
        return self._scalar


class _FakeSession:
    def __init__(self, total_units, booked, blocked, captures=None):
        self.total_units = total_units
        self._booked = booked
        self._blocked = blocked
        self._captures = captures if captures is not None else []

    def get(self, model, pk):
        class _RT:
            total_units = self.total_units
            is_deleted = False
        return _RT()

    def query(self, *args, **kwargs):
        text = str(args[0])
        print(f"FAKE SESSION QUERY: text={text[:100]}")
        if "rooms_requested" in text:
            return _FakeQuery(self._booked)
        if "units_blocked" in text:
            return _FakeQuery(self._blocked, is_blocked_query=True)
        return _FakeQuery(self._blocked)

    def add(self, obj):
        self._captures.append(obj)

    def commit(self):
        pass

    def flush(self):
        pass


class _FakeDB:
    def __init__(self, session):
        self.session = session


def test_debug(monkeypatch):
    db = _FakeDB(_FakeSession(10, 2, 2))
    monkeypatch.setattr(host_service, "db", db)
    
    CI = date(2026, 9, 1)
    CO = date(2026, 9, 3)
    avail = HostService.available_units(1, CI, CO)
    print(f"RESULT: {avail}")
