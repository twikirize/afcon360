"""
tests/wallet/conftest.py
Pytest configuration and fixtures for wallet tests.
"""

import pytest
from decimal import Decimal


@pytest.fixture
def sample_amount():
    """Sample amount for testing."""
    return Decimal('100.00')


@pytest.fixture
def sample_currency():
    """Sample currency for testing."""
    return 'USD'
