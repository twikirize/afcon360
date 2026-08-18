# app/accommodation/models/room.py
"""
Room Management Models - Individual rooms with room types.
"""

from datetime import datetime, timezone, date
from decimal import Decimal
import enum
from sqlalchemy import (
    Column, BigInteger, String, Boolean, DateTime, Date, Float,
    ForeignKey, Integer, Text, Numeric, JSON,
    Index, UniqueConstraint, CheckConstraint, func
)
from sqlalchemy.orm import relationship, validates
from app.extensions import db
from app.models.base import BaseModel


# ==========================================
# RoomType Model (for multi-unit properties)
# ==========================================

class RoomType(BaseModel):
    """Room type - the actual sellable SKU for hotels with multiple room types"""
    __tablename__ = "accommodation_room_types"
    __table_args__ = (
        Index("idx_roomtype_property", "property_id"),
        Index("idx_roomtype_active", "is_active"),
    )

    property_id = Column(BigInteger, ForeignKey("accommodation_properties.id", ondelete="CASCADE"), nullable=False)
    listing = relationship("Property", back_populates="room_types")

    # Room type identity
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    # Capacity
    max_guests = Column(Integer, nullable=False, default=2)
    bedrooms = Column(Integer, default=1)
    beds = Column(Integer, default=1)
    bathrooms = Column(Float, default=1.0)

    # Short code for room type identification
    short_code = Column(String(10), nullable=True)

    # Pricing
    base_price_per_night = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="USD")
    cleaning_fee = Column(Numeric(10, 2), default=0)
    service_fee_pct = Column(Numeric(5, 2), default=10.0)

    # Inventory - total units of this room type
    total_units = Column(Integer, nullable=False, default=1)

    # Status
    is_active = Column(Boolean, default=True, nullable=False, )

    rooms = relationship("Room", back_populates="room_type", cascade="all, delete-orphan")
    inventory_blocks = relationship("InventoryBlock", back_populates="room_type", cascade="all, delete-orphan")

    @property
    def booked_units(self) -> int:
        """Get number of booked/in-checked-in units for this room type (current date)."""
        from app.accommodation.models.booking import AccommodationBooking, AccommodationBookingStatus

        today = date.today()

        booked_sum = int(
            db.session.query(
                func.coalesce(func.sum(func.coalesce(AccommodationBooking.rooms_requested, 1)), 0)
            ).filter(
                AccommodationBooking.room_type_id == self.id,
                AccommodationBooking.status.in_([
                    AccommodationBookingStatus.CONFIRMED.value,
                    AccommodationBookingStatus.CHECKED_IN.value,
                ]),
                AccommodationBooking.check_in <= today,
                AccommodationBooking.check_out > today,
            ).scalar()
            or 0
        )

        blocks = InventoryBlock.query.filter(
            InventoryBlock.room_type_id == self.id,
            InventoryBlock.date_range_start <= today,
            InventoryBlock.date_range_end > today,
            InventoryBlock.reason != 'booked',
        ).all()
        blocked = sum(b.units_blocked for b in blocks)

        return booked_sum + blocked

    @property
    def available_units(self) -> int:
        """Get number of available units for this room type (current date)."""
        return max(0, self.total_units - self.booked_units)

    def __repr__(self):
        return f"<RoomType {self.property_id}: {self.name} ({self.total_units} units)>"


# ==========================================
# InventoryBlockReason enum
# ==========================================

class InventoryBlockReason(enum.Enum):
    """Reason for blocking inventory"""
    MAINTENANCE = "MAINTENANCE"
    RENOVATION = "RENOVATION"
    SEASONAL_CLOSE = "SEASONAL_CLOSE"
    OWNER_BLOCK = "OWNER_BLOCK"
    TEMPORARY_HOLD = "temporary_hold"


# ==========================================
# InventoryBlock Model (sparse availability)
# ==========================================

class InventoryBlock(BaseModel):
    """Sparse table for inventory blocks - only rows for dates that are NOT default-available"""
    __tablename__ = "accommodation_inventory_blocks"
    __table_args__ = (
        Index("idx_inv_block_range", "room_type_id", "date_range_start", "date_range_end"),
        Index("idx_inv_block_booking", "booking_id"),
        CheckConstraint(
            "reason IN ('MAINTENANCE', 'RENOVATION', 'SEASONAL_CLOSE', 'OWNER_BLOCK', 'temporary_hold', 'booked', 'owner_blocked', 'maintenance')",
            name="ck_inventory_block_reason_valid"
        ),
    )

    room_type_id = Column(BigInteger, ForeignKey("accommodation_room_types.id", ondelete="CASCADE"), nullable=False)
    room_type = relationship("RoomType", back_populates="inventory_blocks")

    booking_id = Column(BigInteger, ForeignKey("accommodation_bookings.id", ondelete="SET NULL"), nullable=True)
    booking = relationship("AccommodationBooking")

    date_range_start = Column(Date, nullable=False)
    date_range_end = Column(Date, nullable=False)
    units_blocked = Column(Integer, nullable=False, default=0)
    reason = Column(String(50), nullable=False, default="MAINTENANCE")
    created_by = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    creator = relationship("User", foreign_keys=[created_by])

    @validates("reason")
    def _validate_reason(self, key, value):
        """Allow setting reason by enum or by its string value (e.g., 'MAINTENANCE')."""
        if isinstance(value, enum.Enum):
            return value.value
        if isinstance(value, str):
            try:
                return InventoryBlockReason[value].value if value in InventoryBlockReason.__members__ else InventoryBlockReason(value).value
            except Exception:
                if value == "temporary_hold":
                    return value
                raise ValueError(f"Invalid InventoryBlock.reason: {value}")
        return value

    def __repr__(self):
        return f"<InventoryBlock {self.room_type_id}: {self.date_range_start} to {self.date_range_end} ({self.units_blocked} units)>"


# ==========================================
# Room Model
# ==========================================

class Room(BaseModel):
    """
    Individual room - e.g., Room 101, Suite A-12.
    Physical room level.
    """
    __tablename__ = "accommodation_rooms"
    __table_args__ = (
        Index("idx_room_property", "property_id"),
        Index("idx_room_room_type", "room_type_id"),
        Index("idx_room_status", "status"),
        UniqueConstraint("property_id", "room_number", name="uq_room_number_per_property"),
    )

    property_id = Column(BigInteger, ForeignKey("accommodation_properties.id", ondelete="CASCADE"), nullable=False)
    listing = relationship("Property", back_populates="rooms")

    room_type_id = Column(BigInteger, ForeignKey("accommodation_room_types.id", ondelete="RESTRICT"), nullable=False)
    room_type = relationship("RoomType", back_populates="rooms")

    room_number = Column(String(20), nullable=False)
    floor = Column(String(20), nullable=True)
    name = Column(String(100), nullable=True)

    # Whether this physical room is currently rentable at all (distinct from
    # `status`, which tracks its current occupancy/maintenance state).
    is_active = Column(Boolean, default=True, nullable=False, index=True, server_default='true')

    status = Column(String(50), nullable=False, default="available")
    is_maintenance = Column(Boolean, default=False, nullable=False)
    maintenance_reason = Column(Text, nullable=True)
    maintenance_start = Column(DateTime(timezone=True), nullable=True)
    maintenance_end = Column(DateTime(timezone=True), nullable=True)

    features_override = Column(JSON, default=dict)
    notes = Column(Text, nullable=True)

    bookings = relationship("RoomBooking", back_populates="room", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Room {self.room_number} ({self.status})>"

    @property
    def is_available(self) -> bool:
        return self.status == "available" and not self.is_maintenance

    @property
    def display_name(self) -> str:
        if self.name:
            return f"{self.room_number} - {self.name}"
        return self.room_number

    def set_maintenance(self, reason: str, end_date: datetime = None):
        self.status = "maintenance"
        self.is_maintenance = True
        self.maintenance_reason = reason
        self.maintenance_start = datetime.now(timezone.utc)
        if end_date:
            self.maintenance_end = end_date

    def release_from_maintenance(self):
        self.status = "available"
        self.is_maintenance = False
        self.maintenance_end = datetime.now(timezone.utc)

    def assign_booking(self, booking_id: int):
        self.status = "booked"

    def release(self):
        self.status = "available"


# ==========================================
# RoomBooking Model
# ==========================================

class RoomBooking(BaseModel):
    """
    Tracks which room is assigned to which booking.
    Links bookings to specific rooms.
    """
    __tablename__ = "accommodation_room_bookings"
    __table_args__ = (
        Index("idx_room_booking_booking", "booking_id"),
        Index("idx_room_booking_room", "room_id"),
        UniqueConstraint("booking_id", "room_id", name="uq_room_booking_unique"),
    )

    booking_id = Column(BigInteger, ForeignKey("accommodation_bookings.id", ondelete="CASCADE"), nullable=False)
    booking = relationship("AccommodationBooking", back_populates="room_assignments")

    room_id = Column(BigInteger, ForeignKey("accommodation_rooms.id", ondelete="RESTRICT"), nullable=False)
    room = relationship("Room", back_populates="bookings")

    assigned_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc), nullable=False)
    assigned_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    assigned_by_user = relationship("User", foreign_keys=[assigned_by])

    check_in = Column(Date, nullable=False)
    check_out = Column(Date, nullable=False)

    status = Column(String(50), nullable=False, default="active")

    notes = Column(Text, nullable=True)

    def __repr__(self):
        return f"<RoomBooking room={self.room_id} booking={self.booking_id}>"

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    def check_in(self, user_id: int):
        self.status = "checked_in"
        self.assigned_by = user_id

    def check_out(self):
        self.status = "checked_out"
        if self.room:
            self.room.release()


# -------------------------------
# Relationship wiring (lazy imports to avoid circular dependencies)
# -------------------------------

# Note: Property.room_types, Property.rooms, and RoomType.inventory_blocks
# are now defined directly in their respective models to avoid circular imports.