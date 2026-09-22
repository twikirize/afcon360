# app/transport/api/routes.py - REFACTORED (registration only)
"""
AFCON360 Transport - API Routes
Central registration of all REST resources for transport.
"""

import logging

logger = logging.getLogger(__name__)


def register_api_resources(api):
    """Register all transport API resources with explicit endpoint names."""

    # Track registered endpoints to avoid duplicates
    registered_endpoints = set()

    def safe_add_resource(resource, path, endpoint):
        """Safely add a resource only if endpoint not already registered"""
        if endpoint in registered_endpoints:
            logger.warning(f"Endpoint {endpoint} already registered, skipping")
            return
        api.add_resource(resource, path, endpoint=endpoint)
        registered_endpoints.add(endpoint)

    # Import all resource classes (lazy import inside function)
    from .driver_routes import (
        DriverListResource,
        DriverDetailResource,
        DriverVerificationResource,
        DriverLocationResource,
        DriverHistoryResource,
        DriverOfferListResource,
        DriverOfferAcceptResource,
        DriverOfferDeclineResource,
        DriverTripResource,
        DriverStatusResource,
        DriverVehicleSwitchResource,
    )
    from .vehicle_routes import (
        VehicleListResource,
        VehicleDetailResource,
        VehicleMaintenanceResource,
        VehicleAssignmentResource,
        VehicleContractRequestResource,
        ContractAcceptanceResource,
        MarketplaceApplicationListResource,
        MarketplaceApplicationApproveResource,
        MarketplaceApplicationRejectResource,
        MarketplaceApplicationWithdrawResource,
    )
    from .organisation_routes import (
        OrganisationListResource,
        OrganisationDetailResource,
        OrganisationDriversResource,
    )
    from .booking_routes import (
        BookingListResource,
        BookingDetailResource,
        BookingStatusResource,
        BookingAssignmentResource,
        BookingPaymentResource,
        BookingRouteResource,
    )
    from .incident_routes import (
        IncidentListResource,
        IncidentDetailResource,
        IncidentAssignmentResource,
        IncidentFollowUpResource,
    )
    from .route_routes import (
        ScheduledRouteListResource,
        ScheduledRouteDetailResource,
        ScheduledRouteAssignmentResource,
    )
    from .analytic_routes import (
        AnalyticsSummaryResource,
        AnalyticsRevenueResource,
        AnalyticsPerformanceResource,
    )
    from .settings_routes import (
        SettingsListResource,
        SettingDetailResource,
        SettingByKeyResource,
    )
    from .dashboard_routes import DashboardOverviewResource
    from .reservation_routes import (
        ReservationListResource,
        ReservationDetailResource,
        ReservationCancelResource,
    )
    from .fare_routes import FareConfigResource, FareEstimateResource
    from .ride_options_routes import RideOptionsResource

    # -------------------------------------------------------------------
    # Resource registration with EXPLICIT endpoint names
    # -------------------------------------------------------------------

    # Drivers
    safe_add_resource(DriverListResource, "/drivers", endpoint="api_driver_list")
    safe_add_resource(DriverDetailResource, "/drivers/<int:driver_id>", endpoint="driver_detail")
    safe_add_resource(DriverVerificationResource, "/drivers/<int:driver_id>/verification",
                     endpoint="driver_verification")
    safe_add_resource(DriverLocationResource, "/drivers/<int:driver_id>/location", endpoint="driver_location")
    safe_add_resource(DriverHistoryResource, "/drivers/<int:driver_id>/history", endpoint="driver_history")

    # TH-3-D2 driver offer surface + trip lifecycle
    safe_add_resource(DriverOfferListResource, "/drivers/me/offers", endpoint="driver_me_offers")
    safe_add_resource(DriverOfferAcceptResource, "/drivers/me/offers/<string:booking_reference>/accept",
                     endpoint="driver_me_offer_accept")
    safe_add_resource(DriverOfferDeclineResource, "/drivers/me/offers/<string:booking_reference>/decline",
                     endpoint="driver_me_offer_decline")
    safe_add_resource(DriverTripResource, "/drivers/me/trips/<int:booking_id>/status",
                     endpoint="driver_me_trip_status")

    # Driver self-service go-live toggle (can_go_live gate)
    safe_add_resource(DriverStatusResource, "/drivers/<int:driver_id>/status",
                     endpoint="driver_go_live_status")

    # Driver self-service vehicle switch (Phase C2 Driver Workspace)
    safe_add_resource(DriverVehicleSwitchResource, "/drivers/<int:driver_id>/vehicles/switch",
                     endpoint="driver_me_vehicle_switch")

    # Vehicles
    safe_add_resource(VehicleListResource, "/vehicles", endpoint="vehicle_list")
    safe_add_resource(VehicleDetailResource, "/vehicles/<int:vehicle_id>", endpoint="vehicle_detail")
    safe_add_resource(VehicleMaintenanceResource, "/vehicles/<int:vehicle_id>/maintenance",
                     endpoint="vehicle_maintenance")
    safe_add_resource(VehicleAssignmentResource, "/vehicles/<int:vehicle_id>/assign", endpoint="vehicle_assignment")
    safe_add_resource(VehicleContractRequestResource, "/vehicles/<int:vehicle_id>/request-contract", endpoint="vehicle_contract_request")
    safe_add_resource(ContractAcceptanceResource, "/contracts/<int:contract_id>/accept", endpoint="contract_acceptance")
    safe_add_resource(MarketplaceApplicationListResource, "/listings/<int:listing_id>/applications", endpoint="marketplace_application_list")
    safe_add_resource(MarketplaceApplicationApproveResource, "/applications/<int:application_id>/approve", endpoint="marketplace_application_approve")
    safe_add_resource(MarketplaceApplicationRejectResource, "/applications/<int:application_id>/reject", endpoint="marketplace_application_reject")
    safe_add_resource(MarketplaceApplicationWithdrawResource, "/applications/<int:application_id>/withdraw", endpoint="marketplace_application_withdraw")

    # Organisations
    safe_add_resource(OrganisationListResource, "/organisations", endpoint="organisation_list")
    safe_add_resource(OrganisationDetailResource, "/organisations/<int:org_id>", endpoint="organisation_detail")
    safe_add_resource(OrganisationDriversResource, "/organisations/<int:org_id>/drivers",
                     endpoint="organisation_drivers")

    # Bookings
    safe_add_resource(BookingListResource, "/bookings", endpoint="booking_list")
    safe_add_resource(BookingDetailResource, "/bookings/<string:booking_reference>", endpoint="booking_detail")
    safe_add_resource(BookingStatusResource, "/bookings/<int:booking_id>/status", endpoint="booking_status")
    safe_add_resource(BookingAssignmentResource, "/bookings/<int:booking_id>/assign", endpoint="booking_assignment")
    safe_add_resource(BookingPaymentResource, "/bookings/<int:booking_id>/payments", endpoint="booking_payments")
    safe_add_resource(BookingRouteResource, "/bookings/<int:booking_id>/route", endpoint="booking_route")

    # Fare estimation (fare node: canonical engine, pre-submit preview)
    safe_add_resource(FareEstimateResource, "/fare/estimate", endpoint="fare_estimate")

    # Ride options (hailing node: per-class availability priced by the
    # canonical engine; anonymous-allowed, booking stays gated)
    safe_add_resource(RideOptionsResource, "/ride-options", endpoint="ride_options")

    # Fare configuration governance (fare node: owner/delegated writes only)
    safe_add_resource(FareConfigResource, "/fare/config", endpoint="fare_config")

    # TH-3-D3 reservations intentionally remain separate from Booking.
    safe_add_resource(ReservationListResource, "/reservations", endpoint="reservation_list")
    safe_add_resource(ReservationDetailResource, "/reservations/<string:reservation_reference>", endpoint="reservation_detail")
    safe_add_resource(ReservationCancelResource, "/reservations/<string:reservation_reference>/cancel", endpoint="reservation_cancel")

    # Incidents
    safe_add_resource(IncidentListResource, "/incidents", endpoint="incident_list")
    safe_add_resource(IncidentDetailResource, "/incidents/<int:incident_id>", endpoint="incident_detail")
    safe_add_resource(IncidentAssignmentResource, "/incidents/<int:incident_id>/assign", endpoint="incident_assignment")
    safe_add_resource(IncidentFollowUpResource, "/incidents/<int:incident_id>/followup", endpoint="incident_followup")

    # Scheduled Routes
    safe_add_resource(ScheduledRouteListResource, "/routes", endpoint="route_list")
    safe_add_resource(ScheduledRouteDetailResource, "/routes/<int:route_id>", endpoint="route_detail")
    safe_add_resource(ScheduledRouteAssignmentResource, "/routes/<int:route_id>/assign", endpoint="route_assignment")

    # Analytics
    safe_add_resource(AnalyticsSummaryResource, "/analytics/summary", endpoint="analytics_summary")
    safe_add_resource(AnalyticsRevenueResource, "/analytics/revenue", endpoint="analytics_revenue")
    safe_add_resource(AnalyticsPerformanceResource, "/analytics/performance", endpoint="analytics_performance")

    # Settings
    safe_add_resource(SettingsListResource, "/settings", endpoint="settings_list")
    safe_add_resource(SettingDetailResource, "/settings/<int:setting_id>", endpoint="setting_detail")
    safe_add_resource(SettingByKeyResource, "/settings/key/<string:key>", endpoint="setting_by_key")

    # Dashboard
    safe_add_resource(DashboardOverviewResource, "/dashboard/overview", endpoint="dashboard_overview")

    logger.info(f"✅ Transport API resources registered ({len(registered_endpoints)} endpoints)")