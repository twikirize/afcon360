# app/core/validators.py
"""
Standalone validators for AFCON360.

Provides the two validator contracts referenced by `app.transport.models`:

- `validate_coordinates(lat, lng)`  -> raises when the pair is out of range
  (used by `DriverProfile.update_location`). The range/format rules reuse the
  existing `TransportValidators.validate_coordinates` in
  `app/utils/validators.py`; no new validation architecture is introduced.

- `validate_setting_value(value, data_type, allowed_values, validation_rules)`
  -> returns the normalized value to store or raises `ValidationError`
  (used by `TransportSetting.validate_value`). Its normalization semantics
  mirror `SettingsService._validate_setting_value` in
  `app/transport/services/settings_service.py`.
"""
from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any, List, Optional

from app.utils.exceptions import ValidationError
from app.utils.validators import TransportValidators


def validate_coordinates(latitude: Any, longitude: Any) -> None:
    """Raise ValidationError if the coordinate pair is invalid.

    Valid coordinates pass silently (returns None). Invalid coordinates raise
    so callers (e.g. DriverProfile.update_location) never persist bad data.
    """
    if not TransportValidators.validate_coordinates(latitude, longitude):
        raise ValidationError(
            "Invalid coordinates: latitude must be within [-90, 90] and "
            "longitude within [-180, 180]",
            field="coordinates",
        )


def validate_setting_value(
    value: Any,
    data_type: str,
    allowed_values: Optional[List[Any]] = None,
    validation_rules: Optional[dict] = None,
) -> Any:
    """Validate and normalize a TransportSetting value for storage.

    Mirrors the semantics of SettingsService._validate_setting_value:
    coerce to the declared data_type, enforce allowed_values, apply the
    numeric min/max and string length/pattern rules, and either return the
    normalized value or raise ValidationError.
    """
    errors: List[str] = []
    normalized = value

    if data_type == "boolean":
        if not isinstance(value, bool):
            if isinstance(value, str):
                lowered = value.lower()
                if lowered in ("true", "1", "yes", "on"):
                    normalized = True
                elif lowered in ("false", "0", "no", "off"):
                    normalized = False
                else:
                    errors.append(f"Invalid boolean value: {value}")
            elif isinstance(value, (int, float)):
                normalized = bool(value)
            else:
                errors.append(f"Invalid boolean type: {type(value)}")

    elif data_type == "integer":
        try:
            normalized = int(value)
        except (ValueError, TypeError):
            errors.append(f"Invalid integer value: {value}")

    elif data_type == "decimal":
        try:
            normalized = Decimal(str(value))
        except (ValueError, TypeError, InvalidOperation):
            errors.append(f"Invalid decimal value: {value}")

    elif data_type == "string":
        if not isinstance(value, str):
            normalized = str(value)

    elif data_type == "json":
        if isinstance(value, str):
            try:
                normalized = json.loads(value)
            except json.JSONDecodeError as exc:
                errors.append(f"Invalid JSON: {exc}")
        elif not isinstance(value, (dict, list, str, int, float, bool, type(None))):
            errors.append(f"Invalid JSON type: {type(value)}")

    if allowed_values and normalized not in allowed_values:
        errors.append(f"Value not in allowed values: {allowed_values}")

    if validation_rules and normalized is not None:
        rules = validation_rules
        if data_type in ("integer", "decimal"):
            if "min" in rules and normalized < rules["min"]:
                errors.append(f"Value must be >= {rules['min']}")
            if "max" in rules and normalized > rules["max"]:
                errors.append(f"Value must be <= {rules['max']}")
        if data_type == "string" and isinstance(normalized, str):
            if "min_length" in rules and len(normalized) < rules["min_length"]:
                errors.append(f"Length must be >= {rules['min_length']}")
            if "max_length" in rules and len(normalized) > rules["max_length"]:
                errors.append(f"Length must be <= {rules['max_length']}")
            pattern = rules.get("pattern")
            if pattern and not re.match(pattern, normalized):
                errors.append(f"Value must match pattern: {pattern}")

    if errors:
        raise ValidationError("; ".join(errors), field="value")

    return normalized