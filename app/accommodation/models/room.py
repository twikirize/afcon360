# app/accommodation/models/room.py
"""
Room Management Models - Individual rooms with categories.
"""

from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    Column, BigInteger, String, Boolean, DateTime, Date,
    ForeignKey, Integer, Text, Numeric, JSON,
    Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship, validates
from app.extensions import db
from app.models.base import BaseModel


class RoomCategory(BaseModel):
    """
    Room category/type like VIP Suite, Deluxe King, Standard Twin.
    Groups rooms with same features/pricing.
    """
    __tablename__ = "accommodation_room_categories"
    __table_args__ = (
        Index("idx_room_category_property", "property_id"),
        Index("idx_room_category_active", "is_active"),
        UniqueConstraint("property_id", "name", name="uq_category_per_property"),
        CheckConstraint("base_price_per_night >= 0", name="ck_category_price_positive"),
        CheckConstraint("max_guests >= 1", name="ck_category_guests_min"),
    )

    property_id = Column(BigInteger, ForeignKey("accommodation_properties.id", ondelete="CASCADE"), nullable=False)
    listing = relationship("Property", back_populates="room_categories")

    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    short_code = Column(String(20), nullable=True)

    max_guests = Column(Integer, nullable=False, default=2)
    bedrooms = Column(Integer, default=1)
    beds = Column(Integer, default=1)
    bathrooms = Column(Integer, default=1)

    base_price_per_night = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="USD")
    cleaning_fee = Column(Numeric(10, 2), default=0)

    is_active = Column(Boolean, default=True, nullable=False, index=True)

    rooms = relationship("Room", back_populates="category", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<RoomCategory {self.name} (${self.base_price_per_night})>"

    @property
    def total_rooms(self) -> int:
        return len(self.rooms)

    @property
    def available_rooms(self) -> int:
        return sum(1 for r in self.rooms if r.is_available)

    @property
    def occupancy_rate(self) -> float:
        if self.total_rooms == 0:
            return 0.0
        return ((self.total_rooms - self.available_rooms) / self.total_rooms) * 100


class Room(BaseModel):
    """
    Individual room - e.g., Room 101, Suite A-12.
    Physical room level.
    """
    __tablename__ = "accommodation_rooms"
    __table_args__ = (
        Index("idx_room_property", "property_id"),
        Index("idx_room_category", "category_id"),
        Index("idx_room_status", "status"),
        UniqueConstraint("property_id", "room_number", name="uq_room_number_per_property"),
    )

    property_id = Column(BigInteger, ForeignKey("accommodation_properties.id", ondelete="CASCADE"), nullable=False)
    listing = relationship("Property", back_populates="rooms")

    category_id = Column(BigInteger, ForeignKey("accommodation_room_categories.id", ondelete="RESTRICT"), nullable=False)
    category = relationship("RoomCategory", back_populates="rooms")

    room_number = Column(String(20), nullable=False)
    floor = Column(String(20), nullable=True)
    name = Column(String(100), nullable=True)

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
