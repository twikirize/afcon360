# app/accommodation/utils.py
"""
Shared accommodation helpers.

Centralises the Enum -> string conversion that the ENUM-to-String
migration made necessary. After that migration, DB-loaded columns
hold plain strings, while enum literals still expose `.value`.
Calling `.value` directly on a DB value crashes ('str' has no
attribute 'value'), so always route through `enum_value`.
"""

import enum


def enum_value(val):
    """
    Safely convert an Enum member to its string value.

    - If `val` is an enum member, return its `.value`.
    - If `val` is already a plain string/value, return it unchanged.

    Use this everywhere you would otherwise write `something.value`,
    especially on model attributes that were formerly Enum columns
    (property_type, status, payment_status, cancellation_policy, etc.).
    """
    return val.value if isinstance(val, enum.Enum) else val
