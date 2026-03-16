# app/transport/view_models.py
"""
View models for transport dashboard
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime


@dataclass
class BookingMetric:
    """Booking metrics for dashboard"""
    total: int
    active: int
    today: int
    today_revenue: float
    pending: int
    confirmed: int
    completed: int
    cancelled: int


@dataclass
class ProviderMetric:
    """Provider metrics for dashboard"""
    pending_drivers: int
    active_drivers: int
    pending_vehicles: int
    available_vehicles: int
    total_drivers: int
    total_vehicles: int


@dataclass
class AdminDashboardViewModel:
    """View model specifically shaped for the admin dashboard template"""
    bookings: BookingMetric
    providers: ProviderMetric
    recent_bookings: List[Dict[str, Any]]
    booking_report: Dict[str, Any]
    module_enabled: bool
    last_updated: str

    @classmethod
    def from_services(cls, booking_service, provider_service):
        """Factory method to create view model from services"""
        from app.utils.module_switch import check_module_enabled

        return cls(
            bookings=BookingMetric(
                total=booking_service.count_bookings(),
                active=booking_service.get_active_bookings_count(),
                today=booking_service.get_today_bookings_count(),
                today_revenue=booking_service.get_today_revenue(),
                pending=booking_service.count_bookings_by_status('pending'),
                confirmed=booking_service.count_bookings_by_status('confirmed'),
                completed=booking_service.count_bookings_by_status('completed'),
                cancelled=booking_service.count_bookings_by_status('cancelled')
            ),
            providers=ProviderMetric(
                pending_drivers=provider_service.count_pending_drivers(),
                active_drivers=provider_service.count_active_drivers(),
                pending_vehicles=provider_service.count_pending_vehicles(),
                available_vehicles=provider_service.count_available_vehicles(),
                total_drivers=provider_service.count_total_drivers(),
                total_vehicles=provider_service.count_total_vehicles()
            ),
            recent_bookings=booking_service.get_recent_bookings(10),
            booking_report=booking_service.generate_booking_report(7),
            module_enabled=check_module_enabled("transport"),
            last_updated=datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        )