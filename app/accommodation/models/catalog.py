# app/accommodation/models/catalog.py
"""
Accommodation catalog lookup tables.

These tables are the database-backed source of truth for the *options* shown
on host listing forms (property type, listing type, cancellation policy tier,
booking mode, currency). `Property` keeps its String columns + CHECK
constraints; the config tables below only drive the form options and the
route/template catalogs so values presented to hosts cannot drift from what
the database accepts.

Models intentionally use the `*Config` / distinct names to avoid colliding
with the existing model enums (`AccommodationPropertyType`, etc.).
"""

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.extensions import db
from app.models.base import BaseModel


class AccommodationPropertyTypeConfig(BaseModel):
    """Valid property (structure) types: apartment, house, villa, ..."""

    __tablename__ = "accommodation_property_types"
    __table_args__ = (
        UniqueConstraint("code", name="uq_accommodation_property_type_code"),
    )

    code = Column(String(50), nullable=False, index=True)
    label = Column(String(100), nullable=False)
    commercial = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    host_types = relationship(
        "PropertyTypeHostType",
        back_populates="property_type_config",
        cascade="all, delete-orphan",
    )
    listing_types = relationship(
        "PropertyTypeListingType",
        back_populates="property_type_config",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<AccommodationPropertyTypeConfig {self.code}>"


class AccommodationListingTypeConfig(BaseModel):
    """Valid listing (occupancy) types: entire_place, private_room, ..."""

    __tablename__ = "accommodation_listing_types"
    __table_args__ = (
        UniqueConstraint("code", name="uq_accommodation_listing_type_code"),
    )

    code = Column(String(50), nullable=False, index=True)
    label = Column(String(100), nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<AccommodationListingTypeConfig {self.code}>"


class AccommodationPolicyTier(BaseModel):
    """Cancellation policy tiers (flexible / moderate / strict / super_strict).

    Distinct from `CancellationPolicy` (per-property phase rules); this table
    holds the host-facing tier options and their card copy.
    """

    __tablename__ = "accommodation_policy_tiers"
    __table_args__ = (
        UniqueConstraint("code", name="uq_accommodation_policy_tier_code"),
    )

    code = Column(String(50), nullable=False, index=True)
    label = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    icon = Column(String(16), nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<AccommodationPolicyTier {self.code}>"


class AccommodationBookingMode(BaseModel):
    """Booking modes: instant / host_approval."""

    __tablename__ = "accommodation_booking_modes"
    __table_args__ = (
        UniqueConstraint("code", name="uq_accommodation_booking_mode_code"),
    )

    code = Column(String(50), nullable=False, index=True)
    label = Column(String(120), nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<AccommodationBookingMode {self.code}>"


class AccommodationCurrency(BaseModel):
    """Currencies offered for accommodation pricing."""

    __tablename__ = "accommodation_currencies"
    __table_args__ = (
        UniqueConstraint("code", name="uq_accommodation_currency_code"),
    )

    code = Column(String(3), nullable=False, index=True)
    name = Column(String(80), nullable=True)
    symbol = Column(String(8), nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<AccommodationCurrency {self.code}>"


class PropertyTypeHostType(BaseModel):
    """Which host types (individual/organisation) may list a property type."""

    __tablename__ = "accommodation_property_type_host_types"
    __table_args__ = (
        UniqueConstraint(
            "property_type_code",
            "host_type",
            name="uq_property_type_host_type",
        ),
    )

    property_type_code = Column(
        String(50),
        ForeignKey("accommodation_property_types.code", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    host_type = Column(String(20), nullable=False)

    property_type_config = relationship(
        "AccommodationPropertyTypeConfig",
        back_populates="host_types",
    )

    def __repr__(self):
        return f"<PropertyTypeHostType {self.property_type_code} / {self.host_type}>"


class PropertyTypeListingType(BaseModel):
    """Which listing types are valid for a property type."""

    __tablename__ = "accommodation_property_type_listing_types"
    __table_args__ = (
        UniqueConstraint(
            "property_type_code",
            "listing_type_code",
            name="uq_property_type_listing_type",
        ),
    )

    property_type_code = Column(
        String(50),
        ForeignKey("accommodation_property_types.code", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    listing_type_code = Column(
        String(50),
        ForeignKey("accommodation_listing_types.code", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    property_type_config = relationship(
        "AccommodationPropertyTypeConfig",
        back_populates="listing_types",
    )
    listing_type_config = relationship("AccommodationListingTypeConfig")

    def __repr__(self):
        return f"<PropertyTypeListingType {self.property_type_code} / {self.listing_type_code}>"


class AccommodationCancellationPolicyTypeConfig(BaseModel):
    """Advanced cancellation policy types (FLEX, MOD, STRICT, SUPER, NOSHOW).

    Drives the phase-based CancellationPolicy engine. Each type defines
    default phase rules that can be overridden per property.
    """

    __tablename__ = "accommodation_cancellation_policy_types"
    __table_args__ = (
        UniqueConstraint("code", name="uq_accommodation_cancel_policy_type_code"),
    )

    code = Column(String(20), nullable=False, index=True)
    label = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    pre_checkin_days = Column(Integer, default=0, nullable=False)
    pre_checkin_refund_pct = Column(Numeric(5, 2), default=100.00, nullable=False)
    mid_stay_refund_pct = Column(Numeric(5, 2), default=100.00, nullable=False)
    no_show_penalty = Column(Numeric(10, 2), default=0.00, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<AccommodationCancellationPolicyTypeConfig {self.code}>"


class AccommodationCancellationPhaseConfig(BaseModel):
    """Cancellation phases (pre_checkin, mid_stay, no_show)."""

    __tablename__ = "accommodation_cancellation_phases"
    __table_args__ = (
        UniqueConstraint("code", name="uq_accommodation_cancel_phase_code"),
    )

    code = Column(String(30), nullable=False, index=True)
    label = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<AccommodationCancellationPhaseConfig {self.code}>"


class AccommodationNoShowChargeTypeConfig(BaseModel):
    """No-show charge types (none, first_night, full_booking)."""

    __tablename__ = "accommodation_no_show_charge_types"
    __table_args__ = (
        UniqueConstraint("code", name="uq_accommodation_no_show_charge_type_code"),
    )

    code = Column(String(30), nullable=False, index=True)
    label = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<AccommodationNoShowChargeTypeConfig {self.code}>"