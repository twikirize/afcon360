"""
Focused regression test for agent_onboarding server_default alignment (Item 33b).

Verifies that the three columns have matching Python defaults and server_default metadata
without requiring a database connection or app context.
"""

from sqlalchemy import inspect
from app.wallet.models.agent_onboarding import AgentOnboarding, AgentOnboardingApproval


def test_agent_onboarding_is_deleted_server_default():
    """AgentOnboarding.is_deleted retains Python default and declares server_default='false'."""
    mapper = inspect(AgentOnboarding)
    col = mapper.columns.is_deleted
    
    # Python default
    assert col.default is not None
    assert col.default.arg is False
    
    # Server default
    assert col.server_default is not None
    assert str(col.server_default.arg) == "false"
    
    # Nullable and type
    assert col.nullable is False
    assert str(col.type) == "BOOLEAN"


def test_agent_onboarding_approval_is_deleted_server_default():
    """AgentOnboardingApproval.is_deleted retains Python default and declares server_default='false'."""
    mapper = inspect(AgentOnboardingApproval)
    col = mapper.columns.is_deleted
    
    # Python default
    assert col.default is not None
    assert col.default.arg is False
    
    # Server default
    assert col.server_default is not None
    assert str(col.server_default.arg) == "false"
    
    # Nullable and type
    assert col.nullable is False
    assert str(col.type) == "BOOLEAN"


def test_agent_onboarding_status_server_default():
    """AgentOnboarding.status retains Python default 'submitted' and declares matching server_default."""
    mapper = inspect(AgentOnboarding)
    col = mapper.columns.status
    
    # Python default
    assert col.default is not None
    assert col.default.arg == "submitted"
    
    # Server default
    assert col.server_default is not None
    assert str(col.server_default.arg) == "submitted"
    
    # Nullable and type
    assert col.nullable is False
    assert "VARCHAR" in str(col.type).upper() or "STRING" in str(col.type).upper()


def test_all_three_columns_non_nullable():
    """All three columns remain non-nullable."""
    agent_mapper = inspect(AgentOnboarding)
    approval_mapper = inspect(AgentOnboardingApproval)
    
    assert agent_mapper.columns.is_deleted.nullable is False
    assert agent_mapper.columns.status.nullable is False
    assert approval_mapper.columns.is_deleted.nullable is False