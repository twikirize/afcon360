"""
pytest tests for trust-based security system
Run with: pytest test_trust_system.py -v
"""

import pytest
from app import create_app
from app.identity.models.user import User
from app.events.trust_service import EventTrustService, TrustLevel


@pytest.fixture
def app():
    """Create test app"""
    app = create_app()
    with app.app_context():
        yield app


@pytest.fixture
def sample_users(app):
    """Get sample users for testing"""
    users = User.query.limit(5).all()
    return users


class TestTrustService:
    """Test the trust-based security system"""
    
    def test_calculate_trust_level_returns_valid_level(self, sample_users):
        """Test that trust calculation returns valid levels"""
        for user in sample_users:
            trust_level = EventTrustService.calculate_trust_level(user)
            assert trust_level in [TrustLevel.HIGH, TrustLevel.MEDIUM, TrustLevel.LOW]
    
    def test_high_trust_users_auto_publish(self, sample_users):
        """Test that high trust users get auto-publish"""
        for user in sample_users:
            trust_level = EventTrustService.calculate_trust_level(user)
            should_auto, reason = EventTrustService.should_auto_publish(user, trust_level)
            
            if trust_level == TrustLevel.HIGH:
                assert should_auto is True
                assert "auto-publishing" in reason.lower()
    
    def test_trust_analysis_structure(self, sample_users):
        """Test that trust analysis returns proper structure"""
        for user in sample_users:
            analysis = EventTrustService.get_trust_analysis(user)
            
            # Required fields
            assert 'user_id' in analysis
            assert 'username' in analysis
            assert 'trust_level' in analysis
            assert 'should_auto_publish' in analysis
            assert 'reason' in analysis
            assert 'factors' in analysis
            
            # Factor fields
            factors = analysis['factors']
            assert 'roles' in factors
            assert 'kyc_level' in factors
            assert 'is_verified' in factors
            assert 'account_age_days' in factors
            assert 'successful_events' in factors
    
    def test_super_admin_gets_high_trust(self, app):
        """Test that super admins get high trust automatically"""
        # Find a super admin user using a simpler approach
        from app.auth.helpers import has_global_role
        
        for user in User.query.limit(10).all():
            if has_global_role(user, 'super_admin'):
                trust_level = EventTrustService.calculate_trust_level(user)
                assert trust_level == TrustLevel.HIGH
                break
        else:
            # Skip test if no super admin found
            pytest.skip("No super admin user found in database")
    
    def test_new_unverified_user_gets_low_trust(self, app):
        """Test that new unverified users get low trust"""
        # Find a new, unverified user
        new_user = User.query.filter_by(is_verified=False).order_by(User.created_at.desc()).first()
        if new_user:
            trust_level = EventTrustService.calculate_trust_level(new_user)
            assert trust_level == TrustLevel.LOW
    
    def test_trust_score_consistency(self, sample_users):
        """Test that trust scores are consistent"""
        for user in sample_users:
            # Calculate trust level twice
            trust_level1 = EventTrustService.calculate_trust_level(user)
            trust_level2 = EventTrustService.calculate_trust_level(user)
            
            # Should be the same
            assert trust_level1 == trust_level2


class TestTrustLevels:
    """Test specific trust level scenarios"""
    
    def test_trust_level_enum_values(self):
        """Test that trust level enum has correct values"""
        assert TrustLevel.HIGH == "high"
        assert TrustLevel.MEDIUM == "medium"
        assert TrustLevel.LOW == "low"
    
    def test_should_auto_publish_logic(self, app):
        """Test auto-publish decision logic"""
        users = User.query.all()
        
        for user in users:
            trust_level = EventTrustService.calculate_trust_level(user)
            should_auto, reason = EventTrustService.should_auto_publish(user, trust_level)
            
            # High trust should always auto-publish
            if trust_level == TrustLevel.HIGH:
                assert should_auto is True
                assert "high trust" in reason.lower()
            
            # Low trust should never auto-publish
            elif trust_level == TrustLevel.LOW:
                assert should_auto is False
                assert "low trust" in reason.lower()
            
            # Medium trust should auto-publish (after approval)
            elif trust_level == TrustLevel.MEDIUM:
                assert should_auto is True
                assert "medium trust" in reason.lower()


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])
