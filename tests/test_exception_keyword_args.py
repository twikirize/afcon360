"""
Regression tests for Defect A: Unsupported exception keyword arguments.

Verifies that exception classes in app/utils/exceptions.py accept
``code`` and ``details`` parameters without raising TypeError,
and that the existing error meaning is preserved.
"""
import pytest

from app.utils.exceptions import (
    ValidationError,
    PermissionError,
    ServiceUnavailableError,
    NotFoundError,
    ConflictError,
    DatabaseError,
    AuthenticationError,
    BusinessLogicError,
    ExternalServiceError,
)


# ---- Defect A: Exception constructor keyword argument acceptance ----

@pytest.mark.parametrize(
    "exception_class,kwargs,expected_code,expected_details",
    [
        (
            ValidationError,
            {"message": "test error", "code": "ERR_VALID", "details": {"field": "val"}},
            "ERR_VALID",
            {"field": "val"},
        ),
        (
            PermissionError,
            {"message": "perm denied", "code": "PERM1"},
            "PERM1",
            None,
        ),
        (
            ServiceUnavailableError,
            {"message": "svc down", "code": "SVC1"},
            "SVC1",
            None,
        ),
        (
            NotFoundError,
            {"message": "not found", "code": "NF1"},
            "NF1",
            None,
        ),
        (
            ConflictError,
            {"message": "conflict", "code": "CF1"},
            "CF1",
            None,
        ),
        (
            DatabaseError,
            {"message": "db error", "code": "DB1"},
            "DB1",
            None,
        ),
        (
            AuthenticationError,
            {"message": "auth failed", "code": "AUTH1"},
            "AUTH1",
            None,
        ),
        (
            BusinessLogicError,
            {"message": "logic error", "code": "BL1"},
            "BL1",
            None,
        ),
        (
            ExternalServiceError,
            {"message": "ext error", "code": "EXT1"},
            "EXT1",
            None,
        ),
    ],
)
def test_exception_accepts_code_and_details(
    exception_class, kwargs, expected_code, expected_details
):
    """Each exception class accepts ``code`` and ``details`` kwargs without TypeError."""
    # Arrange & Act
    exc = exception_class(**kwargs)

    # Assert
    assert exc.code == expected_code, f"{exception_class.__name__}.code expected {expected_code}, got {exc.code}"
    assert exc.details == expected_details, (
        f"{exception_class.__name__}.details expected {expected_details}, got {exc.details}"
    )
    assert str(exc) == expected_code or exc.message == kwargs.get("message", "")


# ---- Defect A: Backward compatibility - old raises without code/details still work ----

def test_exception_backward_compatibility():
    """Exception classes still work without code/details (original behavior preserved)."""
    # Act
    e1 = ValidationError(message="validation failed")
    e2 = PermissionError(message="access denied")
    e3 = ServiceUnavailableError(message="service unavailable")
    e4 = NotFoundError(message="resource not found")
    e5 = ConflictError(message="conflict detected")
    e6 = DatabaseError(message="database error")
    e7 = AuthenticationError(message="authentication failed")
    e8 = BusinessLogicError(message="business logic error")
    e9 = ExternalServiceError(message="external service error")

    # Assert - no TypeError, messages preserved
    assert str(e1) == "validation failed"
    assert str(e2) == "access denied"
    assert str(e3) == "service unavailable"
    assert str(e4) == "resource not found"
    assert str(e5) == "conflict detected"
    assert str(e6) == "database error"
    assert str(e7) == "authentication failed"
    assert str(e8) == "business logic error"
    assert str(e9) == "external service error"


# ---- Defect A: Positive and negative paths remain functional ----

def test_validation_error_positive_path():
    """ValidationError with code and details is raised and caught correctly."""
    # Act & Assert
    try:
        raise ValidationError(
            message="Identity not verified",
            details={"identity_verified": False},
            code="IDENTITY_NOT_VERIFIED",
        )
    except ValidationError as e:
        assert e.code == "IDENTITY_NOT_VERIFIED"
        assert e.details == {"identity_verified": False}
        assert e.message == "Identity not verified"


def test_validation_error_negative_path():
    """ValidationError without code/details still works (backward compat)."""
    # Act & Assert
    try:
        raise ValidationError(message="Validation failed")
    except ValidationError as e:
        assert e.code is None
        assert e.details is None
        assert e.message == "Validation failed"