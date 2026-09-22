"""Vehicle Marketplace Service

Handles the core business logic for the vehicle marketplace:
- Listing management (create, update, pause, close)
- Application management (submit, review, approve, reject)
- Contract management (create, terminate, settlements)
- Marketplace discovery (search, recommendations)
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Dict, Any
from sqlalchemy import and_, or_, func, desc
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.transport.models import (
    Vehicle,
    VehicleMarketplaceListing,
    DriverVehicleApplication,
    VehicleContract,
    DriverProfile,
    VerificationTier,
    CompensationModel,
    MarketplaceListingStatus,
    ApplicationStatus,
    ContractStatus,
)
from app.identity.models.user import User
from app.identity.models.organisation import Organisation
from app.identity.services.organization_permissions import OrganizationPermissionService
import logging

logger = logging.getLogger(__name__)


class VehicleMarketplaceService:
    """Core marketplace business logic"""
    
    # =========================================================================
    # LISTING MANAGEMENT
    # =========================================================================
    
    def create_listing(
        self,
        vehicle_id: int,
        owner_id: int,
        data: Dict[str, Any]
    ) -> VehicleMarketplaceListing:
        """Create a new marketplace listing for a vehicle"""
        # Verify vehicle ownership
        vehicle = Vehicle.query.filter_by(id=vehicle_id, is_deleted=False).first()
        if not vehicle:
            raise ValueError("Vehicle not found")
        
        # Verify ownership
        if not self._verify_vehicle_ownership(vehicle, owner_id):
            raise PermissionError("You don't own this vehicle")
        
        # Check if already listed
        existing = VehicleMarketplaceListing.query.filter_by(
            vehicle_id=vehicle_id, is_deleted=False
        ).first()
        if existing:
            raise ValueError("Vehicle is already listed on marketplace")
        
        # Create listing
        listing = VehicleMarketplaceListing(
            vehicle_id=vehicle_id,
            owner_id=owner_id,
            listing_status=data.get('listing_status', 'active'),
            visibility=data.get('visibility', 'public'),
            
            # Requirements
            required_verification_tier=data.get('required_verification_tier', 'basic_verified'),
            required_service_types=data.get('required_service_types', []),
            required_vehicle_classes=data.get('required_vehicle_classes', []),
            min_experience_years=data.get('min_experience_years', 0),
            min_rating=data.get('min_rating', 0),
            
            # Compensation
            compensation_model=data.get('compensation_model', 'revenue_split'),
            driver_revenue_share_pct=data.get('driver_revenue_share_pct', 70.00),
            fixed_rental_amount=data.get('fixed_rental_amount'),
            rental_frequency=data.get('rental_frequency'),
            
            # Operational
            shift_preferences=data.get('shift_preferences', {}),
            max_hours_per_day=data.get('max_hours_per_day', 12),
            allowed_zones=data.get('allowed_zones', []),
            
            # Vehicle requirements
            min_vehicle_rating=data.get('min_vehicle_rating', 4.0),
            require_insurance_verified=data.get('require_insurance_verified', True),
            require_roadworthiness=data.get('require_roadworthiness', True),
            
            # Application settings
            auto_approve=data.get('auto_approve', False),
            max_applications=data.get('max_applications', 10),
            application_deadline=data.get('application_deadline'),
            
            # Display
            title=data.get('title'),
            description=data.get('description'),
            highlights=data.get('highlights', []),
            cover_photo_url=data.get('cover_photo_url'),
            
            expires_at=data.get('expires_at'),
        )
        
        db.session.add(listing)
        db.session.commit()
        
        logger.info(f"Marketplace listing created: listing_id={listing.id}, vehicle_id={vehicle_id}")
        return listing
    
    def update_listing(
        self,
        listing_id: int,
        owner_id: int,
        data: Dict[str, Any]
    ) -> Optional[VehicleMarketplaceListing]:
        """Update a marketplace listing"""
        listing = VehicleMarketplaceListing.query.filter_by(
            id=listing_id, owner_id=owner_id, is_deleted=False
        ).first()
        
        if not listing:
            return None
        
        # Updatable fields
        updatable_fields = [
            'listing_status', 'visibility',
            'required_verification_tier', 'required_service_types',
            'required_vehicle_classes', 'min_experience_years', 'min_rating',
            'compensation_model', 'driver_revenue_share_pct', 'fixed_rental_amount',
            'rental_frequency', 'shift_preferences', 'max_hours_per_day',
            'allowed_zones', 'min_vehicle_rating', 'require_insurance_verified',
            'require_roadworthiness', 'auto_approve', 'max_applications',
            'application_deadline', 'title', 'description', 'highlights',
            'cover_photo_url', 'expires_at'
        ]
        
        for field in updatable_fields:
            if field in data:
                setattr(listing, field, data[field])
        
        db.session.commit()
        logger.info(f"Marketplace listing updated: listing_id={listing_id}")
        return listing
    
    def pause_listing(self, listing_id: int, owner_id: int) -> bool:
        """Pause a marketplace listing"""
        listing = VehicleMarketplaceListing.query.filter_by(
            id=listing_id, owner_id=owner_id, is_deleted=False
        ).first()
        if not listing:
            return False
        
        listing.listing_status = 'paused'
        db.session.commit()
        logger.info(f"Listing paused: listing_id={listing_id}")
        return True
    
    def reactivate_listing(self, listing_id: int, owner_id: int) -> bool:
        """Reactivate a paused listing"""
        listing = VehicleMarketplaceListing.query.filter_by(
            id=listing_id, owner_id=owner_id, is_deleted=False
        ).first()
        if not listing or listing.listing_status != 'paused':
            return False
        
        listing.listing_status = 'active'
        db.session.commit()
        logger.info(f"Listing reactivated: listing_id={listing_id}")
        return True
    
    def close_listing(self, listing_id: int, owner_id: int, reason: str) -> bool:
        """Close a marketplace listing"""
        listing = VehicleMarketplaceListing.query.filter_by(
            id=listing_id, owner_id=owner_id, is_deleted=False
        ).first()
        if not listing:
            return False
        
        listing.listing_status = 'closed'
        listing.filled_at = datetime.now(timezone.utc)
        db.session.commit()
        logger.info(f"Listing closed: listing_id={listing_id}, reason={reason}")
        return True
    
    def get_owner_listings(
        self,
        owner_id: int,
        status: Optional[str] = None
    ) -> List[VehicleMarketplaceListing]:
        """Get all listings owned by a user"""
        query = VehicleMarketplaceListing.query.filter_by(
            owner_id=owner_id, is_deleted=False
        )
        
        if status:
            query = query.filter(VehicleMarketplaceListing.listing_status == status)
        
        return query.order_by(desc(VehicleMarketplaceListing.listed_at)).all()
    
    def get_listing(self, listing_id: int, owner_id: int = None) -> Optional[VehicleMarketplaceListing]:
        """Get a listing by ID, optionally filtering by owner"""
        query = VehicleMarketplaceListing.query.filter_by(is_deleted=False)
        
        if owner_id:
            query = query.filter_by(owner_id=owner_id)
        
        return query.filter_by(id=listing_id).first()
    
    def listing_for_vehicle(self, vehicle_id: int) -> Optional[VehicleMarketplaceListing]:
        """Return the active public marketplace listing for a vehicle, if any.

        A vehicle may have at most one listing (unique ``vehicle_id`` index).
        Only ``active`` + ``public`` listings are discoverable/requestable by
        drivers; draft/paused/filled/closed/private listings are not visible
        through the marketplace request surface.
        """
        return VehicleMarketplaceListing.query.filter(
            VehicleMarketplaceListing.vehicle_id == vehicle_id,
            VehicleMarketplaceListing.is_deleted.is_(False),
            VehicleMarketplaceListing.listing_status == MarketplaceListingStatus.ACTIVE,
            VehicleMarketplaceListing.visibility == 'public',
        ).first()
    
    # =========================================================================
    # APPLICATION MANAGEMENT
    # =========================================================================
    
    def submit_application(
        self,
        driver_user_id: int,
        listing_id: int,
        data: Dict[str, Any]
    ) -> DriverVehicleApplication:
        """Submit an application to drive a marketplace vehicle"""
        listing = VehicleMarketplaceListing.query.filter_by(
            id=listing_id, is_deleted=False, listing_status='active'
        ).first()
        if not listing:
            raise ValueError("Listing not found or not active")
        
        # Get driver profile
        driver = DriverProfile.query.filter_by(
            user_id=driver_user_id, is_deleted=False
        ).first()
        if not driver:
            raise ValueError("Driver profile not found")
        
        # Check if already applied
        existing = DriverVehicleApplication.query.filter_by(
            listing_id=listing_id, driver_id=driver.id, is_deleted=False
        ).first()
        if existing:
            raise ValueError("You have already applied to this listing")
        
        # Check application limit
        if listing.max_applications:
            app_count = DriverVehicleApplication.query.filter_by(
                listing_id=listing_id, is_deleted=False
            ).count()
            if app_count >= listing.max_applications:
                raise ValueError("Application limit reached for this listing")
        
        # Check deadline
        if listing.application_deadline and datetime.now(timezone.utc) > listing.application_deadline:
            raise ValueError("Application deadline has passed")
        
        # Check eligibility
        if not self._check_driver_eligibility(driver, listing):
            raise ValueError("You don't meet the requirements for this listing")
        
        # Create application
        application = DriverVehicleApplication(
            listing_id=listing_id,
            driver_id=driver.id,
            driver_user_id=driver_user_id,
            cover_letter=data.get('cover_letter'),
            proposed_schedule=data.get('proposed_schedule', {}),
            proposed_hours_per_week=data.get('proposed_hours_per_week'),
            expected_earnings=data.get('expected_earnings'),
            license_copy_url=data.get('license_copy_url'),
            cv_url=data.get('cv_url'),
            references=data.get('references', []),
        )
        
        db.session.add(application)
        db.session.commit()
        
        # Auto-approve if enabled
        if listing.auto_approve:
            self._auto_approve_application(application)
        
        logger.info(f"Application submitted: application_id={application.id}, listing_id={listing_id}")
        return application
    
    @staticmethod
    def _normalize_tier(tier) -> Optional[str]:
        """Return the canonical lowercase value of a VerificationTier.

        Accepts:
            - None                               -> None
            - VerificationTier.BASIC_VERIFIED    -> 'basic_verified'
            - 'basic_verified'                   -> 'basic_verified'
            - 'BASIC_VERIFIED'                   -> 'basic_verified'
            - 'VerificationTier.BASIC_VERIFIED'  -> 'basic_verified'
        Returns None if the value cannot be mapped.
        """
        if tier is None:
            return None
        if hasattr(tier, "value"):
            return str(tier.value).lower()
        s = str(tier).strip().lower()
        if "." in s:
            s = s.rsplit(".", 1)[-1]
        return s or None

    def _check_driver_eligibility(self, driver: DriverProfile, listing: VehicleMarketplaceListing) -> bool:
        """Return True if the driver meets every requirement on the listing.

        Never raises. Missing or malformed data on either side is treated as
        "requirement not met" — the caller (submit_application) already
        surfaces a generic ineligibility error to the applicant.
        """
        tier_order = ("pending", "basic_verified", "platform_verified", "event_certified")

        # ── 1. Verification tier ──────────────────────────────────────────
        driver_tier = self._normalize_tier(driver.verification_tier)
        required_tier = self._normalize_tier(listing.required_verification_tier)

        if driver_tier is None or required_tier is None:
            logger.warning(
                "Marketplace eligibility: missing tier "
                "driver_id=%s driver_tier=%r listing_id=%s required_tier=%r",
                getattr(driver, "id", None),
                driver.verification_tier,
                getattr(listing, "id", None),
                listing.required_verification_tier,
            )
            return False

        try:
            driver_rank = tier_order.index(driver_tier)
            required_rank = tier_order.index(required_tier)
        except ValueError:
            logger.warning(
                "Marketplace eligibility: unknown tier value "
                "driver_tier=%r required_tier=%r",
                driver_tier, required_tier,
            )
            return False

        if driver_rank < required_rank:
            return False

        # ── 2. Rating ────────────────────────────────────────────────────
        if driver.average_rating is not None and listing.min_rating is not None:
            if driver.average_rating < listing.min_rating:
                return False

        # ── 3. Service types (JSONB list of strings) ─────────────────────
        required_services = listing.required_service_types or []
        if required_services:
            driver_services = {str(s).lower() for s in (driver.service_types or [])}
            if not any(str(s).lower() in driver_services for s in required_services):
                return False

        # ── 4. Vehicle classes (JSONB list of strings) ───────────────────
        required_classes = listing.required_vehicle_classes or []
        if required_classes:
            driver_classes = {str(c).lower() for c in (driver.vehicle_classes or [])}
            if not any(str(c).lower() in driver_classes for c in required_classes):
                return False

        return True
    
    def _auto_approve_application(self, application: DriverVehicleApplication) -> bool:
        """Auto-approve an application if listing has auto_approve enabled"""
        listing = application.listing
        if not listing.auto_approve:
            return False
        
        # Create contract
        contract = self._create_contract_from_application(application)
        if contract:
            application.status = ApplicationStatus.APPROVED
            application.reviewed_at = datetime.now(timezone.utc)
            application.approved_driver_id = application.driver_id
            application.contract_terms_accepted = True
            application.terms_accepted_at = datetime.now(timezone.utc)
            db.session.commit()
            return True
        return False
    
    def withdraw_application(self, application_id: int, driver_user_id: int) -> bool:
        """Withdraw an application"""
        application = DriverVehicleApplication.query.join(DriverProfile).filter(
            DriverVehicleApplication.id == application_id,
            DriverProfile.user_id == driver_user_id,
            DriverVehicleApplication.is_deleted == False
        ).first()
        
        if not application:
            return False
        
        if application.status not in [ApplicationStatus.PENDING, ApplicationStatus.UNDER_REVIEW]:
            return False
        
        application.status = ApplicationStatus.WITHDRAWN
        db.session.commit()
        logger.info(f"Application withdrawn: application_id={application_id}")
        return True
    
    def get_driver_applications(
        self,
        driver_user_id: int,
        status: Optional[str] = None
    ) -> List[DriverVehicleApplication]:
        """Get all applications by a driver"""
        query = DriverVehicleApplication.query.join(DriverProfile).filter(
            DriverProfile.user_id == driver_user_id,
            DriverVehicleApplication.is_deleted == False
        )
        
        if status:
            query = query.filter(DriverVehicleApplication.status == status)
        
        return query.order_by(desc(DriverVehicleApplication.applied_at)).all()
    
    def get_listing_applications(
        self,
        listing_id: int,
        owner_id: int,
        status: Optional[str] = None
    ) -> List[DriverVehicleApplication]:
        """Get all applications for a listing (owner only)"""
        listing = VehicleMarketplaceListing.query.filter_by(
            id=listing_id, owner_id=owner_id, is_deleted=False
        ).first()
        if not listing:
            return []
        
        query = DriverVehicleApplication.query.filter_by(
            listing_id=listing_id, is_deleted=False
        )
        
        if status:
            query = query.filter(DriverVehicleApplication.status == status)
        
        return query.order_by(desc(DriverVehicleApplication.applied_at)).all()
    
    # =========================================================================
    # APPLICATION REVIEW
    # =========================================================================
    
    def approve_application(
        self,
        application_id: int,
        owner_id: int,
        contract_terms: Optional[Dict] = None
    ) -> Optional[VehicleContract]:
        """Approve an application and create a contract"""
        application = DriverVehicleApplication.query.join(VehicleMarketplaceListing).filter(
            DriverVehicleApplication.id == application_id,
            VehicleMarketplaceListing.owner_id == owner_id,
            VehicleMarketplaceListing.is_deleted == False,
            DriverVehicleApplication.is_deleted == False
        ).first()
        
        if not application:
            return None
        
        if application.status not in [ApplicationStatus.PENDING, ApplicationStatus.UNDER_REVIEW]:
            raise ValueError("Application cannot be approved in current state")
        
        # Create contract from application
        contract = self._create_contract_from_application(application, contract_terms)
        
        if contract:
            application.status = ApplicationStatus.APPROVED
            application.reviewed_at = datetime.now(timezone.utc)
            application.reviewed_by = owner_id
            application.approved_driver_id = application.driver_id
            application.contract_terms_accepted = True
            application.terms_accepted_at = datetime.now(timezone.utc)
            db.session.commit()
            return contract
        
        return None
    
    def reject_application(
        self,
        application_id: int,
        owner_id: int,
        reason: str
    ) -> bool:
        """Reject an application"""
        application = DriverVehicleApplication.query.join(VehicleMarketplaceListing).filter(
            DriverVehicleApplication.id == application_id,
            VehicleMarketplaceListing.owner_id == owner_id,
            VehicleMarketplaceListing.is_deleted == False,
            DriverVehicleApplication.is_deleted == False
        ).first()
        
        if not application:
            return False
        
        application.status = ApplicationStatus.REJECTED
        application.reviewed_at = datetime.now(timezone.utc)
        application.reviewed_by = owner_id
        application.status_reason = reason
        db.session.commit()
        
        logger.info(f"Application rejected: application_id={application_id}, reason={reason}")
        return True
    
    def _create_contract_from_application(
        self,
        application: DriverVehicleApplication,
        contract_terms: Optional[Dict] = None
    ) -> Optional[VehicleContract]:
        """Create a contract from an approved application"""
        listing = application.listing
        
        # Build contract terms from listing and any overrides
        terms = contract_terms or {}
        
        contract = VehicleContract(
            vehicle_id=listing.vehicle_id,
            driver_id=application.driver_id,
            owner_id=listing.owner_id,
            application_id=application.id,
            
            contract_type=terms.get('contract_type', listing.compensation_model),
            driver_revenue_share_pct=terms.get('driver_revenue_share_pct', listing.driver_revenue_share_pct),
            fixed_rental_amount=terms.get('fixed_rental_amount', listing.fixed_rental_amount),
            rental_frequency=terms.get('rental_frequency', listing.rental_frequency),
            
            min_hours_per_week=terms.get('min_hours_per_week', 20),
            max_hours_per_week=terms.get('max_hours_per_week', 60),
            allowed_zones=terms.get('allowed_zones', listing.allowed_zones or []),
            shift_requirements=terms.get('shift_requirements', listing.shift_preferences or {}),
            
            insurance_covered_by=terms.get('insurance_covered_by', 'owner'),
            liability_limit=terms.get('liability_limit'),
            
            status=ContractStatus.PENDING_SIGNATURE,
        )
        
        db.session.add(contract)
        db.session.commit()
        
        # Update listing status
        listing.listing_status = 'filled'
        listing.filled_at = datetime.now(timezone.utc)
        db.session.commit()
        
        logger.info(f"Contract created: contract_id={contract.id}, driver_id={contract.driver_id}, vehicle_id={contract.vehicle_id}")
        return contract
    
    # =========================================================================
    # CONTRACT MANAGEMENT
    # =========================================================================
    
    def create_contract_from_application(
        self,
        application_id: int,
        terms: Optional[Dict] = None
    ) -> Optional[VehicleContract]:
        """Create a contract from an approved application (standalone)"""
        application = DriverVehicleApplication.query.filter_by(
            id=application_id, is_deleted=False
        ).first()
        
        if not application or application.status != ApplicationStatus.APPROVED:
            return None
        
        return self._create_contract_from_application(application)
    
    def terminate_contract(
        self,
        contract_id: int,
        user_id: int,
        reason: str
    ) -> bool:
        """Terminate an ACTIVE contract.

        Both the contracted DRIVER (identified by their User.id) and the
        vehicle OWNER (identified by User.id) may terminate. The two
        identities live in different tables -- ``contract.driver_id`` is a
        ``DriverProfile.id`` and ``contract.owner_id`` is a ``User.id`` --
        so the driver's User.id must be resolved before comparison.
        """
        contract = VehicleContract.query.filter_by(
            id=contract_id, is_deleted=False
        ).first()

        if not contract:
            return False

        # Resolve the driver's User.id. contract.driver_id points at
        # DriverProfile, not User.
        driver_profile = db.session.get(DriverProfile, contract.driver_id)
        driver_user_id = driver_profile.user_id if driver_profile else None

        is_owner = (contract.owner_id == user_id)
        is_driver = (driver_user_id is not None and driver_user_id == user_id)

        if not (is_owner or is_driver):
            return False
        
        if contract.status != ContractStatus.ACTIVE:
            raise ValueError("Can only terminate active contracts")
        
        contract.status = ContractStatus.TERMINATED
        contract.termination_reason = reason
        contract.notice_given_at = datetime.now(timezone.utc)
        contract.actual_end_date = datetime.now(timezone.utc)
        db.session.commit()
        
        logger.info(f"Contract terminated: contract_id={contract_id}, reason={reason}")
        return True
    
    def get_driver_contracts(
        self,
        driver_id: int,
        status: Optional[str] = None
    ) -> List[VehicleContract]:
        """Get all contracts for a driver"""
        query = VehicleContract.query.filter_by(driver_id=driver_id, is_deleted=False)
        
        if status:
            query = query.filter(VehicleContract.status == status)
        
        return query.order_by(desc(VehicleContract.start_date)).all()
    
    def get_owner_contracts(
        self,
        owner_id: int,
        status: Optional[str] = None
    ) -> List[VehicleContract]:
        """Get all contracts for an owner"""
        query = VehicleContract.query.filter_by(owner_id=owner_id, is_deleted=False)
        
        if status:
            query = query.filter(VehicleContract.status == status)
        
        return query.order_by(desc(VehicleContract.start_date)).all()
    
    def get_contract(self, contract_id: int, user_id: int = None) -> Optional[VehicleContract]:
        """Get a contract by ID"""
        query = VehicleContract.query.filter_by(is_deleted=False)
        
        if user_id:
            query = query.filter(
                or_(VehicleContract.driver_id == user_id, VehicleContract.owner_id == user_id)
            )
        
        return query.filter_by(id=contract_id).first()
    
    # =========================================================================
    # CONTRACT ACCEPTANCE & ACTIVATION
    # =========================================================================
    
    def accept_contract_terms(
        self,
        contract_id: int,
        driver_user_id: int
    ) -> bool:
        """Driver accepts contract terms and activates the contract.
        
        Owner acceptance is implicit via approve_application (which creates
        the contract in PENDING_SIGNATURE). Driver acceptance activates
        the contract and creates the authoritative driver-vehicle relationship
        for Go-Live.
        
        Returns True if contract was activated, False otherwise."""
        contract = VehicleContract.query.filter_by(
            id=contract_id, is_deleted=False
        ).first()
        
        if not contract:
            return False
        
        # Verify this is the driver for this contract
        driver = DriverProfile.query.filter_by(
            user_id=driver_user_id, is_deleted=False
        ).first()
        if not driver or contract.driver_id != driver.id:
            return False
        
        # Check contract is in a state that can be accepted
        if contract.status != ContractStatus.PENDING_SIGNATURE:
            return False
        
        # Activate the contract (owner acceptance was implicit via approve_application)
        return self._activate_contract(contract)
    
    def _activate_contract(self, contract: VehicleContract) -> bool:
        """Activate a contract and create the authoritative driver-vehicle relationship."""
        if contract.status != ContractStatus.PENDING_SIGNATURE:
            return False
        
        # Activate contract
        contract.status = ContractStatus.ACTIVE
        contract.start_date = datetime.now(timezone.utc)
        
        # Create authoritative driver-vehicle relationship for Go-Live
        try:
            from app.transport.models import assign_driver_to_vehicle
            from app.transport.models import DriverProfile, Vehicle
            
            driver = db.session.get(DriverProfile, contract.driver_id)
            vehicle = db.session.get(Vehicle, contract.vehicle_id)
            
            if driver and vehicle:
                assign_driver_to_vehicle(
                    driver=driver,
                    vehicle=vehicle,
                    reason='marketplace_contract',
                    authorized_by=None,
                    notes=f"Created from marketplace contract {contract.id}"
                )
                logger.info(f"Contract activated and driver-vehicle relationship created: contract_id={contract.id}")
            else:
                logger.warning(f"Could not create driver-vehicle relationship: driver or vehicle not found")
        except Exception as e:
            logger.error(f"Failed to create driver-vehicle relationship: {e}")
            # Don't fail the contract activation if relationship creation fails
            # The relationship can be created manually later
        
        db.session.commit()
        return True
    
    # =========================================================================
    # MARKETPLACE DISCOVERY
    # =========================================================================
    
    def search_listings(
        self,
        driver_id: int,
        filters: Optional[Dict] = None
    ) -> List[VehicleMarketplaceListing]:
        """Search marketplace listings with filters"""
        filters = filters or {}
        
        query = VehicleMarketplaceListing.query.filter(
            VehicleMarketplaceListing.is_deleted == False,
            VehicleMarketplaceListing.listing_status == 'active'
        )
        
        # Apply filters
        if filters.get('vehicle_class'):
            query = query.filter(
                VehicleMarketplaceListing.required_vehicle_classes.contains([filters['vehicle_class']])
            )
        
        if filters.get('compensation_model'):
            query = query.filter(
                VehicleMarketplaceListing.compensation_model == filters['compensation_model']
            )
        
        if filters.get('min_revenue_share'):
            query = query.filter(
                VehicleMarketplaceListing.driver_revenue_share_pct >= filters['min_revenue_share']
            )
        
        if filters.get('max_rental'):
            query = query.filter(
                VehicleMarketplaceListing.fixed_rental_amount <= filters['max_rental']
            )
        
        # Exclude listings from driver's owned vehicles
        driver = DriverProfile.query.filter_by(
            user_id=driver_id, is_deleted=False
        ).first()
        if driver:
            owned_vehicle_ids = [v.id for v in driver.owned_vehicles or []]
            if owned_vehicle_ids:
                query = query.filter(~VehicleMarketplaceListing.vehicle_id.in_(owned_vehicle_ids))
        
        # Order by recently listed
        return query.order_by(desc(VehicleMarketplaceListing.listed_at)).all()
    
    def get_recommended_listings(
        self,
        driver_id: int,
        limit: int = 10
    ) -> List[VehicleMarketplaceListing]:
        """Get recommended listings for a driver.

        Tier eligibility is evaluated in Python using the canonical
        tier_order (same as _check_driver_eligibility) because a SQL
        string comparison on the enum does not match tier rank.
        """
        driver = DriverProfile.query.filter_by(user_id=driver_id, is_deleted=False).first()
        if not driver:
            return []

        tier_order = ("pending", "basic_verified", "platform_verified", "event_certified")
        driver_tier = self._normalize_tier(driver.verification_tier)
        if driver_tier not in tier_order:
            return []
        driver_rank = tier_order.index(driver_tier)

        # Candidate listings from SQL (no tier filter here — rank
        # comparison happens in Python below).
        query = VehicleMarketplaceListing.query.filter(
            VehicleMarketplaceListing.is_deleted == False,
            VehicleMarketplaceListing.listing_status == 'active',
        )

        # Exclude owned vehicles
        owned_ids = [v.id for v in driver.owned_vehicles or []]
        if owned_ids:
            query = query.filter(~VehicleMarketplaceListing.vehicle_id.in_(owned_ids))

        candidates = query.order_by(desc(VehicleMarketplaceListing.listed_at)).all()

        recommended = []
        for listing in candidates:
            required_tier = self._normalize_tier(listing.required_verification_tier)
            if required_tier not in tier_order:
                continue
            if tier_order.index(required_tier) <= driver_rank:
                recommended.append(listing)
                if len(recommended) >= limit:
                    break

        return recommended
    
    def get_listing_details(
        self,
        listing_id: int,
        driver_id: Optional[int] = None
    ) -> Optional[Dict]:
        """Get detailed listing information for display"""
        listing = VehicleMarketplaceListing.query.options(
            joinedload(VehicleMarketplaceListing.vehicle),
            joinedload(VehicleMarketplaceListing.owner)
        ).filter_by(id=listing_id, is_deleted=False).first()
        
        if not listing:
            return None
        
        # Check if driver already applied
        applied = False
        if driver_id:
            driver = DriverProfile.query.filter_by(user_id=driver_id, is_deleted=False).first()
            if driver:
                applied = DriverVehicleApplication.query.filter_by(
                    listing_id=listing_id, driver_id=driver.id, is_deleted=False
                ).first() is not None
        
        return {
            'listing': listing,
            'vehicle': listing.vehicle,
            'owner': listing.owner,
            'applied': applied,
            'applications_count': len(listing.applications) if listing.applications else 0,
        }
    
    # =========================================================================
    # EARNINGS & SETTLEMENTS
    # =========================================================================
    
    def calculate_driver_earnings(
        self,
        contract_id: int,
        period_start: datetime,
        period_end: datetime
    ) -> Dict[str, Any]:
        """Calculate driver earnings for a contract period"""
        contract = VehicleContract.query.filter_by(id=contract_id).first()
        if not contract:
            return {}
        
        # This would integrate with booking/payment services
        # For now, return placeholder
        return {
            'contract_id': contract_id,
            'period_start': period_start.isoformat(),
            'period_end': period_end.isoformat(),
            'total_revenue': 0.00,
            'driver_share_pct': float(contract.driver_revenue_share_pct),
            'driver_earnings': 0.00,
            'owner_revenue': 0.00,
        }
    
    def process_settlement(
        self,
        contract_id: int,
        period_end: datetime
    ) -> Dict[str, Any]:
        """Process a settlement for a contract"""
        contract = VehicleContract.query.filter_by(id=contract_id).first()
        if not contract:
            return {}
        
        # Placeholder for settlement logic
        return {
            'contract_id': contract_id,
            'settlement_date': datetime.now(timezone.utc).isoformat(),
            'period_end': period_end.isoformat(),
            'driver_payout': 0.00,
            'owner_revenue': 0.00,
        }
    
    def get_contract_earnings_summary(self, contract_id: int) -> Dict[str, Any]:
        """Get earnings summary for a contract"""
        contract = VehicleContract.query.filter_by(id=contract_id).first()
        if not contract:
            return {}
        
        return {
            'contract_id': contract_id,
            'total_driver_earnings': float(contract.total_driver_earnings or 0),
            'total_owner_revenue': float(contract.total_owner_revenue or 0),
            'driver_revenue_share_pct': float(contract.driver_revenue_share_pct),
            'last_settlement_date': contract.last_settlement_date.isoformat() if contract.last_settlement_date else None,
            'contract_type': contract.contract_type,
        }
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _verify_vehicle_ownership(self, vehicle: Vehicle, owner_id: int) -> bool:
        """Verify that a user owns a vehicle"""
        if vehicle.owner_type == 'driver':
            from app.transport.models import DriverProfile
            driver = DriverProfile.query.filter_by(user_id=owner_id, is_deleted=False).first()
            return driver and vehicle.owner_id == driver.id
        elif vehicle.owner_type == 'user':
            return vehicle.owner_id == owner_id
        elif vehicle.owner_type == 'organisation':
            # Check if user is org admin with transport permission
            organisation_user = db.session.get(User, owner_id)
            if organisation_user:
                organisation = db.session.get(Organisation, vehicle.owner_id)
                if organisation:
                    return OrganizationPermissionService.has_permission(
                        organisation_user, organisation, 'org.transport.manage'
                    )
            return False
        return False


# Singleton getter
_marketplace_service = None


def get_marketplace_service() -> VehicleMarketplaceService:
    """Get or create the marketplace service singleton"""
    global _marketplace_service
    if _marketplace_service is None:
        _marketplace_service = VehicleMarketplaceService()
    return _marketplace_service