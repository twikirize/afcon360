"""
Onboarding flow integration tests.
Run with: pytest tests/test_onboarding.py -v
"""
import pytest
from app import create_app
from app.extensions import db
from app.identity.models.user import User, UserRole
from app.identity.models.roles_permission import Role
from app.profile.models import UserProfile, get_profile_by_user


@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.app_context():
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def registered_user(app):
    """Create a registered but not-yet-onboarded user."""
    with app.app_context():
        user = User(
            public_id="test-uuid-1234",
            username="testuser",
            email="test@example.com",
        )
        user.set_password("TestPassword123!")
        user.is_active = True
        user.is_verified = True
        db.session.add(user)
        db.session.flush()
        
        # Fan role
        fan_role = Role.query.filter_by(name="fan").first()
        if fan_role:
            db.session.add(UserRole(user_id=user.id, role_id=fan_role.id))
        
        # Incomplete profile
        profile = UserProfile(
            user_id=user.public_id,
            full_name="Test User",
            profile_completed=False,
        )
        db.session.add(profile)
        db.session.commit()
        
        yield user


class TestOnboardingChoosePage:
    """Test the landing/choose page."""
    
    def test_choose_page_accessible_when_logged_in(self, client, registered_user):
        """Authenticated users can access the choose page."""
        with client.session_transaction() as sess:
            sess["_user_id"] = registered_user.public_id
        
        response = client.get("/onboarding/choose")
        assert response.status_code == 200
        assert b"What brings you" in response.data
    
    def test_choose_page_redirects_if_already_onboarded(self, client, app, registered_user):
        """Users with completed profiles skip the choose page."""
        with app.app_context():
            profile = get_profile_by_user(registered_user.public_id)
            profile.profile_completed = True
            db.session.commit()
        
        with client.session_transaction() as sess:
            sess["_user_id"] = registered_user.public_id
        
        response = client.get("/onboarding/choose")
        assert response.status_code == 302  # Redirect to dashboard
    
    def test_choose_page_requires_login(self, client):
        """Unauthenticated users are redirected to login."""
        response = client.get("/onboarding/choose")
        assert response.status_code == 302
        assert b"login" in response.headers["Location"].lower()


class TestFanOnboarding:
    """Test fan onboarding flow."""
    
    def test_fan_onboarding_completes_profile(self, client, app, registered_user):
        """Submitting fan form marks profile as complete."""
        with client.session_transaction() as sess:
            sess["_user_id"] = registered_user.public_id
        
        response = client.post("/onboarding/fan", data={
            "full_name": "John Doe",
            "city": "Kampala",
            "country": "UG",
        }, follow_redirects=False)
        
        assert response.status_code == 302
        assert "fan/dashboard" in response.headers["Location"]
        
        with app.app_context():
            profile = get_profile_by_user(registered_user.public_id)
            assert profile.profile_completed is True
            assert profile.full_name == "John Doe"
            assert profile.city == "Kampala"
    
    def test_fan_onboarding_requires_full_name(self, client, registered_user):
        """Fan form rejects empty full_name."""
        with client.session_transaction() as sess:
            sess["_user_id"] = registered_user.public_id
        
        response = client.post("/onboarding/fan", data={
            "full_name": "",
            "city": "Kampala",
            "country": "UG",
        })
        
        assert response.status_code == 200  # Stays on form
        assert b"required" in response.data.lower()


class TestOrganisationOnboarding:
    """Test organisation registration flow."""
    
    def test_org_onboarding_step1_saves_to_session(self, client, registered_user):
        """Step 1 data is saved to session and redirects to step 2."""
        with client.session_transaction() as sess:
            sess["_user_id"] = registered_user.public_id
        
        response = client.post("/onboarding/organisation/step/1?type=consumer", data={
            "legal_name": "Test Company Ltd",
            "country": "UG",
            "registration_no": "REG123",
            "tax_id": "TAX456",
            "contact_email": "company@test.com",
            "contact_phone": "+256700000000",
            "website": "https://test.com",
        }, follow_redirects=False)
        
        assert response.status_code == 302
        assert "step/2" in response.headers["Location"]
    
    def test_org_onboarding_creates_organisation_record(self, client, app, registered_user):
        """Completing org onboarding creates Organisation + Member records."""
        with client.session_transaction() as sess:
            sess["_user_id"] = registered_user.public_id
            sess["org_onboarding"] = {
                "step1": {
                    "legal_name": "Test Company Ltd",
                    "country": "UG",
                    "registration_no": "REG123",
                    "tax_id": "TAX456",
                    "contact_email": "company@test.com",
                    "contact_phone": "+256700000000",
                    "website": "",
                    "org_type": "consumer",
                }
            }
            sess["org_onboarding_type"] = "consumer"
        
        response = client.post("/onboarding/organisation/step/2", 
                               follow_redirects=False)
        
        assert response.status_code == 302
        
        with app.app_context():
            from app.identity.models.organisation import Organisation
            org = Organisation.query.filter_by(legal_name="Test Company Ltd").first()
            assert org is not None
            assert org.primary_contact_user_id == registered_user.id


class TestDashboardRouting:
    """Test that _dashboard_for_user routes correctly."""
    
    def test_incomplete_profile_routes_to_onboarding(self, app, registered_user):
        """Users with incomplete profiles go to onboarding."""
        with app.app_context():
            from app.auth.routes import _dashboard_for_user
            with app.test_request_context("/"):
                url = _dashboard_for_user(registered_user)
            assert "onboarding" in url
    
    def test_complete_fan_profile_routes_to_fan_dashboard(self, app, registered_user):
        """Completed fan profiles go to fan dashboard."""
        with app.app_context():
            profile = get_profile_by_user(registered_user.public_id)
            profile.profile_completed = True
            db.session.commit()
            
            from app.auth.routes import _dashboard_for_user
            with app.test_request_context("/"):
                url = _dashboard_for_user(registered_user)
            assert "fan" in url


class TestWalletActivation:
    """Test wallet is not auto-created and requires explicit activation."""
    
    def test_wallet_not_created_at_signup(self, app, registered_user):
        """New users have no wallet by default."""
        with app.app_context():
            from app.wallet.models.ledger import AccountModel, AccountOwnerType
            account = AccountModel.query.filter_by(
                user_id=registered_user.id,
                owner_type=AccountOwnerType.USER
            ).first()
            assert account is None
    
    def test_wallet_created_after_activation(self, client, app, registered_user):
        """Wallet is created only after user accepts terms."""
        with client.session_transaction() as sess:
            sess["_user_id"] = registered_user.public_id
        
        response = client.post("/wallet/activate", data={
            "accept_terms": "on"
        }, follow_redirects=False)
        
        assert response.status_code == 302
        
        with app.app_context():
            from app.wallet.models.ledger import AccountModel, AccountOwnerType
            account = AccountModel.query.filter_by(
                user_id=registered_user.id,
                owner_type=AccountOwnerType.USER
            ).first()
            assert account is not None
