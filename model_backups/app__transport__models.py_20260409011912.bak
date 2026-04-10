#app/transport/models.py
"""
AFCON360 Transport Module - Production Ready Models
All production features implemented but disabled by default settings
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from decimal import Decimal
from sqlalchemy.dialects.postgresql import TSVECTOR

import hashlib
import secrets

from sqlalchemy import (
    Index, UniqueConstraint, CheckConstraint, text, Enum as SQLEnum,
    ForeignKeyConstraint, event, DDL
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import validates, relationship, backref
from sqlalchemy.sql import expression

from app.extensions import db
# from geoalchemy2 import Geometry  # Removed: PostGIS not installed
from app.utils.security import encrypt_field, decrypt_field


# ===========================================================================
# ENUMS (Production with proper string values)
# ===========================================================================

class VerificationTier(str, Enum):
    """Provider verification levels"""
    PENDING = 'pending'
    BASIC_VERIFIED = 'basic_verified'
    PLATFORM_VERIFIED = 'platform_verified'
    EVENT_CERTIFIED = 'event_certified'


class ComplianceStatus(str, Enum):
    """Compliance status"""
    PENDING_REVIEW = 'pending_review'
    UNDER_REVIEW = 'under_review'
    APPROVED = 'approved'
    SUSPENDED = 'suspended'
    REVOKED = 'revoked'
    BLACKLISTED = 'blacklisted'


class BookingStatus(str, Enum):
    """Booking lifecycle"""
    DRAFT = 'draft'
    PENDING_PAYMENT = 'pending_payment'
    CONFIRMED = 'confirmed'
    ASSIGNED = 'assigned'
    DRIVER_EN_ROUTE = 'driver_en_route'
    PICKUP_ARRIVED = 'pickup_arrived'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'
    CANCELLED = 'cancelled'
    NO_SHOW = 'no_show'
    DISPUTED = 'disputed'


class PaymentStatus(str, Enum):
    """Payment status"""
    PENDING = 'pending'
    AUTHORIZED = 'authorized'
    CAPTURED = 'captured'
    PARTIALLY_CAPTURED = 'partially_captured'
    REFUNDED = 'refunded'
    PARTIALLY_REFUNDED = 'partially_refunded'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


class ServiceType(str, Enum):
    """Service types with proper codes"""
    AIRPORT_ARRIVAL = 'airport_arrival'
    AIRPORT_DEPARTURE = 'airport_departure'
    STADIUM_SHUTTLE = 'stadium_shuttle'
    HOTEL_TRANSFER = 'hotel_transfer'
    CITY_TOUR = 'city_tour'
    ON_DEMAND = 'on_demand'
    SCHEDULED_ROUTE = 'scheduled_route'
    CUSTOM_TOUR = 'custom_tour'


class ProviderType(str, Enum):
    """Provider types"""
    INDIVIDUAL_DRIVER = 'individual_driver'
    HOTEL_FLEET = 'hotel_fleet'
    TOUR_OPERATOR = 'tour_operator'
    TRANSPORT_COMPANY = 'transport_company'
    EXTERNAL_PLATFORM = 'external_platform'


class VehicleClass(str, Enum):
    """Vehicle classification"""
    ECONOMY = 'economy'
    COMFORT = 'comfort'
    PREMIUM = 'premium'
    LUXURY = 'luxury'
    VAN = 'van'
    BUS = 'bus'


class IncidentSeverity(str, Enum):
    """Incident severity levels"""
    INFO = 'info'
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'
    CRITICAL = 'critical'


class Currency(str, Enum):
    """Supported currencies"""
    USD = 'USD'
    EUR = 'EUR'
    GBP = 'GBP'
    XOF = 'XOF'
    XAF = 'XAF'
    NGN = 'NGN'
    KES = 'KES'
    GHS = 'GHS'
    ZAR = 'ZAR'
    UGX = 'UGX'


# ===========================================================================
# MIXINS (Reusable functionality)
# ===========================================================================

class TimestampMixin:
    """Automatic timestamp fields"""
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        server_default=db.func.now()
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
        server_default=db.func.now()
    )
    deleted_at = db.Column(db.DateTime(timezone=True), index=True)


class AuditMixin:
    """Audit trail fields"""
    created_by = db.Column(db.BigInteger, db.ForeignKey("users.id"))
    updated_by = db.Column(db.BigInteger, db.ForeignKey("users.id"))
    version = db.Column(db.Integer, default=1, nullable=False)


class SoftDeleteMixin:
    """Soft delete functionality"""
    is_deleted = db.Column(db.Boolean, default=False, nullable=False, index=True)

    @hybrid_property
    def is_active(self):
        return not self.is_deleted

    @is_active.expression
    def is_active(cls):
        return expression.not_(cls.is_deleted)


# ===========================================================================
# BASE MODELS
# ===========================================================================

class TransportBase(db.Model, TimestampMixin, SoftDeleteMixin):
    """Abstract base model for all transport entities"""
    __abstract__ = True

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)

    # Tenant isolation for multi-tenant setup
    tenant_id = db.Column(db.String(50), nullable=False, default='default')

    # Optimistic concurrency control
    version = db.Column(db.Integer, default=1, nullable=False)

    def to_dict(self, include: Optional[List[str]] = None, exclude: Optional[List[str]] = None):
        """Safe serialization with field control"""
        from app.core.serializers import ModelSerializer

        return ModelSerializer.serialize(self, include=include, exclude=exclude)


# ===========================================================================
# DRIVER PROFILES (Production)
# ===========================================================================

class DriverProfile(TransportBase, AuditMixin):
    """Individual driver with complete verification tracking"""
    __tablename__ = "driver_profiles"
    __table_args__ = (
        # Composite indexes for common queries
        Index("ix_driver_user_id", "user_id", unique=True),
        Index("ix_driver_status", "verification_tier", "compliance_status", "is_deleted"),
        Index("ix_driver_online", "is_online", "is_available", "last_seen_at"),

        # Partial indexes for performance
        Index("ix_driver_not_deleted", "is_deleted", postgresql_where=text("is_deleted = false")),
        Index("ix_driver_deleted", "is_deleted"),

        # Foreign key constraints
        ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            ondelete="CASCADE",
            name="fk_driver_user"
        ),

        # Check constraints
        CheckConstraint(
            "reliability_score >= 0 AND reliability_score <= 100",
            name="chk_driver_reliability_score"
        ),
        CheckConstraint(
            "safety_score >= 0 AND safety_score <= 100",
            name="chk_driver_safety_score"
        ),
    )

    # Core identity
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id"), nullable=False, unique=True)
    driver_code = db.Column(db.String(20), unique=True, nullable=False, index=True)

    # Verification tracking
    verification_tier = db.Column(
        SQLEnum(VerificationTier),
        default=VerificationTier.PENDING,
        nullable=False,
        index=True
    )
    compliance_status = db.Column(
        SQLEnum(ComplianceStatus),
        default=ComplianceStatus.PENDING_REVIEW,
        nullable=False,
        index=True
    )

    # Document verification (encrypted at rest)
    license_number_encrypted = db.Column(db.Text, nullable=True)
    license_verified = db.Column(db.Boolean, default=False, nullable=False)
    license_verified_at = db.Column(db.DateTime(timezone=True))
    license_verified_by = db.Column(db.BigInteger, db.ForeignKey("users.id"))#change to admin users.d when created later
    license_expiry = db.Column(db.DateTime(timezone=True))

    police_clearance_verified = db.Column(db.Boolean, default=False, nullable=False)
    police_clearance_date = db.Column(db.DateTime(timezone=True))
    background_check_status = db.Column(db.String(20), default='pending')
    background_check_reference = db.Column(db.String(100))

    # Performance metrics
    reliability_score = db.Column(db.Integer, default=80, nullable=False)
    safety_score = db.Column(db.Integer, default=80, nullable=False)
    acceptance_rate = db.Column(db.Numeric(5, 2), default=100.00)  # Percentage
    cancellation_rate = db.Column(db.Numeric(5, 2), default=0.00)  # Percentage

    # Trip statistics
    total_trips = db.Column(db.Integer, default=0, nullable=False)
    completed_trips = db.Column(db.Integer, default=0, nullable=False)
    total_duration_minutes = db.Column(db.Integer, default=0)
    total_distance_km = db.Column(db.Numeric(10, 2), default=0)

    # Ratings
    average_rating = db.Column(db.Numeric(3, 2), default=0.00)
    total_ratings = db.Column(db.Integer, default=0)
    rating_distribution = db.Column(JSONB, default=lambda: {'1': 0, '2': 0, '3': 0, '4': 0, '5': 0})

    # Capabilities and preferences
    languages_spoken = db.Column(JSONB, default=lambda: ['en'], nullable=False)
    vehicle_classes = db.Column(JSONB, default=lambda: ['comfort'], nullable=False)
    service_types = db.Column(JSONB, default=lambda: ['on_demand'], nullable=False)

    operational_zones = db.Column(JSONB, default=lambda: [], nullable=False)
    preferred_zones = db.Column(JSONB, default=lambda: [], nullable=False)
    blacklisted_zones = db.Column(JSONB, default=lambda: [], nullable=False)

    max_passenger_capacity = db.Column(db.Integer, default=4, nullable=False)
    max_luggage_capacity = db.Column(db.Integer, default=2, nullable=False)

    # Operational settings
    is_online = db.Column(db.Boolean, default=False, nullable=False, index=True)
    is_available = db.Column(db.Boolean, default=False, nullable=False, index=True)
    last_seen_at = db.Column(db.DateTime(timezone=True))
    last_location = db.Column(JSONB)  # Encrypted in application layer
    location_updated_at = db.Column(db.DateTime(timezone=True))

    auto_accept_bookings = db.Column(db.Boolean, default=False)
    max_concurrent_bookings = db.Column(db.Integer, default=1)

    # Financial
    wallet_balance = db.Column(db.Numeric(10, 2), default=0.00)
    total_earnings = db.Column(db.Numeric(10, 2), default=0.00)
    commission_rate = db.Column(db.Numeric(5, 2), default=15.00)  # Percentage

    # Compliance flags
    requires_retraining = db.Column(db.Boolean, default=False)
    last_training_date = db.Column(db.DateTime(timezone=True))
    next_training_due = db.Column(db.DateTime(timezone=True))

    # Emergency contact
    emergency_contact_name = db.Column(db.String(100))
    emergency_contact_phone = db.Column(db.String(20))
    emergency_contact_relationship = db.Column(db.String(50))

    # Metadata
    driver_metadata = db.Column("metadata",JSONB, default=lambda: {})

    # Relationships
    user = relationship("User",foreign_keys=[user_id],backref=backref("driver_profile", uselist=False))

    # The vehicles this driver owns (as primary/owner)
    owned_vehicles = relationship(
        "Vehicle",
        primaryjoin="and_(Vehicle.owner_id==DriverProfile.id, Vehicle.owner_type=='driver')",
        foreign_keys="Vehicle.owner_id",
        backref="vehicle_owner",
        viewonly=True  # This is read-only to avoid confusion
    )


    # Index for full-text search
    __ts_vector__ = db.Column(
        TSVECTOR,
        db.Computed(
            "to_tsvector('english', "
            "COALESCE(driver_code, '') || ' ' || "
            "COALESCE(license_number_encrypted, ''))",
            persisted=True
        )
    )
    # Add this inside the DriverProfile class, with the other relationships

    # Complete driving history (all vehicles they've ever driven)
    driving_history = relationship(
        "DriverVehicleHistory",
        foreign_keys="DriverVehicleHistory.driver_id",
        back_populates="driver",
        order_by="desc(DriverVehicleHistory.started_at)"
    )
    # All vehicles this driver has ever driven (through history) - ADD THIS
    vehicles = relationship(
        "Vehicle",
        secondary="driver_vehicle_history",
        primaryjoin="DriverProfile.id==DriverVehicleHistory.driver_id",
        secondaryjoin="Vehicle.id==DriverVehicleHistory.vehicle_id",
        viewonly=True
    )
    # Organisations this driver belongs to (through the association table)
    organisations = relationship(
        "OrganisationTransportProfile",
        secondary="organisation_drivers",
        back_populates="drivers",
        viewonly=True  # Read-only to avoid conflicts
    )

    # Get current active assignment (if any)
    @property
    def current_assignment(self):
        """Get the current active driving assignment"""
        from sqlalchemy import and_
        return DriverVehicleHistory.query.filter(
            and_(
                DriverVehicleHistory.driver_id == self.id,
                DriverVehicleHistory.ended_at == None
            )
        ).first()



    @validates('license_number_encrypted')
    def encrypt_license_number(self, key, value):
        """Encrypt license number before storage"""
        if value and not value.startswith('enc:'):
            return encrypt_field(value)
        return value

    @hybrid_property
    def license_number(self):
        """Decrypt license number for authorized access"""
        if self.license_number_encrypted and self.license_number_encrypted.startswith('enc:'):
            return decrypt_field(self.license_number_encrypted)
        return self.license_number_encrypted

    @license_number.setter
    def license_number(self, value):
        self.license_number_encrypted = encrypt_field(value) if value else None

    @hybrid_property
    def is_fully_verified(self):
        """Check if driver is fully verified"""
        return (
                self.verification_tier == VerificationTier.EVENT_CERTIFIED and
                self.compliance_status == ComplianceStatus.APPROVED and
                self.license_verified and
                self.police_clearance_verified
        )

    @is_fully_verified.expression
    def is_fully_verified(cls):
        return expression.and_(
            cls.verification_tier == VerificationTier.EVENT_CERTIFIED,
            cls.compliance_status == ComplianceStatus.APPROVED,
            cls.license_verified == True,
            cls.police_clearance_verified == True
        )

    def update_location(self, latitude: float, longitude: float, accuracy: float = 0.0):
        """Update driver location with validation"""
        from app.core.validators import validate_coordinates

        validate_coordinates(latitude, longitude)

        self.last_location = {
            'latitude': latitude,
            'longitude': longitude,
            'accuracy': accuracy,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        self.location_updated_at = datetime.now(timezone.utc)

    @property
    def current_vehicle(self):
        return next(
            (h.vehicle for h in self.driving_history if h.ended_at is None),
            None
        )


# ===========================================================================
# ORGANISATIONS
# ===========================================================================
class OrganisationTransportProfile(TransportBase, AuditMixin):
    """Organisation transport provider with fleet management"""
    __tablename__ = "organisation_transport_profiles"
    __table_args__ = (
        # Composite indexes for common queries
        Index("ix_org_profile_org_id", "organisation_id", unique=True),
        Index("ix_org_profile_status", "registration_type", "compliance_status", "is_deleted"),

        # Partial indexes for performance
        Index("ix_org_not_deleted", "is_deleted", postgresql_where=text("is_deleted = false")),
        Index("ix_org_verified", "registration_type",
              postgresql_where=text("registration_type IN ('platform_verified', 'event_certified')")),
        Index("ix_org_deleted", "is_deleted"),

        # Business rule constraints
        CheckConstraint(
            "registration_type != 'hotel_fleet' OR can_provide_on_demand = FALSE",
            name="chk_hotel_no_on_demand"
        ),
        CheckConstraint(
            "registration_type != 'tour_operator' OR can_provide_on_demand = FALSE",
            name="chk_tour_no_on_demand"
        ),
        CheckConstraint(
            "fleet_size >= 0",
            name="chk_fleet_size_positive"
        ),
    )

    # Core identity
    organisation_id = db.Column(db.BigInteger, db.ForeignKey("organisations.id"), nullable=False, unique=True)
    registration_type = db.Column(db.String(50), nullable=False, index=True)
    business_license_number = db.Column(db.String(100))
    tax_identification_number = db.Column(db.String(50))

    # Verification
    compliance_status = db.Column(
        SQLEnum(ComplianceStatus),
        default=ComplianceStatus.PENDING_REVIEW,
        nullable=False,
        index=True
    )
    license_verified = db.Column(db.Boolean, default=False, nullable=False)
    insurance_verified = db.Column(db.Boolean, default=False, nullable=False)
    insurance_expiry = db.Column(db.DateTime(timezone=True))
    insurance_coverage_amount = db.Column(db.Numeric(12, 2))

    # Performance metrics
    reliability_score = db.Column(db.Integer, default=80, nullable=False)
    safety_score = db.Column(db.Integer, default=80, nullable=False)
    average_rating = db.Column(db.Numeric(3, 2), default=0.00)
    total_bookings = db.Column(db.Integer, default=0)
    completed_bookings = db.Column(db.Integer, default=0)

    # Capabilities
    can_provide_airport_transfers = db.Column(db.Boolean, default=False)
    can_provide_stadium_shuttles = db.Column(db.Boolean, default=False)
    can_provide_hotel_transfers = db.Column(db.Boolean, default=False)
    can_provide_city_tours = db.Column(db.Boolean, default=False)
    can_provide_on_demand = db.Column(db.Boolean, default=False)

    # Fleet management
    fleet_size = db.Column(db.Integer, default=0)
    available_fleet_size = db.Column(db.Integer, default=0)
    max_group_size = db.Column(db.Integer, default=20)
    total_passenger_capacity = db.Column(db.Integer, default=0)

    # Operational
    operational_zones = db.Column(JSONB, default=lambda: [], nullable=False)
    languages_supported = db.Column(JSONB, default=lambda: ['en'], nullable=False)
    service_hours = db.Column(JSONB, default=lambda: {
        'monday': {'start': '06:00', 'end': '22:00'},
        'tuesday': {'start': '06:00', 'end': '22:00'},
        'wednesday': {'start': '06:00', 'end': '22:00'},
        'thursday': {'start': '06:00', 'end': '22:00'},
        'friday': {'start': '06:00', 'end': '23:00'},
        'saturday': {'start': '07:00', 'end': '23:00'},
        'sunday': {'start': '08:00', 'end': '22:00'}
    })

    # Contact information
    transport_manager_name = db.Column(db.String(100))
    transport_manager_phone = db.Column(db.String(20))
    transport_manager_email = db.Column(db.String(255))

    # Financial
    commission_rate = db.Column(db.Numeric(5, 2), default=12.00)  # Percentage
    payment_terms_days = db.Column(db.Integer, default=7)

    # Status
    accepts_bookings = db.Column(db.Boolean, default=True, nullable=False)
    is_suspended = db.Column(db.Boolean, default=False, nullable=False)

    # Metadata
    org_metadata = db.Column(JSONB, default=lambda: {})

    # Relationships
    organisation = relationship(
        "Organisation",
        foreign_keys=[organisation_id],
        backref=backref("transport_profile", uselist=False)
    )
    fleet_vehicles = relationship(
        "Vehicle",
        primaryjoin="and_(OrganisationTransportProfile.organisation_id==Vehicle.owner_id, "
                    "Vehicle.owner_type=='organisation')",
        foreign_keys="[Vehicle.owner_id]",
        # NO uselist here - defaults to True (one-to-many)
        viewonly=True,
        back_populates="organisation_owner"
    )
    drivers = relationship(
        "DriverProfile",
        secondary="organisation_drivers",
        back_populates="organisations"
    )


# ===========================================================================
# VEHICLES (Production)
# ===========================================================================

class Vehicle(TransportBase):
    """Vehicle with complete tracking and maintenance"""
    __tablename__ = "transport_vehicles"
    __table_args__ = (
        # Composite indexes for common queries
        Index("ix_vehicle_plate", "license_plate", unique=True),
        Index("ix_vehicle_owner", "owner_type", "owner_id"),
        Index("ix_vehicle_status", "status", "is_available", "is_deleted"),
        Index("ix_vehicle_class", "vehicle_class", "status"),
        Index("ix_vehicle_location", "current_location"),

        # Check constraints
        CheckConstraint(
            "passenger_capacity > 0 AND passenger_capacity <= 100",
            name="chk_passenger_capacity"
        ),
        CheckConstraint(
            "year >= 2000 AND year <= EXTRACT(YEAR FROM CURRENT_DATE) + 1",
            name="chk_vehicle_year"
        ),
    )

    # Ownership
    owner_type = db.Column(db.String(20), nullable=False)
    owner_id = db.Column(db.BigInteger, nullable=False)

    # Identification
    license_plate = db.Column(db.String(20), unique=True, nullable=False)
    vin_number = db.Column(db.String(17))  # Vehicle Identification Number
    registration_number = db.Column(db.String(50))

    # Specifications
    make = db.Column(db.String(50), nullable=False)
    model = db.Column(db.String(50), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    color = db.Column(db.String(30))
    vehicle_type = db.Column(db.String(30), nullable=False)
    vehicle_class = db.Column(SQLEnum(VehicleClass), nullable=False)

    # Capacity
    passenger_capacity = db.Column(db.Integer, nullable=False)
    max_passenger_capacity = db.Column(db.Integer)
    luggage_capacity = db.Column(db.Integer)
    luggage_space_cubic_meters = db.Column(db.Numeric(5, 2))

    # Compliance and insurance
    insurance_policy_number = db.Column(db.String(100))
    insurance_provider = db.Column(db.String(100))
    insurance_verified = db.Column(db.Boolean, default=False, nullable=False)
    insurance_expiry = db.Column(db.DateTime(timezone=True))
    insurance_coverage_amount = db.Column(db.Numeric(12, 2))

    roadworthiness_certificate = db.Column(db.String(100))
    roadworthiness_expiry = db.Column(db.DateTime(timezone=True))
    last_inspection_date = db.Column(db.DateTime(timezone=True))
    next_inspection_due = db.Column(db.DateTime(timezone=True))



    # Features and amenities
    features = db.Column(JSONB, default=lambda: {
        'ac': True,
        'music_system': True,
        'charging_ports': True,
        'wifi': False,
        'refreshments': False
    })
    accessibility_features = db.Column(JSONB, default=lambda: [])
    safety_features = db.Column(JSONB, default=lambda: [
        'seatbelts',
        'first_aid_kit',
        'fire_extinguisher',
        'emergency_exits'
    ])

    # Tracking and location
    current_location = db.Column(JSONB)
    last_location_update = db.Column(db.DateTime(timezone=True))
    is_trackable = db.Column(db.Boolean, default=False, nullable=False)
    tracking_device_id = db.Column(db.String(100))

    # Safety and verification
    qr_code_hash = db.Column(db.String(64), unique=True, index=True)
    verification_code = db.Column(db.String(10))

    # Maintenance
    odometer_reading_km = db.Column(db.Integer, default=0)
    last_service_km = db.Column(db.Integer)
    next_service_km = db.Column(db.Integer)
    last_service_date = db.Column(db.DateTime(timezone=True))
    next_service_date = db.Column(db.DateTime(timezone=True))
    maintenance_status = db.Column(db.String(20), default='ok')

    # Status
    status = db.Column(db.String(20), default='active', nullable=False)
    is_available = db.Column(db.Boolean, default=True, nullable=False, index=True)
    is_reserved = db.Column(db.Boolean, default=False, nullable=False)

    # Current assignment
    current_booking_id = db.Column(db.BigInteger) #Removed the foreign key db.ForeignKey("transport_bookings.id"))

    # Images
    photo_urls = db.Column(JSONB, default=lambda: [])
    document_urls = db.Column(JSONB, default=lambda: {
        'insurance': None,
        'registration': None,
        'inspection': None
    })

    # Relationships
    # The driver who owns this vehicle
    owner_driver = relationship(
        "DriverProfile",
        primaryjoin="and_(Vehicle.owner_id==DriverProfile.id, Vehicle.owner_type=='driver')",
        foreign_keys=[owner_id],
        back_populates="owned_vehicles",
        overlaps="fleet_vehicles"
    )
    organisation_owner = relationship(
        "OrganisationTransportProfile",
        primaryjoin="and_(Vehicle.owner_id==OrganisationTransportProfile.organisation_id, "
                    "Vehicle.owner_type=='organisation')",
        foreign_keys=[owner_id],
        uselist=False,  # CRITICAL: This makes it many-to-one from Vehicle's perspective
        viewonly=True,
        back_populates="fleet_vehicles"
    )
    # Complete driving history (all drivers who've driven this vehicle)
    driving_history = relationship(
        "DriverVehicleHistory",
        foreign_keys="DriverVehicleHistory.vehicle_id",
        back_populates="vehicle",
        order_by="desc(DriverVehicleHistory.started_at)",
        cascade="all, delete-orphan",
    )

    # All drivers who have driven this vehicle (through history) - ADD THIS
    drivers = relationship(
        "DriverProfile",
        secondary="driver_vehicle_history",
        primaryjoin="Vehicle.id==DriverVehicleHistory.vehicle_id",
        secondaryjoin="DriverProfile.id==DriverVehicleHistory.driver_id",
        viewonly=True
    )

    def generate_qr_code(self):
        """Generate secure QR code hash"""
        import hashlib
        import secrets

        if not self.qr_code_hash:
            unique_data = f"{self.id}:{self.license_plate}:{secrets.token_hex(16)}"
            self.qr_code_hash = hashlib.sha256(unique_data.encode()).hexdigest()

        return self.qr_code_hash

    @validates('current_location')
    def validate_location(self, key, value):
        """Validate geographic coordinates stored as JSONB"""
        if value and isinstance(value, dict):
            lat = value.get('latitude')
            lng = value.get('longitude')
            if lat is not None and not (-90 <= lat <= 90):
                raise ValueError("Invalid latitude value")
            if lng is not None and not (-180 <= lng <= 180):
                raise ValueError("Invalid longitude value")
        return value

    # Get current active driver assignment (if any)
    @property
    def current_assignment(self):
        """Get the current active driver assignment"""
        from sqlalchemy import and_
        return DriverVehicleHistory.query.filter(
            and_(
                DriverVehicleHistory.vehicle_id == self.id,
                DriverVehicleHistory.ended_at == None
            )
        ).first()
    @property
    def current_driver(self):
        return next(
            (h.driver for h in self.driving_history if h.ended_at is None),
            None
        )

    @property
    def current_booking(self):
        """Get the current active booking for this vehicle"""
        from sqlalchemy import and_
        return Booking.query.filter(
            and_(
                Booking.assigned_vehicle_id == self.id,
                Booking.status.in_([
                    BookingStatus.CONFIRMED,
                    BookingStatus.ASSIGNED,
                    BookingStatus.IN_PROGRESS,
                    BookingStatus.DRIVER_EN_ROUTE
                ])
            )
        ).first()


# ===========================================================================
# DRIVER VEHICLE HISTORY (Track everything that happens)
# ===========================================================================

class DriverVehicleHistory(TransportBase):
    """Complete history of which driver drove which vehicle and when"""
    __tablename__ = "driver_vehicle_history"
    __table_args__ = (
        Index("ix_driver_vehicle_history_driver", "driver_id", "started_at"),
        Index("ix_driver_vehicle_history_vehicle", "vehicle_id", "started_at"),
        Index("ix_driver_vehicle_history_active", "ended_at"),
        Index("ix_unique_active_vehicle","vehicle_id",   unique=True,postgresql_where=text("ended_at IS NULL")),
    )
    # Who and What
    driver_id = db.Column(db.BigInteger, db.ForeignKey("driver_profiles.id"), nullable=False)
    vehicle_id = db.Column(db.BigInteger, db.ForeignKey("transport_vehicles.id"), nullable=False)

    # When
    started_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc))
    ended_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Why did this assignment happen?
    assignment_reason = db.Column(db.String(50),
                                  nullable=False)  # 'shift_start', 'breakdown_replacement', 'reassignment', 'ownership_change'

    # What was the situation?
    notes = db.Column(db.Text)  # Any extra details

    # Who authorized this change?
    authorized_by = db.Column(db.BigInteger, db.ForeignKey("users.id"), nullable=True)  # admin, manager, etc.

    # For breakdown scenarios
    was_breakdown = db.Column(db.Boolean, default=False)
    breakdown_reason = db.Column(db.String(100))  # 'mechanical', 'accident', 'flat_tire', etc.
    replacement_vehicle_id = db.Column(db.BigInteger, db.ForeignKey("transport_vehicles.id"), nullable=True)

    # Relationships
    driver = relationship("DriverProfile", foreign_keys=[driver_id], back_populates="driving_history")
    vehicle = relationship("Vehicle", foreign_keys=[vehicle_id], back_populates="driving_history")
    replacement_vehicle = relationship("Vehicle", foreign_keys=[replacement_vehicle_id])
    authorizer = relationship("User", foreign_keys=[authorized_by])

# ===========================================================================
# BOOKINGS (Production)
# ===========================================================================

class Booking(TransportBase):
    """Booking with full audit trail and financial tracking"""
    __tablename__ = "transport_bookings"
    __table_args__ = (
        # Performance indexes
        Index("ix_booking_user", "user_id", "created_at"),
        Index("ix_booking_provider", "provider_type", "provider_id", "status"),
        Index("ix_booking_status", "status", "created_at"),
        Index("ix_booking_dates", "pickup_time", "created_at"),
        Index("ix_booking_reference", "booking_reference", unique=True),

        # Spatial reference indexes
        Index("ix_booking_pickup", "pickup_point"),
        Index("ix_booking_dropoff", "dropoff_point"),

        # Foreign keys
        ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            ondelete='RESTRICT',
            name='fk_booking_user'
        ),
        ForeignKeyConstraint(
            ['assigned_driver_id'], ['driver_profiles.id'],
            ondelete='SET NULL',
            name='fk_booking_driver'
        ),

        # Business rules
        CheckConstraint(
            "pickup_time > created_at",
            name="chk_pickup_time_future"
        ),
        CheckConstraint(
            "passenger_count > 0 AND passenger_count <= 100",
            name="chk_passenger_count"
        ),
        CheckConstraint(
            "base_price >= 0",
            name="chk_base_price_positive"
        ),
        CheckConstraint(
            "final_price >= 0",
            name="chk_final_price_positive"
        ),
    )

    # Identification
    booking_reference = db.Column(db.String(50), unique=True, nullable=False)
    external_reference = db.Column(db.String(100))  # For external platforms

    # User
    user_id = db.Column(db.BigInteger, nullable=False)
    user_type = db.Column(db.String(20), default='fan')  # fan, vip, staff

    # Provider
    provider_type = db.Column(SQLEnum(ProviderType), nullable=False)
    provider_id = db.Column(db.BigInteger, nullable=True)

    # External platform integration
    external_platform = db.Column(db.String(50))  # uber, bolt, etc.
    external_booking_id = db.Column(db.String(100))
    external_confirmation_code = db.Column(db.String(100))

    # Service details
    service_type = db.Column(SQLEnum(ServiceType), nullable=False)
    service_subtype = db.Column(db.String(50))

    # Trip details
    pickup_location = db.Column(JSONB, nullable=False)
    pickup_point = db.Column(JSONB)

    pickup_address = db.Column(db.Text)
    pickup_instructions = db.Column(db.Text)
    pickup_contact_name = db.Column(db.String(100))
    pickup_contact_phone = db.Column(db.String(20))

    dropoff_location = db.Column(JSONB, nullable=False)
    dropoff_point = db.Column(JSONB)
    dropoff_address = db.Column(db.Text)
    dropoff_instructions = db.Column(db.Text)
    dropoff_contact_name = db.Column(db.String(100))
    dropoff_contact_phone = db.Column(db.String(20))

    # Timing
    pickup_time = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    pickup_estimated_time = db.Column(db.DateTime(timezone=True))
    pickup_actual_time = db.Column(db.DateTime(timezone=True))
    dropoff_estimated_time = db.Column(db.DateTime(timezone=True))
    dropoff_actual_time = db.Column(db.DateTime(timezone=True))

    # Duration and distance
    estimated_duration_minutes = db.Column(db.Integer)
    actual_duration_minutes = db.Column(db.Integer)
    estimated_distance_km = db.Column(db.Numeric(8, 2))
    actual_distance_km = db.Column(db.Numeric(8, 2))

    # Passengers and luggage
    passenger_count = db.Column(db.Integer, nullable=False, default=1)
    passenger_details = db.Column(JSONB, default=lambda: [])
    luggage_count = db.Column(db.Integer, default=0)
    luggage_details = db.Column(JSONB, default=lambda: [])

    # Special requirements
    special_requirements = db.Column(JSONB, default=lambda: {})
    accessibility_requirements = db.Column(JSONB, default=lambda: [])

    # Pricing and payment
    base_price = db.Column(db.Numeric(10, 2), nullable=False)
    surge_multiplier = db.Column(db.Numeric(3, 2), default=1.00)
    distance_price = db.Column(db.Numeric(10, 2), default=0.00)
    time_price = db.Column(db.Numeric(10, 2), default=0.00)

    # Fees and taxes
    platform_fee = db.Column(db.Numeric(10, 2), default=0.00)
    service_fee = db.Column(db.Numeric(10, 2), default=0.00)
    tax_amount = db.Column(db.Numeric(10, 2), default=0.00)
    toll_fees = db.Column(db.Numeric(10, 2), default=0.00)
    parking_fees = db.Column(db.Numeric(10, 2), default=0.00)

    # Discounts and promotions
    promotion_discount = db.Column(db.Numeric(10, 2), default=0.00)
    loyalty_discount = db.Column(db.Numeric(10, 2), default=0.00)
    voucher_discount = db.Column(db.Numeric(10, 2), default=0.00)

    # Final amounts
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    final_price = db.Column(db.Numeric(10, 2), nullable=False)

    # Currency
    currency = db.Column(SQLEnum(Currency), default=Currency.USD, nullable=False)
    exchange_rate = db.Column(db.Numeric(10, 6), default=1.000000)

    # Payment tracking
    payment_status = db.Column(SQLEnum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    payment_method = db.Column(db.String(50))
    payment_gateway = db.Column(db.String(50))
    payment_gateway_reference = db.Column(db.String(100))
    payment_captured_at = db.Column(db.DateTime(timezone=True))

    # Wallet integration
    wallet_transaction_id = db.Column(db.String(128))
    wallet_balance_used = db.Column(db.Numeric(10, 2), default=0.00)

    # Status
    status = db.Column(SQLEnum(BookingStatus), default=BookingStatus.DRAFT, nullable=False)
    cancellation_reason = db.Column(db.String(100))
    cancellation_initiated_by = db.Column(db.String(20))  # user, driver, system, admin
    cancellation_fee = db.Column(db.Numeric(10, 2), default=0.00)

    # Assignment

    assigned_driver_id = db.Column(db.BigInteger, db.ForeignKey("driver_profiles.id"))
    assigned_vehicle_id = db.Column(db.BigInteger, db.ForeignKey("transport_vehicles.id"))
    assigned_route_id = db.Column(db.BigInteger,db.ForeignKey("transport_scheduled_routes.id", ondelete='SET NULL'))

    assigned_route = relationship("ScheduledRoute", back_populates="bookings")

    # Driver tracking
    driver_assigned_at = db.Column(db.DateTime(timezone=True))
    driver_en_route_at = db.Column(db.DateTime(timezone=True))
    driver_arrived_at = db.Column(db.DateTime(timezone=True))

    # Contingency handling
    is_contingency_triggered = db.Column(db.Boolean, default=False)
    original_provider_type = db.Column(db.String(20))
    original_provider_id = db.Column(db.BigInteger)
    reassignment_reason = db.Column(db.String(100))
    fallback_provider = db.Column(JSONB)

    # Group booking
    is_group_booking = db.Column(db.Boolean, default=False)
    group_booking_id = db.Column(db.String(50))
    group_leader_id = db.Column(db.BigInteger)
    group_size = db.Column(db.Integer, default=1)

    # Insurance
    insurance_covered = db.Column(db.Boolean, default=False)
    insurance_provider = db.Column(db.String(100))
    insurance_policy_number = db.Column(db.String(100))

    # Metadata
    booking_metadata = db.Column(JSONB, default=lambda: {})
    audit_log = db.Column(JSONB, default=lambda: [])

    # Timestamps for lifecycle
    confirmed_at = db.Column(db.DateTime(timezone=True))
    completed_at = db.Column(db.DateTime(timezone=True))
    cancelled_at = db.Column(db.DateTime(timezone=True))
    archived_at = db.Column(db.DateTime(timezone=True))

    # Relationships
    user = relationship("User", backref="transport_bookings")
    driver = relationship(
        "DriverProfile",
        foreign_keys=[assigned_driver_id],
        backref="assigned_bookings"  # Change from "bookings" to avoid conflict
    )

    vehicle = relationship(
        "Vehicle",
        foreign_keys=[assigned_vehicle_id],
        backref="assigned_bookings"
    )
    assigned_route = relationship("ScheduledRoute", back_populates="bookings")
    rating = relationship("Rating", back_populates="booking", uselist=False)
    incidents = relationship("TransportIncident", back_populates="booking")
    payments = relationship("BookingPayment", back_populates="booking")

    def generate_booking_reference(self):
        """Generate unique booking reference"""
        import secrets
        import string
        from datetime import datetime

        if not self.booking_reference:
            date_prefix = datetime.now().strftime('%y%m%d')
            random_part = ''.join(secrets.choice(string.ascii_uppercase + string.digits)
                                  for _ in range(6))
            self.booking_reference = f"TR{date_prefix}{random_part}"

        return self.booking_reference

    @property
    def is_upcoming(self):
        """Check if booking is upcoming"""
        from datetime import datetime, timezone
        return (
                self.status in [BookingStatus.CONFIRMED, BookingStatus.ASSIGNED, BookingStatus.DRIVER_EN_ROUTE] and
                self.pickup_time > datetime.now(timezone.utc)
        )

    @property
    def is_completed_successfully(self):
        """Check if booking was completed successfully"""
        return (
                self.status == BookingStatus.COMPLETED and
                self.payment_status == PaymentStatus.CAPTURED
        )

    def calculate_cancellation_fee(self, cancelled_at=None):
        """Calculate cancellation fee based on timing"""
        from datetime import datetime, timezone

        if not cancelled_at:
            cancelled_at = datetime.now(timezone.utc)

        hours_before = (self.pickup_time - cancelled_at).total_seconds() / 3600

        if hours_before > 24:
            return Decimal('0.00')  # No fee if cancelled > 24h before
        elif hours_before > 4:
            return self.final_price * Decimal('0.10')  # 10% fee
        elif hours_before > 1:
            return self.final_price * Decimal('0.25')  # 25% fee
        else:
            return self.final_price * Decimal('0.50')  # 50% fee


# ===========================================================================
# PAYMENT TRACKING
# ===========================================================================

class BookingPayment(TransportBase):
    """Detailed payment tracking for bookings"""
    __tablename__ = "transport_booking_payments"
    __table_args__ = (
        Index("ix_payment_booking", "booking_id", "payment_status"),
        Index("ix_payment_reference", "payment_reference", unique=True),
        Index("ix_payment_gateway", "payment_gateway", "gateway_transaction_id"),

        CheckConstraint(
            "amount > 0",
            name="chk_payment_amount_positive"
        ),
    )

    booking_id = db.Column(db.BigInteger, db.ForeignKey("transport_bookings.id"), nullable=False)
    payment_reference = db.Column(db.String(50), unique=True, nullable=False)

    # Amounts
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(SQLEnum(Currency), nullable=False)
    exchange_rate = db.Column(db.Numeric(10, 6), default=1.000000)

    # Payment method
    payment_method = db.Column(db.String(50), nullable=False)  # card, wallet, cash, bank_transfer
    payment_method_details = db.Column(JSONB, default=lambda: {})

    # Gateway integration
    payment_gateway = db.Column(db.String(50))
    gateway_transaction_id = db.Column(db.String(100))
    gateway_response = db.Column(JSONB)

    # Status
    payment_status = db.Column(SQLEnum(PaymentStatus), nullable=False)
    failure_reason = db.Column(db.Text)
    retry_count = db.Column(db.Integer, default=0)

    # Timing
    initiated_at = db.Column(db.DateTime(timezone=True))
    authorized_at = db.Column(db.DateTime(timezone=True))
    captured_at = db.Column(db.DateTime(timezone=True))
    refunded_at = db.Column(db.DateTime(timezone=True))

    # Reconciliation
    is_reconciled = db.Column(db.Boolean, default=False)
    reconciled_at = db.Column(db.DateTime(timezone=True))
    reconciled_by = db.Column(db.BigInteger)

    # Relationships
    booking = relationship("Booking", back_populates="payments")

    def generate_payment_reference(self):
        """Generate unique payment reference"""
        import secrets
        import string

        if not self.payment_reference:
            random_part = ''.join(secrets.choice(string.ascii_uppercase + string.digits)
                                  for _ in range(10))
            self.payment_reference = f"PAY{random_part}"

        return self.payment_reference


# ===========================================================================
# RATINGS AND REVIEWS (Production)
# ===========================================================================

class Rating(TransportBase):
    """Detailed rating system with safety flags"""
    __tablename__ = "transport_ratings"
    __table_args__ = (
        UniqueConstraint("booking_id", name="uq_rating_booking"),
        Index("ix_rating_provider", "provider_type", "provider_id", "created_at"),
        Index("ix_rating_user", "user_id", "created_at"),

        CheckConstraint(
            "overall_rating >= 1 AND overall_rating <= 5",
            name="chk_rating_range"
        ),
    )

    booking_id = db.Column(db.BigInteger, db.ForeignKey("transport_bookings.id", ondelete='CASCADE'),nullable=False,
        unique=True
    )
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete='CASCADE'), nullable=False)

    # Provider
    provider_type = db.Column(db.String(20), nullable=False)
    provider_id = db.Column(db.BigInteger, nullable=False)

    # Ratings (1-5 scale)
    overall_rating = db.Column(db.Integer, nullable=False)
    punctuality_rating = db.Column(db.Integer)
    vehicle_condition_rating = db.Column(db.Integer)
    driver_behavior_rating = db.Column(db.Integer)
    safety_rating = db.Column(db.Integer)
    value_for_money_rating = db.Column(db.Integer)

    # Safety flags (critical)
    felt_safe = db.Column(db.Boolean, nullable=False)
    safety_concern_reported = db.Column(db.Boolean, default=False)
    safety_concern_details = db.Column(db.Text)
    safety_incident_type = db.Column(db.String(50))

    # Review content
    review_title = db.Column(db.String(200))
    review_text = db.Column(db.Text)
    review_response = db.Column(db.Text)
    responded_at = db.Column(db.DateTime(timezone=True))
    responded_by = db.Column(db.BigInteger)

    # Moderation
    is_verified_booking = db.Column(db.Boolean, default=True)
    is_edited = db.Column(db.Boolean, default=False)
    edit_history = db.Column(JSONB, default=lambda: [])
    is_flagged = db.Column(db.Boolean, default=False)
    flag_reason = db.Column(db.String(100))

    # Metadata
    helpful_count = db.Column(db.Integer, default=0)
    report_count = db.Column(db.Integer, default=0)

    # Relationships
    booking = relationship("Booking", back_populates="rating")
    user = relationship("User", backref="transport_ratings_given")

    @property
    def requires_safety_review(self):
        """Check if rating requires safety review"""
        return (
                self.safety_concern_reported or
                self.safety_rating <= 2 or
                not self.felt_safe
        )


# ===========================================================================
# SCHEDULED ROUTES (Production)
# ===========================================================================

class ScheduledRoute(TransportBase):
    """Production scheduled routes with real-time tracking"""
    __tablename__ = "transport_scheduled_routes"
    __table_args__ = (
        Index("ix_route_provider", "provider_type", "provider_id", "is_active"),
        Index("ix_route_departure", "next_departure", "is_active"),
        Index("ix_route_zone", "primary_zone", "route_type"),

        CheckConstraint(
            "vehicle_capacity > 0",
            name="chk_route_capacity_positive"
        ),
    )

    # Provider
    provider_type = db.Column(db.String(20), nullable=False)
    provider_id = db.Column(db.BigInteger, nullable=False)

    # Route details
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    route_type = db.Column(db.String(30), nullable=False)
    route_code = db.Column(db.String(20), unique=True, nullable=False)

    # Schedule
    schedule_pattern = db.Column(JSONB, nullable=False)
    timezone = db.Column(db.String(50), default='UTC')
    duration_minutes = db.Column(db.Integer)

    # Stops and path
    stops = db.Column(JSONB, nullable=False)
    path_coordinates = db.Column(JSONB)
    primary_zone = db.Column(db.String(50))

    # Capacity and pricing
    vehicle_capacity = db.Column(db.Integer, nullable=False)
    booked_seats = db.Column(db.Integer, default=0)
    available_seats = db.Column(db.Integer, default=0)

    price_per_seat = db.Column(db.Numeric(10, 2))
    is_free = db.Column(db.Boolean, default=False)

    # Real-time tracking
    next_departure = db.Column(db.DateTime(timezone=True))
    last_departure = db.Column(db.DateTime(timezone=True))
    current_vehicle_id = db.Column(db.BigInteger, db.ForeignKey("transport_vehicles.id", ondelete='SET NULL'))
    current_driver_id = db.Column(db.BigInteger, db.ForeignKey("driver_profiles.id", ondelete='SET NULL'))

    # Status
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_cancelled = db.Column(db.Boolean, default=False)
    cancellation_reason = db.Column(db.Text)

    # Metadata
    route_metadata = db.Column(JSONB, default=lambda: {})

    # Relationships
    bookings = relationship("Booking", back_populates="assigned_route")

    @property
    def is_full(self):
        """Check if route is fully booked"""
        return self.available_seats <= 0 if self.available_seats is not None else False

    def update_availability(self):
        """Update available seats count"""
        from app.extensions import db
        from sqlalchemy import func

        # Count confirmed bookings for this route
        confirmed_bookings = db.session.query(func.sum(Booking.passenger_count)).filter(
            Booking.assigned_route_id == self.id,
            Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.ASSIGNED])
        ).scalar() or 0

        self.booked_seats = confirmed_bookings
        self.available_seats = max(0, self.vehicle_capacity - confirmed_bookings)

    def can_accommodate(self, passenger_count: int) -> bool:
        """Check if route can accommodate additional passengers"""
        self.update_availability()
        return self.available_seats >= passenger_count


# ===========================================================================
# CONTINGENCY PLANS (Production)
# ===========================================================================

class ContingencyPlan(TransportBase):
    """Production contingency planning with fallback chains"""
    __tablename__ = "transport_contingency_plans"

    # Provider
    provider_type = db.Column(db.String(20), nullable=False)
    provider_id = db.Column(db.BigInteger, nullable=False)

    # Fallback chain configuration
    fallback_chain = db.Column(JSONB, nullable=False, default=lambda: [
        {'type': 'verified_network', 'priority': 1, 'timeout_minutes': 5},
        {'type': 'specific_provider', 'provider_id': None, 'priority': 2, 'timeout_minutes': 10},
        {'type': 'external_platform', 'platform': 'uber', 'priority': 3, 'timeout_minutes': 15}
    ])

    # Timeouts
    auto_release_minutes = db.Column(db.Integer, default=15)
    driver_response_timeout_minutes = db.Column(db.Integer, default=10)

    # External platform preferences
    external_platform_preferences = db.Column(
        JSONB,
        default=lambda: {'uber': 1, 'bolt': 2, 'in_driver': 3}
    )

    # Backup providers
    backup_provider_ids = db.Column(JSONB, default=lambda: [])

    # Price handling
    max_price_increase_percent = db.Column(db.Integer, default=20)
    platform_absorb_increase = db.Column(db.Boolean, default=True)

    # Notification settings
    notify_on_contingency = db.Column(db.Boolean, default=True)
    notify_users = db.Column(db.Boolean, default=True)
    notify_admins = db.Column(db.Boolean, default=True)

    # Status
    is_active = db.Column(db.Boolean, default=False, nullable=False)  # OFF by default
    last_activated = db.Column(db.DateTime(timezone=True))
    activation_count = db.Column(db.Integer, default=0)

    # Performance metrics
    success_rate = db.Column(db.Numeric(5, 2), default=0.00)
    average_resolution_minutes = db.Column(db.Integer, default=0)

    def get_next_fallback(self, current_step: int = 0):
        """Get next fallback in chain"""
        if current_step >= len(self.fallback_chain):
            return None

        return self.fallback_chain[current_step]

    def should_activate(self, booking, reason: str) -> bool:
        """Determine if contingency should activate"""
        from app.transport.services.settings_service import SettingsService

        # Check if feature is enabled
        if not SettingsService.is_feature_enabled('enable_contingency_plans'):
            return False

        # Check if plan is active
        if not self.is_active:
            return False

        # Check activation rules
        activation_rules = {
            'driver_no_show': True,
            'driver_cancellation': True,
            'vehicle_breakdown': True,
            'emergency': True,
            'delay_excessive': booking.delay_minutes > 30 if hasattr(booking, 'delay_minutes') else False
        }

        return activation_rules.get(reason, False)


# ===========================================================================
# DEMAND FORECASTING (Production)
# ===========================================================================

class DemandForecast(TransportBase):
    """AI/ML demand forecasting with confidence scoring"""
    __tablename__ = "transport_demand_forecasts"
    __table_args__ = (
        Index("ix_forecast_zone_time", "zone", "forecast_for", "time_slot"),
        Index("ix_forecast_accuracy", "model_version", "confidence_score"),
    )

    # Forecast target
    zone = db.Column(db.String(50), nullable=False, index=True)
    forecast_type = db.Column(db.String(30), nullable=False)  # daily, match_day, event, peak

    # Time window
    forecast_for = db.Column(db.DateTime(timezone=True), nullable=False)
    time_slot = db.Column(db.String(20), nullable=False)  # morning, afternoon, evening, night
    time_window_hours = db.Column(db.Integer, default=1)

    # Predictions
    expected_demand = db.Column(db.Integer, nullable=False)
    confidence_score = db.Column(db.Integer, nullable=False)  # 0-100
    confidence_interval_lower = db.Column(db.Integer)
    confidence_interval_upper = db.Column(db.Integer)

    # Recommendations
    suggested_supply = db.Column(db.Integer)
    suggested_price_multiplier = db.Column(db.Numeric(3, 2), default=1.00)
    recommended_action = db.Column(db.String(100))

    # Model information
    model_version = db.Column(db.String(50))
    model_parameters = db.Column(JSONB)
    training_data_range = db.Column(JSONB)

    # Influencing factors
    factors = db.Column(JSONB, default=lambda: {})
    weather_impact = db.Column(db.Numeric(5, 2))
    event_impact = db.Column(db.Numeric(5, 2))
    traffic_impact = db.Column(db.Numeric(5, 2))

    # Validation
    actual_demand = db.Column(db.Integer)
    prediction_error = db.Column(db.Numeric(5, 2))
    is_validated = db.Column(db.Boolean, default=False)
    validated_at = db.Column(db.DateTime(timezone=True))

    # Timestamps
    generated_at = db.Column(db.DateTime(timezone=True), nullable=False)
    valid_until = db.Column(db.DateTime(timezone=True), nullable=False)

    def is_current(self) -> bool:
        """Check if forecast is still valid"""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc) < self.valid_until

    @property
    def accuracy_rating(self) -> str:
        """Get accuracy rating"""
        if not self.prediction_error:
            return 'unknown'

        error = abs(self.prediction_error)
        if error <= 10:
            return 'excellent'
        elif error <= 20:
            return 'good'
        elif error <= 30:
            return 'fair'
        else:
            return 'poor'


# ===========================================================================
# INCIDENTS & SAFETY (Production)
# ===========================================================================

class TransportIncident(TransportBase):
    """Production incident tracking with investigation workflow"""
    __tablename__ = "transport_incidents"
    __table_args__ = (
        Index("ix_incident_severity", "severity", "created_at"),
        Index("ix_incident_status", "status", "created_at"),
        Index("ix_incident_booking", "booking_id"),
    )

    # Incident identification
    incident_reference = db.Column(db.String(50), unique=True, nullable=False)
    booking_id = db.Column(db.BigInteger, db.ForeignKey("transport_bookings.id", ondelete='SET NULL'))


    # Classification
    incident_type = db.Column(db.String(50), nullable=False)
    incident_category = db.Column(db.String(50))  # safety, service, vehicle, payment
    severity = db.Column(SQLEnum(IncidentSeverity), nullable=False)

    # Reporting
    reported_by = db.Column(db.String(20), nullable=False)  # user, driver, system, admin
    reported_by_id = db.Column(db.BigInteger)
    reported_via = db.Column(db.String(50))  # app, phone, email, dashboard

    # Details
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(JSONB)
    occurred_at = db.Column(db.DateTime(timezone=True), nullable=False)

    # Involved parties
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete='SET NULL'))
    driver_id = db.Column(db.BigInteger, db.ForeignKey("driver_profiles.id", ondelete='SET NULL'))
    vehicle_id = db.Column(db.BigInteger, db.ForeignKey("transport_vehicles.id", ondelete='SET NULL'))

    # Evidence
    photos = db.Column(JSONB, default=lambda: [])
    videos = db.Column(JSONB, default=lambda: [])
    documents = db.Column(JSONB, default=lambda: [])
    witness_details = db.Column(JSONB, default=lambda: [])

    # Investigation
    status = db.Column(db.String(20), default='reported', nullable=False)
    assigned_to = db.Column(db.BigInteger, db.ForeignKey("users.id"))#change to admin users.d when created later
    priority = db.Column(db.String(20), default='medium')

    investigation_notes = db.Column(db.Text)
    investigation_findings = db.Column(db.Text)
    root_cause = db.Column(db.String(200))

    # Resolution
    resolution = db.Column(db.String(50))
    resolution_details = db.Column(db.Text)
    resolved_at = db.Column(db.DateTime(timezone=True))
    resolved_by = db.Column(db.BigInteger)

    # Actions taken
    actions_taken = db.Column(JSONB, default=lambda: [])
    preventive_measures = db.Column(JSONB, default=lambda: [])

    # Follow-up
    requires_follow_up = db.Column(db.Boolean, default=False)
    follow_up_date = db.Column(db.DateTime(timezone=True))
    follow_up_notes = db.Column(db.Text)

    # Impact assessment
    financial_impact = db.Column(db.Numeric(10, 2))
    reputation_impact = db.Column(db.String(20))
    safety_impact = db.Column(db.String(20))

    # Compliance
    reported_to_authorities = db.Column(db.Boolean, default=False)
    authority_report_details = db.Column(JSONB)
    insurance_claimed = db.Column(db.Boolean, default=False)
    insurance_claim_details = db.Column(JSONB)

    # Relationships
    booking = relationship("Booking", back_populates="incidents")


    def generate_reference(self):
        """Generate unique incident reference"""
        import secrets
        import string

        if not self.incident_reference:
            random_part = ''.join(secrets.choice(string.ascii_uppercase + string.digits)
                                  for _ in range(8))
            self.incident_reference = f"INC{random_part}"

        return self.incident_reference

    @property
    def is_urgent(self):
        """Check if incident requires urgent attention"""
        return (
                self.severity in [IncidentSeverity.HIGH, IncidentSeverity.CRITICAL] or
                'safety' in self.incident_category or
                self.status == 'reported'
        )


# ===========================================================================
# SETTINGS (Production Admin Control)
# ===========================================================================

class TransportSetting(TransportBase):
    """Production settings with audit trail and validation"""
    __tablename__ = "transport_settings"
    __table_args__ = (
        UniqueConstraint("key", name="uq_setting_key"),
        Index("ix_setting_category", "category", "is_public"),
        Index("ix_setting_updated", "updated_at"),
    )

    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(JSONB, nullable=False)

    # Metadata
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50), nullable=False)
    subcategory = db.Column(db.String(50))

    # Configuration
    data_type = db.Column(db.String(20), nullable=False)
    allowed_values = db.Column(JSONB)
    validation_rules = db.Column(JSONB)
    default_value = db.Column(JSONB)

    # Access control
    is_public = db.Column(db.Boolean, default=False)
    is_advanced = db.Column(db.Boolean, default=False)
    requires_permission = db.Column(db.String(100))

    # Operational
    requires_restart = db.Column(db.Boolean, default=False)
    requires_redeploy = db.Column(db.Boolean, default=False)
    can_be_overridden_env = db.Column(db.Boolean, default=True)

    # Audit
    last_modified_by = db.Column(db.BigInteger, db.ForeignKey("users.id"))
    modification_history = db.Column(JSONB, default=lambda: [])

    # Relationships
    modified_by_user = relationship("User", foreign_keys=[last_modified_by])

    @validates('value')
    def validate_value(self, key, value):
        """Validate setting value based on data type and rules"""
        from app.core.validators import validate_setting_value

        return validate_setting_value(
            value=value,
            data_type=self.data_type,
            allowed_values=self.allowed_values,
            validation_rules=self.validation_rules
        )

    def to_safe_dict(self):
        """Return safe representation (excludes sensitive data)"""
        safe_fields = ['key', 'name', 'description', 'category', 'subcategory',
                       'data_type', 'is_public', 'is_advanced']

        result = {field: getattr(self, field) for field in safe_fields}

        # Only include value if setting is public
        if self.is_public:
            result['value'] = self.value

        return result


# ===========================================================================
# ASSOCIATION TABLES
# ===========================================================================

organisation_drivers = db.Table(
    'organisation_drivers',
    db.Column('id', db.BigInteger, primary_key=True, autoincrement=True),
    db.Column('organisation_id', db.BigInteger,
              db.ForeignKey('organisation_transport_profiles.id', ondelete='CASCADE'),
              nullable=False),
    db.Column('driver_id', db.BigInteger,
              db.ForeignKey('driver_profiles.id', ondelete='CASCADE'),
              nullable=False),
    db.Column('role', db.String(50), default='driver'),
    db.Column('is_active', db.Boolean, default=True, nullable=False),
    db.Column('joined_at', db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
    db.Column('left_at', db.DateTime(timezone=True)),
    db.UniqueConstraint('organisation_id', 'driver_id', name='uq_org_driver'),
    Index('ix_org_drivers', 'organisation_id', 'driver_id', 'is_active')
)


# ===========================================================================
# DATABASE EVENTS
# ===========================================================================

@event.listens_for(DriverProfile, 'before_insert')
def generate_driver_code(mapper, connection, target):
    """Generate unique driver code before insert"""
    if not target.driver_code:
        import secrets
        import string

        # Format: DRV-XXXXXX
        random_part = ''.join(secrets.choice(string.ascii_uppercase + string.digits)
                              for _ in range(6))
        target.driver_code = f"DRV-{random_part}"


@event.listens_for(Booking, 'before_insert')
def set_booking_defaults(mapper, connection, target):
    """Set booking defaults before insert"""
    target.generate_booking_reference()

    # Calculate amounts if not set
    if target.subtotal is None:
        target.subtotal = target.base_price or Decimal('0.00')

    if target.total_amount is None:
        target.total_amount = target.subtotal

    if target.final_price is None:
        target.final_price = target.total_amount


@event.listens_for(TransportIncident, 'before_insert')
def set_incident_defaults(mapper, connection, target):
    """Set incident defaults before insert"""
    target.generate_reference()


# ===========================================================================
# HELPER FUNCTIONS
# ===========================================================================

def get_setting(key: str, default: Any = None) -> Any:
    """Get setting with caching and environment variable override"""
    from app.extensions import cache
    from flask import current_app
    import os

    # Check environment variable first (if allowed)
    env_key = f"TRANSPORT_{key.upper()}"
    if os.environ.get(env_key):
        try:
            # Try to parse as JSON first
            import json
            return json.loads(os.environ[env_key])
        except json.JSONDecodeError:
            # Return as string
            return os.environ[env_key]

    # Check cache
    cache_key = f"transport:setting:{key}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # Get from database
    setting = TransportSetting.query.filter_by(key=key, is_deleted=False).first()
    if setting:
        value = setting.value

        # Cache with TTL based on category
        ttl = 300  # 5 minutes default
        if setting.category in ['security', 'payment']:
            ttl = 60  # 1 minute for sensitive settings

        cache.set(cache_key, value, timeout=ttl)
        return value

    # Return default
    return default


def update_setting(key: str, value: Any, modified_by: Optional[int] = None) -> bool:
    """Update setting with audit trail"""
    from app.extensions import cache, db

    setting = TransportSetting.query.filter_by(key=key, is_deleted=False).first()
    if not setting:
        return False

    # Store old value in history
    history_entry = {
        'old_value': setting.value,
        'new_value': value,
        'changed_at': datetime.now(timezone.utc).isoformat(),
        'changed_by': modified_by
    }

    if not setting.modification_history:
        setting.modification_history = [history_entry]
    else:
        setting.modification_history.append(history_entry)

    # Update setting
    setting.value = value
    setting.last_modified_by = modified_by

    try:
        db.session.commit()

        # Invalidate cache
        cache.delete(f"transport:setting:{key}")

        # Log setting change
        from app.core.logging import audit_log
        audit_log(
            action='setting_updated',
            entity_type='transport_setting',
            entity_id=setting.id,
            details={'key': key, 'old_value': history_entry['old_value'], 'new_value': value},
            user_id=modified_by
        )

        return True
    except Exception as e:
        db.session.rollback()
        from app.core.logging import error_log
        error_log(f"Failed to update setting {key}: {e}")
        return False


def init_transport_settings():
    """Initialize production settings with everything disabled by default"""
    from app.extensions import db

    production_settings = [
        # ========== MODULE CONTROL ==========
        {
            'key': 'transport_module_enabled',
            'value': True,
            'name': 'Transport Module',
            'description': 'Enable/disable entire transport module',
            'category': 'module',
            'subcategory': 'control',
            'data_type': 'boolean',
            'is_public': False,
            'is_advanced': False,
            'requires_restart': True,
            'default_value': True,
            'validation_rules': {'required': True}
        },
        {
            'key': 'environment',
            'value': 'development',
            'name': 'Environment',
            'description': 'Application environment',
            'category': 'module',
            'subcategory': 'control',
            'data_type': 'string',
            'allowed_values': ['development', 'staging', 'production'],
            'is_public': False,
            'is_advanced': True,
            'requires_restart': True,
            'default_value': 'development'
        },

        # ========== PROVIDER ONBOARDING ==========
        {
            'key': 'provider_onboarding_enabled',
            'value': True,
            'name': 'Provider Onboarding',
            'description': 'Enable new provider registration',
            'category': 'provider',
            'subcategory': 'onboarding',
            'data_type': 'boolean',
            'default_value': True
        },
        {
            'key': 'require_license_verification',
            'value': False,  # OFF in dev
            'name': 'License Verification',
            'description': 'Require driver license verification',
            'category': 'provider',
            'subcategory': 'verification',
            'data_type': 'boolean',
            'default_value': True,
            'requires_permission': 'provider:verify'
        },
        {
            'key': 'require_police_clearance',
            'value': False,  # OFF in dev
            'name': 'Police Clearance',
            'description': 'Require police clearance certificate',
            'category': 'provider',
            'subcategory': 'verification',
            'data_type': 'boolean',
            'default_value': True,
            'requires_permission': 'provider:verify'
        },
        {
            'key': 'require_insurance_verification',
            'value': False,  # OFF in dev
            'name': 'Insurance Verification',
            'description': 'Require vehicle insurance verification',
            'category': 'provider',
            'subcategory': 'verification',
            'data_type': 'boolean',
            'default_value': True,
            'requires_permission': 'provider:verify'
        },
        {
            'key': 'auto_approve_providers',
            'value': True,  # ON in dev
            'name': 'Auto Approve Providers',
            'description': 'Auto-approve providers in development',
            'category': 'provider',
            'subcategory': 'approval',
            'data_type': 'boolean',
            'default_value': False
        },

        # ========== BOOKING SYSTEM ==========
        {
            'key': 'booking_system_enabled',
            'value': True,
            'name': 'Booking System',
            'description': 'Enable booking creation and management',
            'category': 'booking',
            'subcategory': 'control',
            'data_type': 'boolean',
            'default_value': True
        },
        {
            'key': 'instant_booking_enabled',
            'value': True,
            'name': 'Instant Booking',
            'description': 'Allow instant bookings without provider approval',
            'category': 'booking',
            'subcategory': 'workflow',
            'data_type': 'boolean',
            'default_value': True
        },
        {
            'key': 'group_booking_enabled',
            'value': True,
            'name': 'Group Booking',
            'description': 'Enable group booking functionality',
            'category': 'booking',
            'subcategory': 'features',
            'data_type': 'boolean',
            'default_value': True
        },
        {
            'key': 'max_group_size',
            'value': 50,
            'name': 'Maximum Group Size',
            'description': 'Maximum number of passengers per group booking',
            'category': 'booking',
            'subcategory': 'limits',
            'data_type': 'integer',
            'validation_rules': {'min': 1, 'max': 200},
            'default_value': 50
        },

        # ========== PAYMENT PROCESSING ==========
        {
            'key': 'payment_processing_enabled',
            'value': False,  # OFF in dev
            'name': 'Payment Processing',
            'description': 'Enable real payment processing',
            'category': 'payment',
            'subcategory': 'control',
            'data_type': 'boolean',
            'default_value': False,
            'requires_permission': 'payment:process'
        },
        {
            'key': 'mock_payments_enabled',
            'value': True,  # ON in dev
            'name': 'Mock Payments',
            'description': 'Use mock payment system for testing',
            'category': 'payment',
            'subcategory': 'testing',
            'data_type': 'boolean',
            'default_value': True
        },
        {
            'key': 'platform_commission_percent',
            'value': 15.0,
            'name': 'Platform Commission',
            'description': 'Platform commission percentage',
            'category': 'payment',
            'subcategory': 'fees',
            'data_type': 'decimal',
            'validation_rules': {'min': 0, 'max': 50, 'precision': 2},
            'default_value': 15.0
        },

        # ========== SAFETY FEATURES ==========
        {
            'key': 'safety_features_enabled',
            'value': False,  # OFF in dev
            'name': 'Safety Features',
            'description': 'Enable safety features (SOS, live tracking, etc.)',
            'category': 'safety',
            'subcategory': 'control',
            'data_type': 'boolean',
            'default_value': False
        },
        {
            'key': 'live_tracking_enabled',
            'value': False,  # OFF in dev
            'name': 'Live Tracking',
            'description': 'Enable real-time vehicle tracking',
            'category': 'safety',
            'subcategory': 'tracking',
            'data_type': 'boolean',
            'default_value': False,
            'requires_permission': 'tracking:view'
        },
        {
            'key': 'sos_button_enabled',
            'value': False,  # OFF in dev
            'name': 'SOS Button',
            'description': 'Enable SOS emergency button',
            'category': 'safety',
            'subcategory': 'emergency',
            'data_type': 'boolean',
            'default_value': False
        },

        # ========== INTEGRATIONS ==========
        {
            'key': 'external_integrations_enabled',
            'value': False,  # OFF in dev
            'name': 'External Integrations',
            'description': 'Enable external platform integrations',
            'category': 'integrations',
            'subcategory': 'control',
            'data_type': 'boolean',
            'default_value': False
        },
        {
            'key': 'uber_integration_enabled',
            'value': False,  # OFF in dev
            'name': 'Uber Integration',
            'description': 'Enable Uber integration',
            'category': 'integrations',
            'subcategory': 'platforms',
            'data_type': 'boolean',
            'default_value': False
        },
        {
            'key': 'bolt_integration_enabled',
            'value': False,  # OFF in dev
            'name': 'Bolt Integration',
            'description': 'Enable Bolt integration',
            'category': 'integrations',
            'subcategory': 'platforms',
            'data_type': 'boolean',
            'default_value': False
        },

        # ========== INTELLIGENCE FEATURES ==========
        {
            'key': 'intelligence_features_enabled',
            'value': False,  # OFF in dev
            'name': 'Intelligence Features',
            'description': 'Enable AI/ML features',
            'category': 'intelligence',
            'subcategory': 'control',
            'data_type': 'boolean',
            'default_value': False,
            'is_advanced': True
        },
        {
            'key': 'demand_forecasting_enabled',
            'value': False,  # OFF in dev
            'name': 'Demand Forecasting',
            'description': 'Enable AI demand forecasting',
            'category': 'intelligence',
            'subcategory': 'forecasting',
            'data_type': 'boolean',
            'default_value': False,
            'is_advanced': True
        },
        {
            'key': 'dynamic_pricing_enabled',
            'value': False,  # OFF in dev
            'name': 'Dynamic Pricing',
            'description': 'Enable surge/dynamic pricing',
            'category': 'intelligence',
            'subcategory': 'pricing',
            'data_type': 'boolean',
            'default_value': False,
            'is_advanced': True
        },
        {
            'key': 'contingency_planning_enabled',
            'value': False,  # OFF in dev
            'name': 'Contingency Planning',
            'description': 'Enable automatic contingency handling',
            'category': 'intelligence',
            'subcategory': 'reliability',
            'data_type': 'boolean',
            'default_value': False,
            'is_advanced': True
        },

        # ========== NOTIFICATIONS ==========
        {
            'key': 'notifications_enabled',
            'value': False,  # OFF in dev
            'name': 'Notifications',
            'description': 'Enable email/SMS/push notifications',
            'category': 'notifications',
            'subcategory': 'control',
            'data_type': 'boolean',
            'default_value': False
        },
        {
            'key': 'mock_notifications_enabled',
            'value': True,  # ON in dev
            'name': 'Mock Notifications',
            'description': 'Log notifications instead of sending',
            'category': 'notifications',
            'subcategory': 'testing',
            'data_type': 'boolean',
            'default_value': True
        },

        # ========== PERFORMANCE ==========
        {
            'key': 'caching_enabled',
            'value': True,
            'name': 'Caching',
            'description': 'Enable Redis caching',
            'category': 'performance',
            'subcategory': 'caching',
            'data_type': 'boolean',
            'default_value': True
        },
        {
            'key': 'query_caching_ttl_minutes',
            'value': 5,
            'name': 'Query Cache TTL',
            'description': 'Query cache TTL in minutes',
            'category': 'performance',
            'subcategory': 'caching',
            'data_type': 'integer',
            'validation_rules': {'min': 1, 'max': 60},
            'default_value': 5
        },

        # ========== MONITORING ==========
        {
            'key': 'monitoring_enabled',
            'value': False,  # OFF in dev
            'name': 'Monitoring',
            'description': 'Enable application monitoring',
            'category': 'monitoring',
            'subcategory': 'control',
            'data_type': 'boolean',
            'default_value': False,
            'is_advanced': True
        },
        {
            'key': 'metrics_collection_enabled',
            'value': False,  # OFF in dev
            'name': 'Metrics Collection',
            'description': 'Enable collection of performance metrics',
            'category': 'monitoring',
            'subcategory': 'metrics',
            'data_type': 'boolean',
            'default_value': False,
            'is_advanced': True
        },

        # ========== SECURITY ==========
        {
            'key': 'rate_limiting_enabled',
            'value': False,  # OFF in dev
            'name': 'Rate Limiting',
            'description': 'Enable API rate limiting',
            'category': 'security',
            'subcategory': 'protection',
            'data_type': 'boolean',
            'default_value': False,
            'is_advanced': True
        },
        {
            'key': 'data_encryption_enabled',
            'value': False,  # OFF in dev
            'name': 'Data Encryption',
            'description': 'Enable encryption of sensitive data',
            'category': 'security',
            'subcategory': 'encryption',
            'data_type': 'boolean',
            'default_value': False,
            'is_advanced': True
        },
    ]

    try:
        for setting_data in production_settings:
            exists = TransportSetting.query.filter_by(
                key=setting_data['key'],
                is_deleted=False
            ).first()

            if not exists:
                setting = TransportSetting(**setting_data)
                db.session.add(setting)

        db.session.commit()
        print("✅ Production transport settings initialized")

    except Exception as e:
        db.session.rollback()
        print(f"⚠️  Could not initialize production settings: {e}")
        # Don't crash - settings will be created on first access


# ===========================================================================
# HELPER FUNCTIONS FOR DRIVER-VEHICLE MANAGEMENT
# ===========================================================================

def assign_driver_to_vehicle(driver, vehicle, reason='shift_start', authorized_by=None, notes=None):
    """
    Assign a driver to a vehicle and track it in history

    Scenarios:
    - Driver starts shift
    - Reassign driver to different vehicle
    - New driver takes over
    """
    from sqlalchemy import and_
    from datetime import datetime, timezone

    # Check if driver already has a vehicle
    current_driver_assignment = DriverVehicleHistory.query.filter(
        and_(
            DriverVehicleHistory.driver_id == driver.id,
            DriverVehicleHistory.ended_at == None
        )
    ).first()

    if current_driver_assignment:
        # End the current assignment
        current_driver_assignment.ended_at = datetime.now(timezone.utc)
        current_driver_assignment.notes = f"Ended for reassignment to vehicle {vehicle.id}"

    # Check if vehicle already has a driver
    current_vehicle_assignment = DriverVehicleHistory.query.filter(
        and_(
            DriverVehicleHistory.vehicle_id == vehicle.id,
            DriverVehicleHistory.ended_at == None
        )
    ).first()

    if current_vehicle_assignment:
        # End that driver's assignment to this vehicle
        current_vehicle_assignment.ended_at = datetime.now(timezone.utc)
        current_vehicle_assignment.notes = f"Driver {current_vehicle_assignment.driver_id} removed for new driver {driver.id}"

    # Create new assignment
    new_assignment = DriverVehicleHistory(
        driver_id=driver.id,
        vehicle_id=vehicle.id,
        started_at=datetime.now(timezone.utc),
        ended_at=None,
        assignment_reason=reason,
        notes=notes,
        authorized_by=authorized_by.id if authorized_by else None
    )

    db.session.add(new_assignment)

    # Update the current relationships
    driver.current_vehicle_id = vehicle.id
    vehicle.current_driver_id = driver.id

    db.session.commit()

    return new_assignment


def handle_vehicle_breakdown(driver, broken_vehicle, replacement_vehicle,
                             breakdown_reason, authorized_by=None, notes=None):
    """
    Handle a vehicle breakdown scenario

    Scenario:
    - Driver's vehicle breaks down
    - They need a replacement vehicle
    - Must track why the change happened
    """
    from datetime import datetime, timezone

    # End the current assignment with the broken vehicle
    current_assignment = DriverVehicleHistory.query.filter(
        and_(
            DriverVehicleHistory.driver_id == driver.id,
            DriverVehicleHistory.vehicle_id == broken_vehicle.id,
            DriverVehicleHistory.ended_at == None
        )
    ).first()

    if current_assignment:
        current_assignment.ended_at = datetime.now(timezone.utc)
        current_assignment.was_breakdown = True
        current_assignment.breakdown_reason = breakdown_reason
        current_assignment.notes = notes or f"Breakdown: {breakdown_reason}"

    # Check if replacement vehicle has a driver
    replacement_assignment = DriverVehicleHistory.query.filter(
        and_(
            DriverVehicleHistory.vehicle_id == replacement_vehicle.id,
            DriverVehicleHistory.ended_at == None
        )
    ).first()

    if replacement_assignment:
        # Remove the previous driver from this vehicle
        replacement_assignment.ended_at = datetime.now(timezone.utc)
        replacement_assignment.notes = f"Vehicle reassigned due to breakdown of vehicle {broken_vehicle.id}"
        previous_driver = replacement_assignment.driver
        previous_driver.current_vehicle_id = None

    # Assign driver to replacement vehicle
    new_assignment = DriverVehicleHistory(
        driver_id=driver.id,
        vehicle_id=replacement_vehicle.id,
        started_at=datetime.now(timezone.utc),
        ended_at=None,
        assignment_reason='breakdown_replacement',
        notes=f"Replacement for broken vehicle {broken_vehicle.id}. Reason: {breakdown_reason}",
        authorized_by=authorized_by.id if authorized_by else None,
        was_breakdown=True,
        breakdown_reason=breakdown_reason,
        replacement_vehicle_id=broken_vehicle.id
    )

    db.session.add(new_assignment)

    # Update current relationships
    driver.current_vehicle_id = replacement_vehicle.id
    broken_vehicle.current_driver_id = None
    replacement_vehicle.current_driver_id = driver.id

    db.session.commit()

    return new_assignment


def get_driver_history(driver_id, days=30):
    """Get a driver's complete history for the last X days"""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import and_

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    history = DriverVehicleHistory.query.filter(
        and_(
            DriverVehicleHistory.driver_id == driver_id,
            DriverVehicleHistory.started_at >= cutoff_date
        )
    ).order_by(DriverVehicleHistory.started_at.desc()).all()

    return history


def get_vehicle_history(vehicle_id, days=30):
    """Get a vehicle's complete history for the last X days"""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import and_

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    history = DriverVehicleHistory.query.filter(
        and_(
            DriverVehicleHistory.vehicle_id == vehicle_id,
            DriverVehicleHistory.started_at >= cutoff_date
        )
    ).order_by(DriverVehicleHistory.started_at.desc()).all()

    return history


# ===========================================================================
# INITIALIZATION
# ===========================================================================

def init_transport_module():
    """Initialize transport module with production defaults"""
    try:
        # Create tables if they don't exist
        from app.extensions import db
        db.create_all()

        # Initialize settings
        init_transport_settings()

        print("🚀 Production Transport Module Initialized")

    except Exception as e:
        print(f"⚠️  Transport module initialization warning: {e}")
        # Continue - tables might already exist


# Initialize on import if in development
if __name__ != "__main__":
    # We'll initialize via Flask app factory instead
    pass
