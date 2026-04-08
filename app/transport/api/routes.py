# app/transport/api/routes.py - REFACTORED (registration only)
"""
AFCON360 Transport — API Routes
Central registration of all REST resources for transport.
"""

import logging

logger = logging.getLogger(__name__)


def register_api_resources(api):
    """Register all transport API resources with explicit endpoint names."""

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
    api.add_resource(DriverListResource, "/drivers", endpoint="driver_list")
    api.add_resource(DriverDetailResource, "/drivers/<int:driver_id>", endpoint="driver_detail")
    api.add_resource(DriverVerificationResource, "/drivers/<int:driver_id>/verification",
                     endpoint="driver_verification")
    api.add_resource(DriverLocationResource, "/drivers/<int:driver_id>/location", endpoint="driver_location")
    api.add_resource(DriverHistoryResource, "/drivers/<int:driver_id>/history", endpoint="driver_history")

    # Vehicles
    api.add_resource(VehicleListResource, "/vehicles", endpoint="vehicle_list")
    api.add_resource(VehicleDetailResource, "/vehicles/<int:vehicle_id>", endpoint="vehicle_detail")
    api.add_resource(VehicleMaintenanceResource, "/vehicles/<int:vehicle_id>/maintenance",
                     endpoint="vehicle_maintenance")
    api.add_resource(VehicleAssignmentResource, "/vehicles/<int:vehicle_id>/assign", endpoint="vehicle_assignment")

    # Organisations
    api.add_resource(OrganisationListResource, "/organisations", endpoint="organisation_list")
    api.add_resource(OrganisationDetailResource, "/organisations/<int:org_id>", endpoint="organisation_detail")
    api.add_resource(OrganisationDriversResource, "/organisations/<int:org_id>/drivers",
                     endpoint="organisation_drivers")

    # Bookings
    api.add_resource(BookingListResource, "/bookings", endpoint="booking_list")
    api.add_resource(BookingDetailResource, "/bookings/<int:booking_id>", endpoint="booking_detail")
    api.add_resource(BookingStatusResource, "/bookings/<int:booking_id>/status", endpoint="booking_status")
    api.add_resource(BookingAssignmentResource, "/bookings/<int:booking_id>/assign", endpoint="booking_assignment")
    api.add_resource(BookingPaymentResource, "/bookings/<int:booking_id>/payments", endpoint="booking_payments")
    api.add_resource(BookingRouteResource, "/bookings/<int:booking_id>/route", endpoint="booking_route")

    # Incidents
    api.add_resource(IncidentListResource, "/incidents", endpoint="incident_list")
    api.add_resource(IncidentDetailResource, "/incidents/<int:incident_id>", endpoint="incident_detail")
    api.add_resource(IncidentAssignmentResource, "/incidents/<int:incident_id>/assign", endpoint="incident_assignment")
    api.add_resource(IncidentFollowUpResource, "/incidents/<int:incident_id>/followup", endpoint="incident_followup")

    # Scheduled Routes
    api.add_resource(ScheduledRouteListResource, "/routes", endpoint="route_list")
    api.add_resource(ScheduledRouteDetailResource, "/routes/<int:route_id>", endpoint="route_detail")
    api.add_resource(ScheduledRouteAssignmentResource, "/routes/<int:route_id>/assign", endpoint="route_assignment")

    # Analytics
    api.add_resource(AnalyticsSummaryResource, "/analytics/summary", endpoint="analytics_summary")
    api.add_resource(AnalyticsRevenueResource, "/analytics/revenue", endpoint="analytics_revenue")
    api.add_resource(AnalyticsPerformanceResource, "/analytics/performance", endpoint="analytics_performance")

    # Settings
    api.add_resource(SettingsListResource, "/settings", endpoint="settings_list")
    api.add_resource(SettingDetailResource, "/settings/<int:setting_id>", endpoint="setting_detail")
    api.add_resource(SettingByKeyResource, "/settings/key/<string:key>", endpoint="setting_by_key")

    # Dashboard
    api.add_resource(DashboardOverviewResource, "/dashboard/overview", endpoint="dashboard_overview")

    logger.info("✅ Transport API resources registered")
