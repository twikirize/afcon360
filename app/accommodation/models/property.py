# app/accommodation/models/property.py
"""
Property models - High-standard, using namespaced enums and fully aligned with DB.
"""

from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    Column, BigInteger, String, Boolean, DateTime, Date,
    ForeignKey, Float, Integer, Text, JSON, Numeric,
    Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func
from app.extensions import db
from app.models.base import BaseModel
from app.accommodation.models.review import Review
import enum
import uuid as uuid_lib


# ==========================================
# Namespaced Enums for Property
# ==========================================

class AccommodationPropertyType(enum.Enum):
    """Property type - matches DB enum 'accommodation_propertytype'"""
    ENTIRE_PLACE = "entire_place"
    PRIVATE_ROOM = "private_room"
    SHARED_ROOM = "shared_room"
    HOTEL_ROOM = "hotel_room"
    COMMUNITY_HOST = "community_host"
    LODGE = "lodge"
    HOSTEL = "hostel"


class AccommodationCancellationPolicy(enum.Enum):
    """Cancellation policy - matches DB enum 'accommodation_cancellationpolicy'"""
    FLEXIBLE = "flexible"
    MODERATE = "moderate"
    STRICT = "strict"
    SUPER_STRICT = "super_strict"


class AccommodationPropertyStatus(enum.Enum):
    """Property status - matches DB enum 'accommodation_propertystatus'"""
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    NEEDS_INFORMATION = "needs_information"
    ACTIVE = "active"
    PUBLISHED = "published"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"
    PENDING_REVIEW = "pending_review"


class AccommodationVerificationStatus(enum.Enum):
    """Verification status - matches DB enum 'accommodation_verificationstatus'"""
    UNVERIFIED = "unverified"
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


# FIX 1: Removed AccommodationBlockedReason from here.
# It was defined in BOTH property.py and availability.py, causing a shadowing conflict.
# It belongs in availability.py (alongside BlockedDate which uses it) - import it from there
# if property.py ever needs it directly.


# ==========================================
# Property Model
# ==========================================

class Property(BaseModel):
    __tablename__ = "accommodation_properties"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_property_slug"),
        Index("idx_property_city_country", "city", "country"),
        Index("idx_property_status_active", "status", "is_active"),
        Index("idx_property_price_range", "base_price_per_night"),
        Index("idx_property_geolocation", "latitude", "longitude"),
        Index("idx_property_owner", "owner_user_id", "owner_org_id"),
        Index("idx_property_status", "status"),
        Index("idx_property_verified", "is_verified"),
        Index("idx_property_owner_status", "owner_user_id", "status"),
        CheckConstraint(
            "(owner_user_id IS NOT NULL) OR (owner_org_id IS NOT NULL)",
            name="ck_property_has_owner"
        ),
        CheckConstraint("base_price_per_night >= 0", name="ck_price_positive"),
        CheckConstraint("max_guests >= 1", name="ck_max_guests_min"),
        CheckConstraint(
            "property_type IN ('entire_place', 'private_room', 'shared_room', 'hotel_room', 'community_host', 'lodge', 'hostel')",
            name="ck_property_type_valid"
        ),
        CheckConstraint(
            "cancellation_policy IN ('flexible', 'moderate', 'strict', 'super_strict')",
            name="ck_cancellation_policy_valid"
        ),
        CheckConstraint(
            "status IN ('draft', 'submitted', 'pending_review', 'under_review', 'approved', 'needs_information', 'active', 'published', 'suspended', 'archived')",
            name="ck_property_status_valid"
        ),
        CheckConstraint(
            "visibility IN ('public', 'event_only', 'hidden', 'private_invite')",
            name="ck_property_visibility_valid"
        ),
        CheckConstraint(
            "verification_status IN ('unverified', 'pending', 'verified', 'rejected')",
            name="ck_verification_status_valid"
        ),
    )

    # -------------------------------
    # Ownership (supports both individual and organisation)
    # -------------------------------
    owner_user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    owner_org_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="CASCADE"), nullable=True)

    # -------------------------------
    # Identity
    # -------------------------------
    public_id = Column(
        String(64), unique=True, nullable=False, index=True,
        default=lambda: str(uuid_lib.uuid4()),
    )
    title = Column(String(200), nullable=False)
    slug = Column(String(220), nullable=False, unique=True)
    description = Column(Text, nullable=False)
    summary = Column(String(500), nullable=True)
    property_type = Column(String(50), nullable=False, default="hotel_room")

    # -------------------------------
    # Location
    # -------------------------------
    address_line1 = Column(String(255), nullable=False)
    address_line2 = Column(String(255), nullable=True)
    city = Column(String(100), nullable=False)
    state = Column(String(100), nullable=True)
    country = Column(String(2), nullable=False)
    postal_code = Column(String(20), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # -------------------------------
    # Capacity
    # -------------------------------
    max_guests = Column(Integer, nullable=False, default=2)
    bedrooms = Column(Integer, default=1)
    beds = Column(Integer, default=1)
    bathrooms = Column(Float, default=1.0)

    # -------------------------------
    # Pricing
    # -------------------------------
    base_price_per_night = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="USD")
    cleaning_fee = Column(Numeric(10, 2), default=0)
    service_fee_pct = Column(Numeric(5, 2), default=10.0)

    # -------------------------------
    # Stay Requirements
    # -------------------------------
    min_stay_nights = Column(Integer, default=1, nullable=False)
    max_stay_nights = Column(Integer, nullable=True)

    # -------------------------------
    # Policies
    # -------------------------------
    cancellation_policy = Column(String(50), default="moderate")
    check_in_time = Column(String(20), default="14:00")
    check_out_time = Column(String(20), default="11:00")
    instant_book = Column(Boolean, default=False)
    require_host_approval = Column(Boolean, default=False)
    booking_mode = Column(String(20), default="instant", nullable=False)  # instant, host_approval

    # -------------------------------
    # Policy Violation Tracking
    # -------------------------------
    policy_violations = Column(Integer, default=0, nullable=False)
    auto_suspend_threshold = Column(Integer, default=5, nullable=False)
    is_suspended = Column(Boolean, default=False, nullable=False, index=True)
    suspension_reason = Column(Text, nullable=True)

    # -------------------------------
    # House Rules
    # -------------------------------
    house_rules = Column(Text, nullable=True)
    allow_pets = Column(Boolean, default=False)
    allow_smoking = Column(Boolean, default=False)
    allow_events = Column(Boolean, default=False)

    # -------------------------------
    # Media
    # -------------------------------
    main_image = Column(String(500), nullable=True)
    gallery = Column(JSON, nullable=False, default=list)

    # -------------------------------
    # Status Flags & Architecture Columns
    # -------------------------------
    status = Column(String(50), default="draft", nullable=False)
    visibility = Column(
        String(30),
        default="public",
        nullable=False,
        index=True,
        server_default="public"
    )
    is_publicly_visible = Column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
        server_default="true"
    )
    trust_score = Column(
        Float,
        default=0.0,
        nullable=False,
        server_default="0.0"
    )
    readiness_score = Column(
        Float,
        default=0.0,
        nullable=False,
        server_default="0.0"
    )
    is_verified = Column(Boolean, default=False, nullable=False, )
    is_featured = Column(Boolean, default=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)

    # -------------------------------
    # Verification
    # -------------------------------
    verification_status = Column(String(50), default="unverified")
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    verification_notes = Column(Text, nullable=True)

    # Internal moderation notes (separate from verification_notes which go to host)
    moderation_notes = Column(Text, nullable=True)

    # -------------------------------
    # Archive audit (soft-delete recovery)
    # -------------------------------
    archived_reason = Column(Text, nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    archived_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    # -------------------------------
    # Ratings (denormalized)
    # -------------------------------
    overall_rating = Column(Float, default=0.0)
    total_reviews = Column(Integer, default=0)

    # -------------------------------
    # OTA Trust Signals (denormalized)
    # -------------------------------
    host_response_rate = Column(Numeric(5, 2), nullable=True)  # e.g. 95.5 = 95.5%
    host_response_time_hours = Column(Integer, nullable=True)   # avg hours to respond
    last_booked_at = Column(DateTime(timezone=True), nullable=True)
    total_bookings = Column(Integer, default=0, server_default='0')
    views_last_24h = Column(Integer, default=0, server_default='0')

    # -------------------------------
    # Event Context (for community hosts)
    # -------------------------------
    event_metadata = Column(JSON, nullable=True, default=dict)

    # -------------------------------
    # Relationships to EventHostRegistration
    # -------------------------------
    event_host_registrations = relationship(
        "EventHostRegistration", 
        back_populates="property",
        cascade="all, delete-orphan"
    )

    # -------------------------------
    # SEO
    # -------------------------------
    meta_title = Column(String(255), nullable=True)
    meta_description = Column(String(500), nullable=True)

    # -------------------------------
    # Relationships
    # -------------------------------
    owner_user = relationship("User", foreign_keys=[owner_user_id], backref="owned_properties")
    owner_org = relationship("Organisation", foreign_keys=[owner_org_id], backref="owned_properties")
    photos = relationship("PropertyPhoto", back_populates="property", cascade="all, delete-orphan")
    amenities = relationship("PropertyAmenity", back_populates="property", cascade="all, delete-orphan")
    rules = relationship("PropertyRule", back_populates="property", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="property", cascade="all, delete-orphan")
    bookings = relationship("AccommodationBooking", back_populates="accommodation_property",cascade="all, delete-orphan")

    blocked_dates = relationship("BlockedDate", back_populates="property", cascade="all, delete-orphan")
    availability_rules = relationship("AvailabilityRule", back_populates="property", cascade="all, delete-orphan")

    booking_policy = relationship(
        "PropertyBookingPolicy",
        back_populates="property",
        uselist=False,
        cascade="all, delete-orphan",
    )

    cancellation_policies = relationship(
        "CancellationPolicy",
        back_populates="property",
        cascade="all, delete-orphan",
    )

    payment_methods = relationship(
        "PropertyPaymentMethod",
        back_populates="property",
        cascade="all, delete-orphan",
    )

    room_types = relationship("RoomType", back_populates="listing", cascade="all, delete-orphan")
    rooms = relationship("Room", back_populates="listing", cascade="all, delete-orphan")

    # -------------------------------
    # Core Methods
    # -------------------------------
    def __repr__(self):
        owner = f"user={self.owner_user_id}" if self.owner_user_id else f"org={self.owner_org_id}"
        return f"<Property {self.id}: {self.title} ({owner})>"

    @property
    def owner_display_name(self):
        if self.owner_user:
            return self.owner_user.username or self.owner_user.email
        elif self.owner_org:
            return self.owner_org.legal_name
        return "Unknown"

    @property
    def owner_type(self):
        return "individual" if self.owner_user_id else "organisation"

    @property
    def full_address(self):
        parts = [self.address_line1]
        if self.address_line2:
            parts.append(self.address_line2)
        parts.append(f"{self.city}, {self.state}" if self.state else self.city)
        parts.append(self.country)
        return ", ".join(parts)

    # -------------------------------
    # Unified Media (source of truth: app/media)
    # -------------------------------
    def media_photos(self, media_type: str = None):
        """
        Return all media for this property from the unified media hub
        (module='accommodation', entity_id=self.public_id).
        This is the canonical source of truth for property/room images.
        """
        from app.media.service import MediaService
        return MediaService.get_for_entity(
            module="accommodation",
            entity_id=self.public_id,
            media_type=media_type,
            # Older records used the internal property ID as entity_id. This
            # remains an internal compatibility lookup and is never exposed.
            legacy_entity_ids=[str(self.id), self.slug],
        )

    def legacy_photo_urls(self):
        """Resolve photos from the pre-unified accommodation_photos table."""
        from app.media.service import MediaService
        from app.media.storage import get_storage_backend

        urls = []
        for photo in sorted(self.photos or [], key=lambda item: (
                getattr(item, 'is_cover', False) is not True,
                getattr(item, 'display_order', 0) or 0,
        )):
            storage_key = getattr(photo, 'storage_key', None)
            if not storage_key:
                continue
            url = storage_key if str(storage_key).startswith(('/', 'http://', 'https://')) else None
            if not url:
                try:
                    url = get_storage_backend().get_url(storage_key)
                except Exception:
                    url = None
            if url and url not in urls:
                urls.append(url)
        return urls

    @property
    def cover_image_url(self):
        """
        Cover image URL from the unified media hub (source of truth).
        Falls back to the legacy main_image column for backward compatibility.
        """
        from app.media.service import MediaService
        media = self.media_photos()
        cover = next(
            (
                m for m in media
                if getattr(m, "is_cover", False)
                and MediaService.get_original_url(m)
            ),
            None,
        )
        if cover:
            return MediaService.get_original_url(cover)
        # Fallback to legacy column if no unified media exists yet
        return self.main_image or MediaService.PLACEHOLDER_IMAGE

    @property
    def gallery_images(self):
        """
        List of gallery image URLs from the unified media hub (source of truth).
        Falls back to the legacy `gallery` JSON column for backward
        compatibility when no unified media exists yet.
        """
        from app.media.service import MediaService
        media = self.media_photos()
        if media:
            urls = [
                MediaService.get_original_url(m)
                for m in media
                if MediaService.get_original_url(m)
            ]
            if urls:
                return urls
        urls = self.legacy_photo_urls()
        legacy = self.gallery or []
        if isinstance(legacy, (list, tuple)):
            urls.extend(url for url in legacy if url not in urls)
        if self.main_image and self.main_image not in urls:
            urls.insert(0, self.main_image)
        return urls

    def is_owner(self, user_id=None, org_id=None):
        if user_id and self.owner_user_id == user_id:
            return True
        if org_id and self.owner_org_id == org_id:
            return True
        return False

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = datetime.now(timezone.utc)
        self.status = "archived"
        self.is_active = False

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.status = "draft"
        self.is_active = True

    def can_be_booked(self):
        return (self.status in ["active", "published"] and
                self.is_verified and
                self.is_active and
                not self.is_deleted)

    # -------------------------------
    # Validation
    # -------------------------------
    @validates('title')
    def validate_title(self, key, title):
        if not title or len(title) < 3:
            raise ValueError("Title must be at least 3 characters")
        if len(title) > 200:
            raise ValueError("Title must be less than 200 characters")
        return title.strip()

    @validates('max_guests')
    def validate_max_guests(self, key, value):
        if value < 1:
            raise ValueError("Must accommodate at least 1 guest")
        if value > 50:
            raise ValueError("Maximum 50 guests per property")
        return value


# ==========================================
# Property Photo Model
# ==========================================

class PropertyPhoto(BaseModel):
    __tablename__ = "accommodation_photos"
    __table_args__ = (
        UniqueConstraint("property_id", "display_order", name="uq_photo_order_per_property"),
    )

    property_id = Column(BigInteger, ForeignKey("accommodation_properties.id", ondelete="CASCADE"), nullable=False, index=True)
    property = relationship("Property", back_populates="photos")

    # -------------------------------
    # Image Data
    # -------------------------------
    storage_key = Column(String(500), nullable=False)
    caption = Column(String(200), nullable=True)

    # -------------------------------
    # Ordering
    # -------------------------------
    display_order = Column(Integer, default=0)
    is_cover = Column(Boolean, default=False)

    # -------------------------------
    # Metadata
    # -------------------------------
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String(100), nullable=True)

    def __repr__(self):
        return f"<PropertyPhoto {self.property_id}: order {self.display_order}>"


# ==========================================
# Amenity Models
# ==========================================

class Amenity(BaseModel):
    """Master list of amenities"""
    __tablename__ = "accommodation_amenities_master"

    code = Column(String(50), nullable=False, unique=True)
    name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=True)
    icon = Column(String(50), nullable=True)
    display_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    def __repr__(self):
        return f"<Amenity {self.code}: {self.name}>"


class PropertyAmenity(BaseModel):
    """Junction table: Property <-> Amenity"""
    __tablename__ = "accommodation_property_amenities"
    __table_args__ = (
        UniqueConstraint("property_id", "amenity_id", name="uq_property_amenity"),
    )

    property_id = Column(BigInteger, ForeignKey("accommodation_properties.id", ondelete="CASCADE"), nullable=False, index=True)
    amenity_id = Column(BigInteger, ForeignKey("accommodation_amenities_master.id", ondelete="CASCADE"), nullable=False, index=True)

    property = relationship("Property", back_populates="amenities")
    amenity = relationship("Amenity")


class PropertyRule(BaseModel):
    """Custom rules for each property"""
    __tablename__ = "accommodation_rules"

    property_id = Column(BigInteger, ForeignKey("accommodation_properties.id", ondelete="CASCADE"), nullable=False, index=True)
    property = relationship("Property", back_populates="rules")

    rule_text = Column(Text, nullable=False)
    is_important = Column(Boolean, default=False)

    def __repr__(self):
        return f"<PropertyRule {self.property_id}: {self.rule_text[:50]}>"


# Guarantee every Property has a public_id (UUID) before insert, including
# rows that predate the column. Mirrors the User model's public_id guarantee.
from sqlalchemy import event  # noqa: E402

@event.listens_for(Property, 'before_insert')
def _ensure_property_public_id(mapper, connection, target):
    if not target.public_id:
        target.public_id = str(uuid_lib.uuid4())
