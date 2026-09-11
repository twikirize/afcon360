# app/core/serializers.py
"""
Minimal generic model serializer for AFCON360.

Provides the `ModelSerializer` contract referenced by
`app.transport.models.TransportBase.to_dict`:

    ModelSerializer.serialize(obj, include=None, exclude=None) -> dict

It serializes a model's mapped **column** attributes into a plain,
JSON-safe dict (Enums -> string value, datetimes -> ISO-8601, Decimal ->
string) and never emits the internal DB primary key `id` (dual-ID law,
AGENTS.md §12.1 / §23). Relationships are NOT traversed here -- callers
that need related data serialize the related objects explicitly.
"""
from __future__ import annotations

import datetime
import decimal
import enum
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import inspect
from sqlalchemy.orm.exc import DetachedInstanceError

# Internal entity primary keys that must never cross the API boundary (§12.1).
RESERVED_INTERNAL_KEYS = frozenset({"id"})


class ModelSerializer:
    """Serialize SQLAlchemy models to plain JSON-safe dicts."""

    @staticmethod
    def serialize(
        obj: Any,
        include: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        allow = set(include) if include else None
        deny = set(exclude) if exclude else None

        try:
            attrs = list(inspect(obj).mapper.column_attrs)
        except (AttributeError, TypeError):
            attrs = []

        result: Dict[str, Any] = {}
        for attr in attrs:
            name = attr.key
            if name in RESERVED_INTERNAL_KEYS:
                continue
            if allow is not None and name not in allow:
                continue
            if deny is not None and name in deny:
                continue
            try:
                value = getattr(obj, name)
            except (AttributeError, DetachedInstanceError):
                continue
            result[name] = _json_safe(value)
        return result


def _json_safe(value: Any) -> Any:
    """Return a Flask-jsonify-safe representation of a scalar value."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return str(value)
    # dict / list (e.g. JSONB columns) are JSON structures already.
    if isinstance(value, (dict, list)):
        return value
    # Last resort: keep the API boundary JSON-safe without inventing types.
    return str(value)