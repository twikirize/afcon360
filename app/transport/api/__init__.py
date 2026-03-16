# app/transport/api/__init__.py
"""
AFCON360 Transport — REST API
All resources are registered via Flask-RESTful on api_bp.
init_api(app) is called from transport/__init__.py inside init_transport_module().
"""

from flask import Blueprint
from flask_restful import Api

# -------------------------------------------------------------------
# API Blueprint — url prefix: /api/transport/...
# -------------------------------------------------------------------
api_bp = Blueprint("transport_api", __name__, url_prefix="/api/transport")
api = Api(api_bp)


def init_api(app):
    """
    Register all REST API resources and attach api_bp to the app.
    Called from init_transport_module() — at that point all
    dependencies (extensions, services, blueprints) already exist.
    """

    # --- Drivers ---
    from .driver_routes import (
        DriverListResource,
        DriverDetailResource,
        DriverVerificationResource,
        DriverLocationResource,
        DriverHistoryResource,
    )

    # --- Vehicles ---
    from .vehicle_routes import (
        VehicleListResource,
        VehicleDetailResource,
        VehicleMaintenanceResource,
        VehicleAssignmentResource,
    )

    # --- Organisations ---
    from .organisation_routes import (
        OrganisationListResource,
        OrganisationDetailResource,
        OrganisationDriversResource,
    )

    # --- Bookings ---
    from .booking_routes import (
        BookingListResource,
        BookingDetailResource,
        BookingStatusResource,
        BookingAssignmentResource,
        BookingPaymentResource,
        BookingRouteResource,
    )

    # --- Incidents ---
    from .incident_routes import (
        IncidentListResource,
        IncidentDetailResource,
        IncidentAssignmentResource,
        IncidentFollowUpResource,
    )

    # --- Scheduled Routes ---
    from .route_routes import (
        ScheduledRouteListResource,
        ScheduledRouteDetailResource,
        ScheduledRouteAssignmentResource,
    )

    # --- Analytics ---
    # FIX: file is analytic_routes.py (not analytics_routes.py)
    from .analytic_routes import (
        AnalyticsSummaryResource,
        AnalyticsRevenueResource,
        AnalyticsPerformanceResource,
    )

    # --- Settings ---
    from .settings_routes import (
        SettingsListResource,
        SettingDetailResource,
        SettingByKeyResource,
    )

    # --- Dashboard ---
    from .dashboard_routes import DashboardOverviewResource

    # ---------------------------------------------------------------
    # Resource registration
    # ---------------------------------------------------------------

    # Drivers
    api.add_resource(DriverListResource, "/drivers")
    api.add_resource(DriverDetailResource, "/drivers/<int:driver_id>")
    api.add_resource(DriverVerificationResource, "/drivers/<int:driver_id>/verification")
    api.add_resource(DriverLocationResource, "/drivers/<int:driver_id>/location")
    api.add_resource(DriverHistoryResource, "/drivers/<int:driver_id>/history")

    # Vehicles
    api.add_resource(VehicleListResource, "/vehicles")
    api.add_resource(VehicleDetailResource, "/vehicles/<int:vehicle_id>")
    api.add_resource(VehicleMaintenanceResource, "/vehicles/<int:vehicle_id>/maintenance")
    api.add_resource(VehicleAssignmentResource, "/vehicles/<int:vehicle_id>/assign")

    # Organisations
    api.add_resource(OrganisationListResource, "/organisations")
    api.add_resource(OrganisationDetailResource, "/organisations/<int:org_id>")
    api.add_resource(OrganisationDriversResource, "/organisations/<int:org_id>/drivers")

    # Bookings
    api.add_resource(BookingListResource, "/bookings")
    api.add_resource(BookingDetailResource, "/bookings/<int:booking_id>")
    api.add_resource(BookingStatusResource, "/bookings/<int:booking_id>/status")
    api.add_resource(BookingAssignmentResource, "/bookings/<int:booking_id>/assign")
    api.add_resource(BookingPaymentResource, "/bookings/<int:booking_id>/payments")
    api.add_resource(BookingRouteResource, "/bookings/<int:booking_id>/route")

    # Incidents
    api.add_resource(IncidentListResource, "/incidents")
    api.add_resource(IncidentDetailResource, "/incidents/<int:incident_id>")
    api.add_resource(IncidentAssignmentResource, "/incidents/<int:incident_id>/assign")
    api.add_resource(IncidentFollowUpResource, "/incidents/<int:incident_id>/followup")

    # Scheduled Routes
    api.add_resource(ScheduledRouteListResource, "/routes")
    api.add_resource(ScheduledRouteDetailResource, "/routes/<int:route_id>")
    api.add_resource(ScheduledRouteAssignmentResource, "/routes/<int:route_id>/assign")

    # Analytics
    api.add_resource(AnalyticsSummaryResource, "/analytics/summary")
    api.add_resource(AnalyticsRevenueResource, "/analytics/revenue")
    api.add_resource(AnalyticsPerformanceResource, "/analytics/performance")

    # Settings
    api.add_resource(SettingsListResource, "/settings")
    api.add_resource(SettingDetailResource, "/settings/<int:setting_id>")
    api.add_resource(SettingByKeyResource, "/settings/key/<string:key>")

    # Dashboard
    api.add_resource(DashboardOverviewResource, "/dashboard/overview")

    # ---------------------------------------------------------------
    # Register api_bp on the Flask app
    # This is the step that was missing — without it Flask never
    # knows the /api/transport/* routes exist.
    # ---------------------------------------------------------------
    app.register_blueprint(api_bp)

    app.logger.info("✅ Transport API initialized — /api/transport/* routes live")