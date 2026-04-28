# app/transport/services/provider_service.py
"""
AFCON360 Transport Module - Provider Service with Identity Verification
Single source of truth for identity management
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
import hashlib
import secrets
import json
import uuid
import logging
from functools import wraps
from flask import current_app, request
from sqlalchemy import or_, and_, func, text, case
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload, load_only

from app.extensions import db, redis_client, cache
from app.admin.models import ContentFlag
from app.transport.models import (
    DriverProfile, OrganisationTransportProfile, Vehicle, ScheduledRoute,
    VerificationTier, ComplianceStatus, TransportSetting, Booking, BookingStatus,
    Rating, organisation_drivers, VehicleClass, ProviderType, ServiceType
)
from app.transport.services.settings_service import (
    SettingsService, feature_enabled, development_only
)
from app.utils.exceptions import (
    ValidationError, NotFoundError, PermissionError,
    RateLimitError, ServiceUnavailableError, ConflictError
)

from app.utils.security import (
    sanitize_input, encrypt_field, decrypt_field,
    generate_secure_token, verify_permission, require_permission
)

from app.utils.validators import (
    validate_driver_registration, validate_vehicle_registration,
    validate_organisation_transport, validate_booking_request,
    validate_payment, validate_rating,
)

from app.utils.monitoring import (
    monitor_endpoint, record_metric, start_span,
    track_operation, with_circuit_breaker
)
from app.utils.caching import (
    cached_query, invalidate_cache_pattern,
    with_cache_lock, cache_invalidate_on_change
)
from app.utils.rate_limiting import rate_limit
from app.utils.idempotency import idempotent_request
from app.utils.audit import audit_log

# Create module-level logger
logger = logging.getLogger(__name__)


def _assert_no_open_flags(entity_type: str, entity_id: int):
    """Raise ValueError if the entity has any unresolved ContentFlag records."""
    count = ContentFlag.query.filter_by(
        entity_type=entity_type,
        entity_id=entity_id,
        status="open",
    ).count()
    if count:
        raise ValueError(
            f"Cannot activate {entity_type} {entity_id}: open flags must be resolved first."
        )


class ProviderService:
    """Service for managing transport providers with identity-first approach"""

    CACHE_PREFIX = "transport:provider"
    DRIVER_CACHE_TTL = 300
    VEHICLE_CACHE_TTL = 600

    def __init__(self):
        """Initialize provider service"""
        self.cache_prefix = self.CACHE_PREFIX
        self.driver_cache_ttl = self.DRIVER_CACHE_TTL
        self.vehicle_cache_ttl = self.VEHICLE_CACHE_TTL
        logger.debug("ProviderService initialized")

    # ===========================================================================
    # IDENTITY VERIFICATION METHODS
    # ===========================================================================

    def get_user_identity(self, user_id: int) -> Dict[str, Any]:
        """
        Get verified user identity from central identity service
        """
        try:
            # Use identity service as single source of truth
            from app.identity.services.identity_service import IdentityService

            identity = IdentityService.get_verified_identity(user_id)
            if not identity:
                raise NotFoundError(
                    message="User identity not found",
                    resource_type="user",
                    resource_id=user_id,
                    code="IDENTITY_NOT_FOUND"
                )

            return {
                'user_id': user_id,
                'identity_verified': identity.get('identity_verified', False),
                'email_verified': identity.get('email_verified', False),
                'phone_verified': identity.get('phone_verified', False),
                'kyc_status': identity.get('kyc_status', 'pending'),
                'age': identity.get('age'),
                'has_criminal_record': identity.get('has_criminal_record', False),
                'account_status': identity.get('account_status', 'active'),
                'profile': {
                    'name': identity.get('name'),
                    'email': identity.get('email'),
                    'phone': identity.get('phone'),
                    'birth_year': identity.get('birth_year')
                }
            }

        except ImportError:
            # Fallback for development - mock identity service
            logger.warning("IdentityService not found, using mock data")
            return {
                'user_id': user_id,
                'identity_verified': True,
                'email_verified': True,
                'phone_verified': True,
                'kyc_status': 'verified',
                'age': 25,
                'has_criminal_record': False,
                'account_status': 'active',
                'profile': {
                    'name': f'Test User {user_id}',
                    'email': f'user{user_id}@example.com',
                    'phone': f'+1234567890{user_id}',
                    'birth_year': 1995
                }
            }
        except Exception as e:
            logger.error(f"Error getting user identity: {e}", exc_info=True)
            raise ServiceUnavailableError(
                message="Identity service unavailable",
                code="IDENTITY_SERVICE_UNAVAILABLE"
            )

    def validate_driver_eligibility(self, user_id: int) -> Dict[str, Any]:
        """
        Validate if user is eligible to register as driver
        """
        # Get identity from single source of truth
        identity = self.get_user_identity(user_id)

        # Check identity verification
        if not identity['identity_verified']:
            raise ValidationError(
                message="Identity not verified",
                details={'identity_verified': False},
                code="IDENTITY_NOT_VERIFIED"
            )

        # Check email verification
        if not identity['email_verified']:
            raise ValidationError(
                message="Email not verified",
                details={'email_verified': False},
                code="EMAIL_NOT_VERIFIED"
            )

        # Check phone verification (if required)
        if SettingsService.is_feature_enabled('require_phone_verification') and not identity['phone_verified']:
            raise ValidationError(
                message="Phone not verified",
                details={'phone_verified': False},
                code="PHONE_NOT_VERIFIED"
            )

        # Check age requirement
        min_driver_age = SettingsService.get_setting('min_driver_age', 21)
        if identity.get('age') and identity['age'] < min_driver_age:
            raise ValidationError(
                message=f"Must be at least {min_driver_age} years old",
                details={'age': identity['age'], 'minimum_age': min_driver_age},
                code="AGE_REQUIREMENT_NOT_MET"
            )

        # Check criminal record
        if SettingsService.is_feature_enabled('check_criminal_record') and identity.get('has_criminal_record'):
            raise ValidationError(
                message="Cannot register due to criminal record",
                details={'has_criminal_record': True},
                code="CRIMINAL_RECORD_FOUND"
            )

        # Check account status
        if identity.get('account_status') != 'active':
            raise ValidationError(
                message="Account is not active",
                details={'account_status': identity.get('account_status')},
                code="ACCOUNT_NOT_ACTIVE"
            )

        return {
            'eligible': True,
            'identity': identity
        }

    def get_organisation_identity(self, organisation_id: int) -> Dict[str, Any]:
        """
        Get organisation identity from central registry
        """
        try:
            from app.organisation.services.registry_service import OrganisationRegistry

            org_identity = OrganisationRegistry.get_organisation(organisation_id)
            if not org_identity:
                raise NotFoundError(
                    message="Organisation not found",
                    resource_type="organisation",
                    resource_id=organisation_id,
                    code="ORGANISATION_NOT_FOUND"
                )

            return {
                'organisation_id': organisation_id,
                'verified': org_identity.get('verified', False),
                'business_registered': org_identity.get('business_registered', False),
                'status': org_identity.get('status', 'inactive'),
                'profile': {
                    'name': org_identity.get('name'),
                    'type': org_identity.get('type'),
                    'registration_number': org_identity.get('registration_number')
                }
            }

        except ImportError:
            # Fallback for development
            logger.warning("OrganisationRegistry not found, using mock data")
            return {
                'organisation_id': organisation_id,
                'verified': True,
                'business_registered': True,
                'status': 'active',
                'profile': {
                    'name': f'Test Organisation {organisation_id}',
                    'type': 'hotel_fleet',
                    'registration_number': f'REG{organisation_id}'
                }
            }

    def validate_organisation_eligibility(self, organisation_id: int) -> Dict[str, Any]:
        """
        Validate if organisation is eligible for transport registration
        """
        org_identity = self.get_organisation_identity(organisation_id)

        # Check organisation status
        if org_identity['status'] != 'active':
            raise ValidationError(
                message=f"Organisation is not active (status: {org_identity['status']})",
                details={'status': org_identity['status']},
                code="ORGANISATION_NOT_ACTIVE"
            )

        # Check verification status
        if SettingsService.is_feature_enabled('require_organisation_verification') and not org_identity['verified']:
            raise ValidationError(
                message="Organisation not verified",
                details={'verified': False},
                code="ORGANISATION_NOT_VERIFIED"
            )

        # Check business registration
        if not org_identity['business_registered']:
            raise ValidationError(
                message="Organisation not legally registered",
                details={'business_registered': False},
                code="BUSINESS_NOT_REGISTERED"
            )

        return {
            'eligible': True,
            'organisation': org_identity
        }

    # ===========================================================================
    # COUNT METHODS (For Admin Dashboard)
    # ===========================================================================

    def count_pending_drivers(self) -> int:
        """Count drivers pending approval"""
        try:
            return DriverProfile.query.filter_by(
                verification_tier='pending',
                is_deleted=False
            ).count()
        except Exception as e:
            logger.error(f"Error counting pending drivers: {e}", exc_info=True)
            return 0

    def count_pending_vehicles(self) -> int:
        """Count vehicles pending approval"""
        try:
            return Vehicle.query.filter_by(
                status='pending',
                is_deleted=False
            ).count()
        except Exception as e:
            logger.error(f"Error counting pending vehicles: {e}", exc_info=True)
            return 0

    def count_active_drivers(self) -> int:
        """Count active drivers (online and available)"""
        try:
            return DriverProfile.query.filter_by(
                is_online=True,
                is_available=True,
                is_deleted=False
            ).count()
        except Exception as e:
            logger.error(f"Error counting active drivers: {e}", exc_info=True)
            return 0

    def count_available_vehicles(self) -> int:
        """Count available vehicles"""
        try:
            return Vehicle.query.filter_by(
                is_available=True,
                is_deleted=False
            ).count()
        except Exception as e:
            logger.error(f"Error counting available vehicles: {e}", exc_info=True)
            return 0

    def count_total_drivers(self) -> int:
        """Count total drivers"""
        try:
            return DriverProfile.query.filter_by(is_deleted=False).count()
        except Exception as e:
            logger.error(f"Error counting total drivers: {e}", exc_info=True)
            return 0

    def count_approved_drivers(self) -> int:
        """Count approved drivers"""
        try:
            return DriverProfile.query.filter_by(
                compliance_status=ComplianceStatus.APPROVED,
                is_deleted=False
            ).count()
        except Exception as e:
            logger.error(f"Error counting approved drivers: {e}", exc_info=True)
            return 0

    def count_total_vehicles(self) -> int:
        """Count total vehicles"""
        try:
            return Vehicle.query.filter_by(is_deleted=False).count()
        except Exception as e:
            logger.error(f"Error counting total vehicles: {e}", exc_info=True)
            return 0

    # ===========================================================================
    # GET METHODS
    # ===========================================================================

    def get_driver(self, driver_id: int) -> Optional[DriverProfile]:
        """Get driver by ID"""
        try:
            return DriverProfile.query.get(driver_id)
        except Exception as e:
            logger.error(f"Error getting driver {driver_id}: {e}", exc_info=True)
            return None

    def get_driver_profile(self, user_id: int) -> Optional[DriverProfile]:
        """Get driver profile by user ID"""
        try:
            return DriverProfile.query.filter_by(
                user_id=user_id,
                is_deleted=False
            ).first()
        except Exception as e:
            logger.error(f"Error getting driver profile for user {user_id}: {e}", exc_info=True)
            return None

    def get_driver_rating(self, driver_id: int) -> float:
        """Get driver's average rating"""
        try:
            driver = DriverProfile.query.get(driver_id)
            if driver:
                return float(driver.average_rating) if driver.average_rating else 0.0
            return 0.0
        except Exception as e:
            logger.error(f"Error getting driver rating: {e}", exc_info=True)
            return 0.0

    def get_driver_vehicle(self, driver_id: int) -> Optional[Dict[str, Any]]:
        """Get driver's current vehicle"""
        try:
            driver = DriverProfile.query.get(driver_id)
            if driver and driver.current_vehicle:
                return {
                    'id': driver.current_vehicle.id,
                    'license_plate': driver.current_vehicle.license_plate,
                    'make': driver.current_vehicle.make,
                    'model': driver.current_vehicle.model,
                    'vehicle_class': driver.current_vehicle.vehicle_class.value
                }
            return None
        except Exception as e:
            logger.error(f"Error getting driver vehicle: {e}", exc_info=True)
            return None

    def get_driver_online_status(self, driver_id: int) -> bool:
        """Get driver's online status"""
        try:
            driver = DriverProfile.query.get(driver_id)
            return driver.is_online if driver else False
        except Exception as e:
            logger.error(f"Error getting driver online status: {e}", exc_info=True)
            return False

    def get_driver_availability(self, driver_id: int) -> bool:
        """Get driver's availability"""
        try:
            driver = DriverProfile.query.get(driver_id)
            return driver.is_available if driver else False
        except Exception as e:
            logger.error(f"Error getting driver availability: {e}", exc_info=True)
            return False

    def get_vehicle(self, vehicle_id: int) -> Optional[Vehicle]:
        """Get vehicle by ID"""
        try:
            return Vehicle.query.get(vehicle_id)
        except Exception as e:
            logger.error(f"Error getting vehicle {vehicle_id}: {e}", exc_info=True)
            return None

    def get_user_vehicles(self, user_id: int) -> List[Vehicle]:
        """Get vehicles owned by user"""
        try:
            return Vehicle.query.filter_by(
                owner_type='user',
                owner_id=user_id,
                is_deleted=False
            ).all()
        except Exception as e:
            logger.error(f"Error getting vehicles for user {user_id}: {e}", exc_info=True)
            return []

    # ===========================================================================
    # LIST METHODS
    # ===========================================================================

    def list_drivers(self, page: int = 1, per_page: int = 25,
                     status: Optional[str] = None) -> Dict[str, Any]:
        """List drivers with pagination"""
        try:
            query = DriverProfile.query.filter_by(is_deleted=False)

            if status:
                query = query.filter_by(compliance_status=status)

            paginated = query.order_by(
                DriverProfile.created_at.desc()
            ).paginate(page=page, per_page=per_page, error_out=False)

            return {
                'items': [d.to_dict() for d in paginated.items],
                'total': paginated.total,
                'page': page,
                'per_page': per_page,
                'pages': paginated.pages
            }
        except Exception as e:
            logger.error(f"Error listing drivers: {e}", exc_info=True)
            return {
                'items': [],
                'total': 0,
                'page': page,
                'per_page': per_page,
                'pages': 0
            }

    def list_vehicles(self, page: int = 1, per_page: int = 25,
                      status: Optional[str] = None) -> Dict[str, Any]:
        """List vehicles with pagination"""
        try:
            query = Vehicle.query.filter_by(is_deleted=False)

            if status:
                query = query.filter_by(status=status)

            paginated = query.order_by(
                Vehicle.created_at.desc()
            ).paginate(page=page, per_page=per_page, error_out=False)

            return {
                'items': [v.to_dict() for v in paginated.items],
                'total': paginated.total,
                'page': page,
                'per_page': per_page,
                'pages': paginated.pages
            }
        except Exception as e:
            logger.error(f"Error listing vehicles: {e}", exc_info=True)
            return {
                'items': [],
                'total': 0,
                'page': page,
                'per_page': per_page,
                'pages': 0
            }

    # ===========================================================================
    # DRIVER REGISTRATION
    # ===========================================================================

    @monitor_endpoint("register_driver")
    @rate_limit("provider_registration", limit=10, period=3600)
    @feature_enabled('provider_onboarding_enabled')
    @require_permission('provider:register')
    @idempotent_request('driver_registration', ttl=3600)
    def register_driver(self, user_id: int, driver_data: Dict[str, Any],
                        request_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Register a user as a driver after identity verification
        """
        span = start_span("register_driver")
        span.set_attribute("user.id", user_id)

        try:
            # PHASE 1: IDENTITY VERIFICATION
            eligibility = self.validate_driver_eligibility(user_id)

            # PHASE 2: VALIDATE DRIVER DATA
            sanitized_data = sanitize_input(driver_data)
            validation_result = validate_driver_registration(sanitized_data)

            if not validation_result['valid']:
                raise ValidationError(
                    message="Driver registration validation failed",
                    details=validation_result['errors'],
                    code="VALIDATION_FAILED"
                )

            # PHASE 3: CHECK FOR EXISTING REGISTRATION
            with with_cache_lock(f"lock:driver_registration:{user_id}", timeout=10):
                existing = DriverProfile.query.filter_by(
                    user_id=user_id,
                    is_deleted=False
                ).first()

                if existing:
                    raise ConflictError(
                        message="User is already registered as a driver",
                        resource_type="driver",
                        resource_id=user_id,
                        code="ALREADY_REGISTERED"
                    )

                # PHASE 4: PROCEED WITH REGISTRATION
                # Guard: cannot activate driver if there are open ContentFlag records
                _assert_no_open_flags("driver", user_id)

                db.session.begin_nested()

                # Get settings
                auto_approve = SettingsService.is_feature_enabled('auto_approve_providers')
                require_license = SettingsService.is_feature_enabled('require_license_verification')
                require_police = SettingsService.is_feature_enabled('require_police_clearance')

                # Encrypt sensitive data
                license_number = sanitized_data.get('license_number')
                if license_number and SettingsService.is_feature_enabled('data_encryption_enabled'):
                    license_number = encrypt_field(license_number)

                # Create driver profile
                driver = DriverProfile(
                    user_id=user_id,
                    license_number=license_number,
                    license_verified=auto_approve and bool(license_number) and not require_license,
                    license_expiry=sanitized_data.get('license_expiry'),
                    police_clearance_verified=auto_approve and bool(
                        sanitized_data.get('police_clearance_number')) and not require_police,
                    police_clearance_date=sanitized_data.get('police_clearance_date'),
                    verification_tier=VerificationTier.BASIC_VERIFIED if auto_approve else VerificationTier.PENDING,
                    compliance_status=ComplianceStatus.APPROVED if auto_approve else ComplianceStatus.PENDING_REVIEW,
                    languages_spoken=sanitized_data.get('languages_spoken', ['en']),
                    vehicle_classes=sanitized_data.get('vehicle_classes', [VehicleClass.COMFORT.value]),
                    service_types=sanitized_data.get('service_types', [ServiceType.ON_DEMAND.value]),
                    operational_zones=sanitized_data.get('operational_zones', ['general']),
                    preferred_zones=sanitized_data.get('preferred_zones', []),
                    max_passenger_capacity=sanitized_data.get('passenger_capacity', 4),
                    max_luggage_capacity=sanitized_data.get('luggage_capacity', 2),
                    is_online=auto_approve,
                    is_available=False,
                    auto_accept_bookings=False,
                    commission_rate=Decimal('15.00'),
                    emergency_contact_name=sanitized_data.get('emergency_contact_name'),
                    emergency_contact_phone=sanitized_data.get('emergency_contact_phone'),
                    emergency_contact_relationship=sanitized_data.get('emergency_contact_relationship'),
                    metadata={
                        'identity_verified': eligibility['identity']['identity_verified'],
                        'email_verified': eligibility['identity']['email_verified'],
                        'phone_verified': eligibility['identity']['phone_verified'],
                        'registration_source': sanitized_data.get('registration_source', 'web'),
                        'ip_address': request.remote_addr if request else None,
                        'request_id': request_id
                    }
                )

                db.session.add(driver)
                db.session.flush()

                # Create audit log
                audit_log(
                    action='driver_registered',
                    entity_type='driver',
                    entity_id=driver.id,
                    user_id=user_id,
                    details={
                        'auto_approved': auto_approve,
                        'identity_check': eligibility,
                        'verification_tier': driver.verification_tier.value
                    },
                    request_id=request_id
                )

                # Register vehicle if provided
                if sanitized_data.get('vehicle_data'):
                    vehicle_result = self.register_vehicle_internal(
                        owner_type='user',
                        owner_id=user_id,
                        vehicle_data=sanitized_data['vehicle_data'],
                        driver_id=driver.id,
                        request_id=request_id
                    )

                    if vehicle_result['success']:
                        driver.vehicle_id = vehicle_result['vehicle_id']

                db.session.commit()

                # Invalidate caches
                self._invalidate_provider_caches()

                # Return response
                response = {
                    'success': True,
                    'message': 'Driver registered successfully',
                    'data': {
                        'driver_id': driver.id,
                        'driver_code': driver.driver_code,
                        'verification_tier': driver.verification_tier.value,
                        'compliance_status': driver.compliance_status.value,
                        'auto_approved': auto_approve,
                        'requires_verification': require_license or require_police,
                        'identity_verified': eligibility['identity']['identity_verified'],
                        'next_steps': self._get_next_steps(driver)
                    },
                    'metadata': {
                        'request_id': request_id,
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    }
                }

                span.set_status("OK")
                return response

        except (ValidationError, ConflictError, RateLimitError, NotFoundError) as e:
            db.session.rollback()
            span.set_status("ERROR", str(e))
            record_metric('driver_registration', tags={'status': 'failed', 'error_type': type(e).__name__}, value=1)
            raise

        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Database error in driver registration: {e}", exc_info=True)
            span.set_status("ERROR", f"Database error: {str(e)}")
            record_metric('driver_registration', tags={'status': 'failed', 'error_type': 'database'}, value=1)
            raise ServiceUnavailableError(
                message="Registration service temporarily unavailable",
                code="SERVICE_UNAVAILABLE"
            )

        except Exception as e:
            db.session.rollback()
            logger.error(f"Unexpected error in driver registration: {e}", exc_info=True)
            span.set_status("ERROR", f"Unexpected error: {str(e)}")
            record_metric('driver_registration', tags={'status': 'failed', 'error_type': 'unexpected'}, value=1)
            raise

        finally:
            span.end()

    # ===========================================================================
    # VEHICLE REGISTRATION
    # ===========================================================================

    def register_vehicle_internal(self, owner_type: str, owner_id: int, vehicle_data: Dict[str, Any],
                                  driver_id: Optional[int] = None,
                                  organisation_id: Optional[int] = None,
                                  request_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Internal method for vehicle registration
        """
        try:
            # Validate vehicle data
            sanitized_data = sanitize_input(vehicle_data)
            validation_result = validate_vehicle_registration(sanitized_data)

            if not validation_result['valid']:
                return {
                    'success': False,
                    'error': 'Vehicle validation failed',
                    'details': validation_result['errors']
                }

            # Generate identifiers
            qr_hash = self._generate_vehicle_qr_code(owner_type, owner_id, sanitized_data)
            verification_code = secrets.token_hex(3).upper()

            # Create vehicle
            vehicle = Vehicle(
                owner_type=owner_type,
                owner_id=owner_id,
                license_plate=sanitized_data.get('license_plate', '').upper().strip() or
                              self._generate_temporary_plate(),
                make=sanitized_data.get('make', 'Unknown').title(),
                model=sanitized_data.get('model', 'Unknown').title(),
                year=sanitized_data.get('year', datetime.now().year),
                vehicle_type=sanitized_data.get('vehicle_type', 'sedan'),
                vehicle_class=VehicleClass(sanitized_data.get('vehicle_class', VehicleClass.COMFORT.value)),
                passenger_capacity=sanitized_data.get('passenger_capacity', 4),
                luggage_capacity=sanitized_data.get('luggage_capacity', 2),
                insurance_verified=not SettingsService.is_feature_enabled('require_insurance_verification'),
                qr_code_hash=qr_hash,
                verification_code=verification_code,
                is_trackable=SettingsService.is_feature_enabled('enable_live_tracking'),
                status='active',
                is_available=True,
                metadata={
                    'registered_internal': True,
                    'request_id': request_id
                }
            )

            # Link to driver if provided
            if driver_id and owner_type == 'user':
                vehicle.current_driver_id = driver_id

            db.session.add(vehicle)
            db.session.flush()

            return {
                'success': True,
                'vehicle_id': vehicle.id,
                'qr_code_hash': vehicle.qr_code_hash,
                'verification_code': vehicle.verification_code
            }

        except Exception as e:
            logger.error(f"Error in internal vehicle registration: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }

    @monitor_endpoint("register_vehicle")
    @rate_limit("vehicle_registration", limit=20, period=3600)
    @require_permission('vehicle:register')
    def register_vehicle(self, owner_type: str, owner_id: int, vehicle_data: Dict[str, Any],
                         request_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Public API for vehicle registration with ownership verification
        """
        span = start_span("register_vehicle")

        try:
            # Verify ownership
            if owner_type == 'user':
                # Check if user is a registered driver
                driver = DriverProfile.query.filter_by(
                    user_id=owner_id,
                    is_deleted=False
                ).first()

                if not driver:
                    raise ValidationError(
                        message="User must be a registered driver",
                        code="NOT_A_DRIVER"
                    )

                if driver.compliance_status != ComplianceStatus.APPROVED:
                    raise ValidationError(
                        message="Driver must be approved to register vehicles",
                        details={'compliance_status': driver.compliance_status.value},
                        code="DRIVER_NOT_APPROVED"
                    )
            else:  # organisation
                org_profile = OrganisationTransportProfile.query.filter_by(
                    organisation_id=owner_id,
                    is_deleted=False
                ).first()

                if not org_profile:
                    raise ValidationError(
                        message="Organisation must have transport profile",
                        code="NO_TRANSPORT_PROFILE"
                    )

            # Guard: cannot register vehicle if there are open ContentFlag records
            _assert_no_open_flags("vehicle", owner_id)

            # Use internal method for registration
            result = self.register_vehicle_internal(
                owner_type=owner_type,
                owner_id=owner_id,
                vehicle_data=vehicle_data,
                request_id=request_id
            )

            if not result['success']:
                raise ValidationError(
                    message="Vehicle registration failed",
                    details=result.get('details', {}),
                    code="VEHICLE_REGISTRATION_FAILED"
                )

            # Commit transaction
            db.session.commit()

            # Cache the vehicle
            cache.set(
                f"{self.cache_prefix}:vehicle:{result['vehicle_id']}",
                result,
                timeout=self.vehicle_cache_ttl
            )

            response = {
                'success': True,
                'message': 'Vehicle registered successfully',
                'data': result,
                'metadata': {
                    'request_id': request_id,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            }

            span.set_status("OK")
            return response

        except (ValidationError, ConflictError) as e:
            db.session.rollback()
            span.set_status("ERROR", str(e))
            record_metric('vehicle_registration', tags={'status': 'failed', 'error_type': type(e).__name__}, value=1)
            raise

        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Database error: {e}", exc_info=True)
            span.set_status("ERROR", f"Database error: {str(e)}")
            record_metric('vehicle_registration', tags={'status': 'failed', 'error_type': 'database'}, value=1)
            raise ServiceUnavailableError(
                message="Vehicle registration service unavailable",
                code="SERVICE_UNAVAILABLE"
            )

        finally:
            span.end()

    # ===========================================================================
    # ORGANISATION TRANSPORT REGISTRATION
    # ===========================================================================

    @monitor_endpoint("register_organisation_transport")
    @rate_limit("organisation_registration", limit=5, period=3600)
    @feature_enabled('provider_onboarding_enabled')
    @require_permission('organisation:register_transport')
    @idempotent_request('organisation_transport_registration', ttl=3600)
    def register_organisation_transport(self, organisation_id: int, data: Dict[str, Any],
                                        user_id: Optional[int] = None,
                                        request_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Register organisation for transport services
        """
        span = start_span("register_organisation_transport")
        span.set_attribute("organisation.id", organisation_id)

        try:
            # Verify organisation eligibility
            eligibility = self.validate_organisation_eligibility(organisation_id)

            # Validate transport data
            sanitized_data = sanitize_input(data)
            validation_result = validate_organisation_transport(sanitized_data)

            if not validation_result['valid']:
                raise ValidationError(
                    message="Organisation transport validation failed",
                    details=validation_result['errors'],
                    code="VALIDATION_FAILED"
                )

            # Check for existing registration
            with with_cache_lock(f"lock:org_transport:{organisation_id}", timeout=10):
                existing = OrganisationTransportProfile.query.filter_by(
                    organisation_id=organisation_id,
                    is_deleted=False
                ).first()

                if existing:
                    raise ConflictError(
                        message="Organisation already registered for transport",
                        resource_type="organisation_transport",
                        resource_id=organisation_id,
                        code="ALREADY_REGISTERED"
                    )

                # Guard: cannot register organisation transport if there are open ContentFlag records
                _assert_no_open_flags("organisation_transport", organisation_id)

                # Begin registration
                db.session.begin_nested()

                auto_approve = SettingsService.is_feature_enabled('auto_approve_providers')
                require_insurance = SettingsService.is_feature_enabled('require_insurance_verification')

                # Create organisation transport profile
                profile = OrganisationTransportProfile(
                    organisation_id=organisation_id,
                    registration_type=sanitized_data['registration_type'],
                    business_license_number=sanitized_data.get('business_license_number'),
                    tax_identification_number=sanitized_data.get('tax_identification_number'),
                    compliance_status=ComplianceStatus.APPROVED if auto_approve else ComplianceStatus.PENDING_REVIEW,
                    license_verified=auto_approve and bool(sanitized_data.get('transport_license_number')),
                    insurance_verified=auto_approve and bool(
                        sanitized_data.get('insurance_policy_number')) and not require_insurance,
                    insurance_expiry=sanitized_data.get('insurance_expiry'),
                    insurance_coverage_amount=sanitized_data.get('insurance_coverage_amount'),
                    can_provide_airport_transfers=sanitized_data.get('can_provide_airport_transfers', False),
                    can_provide_stadium_shuttles=sanitized_data.get('can_provide_stadium_shuttles', False),
                    can_provide_hotel_transfers=sanitized_data.get('can_provide_hotel_transfers', False),
                    can_provide_city_tours=sanitized_data.get('can_provide_city_tours', False),
                    can_provide_on_demand=False,
                    fleet_size=sanitized_data.get('fleet_size', 0),
                    operational_zones=sanitized_data.get('operational_zones', []),
                    languages_supported=sanitized_data.get('languages_supported', ['en']),
                    service_hours=sanitized_data.get('service_hours', {
                        'default': {'start': '06:00', 'end': '22:00'}
                    }),
                    transport_manager_name=sanitized_data.get('transport_manager_name'),
                    transport_manager_phone=sanitized_data.get('transport_manager_phone'),
                    transport_manager_email=sanitized_data.get('transport_manager_email'),
                    commission_rate=Decimal(sanitized_data.get('commission_rate', '12.00')),
                    payment_terms_days=sanitized_data.get('payment_terms_days', 7),
                    accepts_bookings=auto_approve,
                    metadata={
                        'registered_by': user_id,
                        'organisation_verified': eligibility['organisation']['verified'],
                        'request_id': request_id
                    }
                )

                db.session.add(profile)
                db.session.flush()

                # Register vehicles
                registered_vehicles = []
                for vehicle_data in sanitized_data.get('vehicles', []):
                    vehicle_result = self.register_vehicle_internal(
                        owner_type='organisation',
                        owner_id=organisation_id,
                        vehicle_data=vehicle_data,
                        organisation_id=profile.id,
                        request_id=request_id
                    )

                    if vehicle_result['success']:
                        registered_vehicles.append(vehicle_result['vehicle_id'])

                # Update fleet stats
                if registered_vehicles:
                    profile.fleet_size = len(registered_vehicles)
                    profile.available_fleet_size = len(registered_vehicles)

                db.session.commit()

                # Invalidate caches
                self._invalidate_provider_caches()

                response = {
                    'success': True,
                    'message': 'Organisation transport registered successfully',
                    'data': {
                        'profile_id': profile.id,
                        'registration_type': profile.registration_type,
                        'compliance_status': profile.compliance_status.value,
                        'fleet_size': profile.fleet_size,
                        'auto_approved': auto_approve,
                        'organisation_verified': eligibility['organisation']['verified'],
                        'vehicles_registered': len(registered_vehicles)
                    },
                    'metadata': {
                        'request_id': request_id,
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    }
                }

                span.set_status("OK")
                return response

        except (ValidationError, ConflictError, NotFoundError) as e:
            db.session.rollback()
            span.set_status("ERROR", str(e))
            record_metric('organisation_transport_registration',
                          tags={'status': 'failed', 'error_type': type(e).__name__},
                          value=1)
            raise

        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Database error: {e}", exc_info=True)
            span.set_status("ERROR", f"Database error: {str(e)}")
            record_metric('organisation_transport_registration',
                          tags={'status': 'failed', 'error_type': 'database'},
                          value=1)
            raise ServiceUnavailableError(
                message="Registration service unavailable",
                code="SERVICE_UNAVAILABLE"
            )

        finally:
            span.end()

    # ===========================================================================
    # DRIVER STATUS MANAGEMENT
    # ===========================================================================

    @monitor_endpoint("update_driver_status")
    @rate_limit("driver_status_update", limit=60, period=60)
    @require_permission('driver:update_status')
    def update_driver_status(self, driver_id: int, status_data: Dict[str, Any],
                             user_id: Optional[int] = None) -> Dict[str, Any]:
        """Update driver status"""
        try:
            driver = DriverProfile.query.get(driver_id)
            if not driver:
                raise NotFoundError(
                    message="Driver not found",
                    resource_type="driver",
                    resource_id=driver_id
                )

            # Verify permission
            if user_id and driver.user_id != user_id:
                raise PermissionError(
                    message="Cannot update another driver's status",
                    code="PERMISSION_DENIED"
                )

            updates = {}

            if 'is_online' in status_data:
                driver.is_online = bool(status_data['is_online'])
                driver.last_seen_at = datetime.now(timezone.utc)
                updates['is_online'] = driver.is_online

            if 'is_available' in status_data:
                if bool(status_data['is_available']) and not driver.is_online:
                    raise ValidationError(
                        message="Driver must be online to become available",
                        code="INVALID_STATUS_TRANSITION"
                    )
                driver.is_available = bool(status_data['is_available'])
                updates['is_available'] = driver.is_available

            db.session.commit()

            # Invalidate driver cache
            self._invalidate_driver_caches(driver_id)
            self._invalidate_available_drivers_cache()

            return {
                'success': True,
                'message': 'Driver status updated',
                'data': {
                    'driver_id': driver_id,
                    'updates': updates
                }
            }

        except (NotFoundError, PermissionError, ValidationError) as e:
            db.session.rollback()
            raise

        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Database error: {e}", exc_info=True)
            raise ServiceUnavailableError(
                message="Status update service unavailable",
                code="SERVICE_UNAVAILABLE"
            )

    # ===========================================================================
    # AVAILABLE DRIVERS QUERY
    # ===========================================================================

    @cached_query(lambda self, zone, vehicle_class, limit, **kwargs:
                  f"{self.cache_prefix}:available_drivers:{zone}:{vehicle_class}:{limit}")
    def get_available_drivers(self, zone: Optional[str] = None,
                              vehicle_class: Optional[str] = None,
                              limit: int = 20) -> List[Dict[str, Any]]:
        """Get available drivers"""
        try:
            query = DriverProfile.query.options(
                joinedload(DriverProfile.user).load_only('id', 'name', 'phone'),
                joinedload(DriverProfile.current_vehicle)
            ).filter(
                DriverProfile.is_active == True,
                DriverProfile.is_online == True,
                DriverProfile.is_available == True,
                DriverProfile.compliance_status == ComplianceStatus.APPROVED
            )

            if zone:
                query = query.filter(
                    DriverProfile.operational_zones.contains([zone])
                )

            if vehicle_class:
                query = query.filter(
                    DriverProfile.vehicle_classes.contains([vehicle_class])
                )

            drivers = query.limit(limit).all()

            return [
                {
                    'driver_id': driver.id,
                    'driver_code': driver.driver_code,
                    'user': {
                        'name': driver.user.name if driver.user else 'Unknown',
                        'phone': driver.user.phone if driver.user else None
                    },
                    'vehicle': {
                        'license_plate': driver.current_vehicle.license_plate if driver.current_vehicle else None,
                        'vehicle_class': driver.current_vehicle.vehicle_class.value if driver.current_vehicle else None
                    },
                    'rating': float(driver.average_rating) if driver.average_rating else 0.0
                }
                for driver in drivers
            ]

        except Exception as e:
            logger.error(f"Error getting available drivers: {e}", exc_info=True)
            return []

    # ===========================================================================
    # HELPER METHODS
    # ===========================================================================

    def _generate_vehicle_qr_code(self, owner_type: str, owner_id: int,
                                  vehicle_data: Dict[str, Any]) -> str:
        """Generate QR code hash for vehicle"""
        unique_data = f"{owner_type}:{owner_id}:{vehicle_data.get('license_plate', '')}:{secrets.token_hex(16)}"
        return hashlib.sha256(unique_data.encode()).hexdigest()

    def _generate_temporary_plate(self) -> str:
        """Generate temporary license plate"""
        import string
        random_part = ''.join(secrets.choice(string.ascii_uppercase + string.digits)
                              for _ in range(6))
        return f"TEMP-{random_part}"

    def _get_next_steps(self, driver: DriverProfile) -> List[Dict[str, Any]]:
        """Get next steps for driver"""
        steps = []

        if driver.verification_tier == VerificationTier.PENDING:
            steps.append({
                'step': 'complete_verification',
                'title': 'Complete Verification',
                'priority': 'high'
            })

        if not driver.vehicle_id:
            steps.append({
                'step': 'register_vehicle',
                'title': 'Register Vehicle',
                'priority': 'high'
            })

        steps.append({
            'step': 'set_availability',
            'title': 'Set Availability',
            'priority': 'low'
        })

        return steps

    def _invalidate_driver_caches(self, driver_id: int):
        """Invalidate driver-specific caches"""
        cache.delete(f"{self.cache_prefix}:driver:{driver_id}")

    def _invalidate_available_drivers_cache(self):
        """Invalidate available drivers cache"""
        try:
            for key in cache.cache._client.scan_iter(f"{self.cache_prefix}:available_drivers:*"):
                cache.delete(key)
        except Exception:
            pass

    def _invalidate_provider_caches(self):
        """Invalidate all provider caches"""
        try:
            for key in cache.cache._client.scan_iter(f"{self.cache_prefix}:*"):
                cache.delete(key)
        except Exception:
            pass


# ===========================================================================
# INITIALIZATION
# ===========================================================================

def init_provider_service():
    """Initialize provider service"""
    try:
        # Register with dependency container if available
        try:
            from app.core.di import Container
            container = Container()
            container.register('provider_service', ProviderService, singleton=True)
        except ImportError:
            pass

        logger.info("✅ Provider Service Initialized")
        return ProviderService

    except Exception as e:
        logger.error(f"Failed to initialize provider service: {e}", exc_info=True)
        raise


# ===========================================================================
# Singleton getter
# ===========================================================================
from threading import Lock

_provider_service_instance = None
_provider_service_lock = Lock()


def get_provider_service() -> ProviderService:
    """Get singleton instance of ProviderService"""
    global _provider_service_instance
    if _provider_service_instance is None:
        with _provider_service_lock:
            if _provider_service_instance is None:
                _provider_service_instance = ProviderService()
                logger.debug("ProviderService singleton created")
    return _provider_service_instance
