# app/transport/api/routes.py - REFACTORED (registration only)
"""
AFCON360 Transport — API Routes
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
    )
    from .vehicle_routes import (
        VehicleListResource,
        VehicleDetailResource,
        VehicleMaintenanceResource,
        VehicleAssignmentResource,
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

    # Vehicles
    safe_add_resource(VehicleListResource, "/vehicles", endpoint="vehicle_list")
    safe_add_resource(VehicleDetailResource, "/vehicles/<int:vehicle_id>", endpoint="vehicle_detail")
    safe_add_resource(VehicleMaintenanceResource, "/vehicles/<int:vehicle_id>/maintenance",
                     endpoint="vehicle_maintenance")
    safe_add_resource(VehicleAssignmentResource, "/vehicles/<int:vehicle_id>/assign", endpoint="vehicle_assignment")

    # Organisations
    safe_add_resource(OrganisationListResource, "/organisations", endpoint="organisation_list")
    safe_add_resource(OrganisationDetailResource, "/organisations/<int:org_id>", endpoint="organisation_detail")
    safe_add_resource(OrganisationDriversResource, "/organisations/<int:org_id>/drivers",
                     endpoint="organisation_drivers")

    # Bookings
    safe_add_resource(BookingListResource, "/bookings", endpoint="booking_list")
    safe_add_resource(BookingDetailResource, "/bookings/<int:booking_id>", endpoint="booking_detail")
    safe_add_resource(BookingStatusResource, "/bookings/<int:booking_id>/status", endpoint="booking_status")
    safe_add_resource(BookingAssignmentResource, "/bookings/<int:booking_id>/assign", endpoint="booking_assignment")
    safe_add_resource(BookingPaymentResource, "/bookings/<int:booking_id>/payments", endpoint="booking_payments")
    safe_add_resource(BookingRouteResource, "/bookings/<int:booking_id>/route", endpoint="booking_route")

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
