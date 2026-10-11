"""Marshmallow-shaped adapter over Pydantic.

The calling code (routes) was written against Marshmallow's API:

    schema = BookingSchema()
    validated = schema.load(request.form)
    # raises ValidationError with .messages == {field: [msg, ...]}

This module provides that API on top of Pydantic so no calling code
needs to know which library validates.
"""
from typing import Any, Dict, Type

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError


class ValidationError(Exception):
    """Marshmallow-compatible error shape."""

    def __init__(self, messages: Dict[str, Any]):
        self.messages = messages
        super().__init__(str(messages))


class BaseSchema:
    """Subclasses set `Model` to a Pydantic BaseModel subclass.

    `load()` validates but returns the ORIGINAL string values, not Pydantic's
    coerced output. Rationale: the transport service re-parses strings
    (ServiceType(value.lower()), int(value), etc.). Coerced output would
    break it. See app/transport/services/booking_service.py.
    """

    Model: Type[BaseModel]

    def load(self, data: Any) -> Dict[str, Any]:
        # request.form is an ImmutableMultiDict; take first value per key.
        if hasattr(data, "to_dict"):
            raw = data.to_dict()
        elif isinstance(data, dict):
            raw = dict(data)
        else:
            raw = {k: v for k, v in dict(data).items()}

        try:
            self.Model(**raw)
        except PydanticValidationError as exc:
            raise ValidationError(self._to_messages(exc)) from exc
        return raw

    @staticmethod
    def _to_messages(exc: PydanticValidationError) -> Dict[str, list]:
        messages: Dict[str, list] = {}
        for error in exc.errors():
            loc = error.get("loc") or ()
            field = str(loc[0]) if loc else "__root__"
            messages.setdefault(field, []).append(error.get("msg", "invalid"))
        return messages


__all__ = ["BaseSchema", "ValidationError"]
