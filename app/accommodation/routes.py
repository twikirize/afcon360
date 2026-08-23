# app/accommodation/routes.py
"""
Consolidated accommodation routes - all routes in one file for optimization
"""

import calendar
import logging
import uuid
import json
import hashlib
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import login_required, current_user
from app.auth.decorators import require_role
from sqlalchemy import or_, and_
from sqlalchemy.exc import OperationalError

from app import db
from app.extensions import limiter
import time
from app.accommodation import accommodation_bp
from app.accommodation.forms import PropertyForm
from app.accommodation.models.property import (
    AccommodationCancellationPolicy,
    AccommodationPropertyStatus,
    AccommodationPropertyType,
    Property,
)
from app.accommodation.models.booking import AccommodationBooking, AccommodationBookingStatus, AccommodationPaymentStatus
from app.accommodation.models.room import Room, RoomBooking, RoomType
from app.accommodation.models.review import Review, AccommodationReviewStatus
from app.identity.models.user import User
from app.events.models import EventAssignment, Event, EventHostRegistration
from app.accommodation.services import search_service
from app.accommodation.services.availability_service import AvailabilityService
from app.accommodation.services.booking_service import BookingService
from app.accommodation.services.host_service import HostService
from app.accommodation.utils import enum_value
from app.accommodation.services.identity_service import AccommodationIdentityService
from app.accommodation.services.pricing_service import PricingService
from app.accommodation.services.urgency_service import urgency_service
from app.accommodation.services.payment_policy_service import PaymentPolicyService
from app.accommodation.services.marketplace_service import MarketplaceService
from app.accommodation.models.booking_policy import PropertyBookingPolicy
from app.accommodation.models.property_payment_method import PropertyPaymentMethod
from app.accommodation.services.payment_processors import PaymentProcessor
from app.accommodation.services.payment_processors.wallet_processor import WalletProcessor
from app.accommodation.services.payment_processors.mobile_money_processor import MobileMoneyProcessor
from app.accommodation.services.payment_processors.card_processor import CardProcessor
from app.accommodation.services.payment_processors.invoice_processor import InvoiceProcessor
from app.accommodation.services.payment_processors.mock_gateway_processor import MockGatewayProcessor
from app.accommodation.services.moderation_service import ModerationService
from app.accommodation.models.moderation import PropertyModerationHistory
from app.accommodation.models.guest_registration import GuestRegistration
from app.accommodation.services.special_request_service import SpecialRequestService
from app.accommodation.services.booking_registration_link_service import BookingRegistrationLinkService
from app.accommodation.services.registration_permission_service import RegistrationPermissionService
from app.accommodation.services.registration_service import RegistrationService
from app.accommodation.services.bulk_registration_service import BulkRegistrationService


@accommodation_bp.route('/api/checkout/payment-options', methods=['GET'])
@login_required
@limiter.limit("30 per minute")
def checkout_payment_options():
    """Return enabled payment methods and their property-specific capabilities."""
    property_id = request.args.get('property_id', type=int)
    if not property_id:
        return jsonify({'success': False, 'error': 'property_id is required'}), 400
    try:
        amount = Decimal(request.args.get('amount', '0'))
    except (ArithmeticError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid amount'}), 400
    try:
        options = PaymentPolicyService.get_allowed_options(property_id, amount)
        return jsonify({'success': True, **options})
    except Exception as exc:
        current_app.logger.exception("Payment option lookup failed for property %s", property_id)
        return jsonify({'success': False, 'error': 'Payment options unavailable'}), 500

def _increment_view_count(property_id, max_retries=3):
    for attempt in range(max_retries):
        try:
            property_obj = db.session.get(Property, property_id)
            if property_obj:
                property_obj.views_last_24h = (property_obj.views_last_24h or 0) + 1
                db.session.add(property_obj)
                db.session.commit()
                return True
        except OperationalError as e:
            db.session.rollback()
            if 'could not serialize access' in str(e) and attempt < max_retries - 1:
                time.sleep(0.1 * (attempt + 1))
                continue
            current_app.logger.warning(f"View count update failed after {attempt+1} attempts: {e}")
            return False
        except Exception as e:
            db.session.rollback()
            current_app.logger.warning(f"View count update error: {e}")
            return False
    return False


@accommodation_bp.route('/admin/pending-properties')
@login_required
@require_role('admin', 'moderator', 'owner')
def pending_properties():
    return redirect(url_for('accommodation.admin_properties', workflow_stage='under_review'))

@accommodation_bp.route('/moderate/property/<int:property_id>/approve', methods=['POST'])
@login_required
@require_role('admin', 'moderator', 'owner')
def moderate_property_approve(property_id):
    notes = request.form.get('notes')
    success, error = ModerationService.approve_property(property_id, current_user.id, notes)
    if success:
        from app.accommodation.models.property import Property as _Prop
        _prop = db.session.get(_Prop, property_id)
        if _prop:
            try:
                from app.notifications.services import NotificationService
                NotificationService.notify_property_approved(_prop)
            except Exception as _ne:
                current_app.logger.warning(f"Property approve notification failed: {_ne}")
        flash("Property approved successfully.", "success")
    else:
        flash(f"Error: {error}", "danger")
    return redirect(url_for('accommodation.admin_properties'))

@accommodation_bp.route('/moderate/property/<int:property_id>/publish', methods=['POST'])
@login_required
@require_role('admin', 'moderator', 'owner')
def moderate_property_publish(property_id):
    notes = request.form.get('notes')
    success, error = ModerationService.publish_property(property_id, current_user.id, notes)
    if success:
        flash("Property published successfully and is now publicly visible.", "success")
    else:
        flash(f"Error: {error}", "danger")
    return redirect(url_for('accommodation.admin_properties'))

@accommodation_bp.route('/host/property/<int:property_id>/publish', methods=['POST'], endpoint="host_publish_property")
@login_required
def host_publish_property(property_id):
    """Host publishes their own approved property."""
    host_info = _ensure_host_identity()
    if not host_info:
        return redirect(url_for('index'))
    
    prop = Property.query.get_or_404(property_id)
    if not AccommodationIdentityService.can_manage_property(
        current_user,
        property_owner_user_id=prop.owner_user_id,
        property_owner_org_id=prop.owner_org_id,
    ):
        abort(403)
    
    # Check if property is approved
    if prop.status != 'approved':
        flash('Property must be approved before publishing.', 'warning')
        return redirect(url_for('accommodation.host_dashboard'))
    
    # Check readiness
    from app.accommodation.services.readiness_service import AccommodationReadinessService
    can_book, failures = AccommodationReadinessService.check_readiness(prop)
    if not can_book:
        flash(f'Cannot publish: {", ".join(failures)}', 'danger')
        return redirect(url_for('accommodation.host_edit_listing', property_id=property_id))
    
    # Publish the property
    success, error = ModerationService.publish_property(property_id, current_user.id, 'Host published')
    if success:
        flash('🎉 Your property is now live and publicly visible!', 'success')
    else:
        flash(f'Error: {error}', 'danger')
    
    return redirect(url_for('accommodation.host_dashboard'))

@accommodation_bp.route('/moderate/property/<int:property_id>/reject', methods=['POST'])
@login_required
@require_role('admin', 'moderator', 'owner')
def moderate_property_reject(property_id):
    reason = request.form.get('reason')
    notes = request.form.get('notes')
    success, error = ModerationService.reject_property(property_id, current_user.id, reason, notes)
    if success:
        from app.accommodation.models.property import Property as _Prop
        _prop = db.session.get(_Prop, property_id)
        if _prop:
            try:
                from app.notifications.services import NotificationService
                NotificationService.notify_property_rejected(_prop, reason=reason)
            except Exception as _ne:
                current_app.logger.warning(f"Property reject notification failed: {_ne}")
        flash("Property rejected.", "success")
    else:
        flash(f"Error: {error}", "danger")
    return redirect(url_for('accommodation.admin_properties'))

@accommodation_bp.route('/moderate/property/<int:property_id>/request-changes', methods=['POST'])
@login_required
@require_role('admin', 'moderator', 'owner')
def moderate_property_request_changes(property_id):
    changes = request.form.get('changes')
    notes = request.form.get('notes')
    success, error = ModerationService.request_changes(property_id, current_user.id, changes, notes)
    if success:
        flash("Changes requested.", "success")
    else:
        flash(f"Error: {error}", "danger")
    return redirect(url_for('accommodation.admin_properties'))

@accommodation_bp.route('/moderate/property/<int:property_id>/suspend', methods=['POST'])
@login_required
@require_role('admin', 'moderator', 'owner')
def moderate_property_suspend(property_id):
    reason = request.form.get('reason')
    notes = request.form.get('notes')
    success, error = ModerationService.suspend_property(property_id, current_user.id, reason, notes)
    if success:
        from app.accommodation.models.property import Property as _Prop
        _prop = db.session.get(_Prop, property_id)
        if _prop:
            try:
                from app.notifications.services import NotificationService
                NotificationService.notify_property_suspended(_prop, reason=reason)
            except Exception as _ne:
                current_app.logger.warning(f"Property suspend notification failed: {_ne}")
        flash("Property suspended.", "success")
    else:
        flash(f"Error: {error}", "danger")
    return redirect(url_for('accommodation.admin_properties'))

@accommodation_bp.route('/moderate/property/<int:property_id>/reinstate', methods=['POST'])
@login_required
@require_role('admin', 'moderator', 'owner')
def moderate_property_reinstate(property_id):
    notes = request.form.get('notes')
    success, error = ModerationService.reinstate_property(property_id, current_user.id, notes)
    if success:
        flash("Property reinstated to pending review.", "success")
    else:
        flash(f"Error: {error}", "danger")
    return redirect(url_for('accommodation.admin_properties'))


@accommodation_bp.route('/moderate/property/<int:property_id>/archive', methods=['POST'])
@login_required
@require_role('admin', 'moderator', 'owner')
def moderate_property_archive(property_id):
    # Ensure property exists (admin-only route; internal id is intentional)
    Property.query.get_or_404(property_id)
    reason = request.form.get('reason') or 'Archived by moderator'
    notes = request.form.get('notes')
    success, error = ModerationService.archive_property(property_id, current_user.id, reason, notes)
    if success:
        flash("Property archived (soft-deleted). It can be restored from the moderation page.", "success")
    else:
        flash(f"Error: {error}", "danger")
    return redirect(url_for('accommodation.admin_properties'))


@accommodation_bp.route('/moderate/property/<int:property_id>/restore', methods=['POST'])
@login_required
@require_role('admin', 'moderator', 'owner')
def moderate_property_restore(property_id):
    """Restore an archived property back to draft (undo soft-delete)."""
    Property.query.get_or_404(property_id)
    notes = request.form.get('notes')
    success, error = ModerationService.restore_archived_property(
        property_id, current_user.id, notes
    )
    if success:
        flash("Property restored to draft. Host can edit and resubmit.", "success")
    else:
        flash(f"Error: {error}", "danger")
    return redirect(url_for('accommodation.admin_properties'))


@accommodation_bp.route("/admin/property/<int:property_id>/edit", methods=["GET", "POST"], endpoint="admin_edit_property")
@login_required
@require_role('admin', 'owner', 'accommodation_admin')
def admin_edit_property(property_id):
    """Admin can edit ANY property directly."""
    prop = Property.query.get_or_404(property_id)
    
    # Allow admins to edit ANY property - bypass ownership check
    form = PropertyForm()
    _populate_form_choices(form)
    
    if request.method == "GET":
        form.process(
            formdata=None,
            data={
                "title": prop.title,
                "summary": prop.summary,
                "description": prop.description,
                "property_type": enum_value(prop.property_type) if prop.property_type else None,
                "address_line1": prop.address_line1,
                "address_line2": prop.address_line2,
                "city": prop.city,
                "state": prop.state,
                "country": prop.country,
                "postal_code": prop.postal_code,
                "base_price_per_night": prop.base_price_per_night,
                "currency": prop.currency,
                "cleaning_fee": prop.cleaning_fee,
                "service_fee_pct": prop.service_fee_pct,
                "max_guests": prop.max_guests,
                "bedrooms": prop.bedrooms,
                "beds": prop.beds,
                "bathrooms": prop.bathrooms,
                "min_stay_nights": prop.min_stay_nights,
                "max_stay_nights": prop.max_stay_nights,
                "cancellation_policy": prop.cancellation_policy if prop.cancellation_policy else None,
                "check_in_time": prop.check_in_time,
                "check_out_time": prop.check_out_time,
                "instant_book": prop.instant_book,
                "allow_pets": prop.allow_pets,
                "allow_smoking": prop.allow_smoking,
                "allow_events": prop.allow_events,
                "house_rules": prop.house_rules,
                "main_image": prop.main_image,
                "gallery_urls": "\n".join(prop.gallery or []),
                "meta_title": prop.meta_title,
                "meta_description": prop.meta_description,
            },
        )
    
    if form.validate_on_submit():
        try:
            # Update all fields
            prop.title = form.title.data
            prop.summary = form.summary.data
            prop.description = form.description.data
            prop.property_type = form.property_type.data
            prop.address_line1 = form.address_line1.data
            prop.address_line2 = form.address_line2.data
            prop.city = form.city.data
            prop.state = form.state.data
            prop.country = form.country.data
            prop.postal_code = form.postal_code.data
            prop.base_price_per_night = form.base_price_per_night.data
            prop.currency = form.currency.data
            prop.cleaning_fee = form.cleaning_fee.data
            prop.service_fee_pct = form.service_fee_pct.data
            prop.max_guests = form.max_guests.data
            prop.bedrooms = form.bedrooms.data
            prop.beds = form.beds.data
            prop.bathrooms = form.bathrooms.data
            prop.min_stay_nights = form.min_stay_nights.data
            prop.max_stay_nights = form.max_stay_nights.data
            prop.cancellation_policy = form.cancellation_policy.data
            prop.check_in_time = form.check_in_time.data
            prop.check_out_time = form.check_out_time.data
            prop.instant_book = form.instant_book.data
            prop.allow_pets = form.allow_pets.data
            prop.allow_smoking = form.allow_smoking.data
            prop.allow_events = form.allow_events.data
            prop.house_rules = form.house_rules.data
            prop.main_image = form.main_image.data
            prop.gallery = [url.strip() for url in form.gallery_urls.data.split('\n') if url.strip()]
            prop.meta_title = form.meta_title.data
            prop.meta_description = form.meta_description.data
            prop.updated_at = datetime.now(timezone.utc)
            
            db.session.commit()
            flash(f"✅ Property '{prop.title}' updated successfully.", "success")
            return redirect(url_for('accommodation.admin_properties'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating property: {str(e)}", "danger")
    
    return render_template(
        "accommodation/host/edit_listing.html",
        form=form,
        property=prop,
        host_info={'display_name': 'Admin', 'type': 'individual'}
    )


def _moderate_property_template_context(property_obj):
    """Shared template context for property moderation detail pages."""
    history = PropertyModerationHistory.query.filter_by(
        property_id=property_obj.id
    ).order_by(PropertyModerationHistory.created_at.desc()).all()
    return {
        'property': property_obj,
        'history': history,
        'ModerationService': ModerationService,
        'available_actions': ModerationService.get_available_actions(property_obj),
        'status_display': ModerationService.get_property_status_display(property_obj),
        'status_color': ModerationService.get_property_status_color(property_obj),
    }


@accommodation_bp.route('/moderate/property/<int:property_id>', endpoint="moderate_property")
@login_required
@require_role('admin', 'moderator', 'owner')
def moderate_property(property_id):
    """Show property review page with moderation actions."""
    property_obj = Property.query.get_or_404(property_id)
    return render_template(
        'accommodation/moderate_property.html',
        **_moderate_property_template_context(property_obj)
    )


from app.auth.decorators import (
    require_moderator,
    require_profile_completion,
    require_role,
)
from app.auth.policy import can
from app.audit.forensic_audit import ForensicAuditService
from app.utils.id_guard import IDGuard

logger = logging.getLogger(__name__)


# ============================================================================
# MAIN ACCOMMODATION ROUTES
# ============================================================================

from app.utils.module_guard import require_module_enabled

@accommodation_bp.route("/", endpoint="home")
@require_module_enabled("accommodation")
def home():
    """Accommodation home page - Public access, no login required"""
    # Fetch featured properties - include both 'active' and 'published'
    featured_properties = Property.query.filter(
        Property.status.in_(['active', 'published']),  # ✅ Include published
        Property.is_verified == True,
        Property.is_active == True,
        Property.is_publicly_visible == True,
        Property.is_deleted == False
    ).order_by(Property.views_last_24h.desc()).limit(8).all()

    # Fetch popular destinations
    from sqlalchemy import func
    popular_destinations = db.session.query(
        Property.city,
        Property.country,
        func.count(Property.id).label('property_count')
    ).filter(
        Property.status.in_(['active', 'published']),
        Property.is_verified == True,
        Property.is_active == True,
        Property.is_publicly_visible == True,
        Property.is_deleted == False
    ).group_by(Property.city, Property.country) \
        .order_by(func.count(Property.id).desc()) \
        .limit(6).all()

    if request.args.get('_pane') == '1':
        # Loaded inside the unified user dashboard pane — render fragment only
        return render_template(
            "accommodation/home_pane.html",
            featured_properties=featured_properties,
            popular_destinations=popular_destinations
        )

    return render_template("accommodation/home.html",
                           featured_properties=featured_properties,
                           popular_destinations=popular_destinations)


@accommodation_bp.route("/detail/<string:public_id>", endpoint="detail")
def detail(public_id):
    """Property detail page with lightweight analytics"""
    IDGuard.check_public_id(public_id, "accommodation detail route")

    property_obj = Property.query.filter_by(public_id=public_id, is_deleted=False).first_or_404()

    # LIGHTWEIGHT analytics - NOT audit logging
    # Simple counter, no personal data, no compliance requirements
    property_obj.views_last_24h = (property_obj.views_last_24h or 0) + 1
    property_obj.total_views = (property_obj.total_views or 0) + 1
    db.session.commit()

    return render_template('accommodation/detail.html',
                           property=property_obj,
                           public_id=public_id)


@accommodation_bp.route("/host/register", methods=["GET", "POST"], endpoint="host_register")
@login_required
@require_profile_completion
def host_register():
    """Host registration — GET shows form, POST creates host profile."""
    from app.accommodation.services.identity_service import AccommodationIdentityService

    if request.method == "POST":
        display_name = request.form.get("display_name", "").strip()
        tax_id = request.form.get("tax_id", "").strip()
        payout_method = request.form.get("payout_method", "wallet")
        org_id = request.form.get("org_id", "").strip()
        org_id = int(org_id) if org_id.isdigit() else None

        success, error, host_identity = AccommodationIdentityService.register_host(
            user_id=current_user.id,
            org_id=org_id,
        )

        if success:
            profile = host_identity.get("profile")
            if profile:
                profile.tax_id = tax_id
                profile.default_payout_method = payout_method
                if display_name and host_identity["type"] == "individual":
                    current_user.display_name = display_name
                db.session.commit()

            flash("Host registration successful! You can now create listings.", "success")
            return redirect(url_for("accommodation.host_dashboard"))
        else:
            flash(f"Host registration failed: {error}", "danger")

    # GET — show form
    user_orgs = AccommodationIdentityService.get_user_organisations(current_user)
    return render_template(
        "accommodation/host/register.html",
        user_orgs=user_orgs,
    )


@accommodation_bp.route("/admin/dashboard", endpoint="admin_dashboard")
@login_required
@require_role('admin', 'owner', 'accommodation_admin')
def admin_dashboard():
    """Accommodation admin dashboard"""
    stats = HostService.get_admin_dashboard_stats()
    return render_template("admin/accommodation_admin_dashboard.html", **stats)


# ── Admin: Analytics ────────────────────────────────────────────────────────
@accommodation_bp.route("/admin/analytics", endpoint="admin_analytics")
@login_required
@require_role('admin', 'owner', 'accommodation_admin')
def admin_analytics():
    """Platform-wide accommodation analytics dashboard."""
    from sqlalchemy import func

    # Revenue by month (last 12 months)
    today = date.today()
    monthly_revenue = []
    for i in range(11, -1, -1):
        month_start = (today.replace(day=1) - timedelta(days=30 * i)).replace(day=1)
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1, day=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1, day=1)

        rev = db.session.query(
            func.coalesce(func.sum(AccommodationBooking.total_amount), 0)
        ).filter(
            AccommodationBooking.created_at >= month_start,
            AccommodationBooking.created_at < month_end,
            AccommodationBooking.status.in_([
                'confirmed', 'checked_in', 'checked_out'
            ])
        ).scalar() or 0
        monthly_revenue.append({
            "month": month_start.strftime("%b %Y"),
            "amount": float(rev)
        })

    # Booking status breakdown
    status_counts = db.session.query(
        AccommodationBooking.status,
        func.count(AccommodationBooking.id).label('count')
    ).group_by(AccommodationBooking.status).all()
    booking_status_breakdown = [
        {"status": s.replace('_', ' ').title(), "count": c}
        for s, c in status_counts
    ]

    # Booking type breakdown
    type_counts = db.session.query(
        AccommodationBooking.booking_type,
        func.count(AccommodationBooking.id).label('count')
    ).group_by(AccommodationBooking.booking_type).all()
    booking_type_breakdown = [
        {"type": t.replace('_', ' ').title(), "count": c}
        for t, c in type_counts
    ]

    # Property type breakdown
    type_counts = db.session.query(
        Property.property_type,
        func.count(Property.id).label('count')
    ).filter(
        Property.is_deleted.is_(False)
    ).group_by(Property.property_type).all()
    property_type_breakdown = [
        {"type": (t.value if hasattr(t, 'value') else str(t)).replace('_', ' ').title(), "count": c}
        for t, c in type_counts
    ]

    # Top cities by listing count
    top_cities = db.session.query(
        Property.city,
        func.count(Property.id).label('count')
    ).filter(
        Property.is_deleted.is_(False),
        Property.is_active.is_(True)
    ).group_by(Property.city).order_by(func.count(Property.id).desc()).limit(8).all()
    top_cities_data = [{"city": city or "Unknown", "count": c} for city, c in top_cities]

    # Summary totals
    total_revenue = db.session.query(
        func.coalesce(func.sum(AccommodationBooking.total_amount), 0)
    ).filter(
        AccommodationBooking.status.in_(['confirmed', 'checked_in', 'checked_out'])
    ).scalar() or 0

    total_bookings = AccommodationBooking.query.count()
    total_properties = Property.query.filter(Property.is_deleted.is_(False)).count()
    total_reviews = Review.query.filter(Review.is_published.is_(True)).count()

    avg_rating_row = db.session.query(
        func.avg(Review.overall_rating)
    ).filter(Review.is_published.is_(True)).scalar()
    avg_rating = round(float(avg_rating_row or 0), 2)

    return render_template(
        "accommodation/admin/analytics.html",
        monthly_revenue=monthly_revenue,
        booking_status_breakdown=booking_status_breakdown,
        booking_type_breakdown=booking_type_breakdown,
        property_type_breakdown=property_type_breakdown,
        top_cities=top_cities_data,
        total_revenue=float(total_revenue),
        total_bookings=total_bookings,
        total_properties=total_properties,
        total_reviews=total_reviews,
        avg_rating=avg_rating,
    )


# ── Admin: Verification queue ────────────────────────────────────────────────
@accommodation_bp.route("/admin/verification", endpoint="admin_verification")
@login_required
@require_role('admin', 'owner', 'accommodation_admin', 'moderator')
def admin_verification():
    """Property verification queue — review and approve/reject pending listings."""
    from app.accommodation.models.property import AccommodationVerificationStatus

    page = request.args.get('page', 1, type=int)
    filter_status = request.args.get('status', 'pending_review')

    q = Property.query.filter(Property.is_deleted.is_(False))
    if filter_status == 'pending_review':
        q = q.filter(Property.status == "pending_review")
    elif filter_status == 'verified':
        q = q.filter(Property.is_verified.is_(True))
    elif filter_status == 'rejected':
        q = q.filter(
            Property.verification_status == "rejected"
        )

    pending_page = q.order_by(Property.created_at.asc()).paginate(
        page=page, per_page=20, error_out=False
    )

    counts = {
        "pending_review": Property.query.filter(
            Property.is_deleted.is_(False),
            Property.status == "pending_review"
        ).count(),
        "verified": Property.query.filter(
            Property.is_deleted.is_(False),
            Property.is_verified.is_(True)
        ).count(),
        "rejected": Property.query.filter(
            Property.is_deleted.is_(False),
            Property.verification_status == "rejected"
        ).count(),
    }

    response = make_response(render_template(
        "accommodation/admin/verification.html",
        properties=pending_page,
        counts=counts,
        filter_status=filter_status,
    ))
    response.headers['Cache-Control'] = 'private, max-age=300'
    return response


@accommodation_bp.route("/admin/verification/<int:property_id>/approve", methods=['POST'],
                        endpoint="admin_verify_approve")
@login_required
@require_role('admin', 'owner', 'accommodation_admin', 'moderator')
def admin_verify_approve(property_id):
    """Approve a property listing."""
    from app.accommodation.models.property import AccommodationVerificationStatus
    prop = Property.query.get_or_404(property_id)
    prop.status = "active"
    prop.is_verified = True
    prop.is_active = True
    prop.verification_status = "verified"
    prop.verified_at = datetime.now(timezone.utc)
    prop.verified_by = current_user.id
    try:
        db.session.commit()
        flash(f"'{prop.title}' approved and is now live.", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error approving property %s", property_id)
        flash("Could not approve property. Please try again.", "danger")
    return redirect(url_for("accommodation.admin_verification"))


@accommodation_bp.route("/admin/verification/<int:property_id>/reject", methods=['POST'],
                        endpoint="admin_verify_reject")
@login_required
@require_role('admin', 'owner', 'accommodation_admin', 'moderator')
def admin_verify_reject(property_id):
    """Reject a property listing with a reason."""
    from app.accommodation.models.property import AccommodationVerificationStatus
    prop = Property.query.get_or_404(property_id)
    reason = request.form.get('reason', '').strip() or 'No reason provided.'
    prop.status = "suspended"
    prop.is_active = False
    prop.verification_status = "rejected"
    prop.verification_notes = reason
    try:
        db.session.commit()
        flash(f"'{prop.title}' rejected.", "warning")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error rejecting property %s", property_id)
        flash("Could not reject property. Please try again.", "danger")
    return redirect(url_for("accommodation.admin_verification"))


# ── Admin: Properties ────────────────────────────────────────────────────────
@accommodation_bp.route("/admin/properties", endpoint="admin_properties")
@login_required
@require_role('admin', 'owner', 'accommodation_admin', 'moderator')
def admin_properties():
    """Browse and manage all property listings with workflow-aware filters."""
    page = request.args.get('page', 1, type=int)
    workflow_stage = request.args.get('workflow_stage', 'all')
    verification_status = request.args.get('verification_status', 'all')
    visibility_filter = request.args.get('visibility', 'all')
    property_type = request.args.get('property_type', 'all')
    missing_info = request.args.get('missing_info', 'all')
    search_q = request.args.get('q', '').strip()

    q = Property.query.filter(Property.is_deleted.is_(False))

    if workflow_stage != 'all':
        q = q.filter(Property.status == workflow_stage)

    if verification_status != 'all':
        q = q.filter(Property.verification_status == verification_status)

    if visibility_filter != 'all':
        q = q.filter(Property.visibility == visibility_filter)

    if property_type != 'all':
        q = q.filter(Property.property_type == property_type)

    if missing_info == 'no_photos':
        q = q.filter(or_(Property.main_image.is_(None), Property.main_image == ''))
    elif missing_info == 'no_pricing':
        q = q.filter(or_(Property.base_price_per_night.is_(None), Property.base_price_per_night <= 0))
    elif missing_info == 'no_rooms':
        q = q.filter(or_(Property.max_guests.is_(None), Property.max_guests < 1))
    elif missing_info == 'no_kyc':
        from app.identity.models.user import User
        q = q.join(User, Property.owner_user_id == User.id).filter(
            or_(User.kyc_level == 0, User.kyc_level.is_(None))
        )

    if search_q:
        q = q.filter(
            or_(
                Property.title.ilike(f'%{search_q}%'),
                Property.city.ilike(f'%{search_q}%'),
                Property.country.ilike(f'%{search_q}%'),
            )
        )

    properties = q.order_by(Property.created_at.desc()).paginate(
        page=page, per_page=25, error_out=False
    )

    workflow_stages = ['draft', 'submitted', 'under_review', 'approved', 'needs_information', 'active', 'suspended', 'archived']
    verification_options = ['unverified', 'pending', 'verified', 'rejected']
    visibility_options = ['public', 'event_only', 'hidden', 'private_invite']
    property_types = ['entire_place', 'private_room', 'shared_room', 'hotel_room', 'lodge', 'hostel']

    return render_template(
        "accommodation/admin/properties.html",
        properties=properties,
        workflow_stage=workflow_stage,
        verification_status=verification_status,
        visibility_filter=visibility_filter,
        property_type=property_type,
        missing_info=missing_info,
        search_q=search_q,
        workflow_stages=workflow_stages,
        verification_options=verification_options,
        visibility_options=visibility_options,
        property_types=property_types,
    )


@accommodation_bp.route("/admin/properties/<int:property_id>/toggle-active", methods=['POST'],
                        endpoint="admin_property_toggle")
@login_required
@require_role('admin', 'owner', 'accommodation_admin')
def admin_property_toggle(property_id):
    """Activate or suspend a property."""
    prop = Property.query.get_or_404(property_id)
    if prop.status == "suspended":
        prop.status = "active"
        prop.is_active = True
        msg = f"'{prop.title}' reactivated."
    else:
        prop.status = "suspended"
        prop.is_active = False
        msg = f"'{prop.title}' suspended."
    try:
        db.session.commit()
        flash(msg, "success")
    except Exception:
        db.session.rollback()
        flash("Could not update property status.", "danger")
    return redirect(url_for("accommodation.admin_properties"))


# ── Admin: Bookings ──────────────────────────────────────────────────────────
@accommodation_bp.route("/admin/bookings", endpoint="admin_bookings")
@login_required
@require_role('admin', 'owner', 'accommodation_admin')
def admin_bookings():
    """Browse and manage all accommodation bookings."""
    from sqlalchemy import func

    page = request.args.get('page', 1, type=int)
    status_filters = request.args.getlist('status')
    if 'all' in status_filters:
        status_filters = []
    search_q = request.args.get('q', '').strip()

    q = AccommodationBooking.query

    if status_filters:
        q = q.filter(AccommodationBooking.status.in_(status_filters))

    if search_q:
        q = q.filter(
            or_(
                AccommodationBooking.booking_reference.ilike(f'%{search_q}%'),
                AccommodationBooking.guest_name.ilike(f'%{search_q}%'),
                AccommodationBooking.guest_email.ilike(f'%{search_q}%'),
            )
        )

    bookings = q.order_by(AccommodationBooking.created_at.desc()).paginate(
        page=page, per_page=25, error_out=False
    )

    # Summary counts for the filter bar
    from app.accommodation.models.booking import AccommodationBookingStatus
    status_counts = {
        s.value: AccommodationBooking.query.filter(
            AccommodationBooking.status == s.value
        ).count()
        for s in AccommodationBookingStatus
    }
    status_counts['all'] = AccommodationBooking.query.count()

    return render_template(
        "accommodation/admin/bookings.html",
        bookings=bookings,
        status_filters=status_filters,
        search_q=search_q,
        status_counts=status_counts,
    )


@accommodation_bp.route("/admin/booking/<int:booking_id>", endpoint="admin_booking_detail")
@login_required
@require_role('admin', 'owner', 'accommodation_admin', 'super_admin')
def admin_booking_detail(booking_id):
    """Admin view of a single booking with full details and audit log."""
    from app.accommodation.models.commission import BookingCommission
    from app.accommodation.services.identity_service import AccommodationIdentityService

    booking = AccommodationBooking.query.get_or_404(booking_id)
    prop = Property.query.get_or_404(booking.property_id)

    # Authorization: admin, owner, accommodation_admin, or super_admin
    if not AccommodationIdentityService.can_manage_property(
        current_user, prop.owner_user_id, prop.owner_org_id
    ) and not current_user.is_super_admin:
        abort(403)

    commission = BookingCommission.query.filter_by(booking_id=booking_id).first()
    property_data = search_service.get_property_by_identifier(str(booking.property_id))
    return render_template(
        "accommodation/admin/booking_detail.html",
        booking=booking,
        property=property_data,
        commission=commission,
    )


# ── Admin: Settings ──────────────────────────────────────────────────────────
@accommodation_bp.route("/admin/settings", endpoint="admin_settings")
@login_required
@require_role('admin', 'owner', 'accommodation_admin')
def admin_settings():
    """Platform-level accommodation settings."""
    from app.models.system_config import SystemConfig
    configs = SystemConfig.query.filter(
        SystemConfig.key.like('accommodation_%')
    ).order_by(SystemConfig.key).all()
    return render_template(
        "accommodation/admin/settings.html",
        configs=configs,
    )


@accommodation_bp.route("/admin/settings/update", methods=['POST'],
                        endpoint="admin_settings_update")
@login_required
@require_role('admin', 'owner', 'accommodation_admin')
def admin_settings_update():
    """Persist an accommodation setting key/value/description."""
    from app.models.system_config import SystemConfig
    key = request.form.get('key', '').strip()
    value = request.form.get('value', '').strip()
    description = request.form.get('description', '').strip() or None
    if not key:
        flash("Setting key is required.", "warning")
        return redirect(url_for("accommodation.admin_settings"))
    cfg = SystemConfig.query.filter_by(key=key).first()
    if cfg:
        cfg.value = value
        if description is not None:
            cfg.description = description
    else:
        cfg = SystemConfig(key=key, value=value, description=description,
                           created_by=current_user.id)
        db.session.add(cfg)
    try:
        db.session.commit()
        flash(f"Setting '{key}' saved.", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error saving setting %s", key)
        flash("Could not save setting.", "danger")
    return redirect(url_for("accommodation.admin_settings"))


@accommodation_bp.route("/moderate", endpoint="moderate")
@login_required
@require_moderator
def moderate():
    """Show all accommodation items for moderators"""
    all_properties = Property.query.filter_by(is_deleted=False).order_by(Property.created_at.desc()).all()
    all_bookings = AccommodationBooking.query.order_by(AccommodationBooking.created_at.desc()).all()
    all_reviews = Review.query.order_by(Review.created_at.desc()).all()

    from app.audit.comprehensive_audit import AuditService
    AuditService.security(
        event_type="moderator_view_accommodation",
        severity="info",
        description=f"Moderator {current_user.id} viewed all accommodation items",
        user_id=current_user.id,
        ip_address=request.remote_addr,
    )

    return render_template('accommodation/moderate.html',
                          properties=all_properties,
                          bookings=all_bookings,
                          reviews=all_reviews,
                          is_moderator=True)


# ============================================================================
# GUEST ROUTES (URL prefix: /guest)
# ============================================================================

@accommodation_bp.route("/guest/", endpoint="guest_search")
def guest_search():
    """Accommodation search page"""
    city = request.args.get('city')
    check_in = request.args.get('check_in')
    check_out = request.args.get('check_out')
    guests = request.args.get('guests', 2, type=int)

    properties = search_service.search_properties({
        'city': city,
        'check_in': check_in,
        'check_out': check_out,
        'guests': guests
    })
    properties = properties.get('properties', []) if isinstance(properties, dict) else (properties or [])

    return render_template(
        "accommodation/guest/search.html",
        properties=properties,
        city=city,
        check_in=check_in,
        check_out=check_out,
        guests=guests
    )


@accommodation_bp.route("/guest/api/search", endpoint="guest_api_search")
@limiter.limit("30 per minute")
def guest_api_search():
    """JSON API for accommodation search"""
    city = request.args.get('city')
    check_in = request.args.get('check_in')
    check_out = request.args.get('check_out')
    guests = request.args.get('guests', 2, type=int)

    properties = search_service.search_properties({
        'city': city,
        'check_in': check_in,
        'check_out': check_out,
        'guests': guests
    })

    return jsonify({
        "success": True,
        "properties": properties,
        "count": len(properties)
    })


@accommodation_bp.route("/guest/api/autocomplete", endpoint="guest_autocomplete")
def guest_autocomplete():
    """Booking.com-style destination autocomplete"""
    from sqlalchemy import func

    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify({'suggestions': []})

    cities = db.session.query(
        Property.city,
        Property.country,
        func.count(Property.id).label('cnt')
    ).filter(
        Property.status.in_(['active', 'published']),
        Property.is_verified == True,
        Property.is_active == True,
        Property.is_deleted == False,
        func.lower(Property.city).like(f'{q.lower()}%')
    ).group_by(Property.city, Property.country)\
     .order_by(func.count(Property.id).desc())\
     .limit(5).all()

    props = Property.query.filter(
        Property.status.in_(['active', 'published']),
        Property.is_verified == True,
        Property.is_active == True,
        Property.is_deleted == False,
        func.lower(Property.title).like(f'%{q.lower()}%')
    ).limit(3).all()

    suggestions = []
    for city, country, cnt in cities:
        suggestions.append({
            'type': 'city', 'label': f'{city}, {country}',
            'city': city, 'country': country, 'count': cnt, 'icon': '📍'
        })
    for p in props:
        suggestions.append({
            'type': 'property', 'label': p.title,
            'id': p.id, 'city': getattr(p, 'city', ''), 'icon': '🏨'
        })

    return jsonify({'suggestions': suggestions[:8]})


@accommodation_bp.route("/guest/api/analytics/event", methods=['POST'], endpoint="guest_analytics_event")
def guest_track_event():
    """Fire-and-forget analytics ingest"""
    try:
        data = request.get_json(silent=True) or {}
        from app.utils.monitoring import track_booking_funnel_event
        track_booking_funnel_event(
            data.get('event', 'unknown'),
            {k: v for k, v in data.get('properties', {}).items()
             if k in ['propertyId', 'session_id', 'page', 'price', 'city']}
        )
        return jsonify({'ok': True}), 200
    except Exception:
        return jsonify({'ok': False}), 200


@accommodation_bp.route("/guest/<identifier>", endpoint="guest_detail")
def guest_detail(identifier):
    """Property detail page"""
    db.session.rollback()
    try:
        property_data = search_service.get_property_by_identifier(identifier)
    except Exception:
        logger.exception("Property serialization failed for identifier %s", identifier)
        db.session.rollback()
        property_data = None

    if property_data is None:
        abort(404)

    if identifier.isdigit():
        property_model = db.session.get(Property, int(identifier))
    else:
        property_model = Property.query.filter_by(public_id=identifier).first()
        if not property_model:
            property_model = Property.query.filter_by(slug=identifier).first()

    if property_model:
        _increment_view_count(property_model.id)
        from app.accommodation.services.media_service import AccommodationMediaService
        from app.media.service import MediaService
        gallery_media = []
        try:
            gallery_media = [
                {
                    'url': MediaService.get_original_url(media),
                    'category': (media.processing_metadata or {}).get('photo_category', 'other'),
                }
                for media in property_model.media_photos(media_type='photo')
                if MediaService.get_original_url(media)
            ]
            existing_urls = {item['url'] for item in gallery_media}
            property_data['gallery_media'] = gallery_media + [
                {'url': url, 'category': 'other'}
                for url in property_model.legacy_photo_urls()
                if url not in existing_urls
            ]
        except Exception:
            logger.exception("Property media serialization failed for property %s", property_model.id)
            db.session.rollback()
            fallback_images = property_data.get('images', []) if isinstance(property_data, dict) else []
            property_data['gallery_media'] = [
                {'url': url, 'category': 'other'}
                for url in fallback_images
                if isinstance(url, str) and url
            ]
    else:
        property_data['gallery_media'] = []

    urgency = urgency_service.get_signals(property_model.id) if property_model else {}

    check_in = request.args.get('check_in')
    check_out = request.args.get('check_out')
    guests = request.args.get('guests', 2, type=int)
    selected_room_type_id = request.args.get('room_type_id', type=int)

    # Resolve the default room type. Retry once after rollback because this
    # relationship is lazy-loaded and can otherwise mask an earlier failure.
    if property_model and not selected_room_type_id:
        try:
            room_types = property_model.room_types
        except Exception as exc:
            db.session.rollback()
            logger.exception("Room-type lookup failed for property %s; retrying", property_model.id)
            try:
                room_types = property_model.room_types
            except Exception as retry_exc:
                db.session.rollback()
                logger.error("Room-type lookup failed after recovery for property %s: %s", property_model.id, retry_exc)
                room_types = []
        active_rts = [rt for rt in room_types if rt.is_active]
        if active_rts:
            selected_room_type_id = active_rts[0].id

    availability_status = None
    price_breakdown = None

    if check_in and check_out and property_model:
        try:
            check_in_date = datetime.strptime(check_in, '%Y-%m-%d').date()
            check_out_date = datetime.strptime(check_out, '%Y-%m-%d').date()

            # ============================================================
            # VALIDATION: Past date check for display
            # ============================================================
            today = date.today()
            if check_in_date < today:
                availability_status = "past_date"
                flash('Please select a future date for your stay.', 'warning')
            elif check_out_date <= check_in_date:
                availability_status = "invalid_range"
                flash('Check-out must be after check-in.', 'warning')
            else:
                # Check room type counter availability first if selected_room_type_id is set
                if selected_room_type_id:
                    availability = AvailabilityService.get_room_type_availability(
                        property_model.id,
                        check_in_date,
                        check_out_date,
                        num_guests=guests,
                        num_rooms=1,
                    )
                    selected_availability = next(
                        (
                            room_type
                            for room_type in availability['room_types']
                            if room_type['id'] == selected_room_type_id
                        ),
                        None,
                    )
                    is_available = bool(
                        selected_availability
                        and selected_availability['is_available']
                        and selected_availability['can_accommodate_guests']
                    )
                    error = (
                        None
                        if is_available
                        else "Selected room type cannot accommodate the guests for these dates"
                    )
                else:
                    is_available, blocked_dates, error = AvailabilityService.is_range_available(
                        property_model.id, check_in_date, check_out_date
                    )

                if is_available:
                    price_breakdown = PricingService.calculate_total(
                        property_model, check_in_date, check_out_date, guests, room_type_id=selected_room_type_id
                    )
                    availability_status = "available"
                else:
                    availability_status = "unavailable"
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error checking availability: {e}")

    return render_template(
        "accommodation/guest/detail.html",
        property=property_data,
        property_model=property_model,
        availability_status=availability_status,
        price_breakdown=price_breakdown,
        selected_check_in=check_in,
        selected_check_out=check_out,
        selected_guests=guests,
        selected_room_type_id=selected_room_type_id,
        urgency=urgency,
        now=datetime.now(timezone.utc)
    )
# app/accommodation/routes.py - Add after host routes

@accommodation_bp.route("/host/property/<int:property_id>/booking-policy", methods=['GET', 'POST'], endpoint="host_booking_policy")
@login_required
def host_booking_policy(property_id):
    """Host manages booking policy for a property."""
    host_info = _ensure_host_identity()
    if not host_info:
        return redirect(url_for('index'))

    prop = Property.query.get_or_404(property_id)
    if not AccommodationIdentityService.can_manage_property(
        current_user,
        property_owner_user_id=prop.owner_user_id,
        property_owner_org_id=prop.owner_org_id,
    ):
        abort(403)

    policy = PropertyBookingPolicy.query.filter_by(property_id=property_id).first()
    if not policy:
        policy = PropertyBookingPolicy(property_id=property_id)
        db.session.add(policy)
        db.session.commit()

    # Get available payment methods (all globally enabled methods, not just property-specific)
    from app.wallet.models.payment_method import PaymentMethodConfig
    all_payment_methods = PaymentMethodConfig.query.filter(
        PaymentMethodConfig.is_enabled == True,
        PaymentMethodConfig.is_active == True,
    ).all()

    payment_options = {
        'payment_methods': [
            {
                'id': m.id,
                'method_id': m.method_id,
                'display_name': m.display_name,
                'method_type': m.method_type,
                'icon': m.method_type,
            }
            for m in all_payment_methods
        ],
        'allowed_methods': [m.method_id for m in all_payment_methods],
    }

    if request.method == 'POST':
        try:
            # Update policy fields
            policy.allow_pay_now = request.form.get('allow_pay_now') == 'on'
            policy.allow_pay_on_arrival = request.form.get('allow_pay_on_arrival') == 'on'
            policy.allow_deposit_payment = request.form.get('allow_deposit_payment') == 'on'
            deposit_pct = request.form.get('deposit_percentage', '0')
            policy.deposit_percentage = Decimal(deposit_pct) if deposit_pct else Decimal('0')
            balance_due = request.form.get('balance_due_days_before_checkin', '0')
            policy.balance_due_days_before_checkin = int(balance_due) if balance_due else 0

            policy.require_payment_guarantee = request.form.get('require_payment_guarantee') == 'on'
            hold_minutes = request.form.get('reservation_hold_minutes', '30')
            policy.reservation_hold_minutes = int(hold_minutes) if hold_minutes else 30

            policy.cancellation_policy = request.form.get('cancellation_policy', 'flexible')
            free_cancel = request.form.get('free_cancel_hours', '24')
            policy.free_cancel_hours = int(free_cancel) if free_cancel else 24

            policy.no_show_charge_type = request.form.get('no_show_charge_type', 'none')
            no_show_amount = request.form.get('no_show_charge_amount', '0')
            policy.no_show_charge_amount = Decimal(no_show_amount) if no_show_amount else Decimal('0')

            policy.is_active = request.form.get('is_active') == 'on'

            # Verification level (D-006)
            verification_level = request.form.get('verification_level', 'none')
            if verification_level not in ('none', 'basic_identity', 'document_upload', 'biometric_liveness', 'third_party_attestation'):
                verification_level = 'none'
            policy.verification_level = verification_level

            # Host-configurable registration fields (D-024)
            reg_fields = request.form.getlist('required_registration_fields')
            valid_fields = {'full_name', 'phone', 'email', 'id_document_type', 'id_document_number', 'date_of_birth', 'nationality'}
            policy.required_registration_fields = [f for f in reg_fields if f in valid_fields]

            request_types = request.form.getlist('available_request_options')
            request_labels = {
                'late_checkout': 'Late checkout',
                'extra_bedding': 'Extra bedding',
                'early_checkin': 'Early check-in',
            }
            policy.available_request_options = [
                {'type': value, 'label': request_labels[value]}
                for value in request_types
                if value in request_labels
            ]

            # Update payment methods safely (avoid stale identity-map issues)
            selected_methods = set(request.form.getlist('payment_methods'))
            existing_methods = PropertyPaymentMethod.query.filter_by(
                property_id=property_id
            ).all()
            selected_method_ids = set()

            for pm in existing_methods:
                config = PaymentMethodConfig.query.get(pm.wallet_method_id)
                if config and config.method_id in selected_methods:
                    pm.enabled = True
                    selected_method_ids.add(config.method_id)
                else:
                    pm.enabled = False

            for method_id_str in selected_methods:
                if method_id_str in selected_method_ids:
                    continue
                config = PaymentMethodConfig.query.filter_by(method_id=method_id_str).first()
                if not config:
                    continue
                pm = PropertyPaymentMethod(
                    property_id=property_id,
                    wallet_method_id=config.id,
                    enabled=True
                )
                db.session.add(pm)

            # Save cash payment protection settings (gracefully handle missing columns)
            try:
                policy.allow_cash_payments = request.form.get('allow_cash_payments') == 'on'
                policy.cash_requires_deposit = request.form.get('cash_requires_deposit') == 'on'
                cash_deposit_pct = request.form.get('cash_deposit_percentage', '30')
                policy.cash_deposit_percentage = Decimal(cash_deposit_pct) if cash_deposit_pct else Decimal('30')
                cash_max = request.form.get('cash_max_amount', '500000')
                policy.cash_max_amount = Decimal(cash_max) if cash_max else Decimal('500000')
                cash_kyc = request.form.get('cash_min_kyc_level', '2')
                policy.cash_min_kyc_level = int(cash_kyc) if cash_kyc else 2
                cash_min_bookings = request.form.get('cash_min_previous_bookings', '0')
                policy.cash_min_previous_bookings = int(cash_min_bookings) if cash_min_bookings else 0
                policy.cash_requires_verified_guest = request.form.get('cash_requires_verified_guest') == 'on'
            except Exception:
                pass  # Columns may not exist yet — migration needed

            # Security deposit (D-012)
            policy.require_security_deposit = request.form.get('require_security_deposit') == 'on'
            security_deposit = request.form.get('security_deposit_amount', '0')
            policy.security_deposit_amount = Decimal(security_deposit) if security_deposit else Decimal('0')

            db.session.commit()
            flash('Booking policy updated successfully.', 'success')
            return redirect(url_for('accommodation.host_booking_policy', property_id=property_id))

        except Exception as e:
            db.session.rollback()
            logger.exception("Failed to update booking policy")
            flash(f'Failed to update policy: {str(e)}', 'danger')

    return render_template(
        "accommodation/host/booking_policy.html",
        policy=policy,
        property=prop,
        payment_options=payment_options,
        host_info=host_info
    )


@accommodation_bp.route("/api/availability", methods=['GET'])
@limiter.limit("30 per minute")
def api_availability():
    """
    Live AJAX endpoint for real-time availability checking.
    Returns count-based availability per room type, partial availability info,
    and same-property/nearby alternatives (Tier 0-2 cascade).
    """
    from datetime import datetime

    property_id = request.args.get('property_id', type=int)
    check_in_str = request.args.get('check_in', '')
    check_out_str = request.args.get('check_out', '')
    num_guests = request.args.get('num_guests', 2, type=int)
    num_rooms = request.args.get('num_rooms', 1, type=int)

    if not property_id or not check_in_str or not check_out_str:
        return jsonify({'success': False, 'error': 'Missing required parameters'}), 400

    try:
        check_in = datetime.strptime(check_in_str, '%Y-%m-%d').date()
        check_out = datetime.strptime(check_out_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid date format'}), 400

    if check_out <= check_in:
        return jsonify({'success': False, 'error': 'Check-out date must be after check-in date.'}), 400

    try:
        from app.accommodation.services.availability_service import AvailabilityService
        result = AvailabilityService.get_availability_cascade(
            property_id=property_id,
            check_in=check_in,
            check_out=check_out,
            num_guests=num_guests,
            num_rooms=num_rooms,
        )
        status_code = 200 if 'error' not in result else 404
        return jsonify({'success': 'error' not in result, **result}), status_code
    except Exception as e:
        current_app.logger.error(f"Availability API error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@accommodation_bp.route("/guest/checkout", methods=['GET', 'POST'], endpoint="guest_checkout")
@login_required
@limiter.limit("5 per minute")
def guest_checkout():
    """Enhanced checkout supporting self-booking, book-for-others, and multi-room"""
    from app.accommodation.services.booking_service import BookingService
    from datetime import timedelta

    # ============================================================
    # DEBUG: Log incoming data for troubleshooting
    # ============================================================
    if request.method == 'POST':
        current_app.logger.info("=" * 60)
        current_app.logger.info("CHECKOUT DEBUG - INCOMING POST DATA")
        current_app.logger.info("=" * 60)
        current_app.logger.info(f"FORM DATA: {dict(request.form)}")
        current_app.logger.info(f"SESSION pending_booking: {session.get('pending_booking', 'None')}")
        current_app.logger.info(f"USER ID: {current_user.id}")
        current_app.logger.info("=" * 60)

    if request.method == 'GET':
        # Query params take precedence over stale session data.
        # This prevents a previously-started booking for a different property
        # from leaking into a new checkout flow.
        if 'property_id' in request.args:
            try:
                booking_data = {
                    'property_id': int(request.args.get('property_id')),
                    'room_type_id': int(request.args.get('room_type_id')) if request.args.get('room_type_id') and request.args.get('room_type_id') != 'None' else None,
                    'host_user_id': int(request.args.get('host_user_id', 0)),
                    'check_in': request.args.get('check_in'),
                    'check_out': request.args.get('check_out'),
                    'num_guests': int(request.args.get('num_guests', 1)),
                    'nightly_rate': Decimal(request.args.get('nightly_rate', '0')),
                    'nights': int(request.args.get('nights', 0)),
                    'subtotal': Decimal(request.args.get('subtotal', '0')),
                    'cleaning_fee': Decimal(request.args.get('cleaning_fee', '0')),
                    'service_fee': Decimal(request.args.get('service_fee', '0')),
                    'total': Decimal(request.args.get('total', '0')),
                    'name': request.args.get('name', ''),
                    'city': request.args.get('city', ''),
                    'currency': request.args.get('currency', 'USD'),
                    'context_type': request.args.get('context_type', 'none'),
                    'context_id': request.args.get('context_id', ''),
                    'context_metadata': request.args.get('context_metadata', '{}'),
                }
                session['pending_booking'] = booking_data
            except (ValueError, TypeError) as e:
                current_app.logger.warning(f"Invalid checkout query params: {e}")
                flash('Invalid booking data. Please try again.', 'danger')
                return redirect(url_for('accommodation.guest_search'))
        else:
            booking_data = session.get('pending_booking')
            if not booking_data:
                flash('No booking in progress', 'warning')
                return redirect(url_for('accommodation.guest_search'))

        # Normalize session data types for template rendering
        numeric_fields = ['nightly_rate', 'subtotal', 'cleaning_fee', 'service_fee', 'total']
        for field in numeric_fields:
            if field in booking_data and not isinstance(booking_data[field], Decimal):
                try:
                    booking_data[field] = Decimal(str(booking_data[field]))
                except Exception:
                    booking_data[field] = Decimal('0')

        int_fields = ['num_guests', 'rooms_requested', 'nights', 'property_id', 'room_type_id', 'host_user_id']
        for field in int_fields:
            if field in booking_data and not isinstance(booking_data[field], int):
                try:
                    booking_data[field] = int(booking_data[field])
                except Exception:
                    booking_data[field] = 0

        # Ensure currency is present (fallback to property currency or USD)
        if 'currency' not in booking_data or not booking_data.get('currency'):
            try:
                from app.accommodation.models.property import Property as _Prop
                _prop = db.session.get(_Prop, booking_data.get('property_id', 0))
                booking_data['currency'] = (_prop.currency if _prop else 'USD') or 'USD'
            except Exception:
                booking_data['currency'] = 'USD'

        # Resolve property_id from booking data (single source of truth)
        property_id = booking_data.get('property_id')

        # Guard: property_id must be a valid positive integer for checkout
        # Missing or invalid property_id is a data integrity violation that
        # must never proceed to availability checks or inventory calculations
        if not isinstance(property_id, int) or property_id <= 0:
            current_app.logger.error(
                f"Checkout blocked: invalid property_id={property_id!r} "
                f"(expected positive integer). Booking data: {booking_data.get('check_in')} to "
                f"{booking_data.get('check_out')}, guests={booking_data.get('num_guests')}"
            )
            flash('Booking data is incomplete or corrupted. Please restart your booking.', 'danger')
            session.pop('pending_booking', None)
            return redirect(url_for('accommodation.guest_search'))

        # Check availability before showing checkout
        from app.accommodation.services.availability_service import AvailabilityService
        try:
            check_in = datetime.strptime(booking_data['check_in'], '%Y-%m-%d').date()
            check_out = datetime.strptime(booking_data['check_out'], '%Y-%m-%d').date()
            is_available, blocked_dates, error = AvailabilityService.is_range_available(
                int(property_id), check_in, check_out
            )
            if not is_available:
                flash(f'Selected dates are no longer available: {error or "Please try different dates"}', 'danger')
                session.pop('pending_booking', None)
                return redirect(url_for('accommodation.guest_detail', identifier=property_id))

            requested_guests = int(booking_data.get('num_guests') or 0)
            requested_rooms = int(booking_data.get('rooms_requested') or 1)
            room_type_id = booking_data.get('room_type_id')
            if requested_guests < 1 or requested_rooms < 1:
                raise ValueError('Guest and room counts must be positive')
            room_availability = AvailabilityService.get_room_type_availability(
                int(property_id), check_in, check_out,
                num_guests=requested_guests, num_rooms=requested_rooms,
            )
            selected_room = next(
                (item for item in room_availability['room_types']
                 if room_type_id and item['id'] == int(room_type_id)),
                None,
            )
            if room_type_id and (not selected_room or not selected_room['is_available']):
                message = (
                    f"This room accommodates {selected_room['max_guests'] * requested_rooms} guest(s) "
                    f"across {requested_rooms} room(s). Please reduce the guest count or choose more rooms."
                    if selected_room and requested_guests > selected_room['max_guests'] * requested_rooms
                    else 'The selected room type is no longer available for this party size.'
                )
                flash(message, 'danger')
                session.pop('pending_booking', None)
                return redirect(url_for('accommodation.guest_detail', identifier=property_id))
            if selected_room:
                booking_data['room_max_guests'] = selected_room['max_guests']
        except (ValueError, KeyError) as e:
            current_app.logger.warning(f"Checkout blocked by availability validation: {e}")
            flash('The selected room cannot accommodate this party. Please choose more rooms or fewer guests.', 'danger')
            session.pop('pending_booking', None)
            return redirect(url_for('accommodation.guest_detail', identifier=property_id))

        # Load payment options for the property
        property_id = booking_data.get('property_id')
        payment_options = {}
        if property_id:
            payment_options = PaymentPolicyService.get_allowed_options(
                property_id=int(property_id),
                booking_amount=Decimal(str(booking_data.get('total', 0))),
                guest_type='normal'
            )

        return render_template(
            "accommodation/guest/checkout.html",
            booking=booking_data,
            payment_options=payment_options
        )

    try:
        data = request.form

        # ============================================================
        # Parse booking type
        # ============================================================
        booking_type = data.get('booking_type', 'self')  # self, third_party, group

        # Initialize group-specific variables upfront to avoid NameError
        group_booking_id = None
        room_number = None
        total_rooms = 1

        # ============================================================
        # Determine guest info (who is staying)
        # ============================================================
        if booking_type == 'self':
            # I am staying
            primary_guest_id = current_user.id
            primary_guest_name = current_user.username or data.get('guest_name')
            primary_guest_email = current_user.email
            primary_guest_phone = data.get('guest_phone')
            guest_user_id = current_user.id

        elif booking_type == 'third_party':
            # Booking for someone else
            primary_guest_name = data.get('primary_guest_name')
            primary_guest_email = data.get('primary_guest_email')
            primary_guest_phone = data.get('primary_guest_phone')
            primary_guest_id = None

            # Try to find if guest already has an account
            guest_user = User.query.filter_by(email=primary_guest_email).first() if primary_guest_email else None
            if guest_user:
                primary_guest_id = guest_user.id
                guest_user_id = guest_user.id
            else:
                guest_user_id = None  # Guest not registered

        elif booking_type == 'group':
            # One atomic group booking; room assignment happens after checkout.
            group_booking_id = data.get('group_booking_id') or str(uuid.uuid4())
            try:
                total_rooms = int(data.get('total_rooms', 1))
                group_guest_count = int(data.get('num_guests_group') or data.get('num_guests') or 0)
            except (TypeError, ValueError):
                total_rooms = 0
                group_guest_count = 0
            # Guest info for the booking, not for an individual room.
            primary_guest_name = data.get('guest_name')
            primary_guest_email = data.get('guest_email')
            primary_guest_phone = data.get('guest_phone')
            primary_guest_id = None

            guest_user = User.query.filter_by(email=primary_guest_email).first() if primary_guest_email else None
            if guest_user:
                primary_guest_id = guest_user.id
                guest_user_id = guest_user.id
            else:
                guest_user_id = None

        rooms_requested = total_rooms if booking_type == 'group' else 1
        requested_guests = group_guest_count if booking_type == 'group' else int(data.get('num_guests') or 0)

        # ============================================================
        # ERROR CHECKING BLOCK – Each check tells you exactly what's wrong
        # ============================================================

        # CHECK 1: Required fields
        required_fields = ['property_id', 'check_in', 'check_out']
        for field in required_fields:
            if not data.get(field):
                current_app.logger.error(f"❌ CHECKOUT FAILED: Missing required field '{field}'")
                flash(f'Missing required field: {field}', 'danger')
                return redirect(url_for('accommodation.guest_search'))

        if requested_guests < 1:
            flash('Please enter at least one guest.', 'danger')
            return redirect(url_for('accommodation.guest_detail', identifier=data.get('property_id', '')))
        if rooms_requested < 1:
            flash('Please request at least one room.', 'danger')
            return redirect(url_for('accommodation.guest_detail', identifier=data.get('property_id', '')))

        # CHECK 2: property_id is valid
        property_id_str = data.get('property_id', '').strip()
        if not property_id_str.isdigit():
            current_app.logger.error(f"❌ CHECKOUT FAILED: Invalid property_id '{property_id_str}'")
            flash('Invalid property ID', 'danger')
            return redirect(url_for('accommodation.guest_search'))
        property_id = int(property_id_str)

        # CHECK 3: Property exists in database
        from app.accommodation.models.property import Property
        property_obj = db.session.get(Property, property_id)
        if not property_obj:
            current_app.logger.error(f"❌ CHECKOUT FAILED: Property {property_id} not found in database")
            flash('Property not found', 'danger')
            return redirect(url_for('accommodation.guest_search'))

        # CHECK 4: Property is bookable
        if not property_obj.can_be_booked():
            current_app.logger.error(f"❌ CHECKOUT FAILED: Property {property_id} is NOT bookable. Status: {property_obj.status}, is_active: {property_obj.is_active}, is_verified: {property_obj.is_verified}, is_deleted: {property_obj.is_deleted}")
            flash('This property is not currently available for booking', 'danger')
            return redirect(url_for('accommodation.guest_detail', identifier=property_id))

        # CHECK 5: Date validation
        try:
            check_in = datetime.strptime(data['check_in'], '%Y-%m-%d').date()
            check_out = datetime.strptime(data['check_out'], '%Y-%m-%d').date()
        except ValueError as e:
            current_app.logger.error(f"❌ CHECKOUT FAILED: Invalid date format: {e}")
            flash('Invalid date format', 'danger')
            return redirect(url_for('accommodation.guest_detail', identifier=property_id))

        today = date.today()
        if check_in < today:
            current_app.logger.error(f"❌ CHECKOUT FAILED: Check-in date {check_in} is in the past (today: {today})")
            flash('Check-in date cannot be in the past. Please select a future date.', 'danger')
            return redirect(url_for('accommodation.guest_detail', identifier=property_id))

        if check_out <= check_in:
            current_app.logger.error(f"❌ CHECKOUT FAILED: Check-out {check_out} must be after check-in {check_in}")
            flash('Check-out date must be after check-in date.', 'danger')
            return redirect(url_for('accommodation.guest_detail', identifier=property_id))

        if check_out <= today:
            current_app.logger.error(f"❌ CHECKOUT FAILED: Check-out date {check_out} is in the past")
            flash('Check-out date must be in the future.', 'danger')
            return redirect(url_for('accommodation.guest_detail', identifier=property_id))

        # CHECK 6: Room type validation
        room_type_id_raw = data.get('room_type_id', '').strip()
        from app.accommodation.models.room import RoomType
        active_room_types = RoomType.query.filter_by(property_id=property_obj.id, is_active=True).count()

        if active_room_types > 0:
            if not room_type_id_raw or room_type_id_raw == 'None':
                current_app.logger.error(f"❌ CHECKOUT FAILED: Property {property_id} has {active_room_types} room types but no room_type_id provided")
                flash('Please select a room type before proceeding to checkout.', 'danger')
                return redirect(url_for('accommodation.guest_detail', identifier=property_id))

            try:
                room_type_id = int(room_type_id_raw)
                room_type = RoomType.query.filter_by(id=room_type_id, property_id=property_obj.id, is_active=True).first()
                if not room_type:
                    current_app.logger.error(f"❌ CHECKOUT FAILED: Invalid room_type_id {room_type_id} for property {property_id}")
                    flash('Selected room type is not available.', 'danger')
                    return redirect(url_for('accommodation.guest_detail', identifier=property_id))
            except ValueError:
                current_app.logger.error(f"❌ CHECKOUT FAILED: Invalid room_type_id format '{room_type_id_raw}'")
                flash('Invalid room type selected.', 'danger')
                return redirect(url_for('accommodation.guest_detail', identifier=property_id))
        else:
            room_type_id = None

        # CHECK 7: Host resolution
        if property_obj.owner_user_id:
            host_user_id = property_obj.owner_user_id
        elif property_obj.owner_org_id:
            org_contact_id = getattr(property_obj.owner_org, "primary_contact_user_id", None)
            if not org_contact_id:
                current_app.logger.error(f"❌ CHECKOUT FAILED: Property {property_id} has owner_org_id {property_obj.owner_org_id} but no primary_contact_user_id")
                flash('This property\'s organisation has no primary contact configured for bookings.', 'danger')
                return redirect(url_for('accommodation.guest_detail', identifier=property_id))
            host_user_id = org_contact_id
        else:
            current_app.logger.error(f"❌ CHECKOUT FAILED: Property {property_id} has no owner_user_id or owner_org_id")
            flash('Property has no valid owner configured.', 'danger')
            return redirect(url_for('accommodation.guest_search'))

        # CHECK 8: Availability check
        from app.accommodation.services.availability_service import AvailabilityService
        is_available, blocked_dates, error = AvailabilityService.is_range_available(property_obj.id, check_in, check_out)
        if is_available and room_type_id:
            room_availability = AvailabilityService.get_room_type_availability(
                property_obj.id, check_in, check_out,
                num_guests=requested_guests, num_rooms=rooms_requested,
            )
            selected = next((item for item in room_availability['room_types'] if item['id'] == room_type_id), None)
            if not selected or not selected['is_available']:
                is_available = False
                error = 'The selected room type cannot accommodate this guest and room quantity.'
        if not is_available:
            current_app.logger.error(f"❌ CHECKOUT FAILED: Property {property_id} not available from {check_in} to {check_out}. Error: {error}")
            flash(f'Selected dates are not available: {error or "Please try different dates"}', 'danger')
            return redirect(url_for('accommodation.guest_detail', identifier=property_id))

        # ============================================================
        # ALL CHECKS PASSED – Create hold, process payment, then book
        # ============================================================
        current_app.logger.info(f"✅ ALL CHECKS PASSED for property {property_id} - Proceeding with hold + payment")

        # ============================================================
        # CHECK 9: Payment method and timing are required
        # ============================================================
        payment_method = data.get('payment_method', '').strip()
        payment_timing = data.get('payment_timing', '').strip()

        if not payment_method or not payment_timing:
            session['pending_booking'] = {
                'property_id': property_id,
                'room_type_id': room_type_id,
                'host_user_id': host_user_id,
                'check_in': check_in.isoformat(),
                'check_out': check_out.isoformat(),
                'num_guests': requested_guests,
                'rooms_requested': rooms_requested,
                'nightly_rate': Decimal(data.get('nightly_rate', '0')),
                'nights': int(data.get('nights', 0)),
                'subtotal': Decimal(data.get('subtotal', '0')),
                'cleaning_fee': Decimal(data.get('cleaning_fee', '0')),
                'service_fee': Decimal(data.get('service_fee', '0')),
                'total': Decimal(data.get('total', '0')),
                'name': data.get('name', ''),
                'city': data.get('city', ''),
                'context_type': data.get('context_type', 'none'),
                'context_id': data.get('context_id', ''),
                'context_metadata': data.get('context_metadata', '{}'),
            }
            if not payment_method:
                flash('Please select a payment method.', 'warning')
            else:
                flash('Please select how you want to pay.', 'warning')
            return redirect(url_for('accommodation.guest_checkout'))

        # ============================================================
        # STEP 1: Calculate pricing FIRST (needed for validation)
        # ============================================================
        from app.accommodation.services.pricing_service import PricingService
        pricing = None
        try:
            pricing = PricingService.calculate_total(
                property_obj, check_in, check_out, requested_guests,
                room_type_id=room_type_id, num_rooms=rooms_requested,
            )
        except ValueError as e:
            AvailabilityService.release_hold(property_obj.id, check_in, check_out, current_user.id)
            flash(f'Price calculation failed: {str(e)}', 'danger')
            return redirect(url_for('accommodation.guest_detail', identifier=data['property_id']))

        if not pricing:
            AvailabilityService.release_hold(property_obj.id, check_in, check_out, current_user.id)
            flash('Price calculation failed: invalid pricing result.', 'danger')
            return redirect(url_for('accommodation.guest_detail', identifier=data['property_id']))

        payment_options = PaymentPolicyService.get_allowed_options(
            property_id=property_id,
            booking_amount=pricing['total'],
            guest_type='normal'
        )

        if payment_method not in payment_options.get('allowed_methods', []):
            AvailabilityService.release_hold(property_obj.id, check_in, check_out, current_user.id)
            flash('Invalid payment method selected.', 'danger')
            return redirect(url_for('accommodation.guest_detail', identifier=data['property_id']))

        selected_method = next(
            (method for method in payment_options.get('payment_methods', [])
             if method.get('method_id') == payment_method),
            None,
        )
        if not selected_method or payment_timing not in selected_method.get('allowed_timings', []):
            AvailabilityService.release_hold(property_obj.id, check_in, check_out, current_user.id)
            flash('This payment method does not support the selected payment timing.', 'danger')
            return redirect(url_for('accommodation.guest_detail', identifier=data['property_id']))

        allowed_timings = payment_options.get('allowed_timings', [])
        if allowed_timings and payment_timing not in allowed_timings:
            AvailabilityService.release_hold(property_obj.id, check_in, check_out, current_user.id)
            flash('This payment option is not available for this property.', 'danger')
            return redirect(url_for('accommodation.guest_detail', identifier=data['property_id']))

        # Check wallet requirements if wallet is selected
        if payment_method == 'wallet':
            from app.wallet.models import AccountModel
            account = AccountModel.query.filter_by(user_id=current_user.id).first()
            if not account:
                AvailabilityService.release_hold(property_obj.id, check_in, check_out, current_user.id)
                flash('You don\'t have a wallet account. Please choose another payment method or create a wallet first.', 'warning')
                return redirect(url_for('accommodation.guest_detail', identifier=data['property_id']))

        # Resolve processor
        processor_map = {
            'wallet': WalletProcessor(),
            'mobile_money': MobileMoneyProcessor(),
            'card': CardProcessor(),
            'invoice': InvoiceProcessor(),
            'mock_gateway': MockGatewayProcessor(),
        }
        processor = processor_map.get(payment_method)
        
        # Handle cash payment (no processor needed)
        if payment_method == 'cash':
            charge_amount = Decimal('0')
            payment_timing = 'pay_on_arrival'

            # Check cash eligibility (fraud protection)
            from app.accommodation.services.booking_service import check_cash_eligibility
            total = pricing['total']
            eligibility = check_cash_eligibility(
                guest_user=current_user,
                property_id=property_obj.id,
                booking_amount=total
            )
            if not eligibility['allowed']:
                AvailabilityService.release_hold(property_obj.id, check_in, check_out, current_user.id)
                flash(f'Cash payment not available: {eligibility["reason"]}', 'warning')
                return redirect(url_for('accommodation.guest_detail', identifier=data['property_id']))
        elif not processor:
            AvailabilityService.release_hold(property_obj.id, check_in, check_out, current_user.id)
            flash('Invalid payment method selected.', 'danger')
            return redirect(url_for('accommodation.guest_detail', identifier=data['property_id']))

        # ============================================================
        # STEP 1: Create temporary hold on dates (NOT a booking yet)
        # ============================================================
        from app.accommodation.services.availability_service import AvailabilityService
        hold_success, hold_id = AvailabilityService.create_hold(
            property_id=property_obj.id,
            check_in=check_in,
            check_out=check_out,
            created_by=current_user.id,
            room_type_id=room_type_id,
            units=rooms_requested,
            hold_minutes=15,
            hold_type="payment",
        )

        if not hold_success:
            current_app.logger.error(f"❌ CHECKOUT FAILED: Could not create hold - {hold_id}")
            flash(hold_id or 'Could not hold dates. Please try again.', 'danger')
            return redirect(url_for('accommodation.guest_detail', identifier=data['property_id']))

        current_app.logger.info(f"✅ Temporary hold created for property {property_id} ({check_in} → {check_out}), hold_id={hold_id}")

        # ============================================================
        # Calculate charge amount based on timing
        # ============================================================
        total = pricing['total']
        charge_amount = Decimal('0')
        deposit_amount = Decimal('0')
        amount_due = total
        balance_due_date = None

        if payment_timing == 'deposit':
            deposit_pct = Decimal(str(data.get('deposit_percentage', 0)))
            charge_amount = (total * deposit_pct / Decimal('100')).quantize(Decimal('0.01'))
            deposit_amount = charge_amount
            amount_due = total - charge_amount
            policy = PropertyBookingPolicy.query.filter_by(property_id=property_obj.id).first()
            if policy and policy.balance_due_days_before_checkin:
                balance_due_date = check_in - timedelta(days=policy.balance_due_days_before_checkin)
            else:
                balance_due_date = check_in - timedelta(days=1)
        elif payment_timing == 'pay_now':
            charge_amount = total
        elif payment_timing == 'invoice':
            balance_due_date = datetime.now(timezone.utc).date() + timedelta(days=30)

        # Check wallet balance if needed
        if payment_method == 'wallet' and charge_amount > 0:
            account = AccountModel.query.filter_by(user_id=current_user.id).first()
            if account.balance < charge_amount:
                AvailabilityService.release_hold(property_obj.id, check_in, check_out, current_user.id)
                flash(f'Insufficient wallet balance. Your balance is {account.balance} {property_obj.currency} but the required amount is {charge_amount} {property_obj.currency}.', 'danger')
                return redirect(url_for('accommodation.guest_detail', identifier=data['property_id']))

        # ============================================================
        # STEP 3.5: Compute idempotency_key once, create booking as pending
        # ============================================================
        idempotency_data = {
            'user_id': current_user.id,
            'property_id': int(data['property_id']),
            'check_in': data['check_in'],
            'check_out': data['check_out'],
            'num_guests': requested_guests,
            'booking_type': booking_type,
            'primary_guest_email': primary_guest_email if booking_type == 'third_party' else current_user.email,
        }
        idempotency_key = hashlib.sha256(
            json.dumps(idempotency_data, sort_keys=True).encode()
        ).hexdigest()

        booking, error = BookingService.create_booking(
            property_id=int(data['property_id']),
            guest_user_id=guest_user_id if guest_user_id else current_user.id,
            host_user_id=host_user_id,
            check_in=check_in,
            check_out=check_out,
            num_guests=requested_guests,
            rooms_requested=rooms_requested,
            guest_name=None if booking_type in ('third_party', 'group') and not primary_guest_name else primary_guest_name,
            guest_email=None if booking_type in ('third_party', 'group') and not primary_guest_email else primary_guest_email,
            guest_phone=primary_guest_phone,
            special_requests=data.get('special_requests'),
            idempotency_key=idempotency_key,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            context_type=data.get('context_type'),
            context_id=data.get('context_id'),
            context_metadata=data.get('context_metadata'),
            booked_by_user_id=current_user.id,
            primary_guest_id=primary_guest_id,
            primary_guest_name=primary_guest_name,
            primary_guest_email=primary_guest_email,
            primary_guest_phone=primary_guest_phone,
            booking_type=booking_type,
            group_booking_id=data.get('group_booking_id') if booking_type == 'group' else None,
            room_number=None,
            guest_instructions=data.get('guest_instructions'),
            room_type_id=room_type_id,
            skip_hold_creation=True,
            payment_method=payment_method,
            payment_timing=payment_timing,
            payment_guaranteed=(payment_method in ('wallet', 'card')) and charge_amount > 0,
            guarantee_type='card_authorization' if payment_method == 'card' else ('wallet_balance' if payment_method == 'wallet' else 'none'),
            # Booking Owner (D-003, D-004)
            booking_owner_id=primary_guest_id if booking_type == 'third_party' and primary_guest_id else None,
            owner_email=primary_guest_email if booking_type == 'third_party' else None,
        )

        if error:
            AvailabilityService.release_hold(property_obj.id, check_in, check_out, current_user.id)
            current_app.logger.error(f"❌ CHECKOUT FAILED: Booking creation failed - {error}")
            flash(f'Booking creation failed: {error}', 'danger')
            return redirect(url_for('accommodation.guest_detail', identifier=data['property_id']))

        current_app.logger.info(f"✅ Booking created: {booking.booking_reference}")

        # Link the RoomHold to the booking
        if hold_id:
            from app.accommodation.models.availability import RoomHold
            room_hold = db.session.get(RoomHold, hold_id)
            if room_hold and room_hold.status == "active":
                room_hold.mark_converted(booking.id)
                db.session.add(room_hold)
            db.session.commit()

        # Set phase-specific deadlines based on payment timing
        now = datetime.now(timezone.utc)
        if payment_timing == 'pay_now':
            booking.hold_expires_at = now + timedelta(minutes=15)


        current_app.logger.info(f"✅ Booking created: {booking.booking_reference}")

        # Set phase-specific deadlines based on payment timing
        now = datetime.now(timezone.utc)
        if payment_timing == 'pay_now':
            booking.hold_expires_at = now + timedelta(minutes=15)
            booking.approval_deadline = None
        elif payment_timing == 'deposit':
            booking.hold_expires_at = now + timedelta(minutes=15)
            booking.approval_deadline = None
        elif payment_timing == 'pay_on_arrival':
            booking.hold_expires_at = now + timedelta(minutes=15)
            booking.approval_deadline = now + timedelta(hours=24)
        elif payment_timing == 'invoice':
            booking.hold_expires_at = now + timedelta(minutes=30)
            booking.approval_deadline = now + timedelta(hours=48)

        # Guest registration deadline: 48 hours before check-in
        booking.registration_deadline = booking.check_in - timedelta(hours=48)

        # Generate claim token for third-party bookings where owner has no account
        if booking_type == 'third_party' and not primary_guest_id:
            from app.accommodation.services.booking_service import BookingService
            claim_token = BookingService.generate_claim_token(booking.id)
            booking.claim_token_hash = claim_token
            db.session.commit()
            try:
                from app.notifications.services import NotificationService
                NotificationService.send(
                    user_id=current_user.id,
                    notification_type='owner_claim_invite',
                    title=f'Claim your booking: {booking.booking_reference}',
                    message=f'{primary_guest_name}, you have been booked for {property_obj.title} from {check_in} to {check_out}. Click the link to claim and manage this booking.',
                    channels=['in_app', 'email'],
                    data={
                        'booking_reference': booking.booking_reference,
                        'claim_token': claim_token,
                        'property_title': property_obj.title,
                    },
                )
            except Exception as e:
                current_app.logger.error(f"Failed to send owner claim invite: {e}")

        db.session.commit()

        # ============================================================
        # STEP 4: Process payment (if required)
        # ============================================================
        txn_id = None
        payment_success = True
        payment_error = None

        if charge_amount > 0:
            current_app.logger.info(f"💳 Processing payment: {charge_amount} {property_obj.currency} via {payment_method}")
            success, txn_id, payment_error = processor.charge(
                user_id=current_user.id,
                amount=charge_amount,
                currency=property_obj.currency,
                description=f"Accommodation booking: {property_obj.title} - for {primary_guest_name}",
                idempotency_key=idempotency_key,
                metadata={
                    'property_id': property_obj.id,
                    'check_in': check_in.isoformat(),
                    'check_out': check_out.isoformat(),
                    'guest_name': primary_guest_name,
                    'guest_email': primary_guest_email,
                    'payment_timing': payment_timing,
                }
            )

            if not success:
                payment_success = False
                current_app.logger.error(f"❌ PAYMENT FAILED: {payment_error}")

                booking.payment_status = AccommodationPaymentStatus.FAILED.value
                db.session.commit()

                AvailabilityService.release_hold(property_obj.id, check_in, check_out, current_user.id)

                try:
                    from app.notifications.services import NotificationService
                    NotificationService.send(
                        user_id=current_user.id,
                        notification_type='payment_failed',
                        title=f'Payment Failed: {property_obj.title}',
                        message=f'Your payment of {charge_amount} {property_obj.currency} failed: {payment_error}. Your hold has been released.',
                        channels=['in_app', 'email'],
                        data={
                            'property_id': property_obj.id,
                            'amount': str(charge_amount),
                            'error': payment_error,
                        }
                    )
                except Exception as e:
                    current_app.logger.error(f"Failed to send payment failed notification: {e}")

                flash(f'Payment failed: {payment_error}. Your hold has been released. Please try again.', 'danger')
                return redirect(url_for('accommodation.guest_detail', identifier=data['property_id']))

            current_app.logger.info(f"✅ Payment successful: txn_id={txn_id}")

        # ============================================================
        # STEP 5: Update booking with payment info
        # ============================================================
        booking.payment_timing = payment_timing
        booking.payment_method = payment_method
        booking.deposit_amount = deposit_amount
        booking.amount_paid = charge_amount
        booking.amount_due = amount_due
        booking.balance_due_date = balance_due_date

        if charge_amount > 0:
            booking.payment_status = AccommodationPaymentStatus.PAID.value
            booking.wallet_txn_id = txn_id
            booking.paid_at = datetime.now(timezone.utc)
        else:
            booking.payment_status = AccommodationPaymentStatus.PENDING.value

        # Store policy snapshot
        policy_obj = PropertyBookingPolicy.query.filter_by(property_id=property_obj.id).first()
        if policy_obj:
            booking.policy_snapshot = {
                'cancellation_policy': policy_obj.cancellation_policy,
                'free_cancel_hours': policy_obj.free_cancel_hours,
                'no_show_charge_type': policy_obj.no_show_charge_type,
                'no_show_charge_amount': str(policy_obj.no_show_charge_amount) if policy_obj.no_show_charge_amount else None,
                'deposit_percentage': str(policy_obj.deposit_percentage) if policy_obj.deposit_percentage else None,
                'balance_due_days_before_checkin': policy_obj.balance_due_days_before_checkin,
            }

        # 6.5 UPDATE PAYMENT LEDGER (thin wallet-linked index)
        try:
            BookingService.update_payment_event(
                booking_id=booking.id,
                payment_status="success" if charge_amount > 0 else "pending",
                wallet_txn_id=txn_id,
                payment_method=payment_method,
                payment_gateway=payment_method,
                gateway_transaction_id=txn_id,
                idempotency_key=idempotency_key,
            )
        except Exception as ledger_error:
            current_app.logger.warning(f"Payment ledger write failed: {ledger_error}")

        db.session.flush()

        # ============================================================
        # STEP 7: Confirm booking
        # ============================================================
        if payment_timing in ('pay_now', 'deposit'):
            if booking.status == AccommodationBookingStatus.PENDING_APPROVAL.value:
                # Request-to-book properties remain pending host approval even
                # when a deposit/full payment has been captured.
                db.session.commit()
                current_app.logger.info(
                    f"✅ Booking paid and awaiting host approval: {booking.booking_reference}"
                )
            else:
                # Already paid - confirm immediately
                success, confirm_error = BookingService.confirm_booking(
                    booking.id,
                    wallet_transaction_id=txn_id,
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent')
                )

                if not success:
                    current_app.logger.error(f"❌ BOOKING CONFIRMATION FAILED: {confirm_error}")
                    flash(f'Booking confirmation failed: {confirm_error}', 'danger')
                    return redirect(url_for('accommodation.guest_detail', identifier=data['property_id']))

                current_app.logger.info(f"✅ Booking confirmed: {booking.booking_reference}")
        else:
            # pay_on_arrival or invoice - move through the state machine so
            # host approval requests are audited.
            from app.accommodation.state_machine.booking_states import BookingStateMachine

            if booking.status != AccommodationBookingStatus.PENDING_APPROVAL.value:
                BookingStateMachine.transition(
                    booking,
                    AccommodationBookingStatus.PENDING_APPROVAL,
                    changed_by_user_id=current_user.id,
                    reason="Pay-on-arrival/invoice booking requires host approval",
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent'),
                    trigger="checkout_pending_approval",
                    metadata={"payment_timing": payment_timing, "payment_method": payment_method},
                )
            db.session.commit()
            current_app.logger.info(f"✅ Booking created (pending approval): {booking.booking_reference}")

            # Extend hold expiration for approval bookings (48h SLA instead of 15min)
            if booking.status == AccommodationBookingStatus.PENDING_APPROVAL.value:
                from app.accommodation.models.availability import RoomHold
                from datetime import timedelta
                hold = RoomHold.query.filter(
                    RoomHold.property_id == booking.property_id,
                    RoomHold.check_in == booking.check_in,
                    RoomHold.check_out == booking.check_out,
                    RoomHold.guest_user_id == current_user.id,
                    RoomHold.status == "active",
                ).order_by(RoomHold.created_at.desc()).first()
                if hold and hold.hold_type == "payment":
                    hold.hold_type = "approval"
                    hold.approval_sla_hours = 48
                    hold.expires_at = datetime.now(timezone.utc) + timedelta(hours=48)
                    hold.hold_minutes = 48 * 60
                    db.session.commit()
                    current_app.logger.info(
                        f"Extended hold to 48h approval SLA for booking {booking.booking_reference}"
                    )

        # Group bookings and third-party bookings without known guest details
        # receive one capped link that can be shared with the whole party.
        if booking_type == 'group' or (booking_type == 'third_party' and not primary_guest_id):
            try:
                _, registration_token = BookingRegistrationLinkService.create_for_booking(booking)
                if registration_token:
                    session['registration_link_token'] = registration_token
            except Exception:
                current_app.logger.exception(
                    "Failed to create shared registration link for booking %s",
                    booking.booking_reference,
                )

        # Preserve the legacy snapshot for compatibility, but use the central
        # table for all newly submitted checkout requests.
        checkout_request = (data.get('special_requests') or '').strip()
        if checkout_request:
            try:
                SpecialRequestService.add_request(
                    booking.id,
                    checkout_request,
                    request_type='other',
                    requested_by_user_id=current_user.id,
                    source='checkout',
                )
            except Exception:
                current_app.logger.exception(
                    "Failed to persist checkout special request for booking %s",
                    booking.booking_reference,
                )

        session.pop('pending_booking', None)

        # ============================================================
        # STEP 8: Send notifications
        # ============================================================
        try:
            from app.notifications.services import NotificationService
            if payment_success and payment_timing in ('pay_now', 'deposit'):
                NotificationService.send(
                    user_id=current_user.id,
                    notification_type='booking_confirmed',
                    title=f'Booking Confirmed: {booking.booking_reference}',
                    message=f'Your booking at {property_obj.title} from {check_in} to {check_out} has been confirmed. Reference: {booking.booking_reference}',
                    channels=['in_app', 'email'],
                    data={
                        'booking_reference': booking.booking_reference,
                        'property_id': property_obj.id,
                        'check_in': check_in.isoformat(),
                        'check_out': check_out.isoformat(),
                    },
                    module='accommodation',
                    link=url_for('accommodation.guest_confirmation', reference=booking.booking_reference)
                )
            elif payment_timing in ('pay_on_arrival', 'invoice'):
                NotificationService.send(
                    user_id=current_user.id,
                    notification_type='booking_pending',
                    title=f'Booking Pending: {booking.booking_reference}',
                    message=f'Your booking at {property_obj.title} from {check_in} to {check_out} is pending host approval. Reference: {booking.booking_reference}',
                    channels=['in_app', 'email'],
                    data={
                        'booking_reference': booking.booking_reference,
                        'property_id': property_obj.id,
                        'check_in': check_in.isoformat(),
                        'check_out': check_out.isoformat(),
                    },
                    module='accommodation',
                    link=url_for('accommodation.guest_confirmation', reference=booking.booking_reference)
                )

            # Notify third-party guest
            if booking_type == 'third_party' and primary_guest_email != current_user.email:
                NotificationService.send(
                    user_id=current_user.id,
                    notification_type='third_party_booking',
                    title=f'Booking for Guest: {booking.booking_reference}',
                    message=f'You booked {property_obj.title} for {primary_guest_name} ({primary_guest_email}). Reference: {booking.booking_reference}',
                    channels=['in_app', 'email'],
                    data={
                        'booking_reference': booking.booking_reference,
                        'guest_name': primary_guest_name,
                        'guest_email': primary_guest_email,
                    }
                )
        except Exception as e:
            current_app.logger.error(f"Failed to send notifications: {e}")

        # ============================================================
        # STEP 9: Final redirect
        # ============================================================
        if payment_timing in ('pay_on_arrival', 'invoice'):
            flash(f'Booking created! Your reference: {booking.booking_reference}. Awaiting host approval.', 'success')
        elif booking_type == 'third_party':
            flash(f'Booking confirmed for {primary_guest_name}! They will receive an email with details.', 'success')
        else:
            flash(f'Booking confirmed! Your reference: {booking.booking_reference}', 'success')

        return redirect(url_for('accommodation.guest_confirmation', reference=booking.booking_reference))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"❌ CHECKOUT EXCEPTION: {type(e).__name__}: {str(e)}")
        current_app.logger.error(f"Full traceback:", exc_info=True)
        flash(f'Error processing booking: {str(e)}', 'danger')
        return redirect(url_for('accommodation.guest_search'))


@accommodation_bp.route("/guest/profile", methods=["GET", "POST"], endpoint="guest_profile")
@login_required
def guest_profile():
    """View and update guest profile preferences."""
    from app.accommodation.models.guest_profile import GuestProfile

    profile = GuestProfile.query.filter_by(guest_user_id=current_user.id).first()
    if not profile:
        profile = GuestProfile(guest_user_id=current_user.id)
        db.session.add(profile)
        db.session.commit()

    if request.method == "POST":
        profile.preferred_currency = request.form.get("preferred_currency", profile.preferred_currency)
        profile.preferred_language = request.form.get("preferred_language", profile.preferred_language)
        profile.special_requests_template = request.form.get("special_requests_template", profile.special_requests_template)
        profile.dietary_restrictions = request.form.get("dietary_restrictions", profile.dietary_restrictions)
        profile.accessibility_needs = request.form.get("accessibility_needs", profile.accessibility_needs)
        profile.marketing_opt_in = request.form.get("marketing_opt_in") == "on"
        profile.sms_notifications = request.form.get("sms_notifications") == "on"
        profile.email_notifications = request.form.get("email_notifications") == "on"
        profile.internal_notes = request.form.get("internal_notes", profile.internal_notes)
        db.session.commit()
        flash("Guest profile updated.", "success")
        return redirect(url_for("accommodation.guest_profile"))

    return render_template(
        "accommodation/guest/profile.html",
        profile=profile,
    )


@accommodation_bp.route("/guest/booking/claim/<token>", endpoint="guest_claim_booking")
def guest_claim_booking(token):
    """
    Claim a third-party booking using a secure single-use token.
    No login required — the page offers login or registration options.
    """
    from app.accommodation.services.booking_service import BookingService
    from app.identity.models.user import User

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'claim':
            # User is logging in or registering to claim the booking
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')

            user = User.query.filter_by(email=email).first()
            if user and user.check_password(password):
                success, msg = BookingService.claim_booking(token, user.id)
                if success:
                    flash('Booking claimed successfully! You can now manage this booking.', 'success')
                    return redirect(url_for('accommodation.guest_my_bookings'))
                flash(msg, 'danger')
            elif user:
                flash('Invalid password.', 'danger')
            else:
                # No account — redirect to registration with pre-filled email
                flash('No account found with that email. Please create one first.', 'warning')
                return redirect(url_for('auth.register', email=email))

        elif action == 'register':
            # Redirect to registration with the email pre-filled
            email = request.form.get('email', '').strip().lower()
            return redirect(url_for('auth.register', email=email))

    # Resolve booking from token for display
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    booking = AccommodationBooking.query.filter_by(
        claim_token_hash=token_hash
    ).first()

    if not booking:
        flash('Invalid or expired claim link.', 'danger')
        return redirect(url_for('accommodation.guest_search'))

    return render_template(
        'accommodation/guest/claim_booking.html',
        booking=booking,
        token=token,
    )


@accommodation_bp.route("/guest/confirmation/<reference>", endpoint="guest_confirmation")
@login_required
def guest_confirmation(reference):
    """Booking confirmation page"""
    booking = BookingService.get_booking_by_reference(reference)

    if not booking:
        flash('Booking not found', 'danger')
        return redirect(url_for('accommodation.guest_my_bookings'))

    # Authorization: booking can be viewed by booker, guest, primary guest, or host
    is_authorized = (
        booking.booked_by_user_id == current_user.id or
        booking.guest_user_id == current_user.id or
        booking.primary_guest_id == current_user.id or
        booking.host_user_id == current_user.id
    )
    if not is_authorized:
        abort(403)

    # Every booking has a module-level payment identity, including unpaid
    # bookings. Backfill the thin ledger row for legacy bookings created before
    # payment-event registration was added.
    payment_event = BookingService.get_payment_event(booking.id)
    if not payment_event:
        payment_event = BookingService.update_payment_event(
            booking_id=booking.id,
            payment_status="pending",
            payment_method=booking.payment_method or "pending",
            idempotency_key=f"booking-{booking.id}-payment-event",
        )

    property_data = search_service.get_property_by_identifier(str(booking.property_id))
    registration_link = booking.registration_link
    registration_url = None
    token = session.get('registration_link_token')
    if token and registration_link:
        registration_url = url_for('accommodation.shared_registration', token=token, _external=True)
        session.pop('registration_link_token', None)

    formatted_check_in = booking.check_in.strftime('%a, %b %d, %Y')
    formatted_check_out = booking.check_out.strftime('%a, %b %d, %Y')
    formatted_paid_at = booking.paid_at.strftime('%b %d, %Y %H:%M UTC') if booking.paid_at else None
    formatted_registration_deadline = (
        booking.registration_deadline.strftime('%b %d, %Y %H:%M UTC')
        if booking.registration_deadline else None
    )
    formatted_approval_deadline = (
        booking.approval_deadline.strftime('%b %d, %Y %H:%M UTC')
        if booking.approval_deadline else None
    )

    return render_template(
        "accommodation/guest/confirmation.html",
        booking=booking,
        payment_event=payment_event,
        property=property_data,
        special_requests=SpecialRequestService.get_for_booking(booking.id),
        registration_link=registration_link,
        registration_url=registration_url,
        formatted_check_in=formatted_check_in,
        formatted_check_out=formatted_check_out,
        formatted_paid_at=formatted_paid_at,
        formatted_registration_deadline=formatted_registration_deadline,
        formatted_approval_deadline=formatted_approval_deadline,
        now=datetime.now(timezone.utc),
    )


@accommodation_bp.route("/r/<token>", methods=["GET", "POST"], endpoint="shared_registration")
@limiter.limit("10 per minute")
def shared_registration(token):
    """Public, capped registration form for a shared booking link."""
    from app.accommodation.booking_forms import GuestRosterEntryForm, SpecialRequestsForm

    link = BookingRegistrationLinkService.find_by_token(token)
    if not link or link.is_expired:
        return render_template("accommodation/guest/registration_link.html", link=None)

    booking = link.booking
    roster_form = GuestRosterEntryForm()
    request_form = SpecialRequestsForm()
    if request.method == "POST":
        submitted_email = (roster_form.guest_email.data or "").strip().lower()
        existing = None
        if submitted_email:
            existing = GuestRegistration.query.filter_by(
                booking_id=booking.id, guest_email=submitted_email, is_active=True
            ).first()

        is_event_coordination_slot = (
            existing
            and existing.registration_source == "event_coordination"
        )

        if is_event_coordination_slot and existing.status == "completed":
            return render_template(
                "accommodation/guest/registration_link.html",
                link=link,
                booking=booking,
                registered=True,
            )

        if not is_event_coordination_slot and link.is_full:
            return render_template(
                "accommodation/guest/registration_link.html",
                link=link,
                booking=booking,
                full=True,
                roster_form=roster_form,
                request_form=request_form,
            ), 409
        if not roster_form.validate_on_submit():
            return render_template(
                "accommodation/guest/registration_link.html",
                link=link,
                booking=booking,
                roster_form=roster_form,
                request_form=request_form,
            ), 400

        try:
            locked_link = BookingRegistrationLinkService.find_by_token(token, lock=True)
            if not is_event_coordination_slot and locked_link.is_full:
                db.session.rollback()
                return render_template(
                    "accommodation/guest/registration_link.html",
                    link=locked_link,
                    booking=booking,
                    full=True,
                    roster_form=roster_form,
                    request_form=request_form,
                ), 409

            if is_event_coordination_slot:
                existing.guest_name = (roster_form.guest_name.data or existing.guest_name).strip()[:255]
                existing.guest_phone = (
                    f"{roster_form.guest_phone_country_code.data.strip()}"
                    f"{roster_form.guest_phone_national.data.strip()}"
                ).strip()[:50]
                existing.id_document_type = roster_form.id_document_type.data or existing.id_document_type
                existing.is_placeholder = False
                complete = bool(existing.guest_name and existing.guest_email and existing.guest_phone and existing.id_document_type)
                existing.status = "completed" if complete else "in_progress"
                db.session.flush()
                registration = existing
            else:
                registration = RegistrationService.create(
                    booking,
                    name=roster_form.guest_name.data,
                    email=submitted_email,
                    phone=(
                        f"{roster_form.guest_phone_country_code.data.strip()}"
                        f"{roster_form.guest_phone_national.data.strip()}"
                    ),
                    id_document_type=roster_form.id_document_type.data,
                    source="self",
                    status="completed",
                )
                db.session.flush()

            request_text = (request_form.special_requests.data or "").strip()
            if request_text:
                SpecialRequestService.add_request(
                    booking.id,
                    request_text,
                    request_type="other",
                    guest_registration_id=registration.id,
                    source="guest_self_registration",
                )
                db.session.commit()
            else:
                db.session.commit()
            return render_template(
                "accommodation/guest/registration_link.html",
                link=locked_link,
                booking=booking,
                registered=True,
            )
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Shared guest registration failed")
            return render_template(
                "accommodation/guest/registration_link.html",
                link=link,
                booking=booking,
                roster_form=roster_form,
                request_form=request_form,
                error="We could not save your registration. Please try again.",
            ), 500

    return render_template(
        "accommodation/guest/registration_link.html",
        link=link,
        booking=booking,
        roster_form=roster_form,
        request_form=request_form,
        full=link.is_full,
    )


@accommodation_bp.route("/assignment/<token>", methods=["GET", "POST"], endpoint="assignment_completion")
@limiter.limit("20 per minute")
def assignment_completion(token):
    """Attendee-specific accommodation completion via event assignment token."""
    from app.accommodation.booking_forms import GuestRosterEntryForm, SpecialRequestsForm
    from app.events.models import EventAssignment

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    assignment = EventAssignment.query.filter_by(
        acc_link_token_hash=token_hash, is_deleted=False
    ).first()
    if not assignment:
        return render_template("accommodation/guest/assignment_completion.html", assignment=None, expired=True), 404

    if assignment.acc_link_expires_at and assignment.acc_link_expires_at < datetime.now(timezone.utc):
        return render_template("accommodation/guest/assignment_completion.html", assignment=None, expired=True), 410

    booking = db.session.get(AccommodationBooking, assignment.accommodation_booking_id)
    if not booking or booking.is_deleted:
        return render_template("accommodation/guest/assignment_completion.html", assignment=None, expired=True), 404

    # Resolve the specific guest registration slot for this assignment
    slot = GuestRegistration.query.filter_by(
        booking_id=booking.id,
        event_assignment_id=assignment.id,
        is_active=True
    ).first()
    if not slot:
        return render_template("accommodation/guest/assignment_completion.html", assignment=None, expired=True), 404

    roster_form = GuestRosterEntryForm(obj=slot)
    request_form = SpecialRequestsForm()

    if request.method == "POST":
        if not roster_form.validate_on_submit():
            return render_template(
                "accommodation/guest/assignment_completion.html",
                assignment=assignment,
                booking=booking,
                slot=slot,
                roster_form=roster_form,
                request_form=request_form,
            ), 400

        slot.guest_name = (roster_form.guest_name.data or slot.guest_name).strip()[:255]
        slot.guest_phone = (
            f"{roster_form.guest_phone_country_code.data.strip()}"
            f"{roster_form.guest_phone_national.data.strip()}"
        ).strip()[:50]
        slot.id_document_type = roster_form.id_document_type.data or slot.id_document_type
        slot.is_placeholder = False
        complete = bool(slot.guest_name and slot.guest_email and slot.guest_phone and slot.id_document_type)
        slot.status = "completed" if complete else "in_progress"
        db.session.flush()

        request_text = (request_form.special_requests.data or "").strip()
        if request_text:
            SpecialRequestService.add_request(
                booking.id,
                request_text,
                request_type="other",
                guest_registration_id=slot.id,
                source="guest_self_registration",
            )
            db.session.commit()
        else:
            db.session.commit()

        return render_template(
            "accommodation/guest/assignment_completion.html",
            assignment=assignment,
            booking=booking,
            slot=slot,
            registered=True,
        )

    return render_template(
        "accommodation/guest/assignment_completion.html",
        assignment=assignment,
        booking=booking,
        slot=slot,
        roster_form=roster_form,
        request_form=request_form,
    )


def _managed_registration_booking(booking_id):
    booking = db.session.get(AccommodationBooking, booking_id)
    if not booking:
        abort(404)
    if not RegistrationPermissionService.can_manage_registrations(current_user, booking):
        abort(403)
    return booking


@accommodation_bp.route("/booking/<int:booking_id>/registrations", methods=["GET"], endpoint="guest_roster")
@login_required
def guest_roster(booking_id):
    booking = _managed_registration_booking(booking_id)
    registrations = GuestRegistration.query.filter_by(booking_id=booking.id).order_by(
        GuestRegistration.is_active.desc(), GuestRegistration.created_at.asc()
    ).all()
    active_count = RegistrationService.active_count(booking.id)
    return render_template(
        "accommodation/guest/guest_roster.html",
        booking=booking, registrations=registrations, active_count=active_count,
    )


@accommodation_bp.route("/booking/<int:booking_id>/registrations/bulk-upload", methods=["POST"], endpoint="bulk_registration_upload")
@login_required
@limiter.limit("5 per minute")
def bulk_registration_upload(booking_id):
    booking = _managed_registration_booking(booking_id)
    upload = request.files.get("file")
    if not upload or not upload.filename:
        return jsonify({"success": False, "error": "A CSV or XLSX file is required"}), 400
    try:
        summary = BulkRegistrationService.import_file(booking, upload)
        return jsonify({"success": True, **summary})
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Bulk registration upload failed for booking %s", booking_id)
        return jsonify({"success": False, "error": "Upload could not be processed"}), 500


@accommodation_bp.route("/booking/<int:booking_id>/registrations/placeholder", methods=["POST"], endpoint="create_registration_placeholder")
@login_required
def create_registration_placeholder(booking_id):
    booking = _managed_registration_booking(booking_id)
    try:
        row = RegistrationService.create(
            booking, name=request.form.get("name", "Guest — TBD"),
            source="placeholder", placeholder=True,
        )
        db.session.commit()
        return jsonify({"success": True, "registration_id": row.id, "status": row.status}), 201
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"success": False, "error": str(exc)}), 400


@accommodation_bp.route("/booking/<int:booking_id>/registrations/<int:registration_id>/remove", methods=["POST"], endpoint="remove_registration")
@login_required
def remove_registration(booking_id, registration_id):
    booking = _managed_registration_booking(booking_id)
    row = GuestRegistration.query.filter_by(id=registration_id, booking_id=booking.id).first_or_404()
    try:
        RegistrationService.remove(row, current_user.id, request.form.get("removed_reason"))
        db.session.commit()
        if row.guest_user_id:
            try:
                from app.notifications.services import NotificationService
                NotificationService.send(
                    user_id=row.guest_user_id,
                    notification_type="guest_registration_removed",
                    title="Your booking guest registration was updated",
                    message="You are no longer listed on this accommodation booking.",
                    channels=["in_app", "email"],
                    data={"booking_reference": booking.booking_reference},
                )
            except Exception:
                current_app.logger.exception("Guest removal notification failed")
        return jsonify({"success": True, "registration_id": row.id, "is_active": False})
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"success": False, "error": str(exc)}), 400


@accommodation_bp.route("/booking/<int:booking_id>/registrations/<int:registration_id>/replace", methods=["POST"], endpoint="replace_registration")
@login_required
def replace_registration(booking_id, registration_id):
    booking = _managed_registration_booking(booking_id)
    row = GuestRegistration.query.filter_by(id=registration_id, booking_id=booking.id).first_or_404()
    try:
        replacement = RegistrationService.replace(
            booking, row, current_user.id, request.form.get("removed_reason"),
            name=request.form.get("name"), email=request.form.get("email"),
            phone=request.form.get("phone"),
            id_document_type=request.form.get("id_document_type"),
            id_document_number=request.form.get("id_document_number"),
            source="host",
        )
        db.session.commit()
        return jsonify({"success": True, "registration_id": replacement.id, "replaces_registration_id": row.id}), 201
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"success": False, "error": str(exc)}), 400


@accommodation_bp.route("/booking/<int:booking_id>/delegate", methods=["POST"], endpoint="delegate_registration_management")
@login_required
def delegate_registration_management(booking_id):
    booking = _managed_registration_booking(booking_id)
    if current_user.id not in {booking.booked_by_user_id, booking.booking_owner_id}:
        abort(403)
    delegatee = User.query.filter_by(email=(request.form.get("email") or "").strip().lower()).first()
    if not delegatee:
        return jsonify({"success": False, "error": "Delegate user was not found"}), 404
    from app.auth.delegation import DelegationScope, DelegationService
    service = DelegationService()
    delegator_roles = current_user.role_names or ["user"]
    delegatee_roles = delegatee.role_names or ["user"]
    result = service.create_delegation(
        current_user.id, delegatee.id, delegator_roles[0], delegatee_roles[0],
        [DelegationScope.ACCOMMODATION_REGISTRATION_MANAGEMENT],
        min(request.form.get("duration_hours", type=int) or 24, 168),
        (request.form.get("reason") or "Accommodation registration support").strip(),
    )
    return jsonify(result), 200 if result.get("success") else 400


@accommodation_bp.route("/guest/pass/<reference>", endpoint="guest_pass")
@login_required
def guest_pass(reference):
    """Scannable booking pass (QR code) for guest check-in."""
    booking = BookingService.get_booking_by_reference(reference)

    if not booking:
        flash('Booking not found', 'danger')
        return redirect(url_for('accommodation.guest_my_bookings'))

    is_authorized = (
        booking.booked_by_user_id == current_user.id or
        booking.guest_user_id == current_user.id or
        booking.primary_guest_id == current_user.id or
        booking.host_user_id == current_user.id
    )
    if not is_authorized:
        abort(403)

    property_data = search_service.get_property_by_identifier(str(booking.property_id))

    # Build the canonical, scannable pass URL and encode it into a QR code so
    # hosts can scan it directly at check-in. Uses the configured public base
    # URL so the QR works on any device, not just the request host.
    from app.utils.url import absolute_url_for
    from app.utils.qr import qr_data_uri
    try:
        pass_url = absolute_url_for('accommodation.guest_pass', reference=reference)
    except Exception:
        pass_url = url_for('accommodation.guest_pass', reference=reference)
    qr_uri = qr_data_uri(pass_url, box_size=8, border=4)

    return render_template(
        "accommodation/guest/pass.html",
        booking=booking,
        property=property_data,
        qr_uri=qr_uri,
        pass_url=pass_url,
    )


@accommodation_bp.route("/guest/my-bookings", endpoint="guest_my_bookings")
@login_required
def guest_my_bookings():
    """User's booking history"""
    bookings = BookingService.get_user_bookings(current_user.id)

    enriched_bookings = []
    for booking in bookings:
        property_data = search_service.get_property_by_identifier(str(booking.property_id))
        enriched_bookings.append({
            'booking': booking,
            'property': property_data
        })

    return render_template(
        "accommodation/guest/my_bookings.html",
        bookings=enriched_bookings
    )


@accommodation_bp.route("/guest/booking/<int:booking_id>/review", methods=["GET", "POST"], endpoint="guest_submit_review")
@login_required
def guest_submit_review(booking_id):
    """Submit a review for a completed booking."""
    from app.accommodation.services.review_service import ReviewService

    booking = AccommodationBooking.query.get_or_404(booking_id)
    is_authorized = (
        booking.booked_by_user_id == current_user.id or
        booking.primary_guest_id == current_user.id
    )
    if not is_authorized:
        abort(403)

    if booking.status != AccommodationBookingStatus.CHECKED_OUT.value:
        flash("You can only review after check-out.", "warning")
        return redirect(url_for("accommodation.guest_my_bookings"))

    existing_review = ReviewService.get_booking_review(booking_id)
    if existing_review:
        flash("You have already reviewed this booking.", "info")
        return redirect(url_for("accommodation.guest_my_bookings"))

    property_data = search_service.get_property_by_identifier(str(booking.property_id))

    if request.method == "POST":
        overall_rating = int(request.form.get("overall_rating", 0))
        if not (1 <= overall_rating <= 5):
            flash("Please select an overall rating.", "warning")
        else:
            review, error = ReviewService.submit_review(
                booking_id=booking_id,
                reviewer_id=current_user.id,
                overall_rating=overall_rating,
                comment=request.form.get("comment", ""),
                cleanliness_rating=int(request.form.get("cleanliness_rating", 0)) or None,
                accuracy_rating=int(request.form.get("accuracy_rating", 0)) or None,
                checkin_rating=int(request.form.get("checkin_rating", 0)) or None,
                communication_rating=int(request.form.get("communication_rating", 0)) or None,
                location_rating=int(request.form.get("location_rating", 0)) or None,
                value_rating=int(request.form.get("value_rating", 0)) or None,
            )
            if error:
                flash(f"Failed to submit review: {error}", "danger")
            else:
                flash("Review submitted! It will be published after moderation.", "success")
                return redirect(url_for("accommodation.guest_my_bookings"))

    return render_template(
        "accommodation/guest/review_form.html",
        booking=booking,
        property=property_data,
    )


@accommodation_bp.route("/guest/booking/<int:booking_id>/register", methods=["GET", "POST"], endpoint="guest_register")
@login_required
def guest_register(booking_id):
    """Guest registration for a booking (self, third-party, or group)."""
    from app.accommodation.models.guest_registration import GuestRegistration
    from app.accommodation.services.booking_service import BookingService

    booking = AccommodationBooking.query.get_or_404(booking_id)
    is_authorized = (
        booking.booked_by_user_id == current_user.id or
        booking.primary_guest_id == current_user.id or
        booking.guest_user_id == current_user.id
    )
    if not is_authorized:
        abort(403)

    if booking.status not in [
        AccommodationBookingStatus.CONFIRMED.value,
        AccommodationBookingStatus.PENDING_APPROVAL.value,
    ]:
        flash("Registration is only available for confirmed or pending-approval bookings.", "warning")
        return redirect(url_for("accommodation.guest_my_bookings"))

    if request.method == "POST":
        guest_name = request.form.get("guest_name", "").strip()
        guest_email = request.form.get("guest_email", "").strip()
        guest_phone = request.form.get("guest_phone", "").strip()
        relationship_type = request.form.get("relationship_type", "adult")
        id_document_type = request.form.get("id_document_type")
        id_document_number = request.form.get("id_document_number", "").strip()
        age = request.form.get("age", type=int)
        date_of_birth = request.form.get("date_of_birth") or None
        nationality = request.form.get("nationality") or None

        # Validate host-configured required registration fields (D-024)
        try:
            policy = PropertyBookingPolicy.query.filter_by(
                property_id=booking.property_id
            ).first()
            if policy and policy.required_registration_fields:
                field_labels = {
                    "full_name": "Full name",
                    "phone": "Phone",
                    "email": "Email",
                    "id_document_type": "ID document type",
                    "id_document_number": "ID document number",
                    "date_of_birth": "Date of birth",
                    "nationality": "Nationality",
                }
                field_values = {
                    "full_name": guest_name,
                    "phone": guest_phone,
                    "email": guest_email,
                    "id_document_type": id_document_type,
                    "id_document_number": id_document_number,
                    "date_of_birth": request.form.get("date_of_birth", "").strip(),
                    "nationality": request.form.get("nationality", "").strip(),
                }
                for field in policy.required_registration_fields:
                    value = field_values.get(field, "")
                    if not value:
                        label = field_labels.get(field, field)
                        flash(f"{label} is required.", "danger")
                        return redirect(request.url)
        except Exception:
            pass

        if not guest_name:
            flash("Guest name is required.", "danger")
            return redirect(request.url)

        registration = GuestRegistration(
            booking_id=booking.id,
            guest_user_id=current_user.id if relationship_type == "primary" else None,
            guest_name=guest_name,
            guest_email=guest_email,
            guest_phone=guest_phone,
            relationship_type=relationship_type,
            age=age,
            date_of_birth=date_of_birth,
            nationality=nationality,
            id_document_type=id_document_type,
            id_document_number=id_document_number,
            status="completed",
            is_verified=False,
            registration_source="self",
        )
        db.session.add(registration)
        db.session.commit()

        request_text = (request.form.get("special_requests") or "").strip()
        if request_text:
            try:
                SpecialRequestService.add_request(
                    booking.id,
                    request_text,
                    request_type=request.form.get("request_type") or "other",
                    guest_registration_id=registration.id,
                    requested_by_user_id=current_user.id,
                    source="guest_self_registration",
                )
            except Exception:
                current_app.logger.exception(
                    "Failed to save registration request for booking %s", booking.id
                )

        flash("Guest registration saved.", "success")
        return redirect(url_for("accommodation.guest_my_bookings"))

    existing = GuestRegistration.query.filter_by(booking_id=booking.id).all()

    # Get host-configured required registration fields
    try:
        from app.accommodation.models.booking_policy import PropertyBookingPolicy
        policy = PropertyBookingPolicy.query.filter_by(
            property_id=booking.property_id
        ).first()
        required_fields = policy.required_registration_fields if policy else []
    except Exception:
        required_fields = []

    return render_template(
        "accommodation/guest/register.html",
        booking=booking,
        registrations=existing,
        required_fields=required_fields,
    )


@accommodation_bp.route("/guest/booking/<int:booking_id>/request", methods=["GET", "POST"], endpoint="guest_add_request")
@login_required
@limiter.limit("20 per minute")
def guest_add_request(booking_id):
    """Add an optional request from the authenticated booking dashboard."""
    booking = AccommodationBooking.query.get_or_404(booking_id)
    if current_user.id not in {
        booking.booked_by_user_id,
        booking.guest_user_id,
        booking.primary_guest_id,
    }:
        abort(403)

    # Special requests are only meaningful while the stay is live
    # (awaiting approval, confirmed, or in progress). Terminal states
    # (expired, cancelled, no_show, checked_out, closed, refunded) must
    # not keep prompting the guest to add requests.
    ALLOWED_REQUEST_STATUSES = {
        AccommodationBookingStatus.PENDING_APPROVAL.value,
        AccommodationBookingStatus.CONFIRMED.value,
        AccommodationBookingStatus.CHECKED_IN.value,
    }
    if booking.status not in ALLOWED_REQUEST_STATUSES:
        flash(
            "This booking can no longer accept special requests.",
            "info",
        )
        return redirect(
            url_for("accommodation.guest_my_bookings")
        )

    if request.method == "POST":
        request_text = (request.form.get("request_text") or "").strip()
        if request_text:
            try:
                SpecialRequestService.add_request(
                    booking.id,
                    request_text,
                    request_type=request.form.get("request_type") or "other",
                    requested_by_user_id=current_user.id,
                    source="dashboard",
                )
                flash("Your request was sent to the host.", "success")
            except ValueError as exc:
                flash(str(exc), "danger")
        else:
            flash("Please describe your request.", "warning")
        return redirect(url_for("accommodation.guest_confirmation", reference=booking.booking_reference))
    return render_template(
        "accommodation/guest/add_request.html",
        booking=booking,
        special_requests=SpecialRequestService.get_for_booking(booking.id),
    )


@accommodation_bp.route("/host/booking/<int:booking_id>/guest/<int:reg_id>/override", methods=["POST"], endpoint="host_override_registration")
@accommodation_bp.route("/host/booking/<int:booking_id>/registration/override", methods=["POST"], endpoint="host_override_registration_all")
@login_required
def host_override_registration(booking_id, reg_id=None):
    """
    Host override for incomplete guest registration.

    The registration deadline is a soft limit, so this is the safety valve that
    lets a host admit a guest who never registered online. With ``reg_id`` it
    overrides a single manifest entry; without it, it clears the whole booking
    so the guest can be checked in and their details captured on arrival.
    """
    from app.accommodation.models.guest_registration import GuestRegistration
    from app.accommodation.services.identity_service import AccommodationIdentityService

    booking = AccommodationBooking.query.get_or_404(booking_id)

    host_info = _ensure_host_identity()
    if not host_info or not AccommodationIdentityService.can_manage_property(current_user, booking.accommodation_property.owner_user_id, booking.accommodation_property.owner_org_id):
        flash("You do not have permission to override registration.", "danger")
        return redirect(url_for("accommodation.host_bookings"))

    reason = request.form.get("reason", "Host override")

    if reg_id is not None:
        registration = GuestRegistration.query.get_or_404(reg_id)
        if registration.booking_id != booking.id:
            abort(404)
        registration.mark_skipped(reason=reason, overridden_by_user_id=current_user.id)
    else:
        pending = [
            r for r in GuestRegistration.query.filter_by(booking_id=booking.id).all()
            if r.status not in ("completed", "skipped")
        ]
        if pending:
            for registration in pending:
                registration.mark_skipped(reason=reason, overridden_by_user_id=current_user.id)
        else:
            # Nobody registered at all - record the override so the manifest
            # reflects that the host admitted the guest knowingly.
            placeholder = GuestRegistration(
                booking_id=booking.id,
                guest_name=booking.primary_guest_name or booking.guest_name or booking.primary_guest_phone or booking.guest_phone or "Guest",
                guest_email=booking.primary_guest_email or booking.guest_email,
                guest_phone=booking.primary_guest_phone or booking.guest_phone,
                relationship_type="primary",
                status="pending",
                is_verified=False,
                registration_source="host",
            )
            db.session.add(placeholder)
            db.session.flush()
            placeholder.mark_skipped(reason=reason, overridden_by_user_id=current_user.id)

    db.session.commit()

    flash("Guest registration overridden by host.", "success")
    return redirect(url_for("accommodation.host_booking_detail", booking_id=booking_id))


@accommodation_bp.route("/my-accommodation", endpoint="my_accommodation")
@login_required
def my_accommodation():
    """
    Unified accommodation dashboard showing:
    1. Where I'm staying (guest view) - all sources
    2. What I booked (booker view) - what I paid for
    """
    from app.events.models import EventAssignment, Event, EventHostRegistration
    from app.accommodation.models.booking import AccommodationBooking, BookingContextType
    from app.accommodation.models.property import Property
    from sqlalchemy import or_, and_
    from datetime import datetime, timezone

    current_user_id = current_user.id
    current_user_email = current_user.email

    # ============================================================
    # SECTION 1: WHERE I'M STAYING (Guest View)
    # ============================================================

    guest_stays = []

    # 1A. Self-booked stays (I booked for myself, I am the guest)
    self_booked = AccommodationBooking.query.filter(
        AccommodationBooking.guest_user_id == current_user_id,
        AccommodationBooking.status.in_(['confirmed', 'checked_in', 'pending_approval']),
        AccommodationBooking.is_deleted == False
    ).all()

    for booking in self_booked:
        guest_stays.append({
            'type': 'self_booked',
            'source': 'booking',
            'booking_id': booking.id,
            'booking_reference': booking.booking_reference,
            'property_name': booking.accommodation_property.title if booking.accommodation_property else 'Property',
            'property_id': booking.property_id,
            'check_in': booking.check_in,
            'check_out': booking.check_out,
            'nights': booking.num_nights,
            'guests': booking.num_guests,
            'status': booking.status,
            'payment_status': booking.payment_status,
            'total_amount': float(booking.total_amount),
            'currency': booking.currency,
            'booked_by': 'Myself',
            'booked_by_name': current_user.username,
            'can_cancel': booking.can_cancel()[0] if hasattr(booking, 'can_cancel') else False,
            'cancellation_policy': booking.accommodation_property.cancellation_policy if booking.accommodation_property else None,
            'host_contact': {
                'name': booking.accommodation_property.owner_display_name if booking.accommodation_property else None,
                'phone': booking.accommodation_property.owner_user.phone if booking.accommodation_property and booking.accommodation_property.owner_user else None,
                'email': booking.accommodation_property.owner_user.email if booking.accommodation_property and booking.accommodation_property.owner_user else None,
            } if booking.accommodation_property else None,
            'address': booking.accommodation_property.full_address if booking.accommodation_property else None,
            'images': booking.accommodation_property.gallery_images[:3] if booking.accommodation_property and booking.accommodation_property.gallery_images else [],
        })

    # 1B. Booked for me by someone else (third-party booking where I am primary guest)
    third_party_for_me = AccommodationBooking.query.filter(
        and_(
            or_(
                AccommodationBooking.primary_guest_id == current_user_id,
                AccommodationBooking.primary_guest_email == current_user_email
            ),
            AccommodationBooking.booking_type == 'third_party',
            AccommodationBooking.status.in_(['confirmed', 'checked_in', 'pending_approval']),
            AccommodationBooking.is_deleted == False
        )
    ).all()

    for booking in third_party_for_me:
        booker = db.session.get(User, booking.booked_by_user_id)
        guest_stays.append({
            'type': 'booked_for_me',
            'source': 'booking',
            'booking_id': booking.id,
            'booking_reference': booking.booking_reference,
            'property_name': booking.accommodation_property.title if booking.accommodation_property else 'Property',
            'property_id': booking.property_id,
            'check_in': booking.check_in,
            'check_out': booking.check_out,
            'nights': booking.num_nights,
            'guests': booking.num_guests,
            'status': booking.status,
            'payment_status': booking.payment_status,
            'total_amount': float(booking.total_amount),
            'currency': booking.currency,
            'booked_by': 'Someone else',
            'booked_by_name': booker.username if booker else 'Unknown',
            'can_cancel': False,  # Only the booker can cancel
            'cancellation_policy': booking.accommodation_property.cancellation_policy if booking.accommodation_property else None,
            'host_contact': {
                'name': booking.accommodation_property.owner_display_name if booking.accommodation_property else None,
                'phone': booking.accommodation_property.owner_user.phone if booking.accommodation_property and booking.accommodation_property.owner_user else None,
                'email': booking.accommodation_property.owner_user.email if booking.accommodation_property and booking.accommodation_property.owner_user else None,
            } if booking.accommodation_property else None,
            'address': booking.accommodation_property.full_address if booking.accommodation_property else None,
            'images': booking.accommodation_property.gallery_images[:3] if booking.accommodation_property and booking.accommodation_property.gallery_images else [],
            'guest_instructions': booking.guest_instructions,
        })

    # 1C. Assigned to me by event organizer
    assignments = EventAssignment.query.filter_by(
        attendee_id=current_user_id,
        status='active'
    ).all()

    for assignment in assignments:
        event = db.session.get(Event, assignment.event_id)
        if not event:
            continue

        # Check if hotel booking
        if assignment.accommodation_booking_id:
            booking = db.session.get(AccommodationBooking, assignment.accommodation_booking_id)
            if booking and booking.accommodation_property:
                guest_stays.append({
                    'type': 'event_assigned_hotel',
                    'source': 'assignment',
                    'assignment_id': assignment.id,
                    'event_id': event.id,
                    'event_name': event.name,
                    'event_slug': event.slug,
                    'event_dates': f"{event.start_date} - {event.end_date}" if event.start_date else None,
                    'booking_reference': booking.booking_reference,
                    'property_name': booking.accommodation_property.title,
                    'property_id': booking.property_id,
                    'check_in': booking.check_in,
                    'check_out': booking.check_out,
                    'nights': booking.num_nights,
                    'guests': booking.num_guests,
                    'status': booking.status,
                    'total_amount': float(booking.total_amount),
                    'currency': booking.currency,
                    'booked_by': f"Event Organizer ({event.organizer.username if event.organizer else 'Unknown'})",
                    'booked_by_name': event.organizer.username if event.organizer else 'Event Organizer',
                    'can_cancel': False,
                    'host_contact': {
                        'name': booking.accommodation_property.owner_display_name,
                        'phone': booking.accommodation_property.owner_user.phone if booking.accommodation_property.owner_user else None,
                        'email': booking.accommodation_property.owner_user.email if booking.accommodation_property.owner_user else None,
                    },
                    'address': booking.accommodation_property.full_address,
                    'images': booking.accommodation_property.gallery_images[:3] if booking.accommodation_property.gallery_images else [],
                })

        # Check if community host
        elif assignment.community_host_id:
            property_obj = db.session.get(Property, assignment.community_host_id)
            host_reg = EventHostRegistration.query.filter_by(
                event_id=event.id,
                property_id=assignment.community_host_id
            ).first()

            if property_obj:
                guest_stays.append({
                    'type': 'event_assigned_community',
                    'source': 'assignment',
                    'assignment_id': assignment.id,
                    'event_id': event.id,
                    'event_name': event.name,
                    'event_slug': event.slug,
                    'event_dates': f"{event.start_date} - {event.end_date}" if event.start_date else None,
                    'property_name': property_obj.title,
                    'property_id': property_obj.id,
                    'check_in': event.start_date,  # Use event dates for community hosts
                    'check_out': event.end_date,
                    'guests': host_reg.max_guests if host_reg else property_obj.max_guests,
                    'status': 'confirmed',
                    'is_free': host_reg.is_free if host_reg else property_obj.base_price_per_night == 0,
                    'price_per_night': float(host_reg.price_per_night) if host_reg and host_reg.price_per_night else float(property_obj.base_price_per_night),
                    'currency': host_reg.currency if host_reg else property_obj.currency,
                    'booked_by': f"Event Organizer ({event.organizer.username if event.organizer else 'Unknown'})",
                    'can_cancel': False,
                    'host_contact': {
                        'name': property_obj.owner_display_name,
                        'phone': property_obj.owner_user.phone if property_obj.owner_user else None,
                        'email': property_obj.owner_user.email if property_obj.owner_user else None,
                    },
                    'address': property_obj.full_address,
                    'house_rules': property_obj.house_rules,
                    'special_instructions': host_reg.special_instructions if host_reg else None,
                    'images': property_obj.gallery_images[:3] if property_obj.gallery_images else [],
                })

    # ============================================================
    # SECTION 2: WHAT I BOOKED (Booker View - What I paid for)
    # ============================================================

    my_bookings = []

    # All bookings I made (as booker)
    bookings_i_made = AccommodationBooking.query.filter(
        AccommodationBooking.booked_by_user_id == current_user_id,
        AccommodationBooking.is_deleted == False
    ).order_by(AccommodationBooking.created_at.desc()).all()

    for booking in bookings_i_made:
        # Determine if this is for me or for someone else
        is_for_me = (booking.guest_user_id == current_user_id)

        # Get guest info
        if booking.primary_guest_id:
            guest_user = db.session.get(User, booking.primary_guest_id)
            guest_name = guest_user.username if guest_user else booking.primary_guest_name
            guest_email = guest_user.email if guest_user else booking.primary_guest_email
        elif booking.guest_user_id:
            guest_user = db.session.get(User, booking.guest_user_id)
            guest_name = guest_user.username if guest_user else booking.guest_name
            guest_email = guest_user.email if guest_user else booking.guest_email
        else:
            guest_name = booking.guest_name
            guest_email = booking.guest_email

        my_bookings.append({
            'type': 'for_self' if is_for_me else 'for_other',
            'booking_id': booking.id,
            'booking_reference': booking.booking_reference,
            'property_name': booking.accommodation_property.title if booking.accommodation_property else 'Property',
            'property_id': booking.property_id,
            'check_in': booking.check_in,
            'check_out': booking.check_out,
            'nights': booking.num_nights,
            'guests': booking.num_guests,
            'status': booking.status,
            'payment_status': booking.payment_status,
            'total_amount': float(booking.total_amount),
            'currency': booking.currency,
            'paid_at': booking.paid_at,
            'guest_name': guest_name,
            'guest_email': guest_email,
            'guest_phone': booking.primary_guest_phone or booking.guest_phone,
            'is_group_booking': booking.group_booking_id is not None,
            'group_id': booking.group_booking_id,
            'room_number': booking.room_number,
            'can_cancel': booking.can_cancel()[0] if hasattr(booking, 'can_cancel') else False,
            'property_image': booking.accommodation_property.cover_image_url if booking.accommodation_property else None,
        })

    # Group bookings summary (for display)
    group_bookings = {}
    for booking in my_bookings:
        if booking.get('group_id'):
            if booking['group_id'] not in group_bookings:
                group_bookings[booking['group_id']] = {
                    'rooms': [],
                    'total_guests': 0,
                    'total_amount': 0,
                    'check_in': booking['check_in'],
                    'check_out': booking['check_out'],
                    'property_name': booking['property_name'],
                }
            group_bookings[booking['group_id']]['rooms'].append(booking)
            group_bookings[booking['group_id']]['total_guests'] += booking['guests']
            group_bookings[booking['group_id']]['total_amount'] += booking['total_amount']

    # Sort guest stays by check-in date (upcoming first)
    guest_stays.sort(key=lambda x: x.get('check_in') or datetime.max.date())

    # ============================================================
    # RENDER
    # ============================================================

    # Check if pane request (for dashboard embedding)
    if request.args.get('_pane') == '1':
        return render_template(
            'accommodation/my_accommodation_pane.html',
            guest_stays=guest_stays,
            my_bookings=my_bookings,
            group_bookings=group_bookings,
            now=datetime.now(timezone.utc)
        )

    return render_template(
        'accommodation/my_accommodation.html',
        guest_stays=guest_stays,
        my_bookings=my_bookings,
        group_bookings=group_bookings,
        now=datetime.now(timezone.utc)
    )


@accommodation_bp.route("/guest/booking/<reference>/cancel", methods=['POST'], endpoint="guest_cancel_booking")
@login_required
@limiter.limit("10 per minute")
def guest_cancel_booking(reference):
    """Cancel a booking"""
    booking = BookingService.get_booking_by_reference(reference)

    if not booking:
        flash('Booking not found', 'danger')
        return redirect(url_for('accommodation.guest_my_bookings'))

    # Allow cancellation if current user is the guest, primary guest, booking
    # owner, or booker (for third-party bookings).
    is_guest = booking.guest_user_id == current_user.id
    is_booker = booking.booked_by_user_id == current_user.id
    is_primary_guest = booking.primary_guest_id == current_user.id
    is_booking_owner = booking.booking_owner_id == current_user.id
    if not (is_guest or is_booker or is_primary_guest or is_booking_owner):
        flash('You are not authorized to cancel this booking', 'danger')
        return redirect(url_for('accommodation.guest_my_bookings'))

    reason = request.form.get('reason', 'User requested cancellation')

    success, message, refund = BookingService.cancel_booking(
        booking.id,
        cancelled_by_user_id=current_user.id,
        reason=reason,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
    )

    return_to_confirmation = request.form.get("return_to_confirmation") == "1"
    confirmation_url = url_for(
        "accommodation.guest_confirmation",
        reference=booking.booking_reference,
    )

    if success:
        if refund > 0:
            WalletService.refund_wallet(
                user_id=current_user.id,
                amount=refund,
                description=f"Refund for cancelled booking: {reference}",
                original_transaction_id=booking.wallet_txn_id
            )
            flash(f'{message} Refund of ${refund} has been processed.', 'success')
        else:
            flash(message, 'info')
    else:
        flash(message, 'danger')

    if return_to_confirmation:
        return redirect(confirmation_url)
    return redirect(url_for('accommodation.guest_my_bookings'))


# ============================================================================
# GUEST DASHBOARD (URL prefix: /guest)
# ============================================================================

@accommodation_bp.route("/guest/dashboard", endpoint="guest_dashboard")
@login_required
def guest_dashboard():
    """Unified guest dashboard: stays, payments, check-in/out, reviews, complaints."""
    from app.accommodation.services.guest_dashboard_service import GuestDashboardService

    data = GuestDashboardService.get_dashboard_data(current_user.id)

    # When loaded inside the shared shell (?_pane=1) return a fragment only so it
    # injects into the right pane without nesting the full page layout.
    if request.args.get("_pane") == "1":
        return render_template(
            "accommodation/guest/dashboard_pane.html",
            **data,
            now=datetime.now(timezone.utc),
        )

    return render_template(
        "accommodation/guest/dashboard.html",
        **data,
        now=datetime.now(timezone.utc),
    )


@accommodation_bp.route("/guest/complaints", endpoint="guest_complaints")
@login_required
def guest_complaints():
    """List the guest's complaints and provide a create form."""
    from app.accommodation.models.feedback import AccommodationComplaint

    complaints = (
        AccommodationComplaint.query.filter_by(user_id=current_user.id)
        .filter(AccommodationComplaint.is_deleted == False)  # noqa: E712
        .order_by(AccommodationComplaint.created_at.desc())
        .all()
    )

    # Bookings the guest can attach a complaint to.
    from app.accommodation.models.booking import AccommodationBooking
    from sqlalchemy import or_
    bookings = (
        AccommodationBooking.query.filter(
            or_(
                AccommodationBooking.guest_user_id == current_user.id,
                AccommodationBooking.primary_guest_id == current_user.id,
                AccommodationBooking.booked_by_user_id == current_user.id,
            ),
            AccommodationBooking.is_deleted == False,  # noqa: E712
        )
        .order_by(AccommodationBooking.check_in.desc())
        .limit(50)
        .all()
    )

    return render_template(
        "accommodation/guest/complaints.html",
        complaints=complaints,
        bookings=bookings,
        now=datetime.now(timezone.utc),
    )


@accommodation_bp.route("/guest/complaints/new", methods=["POST"], endpoint="guest_complaint_new")
@login_required
@limiter.limit("10 per minute")
def guest_complaint_new():
    """Create a new complaint for a stay or property."""
    from app.accommodation.models.feedback import AccommodationComplaint

    category = request.form.get("category", "other")
    subject = (request.form.get("subject") or "").strip()
    description = (request.form.get("description") or "").strip()
    booking_id = request.form.get("booking_id") or None
    property_id = request.form.get("property_id") or None
    priority = request.form.get("priority", "medium")

    if not subject or not description:
        flash("Subject and description are required.", "warning")
        return redirect(url_for("accommodation.guest_complaints"))

    complaint = AccommodationComplaint(
        user_id=current_user.id,
        category=category,
        subject=subject,
        description=description,
        priority=priority,
        status="open",
    )
    if booking_id and booking_id.isdigit():
        complaint.booking_id = int(booking_id)
        booking = AccommodationBooking.query.get(int(booking_id))
        if booking:
            complaint.property_id = booking.property_id
            complaint.host_user_id = booking.host_user_id
    elif property_id and property_id.isdigit():
        complaint.property_id = int(property_id)

    complaint.generate_reference()
    db.session.add(complaint)
    db.session.commit()

    try:
        from app.notifications.services import NotificationService
        NotificationService.send(
            user_id=current_user.id,
            notification_type="accommodation_complaint_opened",
            title="Complaint received",
            message=f"Your complaint '{subject}' has been logged. Reference {complaint.reference}.",
            channels=["in_app"],
        )
    except Exception:
        pass

    flash(f"Complaint submitted. Reference: {complaint.reference}", "success")
    return redirect(url_for("accommodation.guest_complaints"))


@accommodation_bp.route("/guest/complaints/<reference>", endpoint="guest_complaint_detail")
@login_required
def guest_complaint_detail(reference):
    """View a single complaint."""
    from app.accommodation.models.feedback import AccommodationComplaint

    complaint = AccommodationComplaint.query.filter_by(
        reference=reference, user_id=current_user.id
    ).filter(AccommodationComplaint.is_deleted == False).first_or_404()  # noqa: E712

    return render_template(
        "accommodation/guest/complaint_detail.html",
        complaint=complaint,
        now=datetime.now(timezone.utc),
    )


@accommodation_bp.route("/guest/booking/<int:booking_id>/amend", methods=["GET", "POST"], endpoint="guest_amend_booking")
@login_required
def guest_amend_booking(booking_id):
    """Request an amendment to a booking (dates, guests, or special requests)."""
    from app.accommodation.models.feedback import AccommodationBookingAmendment

    booking = AccommodationBooking.query.get_or_404(booking_id)
    is_authorized = (
        booking.booked_by_user_id == current_user.id
        or booking.primary_guest_id == current_user.id
        or booking.guest_user_id == current_user.id
    )
    if not is_authorized:
        abort(403)

    if booking.status not in [
        AccommodationBookingStatus.CONFIRMED.value,
        AccommodationBookingStatus.PENDING_APPROVAL.value,
    ]:
        flash("This booking can no longer be amended.", "warning")
        return redirect(url_for("accommodation.guest_dashboard"))

    if request.method == "POST":
        amendment_type = request.form.get("amendment_type", "other")
        reason = (request.form.get("reason") or "").strip()
        return_to_confirmation = request.form.get("return_to_confirmation") == "1"
        confirmation_url = url_for(
            "accommodation.guest_confirmation",
            reference=booking.booking_reference,
        )

        amendment = AccommodationBookingAmendment(
            booking_id=booking.id,
            requested_by_user_id=current_user.id,
            amendment_type=amendment_type,
            current_check_in=booking.check_in,
            current_check_out=booking.check_out,
            current_guests=booking.num_guests,
            reason=reason,
            status="pending",
        )

        if amendment_type == "dates":
            ci = request.form.get("requested_check_in")
            co = request.form.get("requested_check_out")
            try:
                requested_check_in = datetime.strptime(ci, "%Y-%m-%d").date() if ci else None
                requested_check_out = datetime.strptime(co, "%Y-%m-%d").date() if co else None
            except ValueError:
                flash("Invalid date format.", "warning")
                return redirect(confirmation_url if return_to_confirmation else request.url)
            if not requested_check_in or not requested_check_out:
                flash("Both new dates are required.", "warning")
                return redirect(confirmation_url if return_to_confirmation else request.url)
            if requested_check_in < date.today():
                flash("New check-in date cannot be in the past.", "warning")
                return redirect(confirmation_url if return_to_confirmation else request.url)
            if requested_check_out <= requested_check_in:
                flash("New check-out must be after check-in.", "warning")
                return redirect(confirmation_url if return_to_confirmation else request.url)
            amendment.requested_check_in = requested_check_in
            amendment.requested_check_out = requested_check_out
        elif amendment_type == "guests":
            try:
                amendment.requested_guests = int(request.form.get("requested_guests", booking.num_guests))
            except (ValueError, TypeError):
                amendment.requested_guests = booking.num_guests
        elif amendment_type == "special_requests":
            amendment.requested_special_requests = (request.form.get("requested_special_requests") or "").strip()

        db.session.add(amendment)
        db.session.commit()
        flash("Amendment request submitted. The host will review it shortly.", "success")
        if return_to_confirmation:
            return redirect(confirmation_url)
        return redirect(url_for("accommodation.guest_dashboard"))

    return render_template(
        "accommodation/guest/amend.html",
        booking=booking,
        now=datetime.now(timezone.utc),
    )


@accommodation_bp.route("/guest/booking/<int:booking_id>/check-in", methods=["POST"], endpoint="guest_self_checkin")
@login_required
@limiter.limit("20 per minute")
def guest_self_checkin(booking_id):
    """Guest self check-in (when eligible)."""
    from app.accommodation.state_machine.booking_states import BookingStateMachine, InvalidStateTransition

    booking = AccommodationBooking.query.get_or_404(booking_id)
    is_authorized = (
        booking.guest_user_id == current_user.id
        or booking.primary_guest_id == current_user.id
        or booking.booked_by_user_id == current_user.id
    )
    if not is_authorized:
        abort(403)

    try:
        BookingStateMachine.transition(
            booking,
            AccommodationBookingStatus.CHECKED_IN,
            changed_by_user_id=current_user.id,
            reason="Guest self check-in",
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
            trigger="guest_self_checkin",
        )
        booking.is_checked_in = True
        booking.checked_in_at = datetime.now(timezone.utc)
        booking.checked_in_by = current_user.id
        db.session.commit()
        flash("You are checked in. Enjoy your stay!", "success")
    except InvalidStateTransition:
        flash("Check-in is not available yet (date, payment, or registration may be incomplete).", "warning")
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error(f"Guest check-in failed: {exc}")
        flash("Check-in could not be completed. Please try again or contact the host.", "danger")

    return redirect(url_for("accommodation.guest_dashboard"))


@accommodation_bp.route("/guest/booking/<int:booking_id>/check-out", methods=["POST"], endpoint="guest_self_checkout")
@login_required
@limiter.limit("20 per minute")
def guest_self_checkout(booking_id):
    """Guest self check-out (when checked in)."""
    from app.accommodation.state_machine.booking_states import BookingStateMachine, InvalidStateTransition

    booking = AccommodationBooking.query.get_or_404(booking_id)
    is_authorized = (
        booking.guest_user_id == current_user.id
        or booking.primary_guest_id == current_user.id
        or booking.booked_by_user_id == current_user.id
    )
    if not is_authorized:
        abort(403)

    try:
        BookingStateMachine.transition(
            booking,
            AccommodationBookingStatus.CHECKED_OUT,
            changed_by_user_id=current_user.id,
            reason="Guest self check-out",
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
            trigger="guest_self_checkout",
        )
        booking.is_checked_out = True
        booking.checked_out_at = datetime.now(timezone.utc)
        booking.checked_out_by = current_user.id
        db.session.commit()
        flash("You are checked out. We hope you enjoyed your stay!", "success")
    except InvalidStateTransition:
        flash("Check-out is not available. You must be checked in first.", "warning")
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error(f"Guest check-out failed: {exc}")
        flash("Check-out could not be completed. Please try again or contact the host.", "danger")

    return redirect(url_for("accommodation.guest_dashboard"))


@accommodation_bp.route("/guest/booking/<int:booking_id>/pay", methods=["POST"], endpoint="guest_pay_booking")
@login_required
@limiter.limit("10 per minute")
def guest_pay_booking(booking_id):
    """Pay the outstanding balance for a booking via the guest wallet."""
    from decimal import Decimal as _D
    from app.accommodation.services.payment_processors.wallet_processor import WalletProcessor
    from app.accommodation.services.booking_service import BookingService

    booking = AccommodationBooking.query.get_or_404(booking_id)
    is_authorized = (
        booking.guest_user_id == current_user.id
        or booking.primary_guest_id == current_user.id
        or booking.booked_by_user_id == current_user.id
    )
    if not is_authorized:
        abort(403)

    amount_due = _D(str(booking.amount_due or 0))
    if amount_due <= _D("0.00"):
        try:
            amount_due = max(_D("0.00"), _D(str(booking.total_amount or 0)) - _D(str(booking.amount_paid or 0)))
        except Exception:
            amount_due = _D("0.00")

    if amount_due <= _D("0.00"):
        flash("There is no outstanding balance to pay.", "info")
        return redirect(url_for("accommodation.guest_dashboard"))

    # Use a fresh idempotency key for this balance capture.
    idempotency_key = f"bal-{booking.booking_reference}-{uuid.uuid4().hex[:8]}"
    booking.idempotency_key = idempotency_key
    db.session.commit()

    processor = WalletProcessor()
    try:
        currency = booking.currency or "USD"
        success, txn_id, error = processor.charge(
            user_id=current_user.id,
            amount=amount_due,
            currency=currency,
            description=f"Balance payment for booking {booking.booking_reference}",
            idempotency_key=idempotency_key,
            metadata={"balance_payment": True, "booking_id": booking.id},
        )
        if not success:
            db.session.rollback()
            flash(f"Payment failed: {error}", "danger")
            return redirect(url_for("accommodation.guest_dashboard"))

        booking.amount_paid = (booking.amount_paid or _D("0.00")) + amount_due
        booking.amount_due = _D("0.00")
        booking.payment_status = AccommodationPaymentStatus.PAID.value
        booking.wallet_txn_id = txn_id
        booking.paid_at = datetime.now(timezone.utc)
        db.session.commit()

        try:
            BookingService.update_payment_event(
                booking_id=booking.id,
                payment_status="success",
                wallet_txn_id=txn_id,
                payment_method="wallet",
                payment_gateway="wallet",
                gateway_transaction_id=txn_id,
                idempotency_key=idempotency_key,
            )
        except Exception:
            pass

        flash(f"Balance of {amount_due} {currency} paid successfully.", "success")
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error(f"Guest balance payment failed: {exc}")
        flash("Payment could not be processed. Please try again.", "danger")

    return redirect(url_for("accommodation.guest_dashboard"))


# ============================================================================
# HOST ROUTES (URL prefix: /host)
# ============================================================================

def _ensure_host_identity():
    """Return host identity data if current user can host; otherwise flash warning"""
    can_host, reason = AccommodationIdentityService.can_host(current_user)
    if not can_host:
        flash(f"Cannot access host tools: {reason}", "warning")
        return None
    host_info = AccommodationIdentityService.get_host_identity(current_user)
    if not host_info:
        return None

    from app.auth.context import ContextType, get_active_context

    active_context = get_active_context(current_user)
    if active_context.type is ContextType.PLATFORM:
        return host_info
    if active_context.type is not ContextType.ACCOMMODATION_HOST:
        flash("Select an accommodation host context before opening host tools.", "warning")
        return None
    if host_info["type"] == "individual":
        if active_context.public_id != str(current_user.public_id):
            abort(403)
        return host_info

    from app.identity.models.organisation import Organisation

    organisation = db.session.get(Organisation, host_info["id"])
    if not organisation or str(organisation.org_id) != str(active_context.public_id):
        abort(403)
    return host_info


def _populate_form_choices(form: PropertyForm) -> None:
    """Populate select fields for property forms"""
    property_type_choices = [
        (ptype.value, ptype.name.replace("_", " ").title())
        for ptype in AccommodationPropertyType
    ]
    cancellation_choices = [
        (policy.value, policy.name.replace("_", " ").title())
        for policy in AccommodationCancellationPolicy
    ]
    supported_currencies = current_app.config.get(
        "SUPPORTED_CURRENCIES",
        ["USD", "EUR", "GBP", "UGX", "KES", "NGN"],
    )

    form.set_choices(
        property_types=property_type_choices,
        currencies=supported_currencies,
        cancellation_policies=cancellation_choices,
    )


def _resolve_month(month_str: Optional[str]) -> dict:
    """Parse a YYYY-MM month hint into year/month integers with fallbacks"""
    today = date.today()
    if not month_str:
        return {"year": today.year, "month": today.month}

    try:
        year, month = month_str.split("-", 1)
        return {"year": int(year), "month": int(month)}
    except (ValueError, AttributeError):
        return {"year": today.year, "month": today.month}


@accommodation_bp.route("/host/dashboard", endpoint="host_dashboard")
@login_required
def host_dashboard():
    host_info = _ensure_host_identity()
    if not host_info:
        return redirect(url_for("index"))

    dashboard_data = HostService.get_dashboard_data(
        owner_user_id=host_info["id"] if host_info["type"] == "individual" else None,
        owner_org_id=host_info["id"] if host_info["type"] == "organisation" else None,
    )

    # Get blocked dates for host's properties
    from app.accommodation.models.availability import BlockedDate
    from datetime import date, timedelta
    from sqlalchemy import and_

    host_property_ids = [p.id for p in dashboard_data["properties"]]
    blocked_dates = []
    if host_property_ids:
        today = date.today()
        blocked_dates = BlockedDate.query.filter(
            and_(
                BlockedDate.property_id.in_(host_property_ids),
                BlockedDate.blocked_date >= today,
                BlockedDate.reason == 'temporary_hold'
            )
        ).order_by(BlockedDate.blocked_date).all()

    return render_template(
        "accommodation/host/dashboard.html",
        host_info=host_info,
        listings=dashboard_data["properties"],
        bookings=dashboard_data["upcoming_bookings"],
        recent_bookings=dashboard_data.get("recent_bookings", []),
        stats=dashboard_data["stats"],
        revenue_summary=dashboard_data["revenue_summary"],
        monthly_revenue=dashboard_data.get("monthly_revenue", []),
        total_bookings_count=dashboard_data.get("total_bookings_count", 0),
        total_revenue=dashboard_data.get("total_revenue", 0),
        avg_rating=dashboard_data.get("avg_rating", 0),
        total_reviews=dashboard_data.get("total_reviews", 0),
        avg_response_rate=dashboard_data.get("avg_response_rate"),
        total_views=dashboard_data.get("total_views", 0),
        conversion_rate=dashboard_data.get("conversion_rate", 0),
        insights=dashboard_data.get("insights", []),
        # Advanced analytics
        advanced_metrics=dashboard_data.get("advanced_metrics", {}),
        performance_metrics=dashboard_data.get("performance_metrics", {}),
        guest_intelligence=dashboard_data.get("guest_intelligence", {}),
        competitive_intelligence=dashboard_data.get("competitive_intelligence", {}),
        ai_insights=dashboard_data.get("ai_insights", []),
        revenue_forecast=dashboard_data.get("revenue_forecast", {}),
        channel_performance=dashboard_data.get("channel_performance", []),
        seasonal_trends=dashboard_data.get("seasonal_trends", {}),
        booking_velocity=dashboard_data.get("booking_velocity", {}),
        blocked_dates=blocked_dates,
    )


@accommodation_bp.route('/host/release-hold/<int:block_id>', methods=['POST'], endpoint='host_release_hold')
@login_required
def host_release_hold(block_id):
    """Release a temporary hold on a date (host/admin action)."""
    from app.accommodation.models.availability import BlockedDate, AccommodationBlockedReason
    from app.accommodation.models.property import Property

    block = BlockedDate.query.get_or_404(block_id)

    prop = db.session.get(Property, block.property_id)
    if not prop:
        flash('Property not found.', 'danger')
        return redirect(url_for('accommodation.host_dashboard'))

    is_admin = current_user.has_role('owner', 'super_admin', 'admin', 'moderator')
    is_host = (prop.owner_user_id == current_user.id or
               (prop.owner_org_id and hasattr(current_user, 'managed_organisations') and
                any(org.id == prop.owner_org_id for org in current_user.managed_organisations)))

    if not is_admin and not is_host:
        abort(403)

    if block.reason != AccommodationBlockedReason.TEMPORARY_HOLD.value:
        flash('Only temporary holds can be released.', 'warning')
        return redirect(url_for('accommodation.host_dashboard'))

    db.session.delete(block)
    db.session.commit()

    flash(f'Released hold for {block.blocked_date}', 'success')
    return redirect(url_for('accommodation.host_dashboard'))


@accommodation_bp.route("/host/earnings", endpoint="host_earnings")
@login_required
def host_earnings():
    """Host earnings and payout dashboard."""
    host_info = _ensure_host_identity()
    if not host_info:
        return redirect(url_for("index"))

    earnings = MarketplaceService.get_host_earnings(current_user.id)
    payout_history = MarketplaceService.get_host_payout_history(current_user.id)

    return render_template(
        "accommodation/host/earnings.html",
        host_info=host_info,
        earnings=earnings,
        payout_history=payout_history,
    )


@accommodation_bp.route("/host/property/<int:property_id>/documents", methods=["GET", "POST"], endpoint="host_property_documents")
@login_required
def host_property_documents(property_id):
    """Upload and manage property verification documents."""
    from app.accommodation.models.property_document import PropertyDocument, PropertyDocumentType, PropertyDocumentStatus

    prop = Property.query.get_or_404(property_id)
    host_info = _ensure_host_identity()
    if not host_info or not AccommodationIdentityService.can_manage_property(current_user, prop.owner_user_id, prop.owner_org_id):
        flash("You do not have permission to manage this property.", "danger")
        return redirect(url_for("accommodation.host_dashboard"))

    if request.method == "POST":
        file = request.files.get("document")
        document_type = request.form.get("document_type")
        if not file or not document_type:
            flash("Please select a file and document type.", "warning")
        else:
            try:
                from app.media.service import upload_file
                file_url = upload_file(file, module="accommodation", entity_id=property_id)
                doc = PropertyDocument(
                    property_id=property_id,
                    host_user_id=current_user.id,
                    document_type=PropertyDocumentType(document_type),
                    file_url=file_url,
                    file_name=file.filename,
                    file_size=file.content_length,
                    mime_type=file.mimetype,
                )
                db.session.add(doc)
                db.session.commit()
                flash("Document uploaded successfully.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Upload failed: {e}", "danger")

    documents = PropertyDocument.query.filter_by(property_id=property_id).order_by(PropertyDocument.created_at.desc()).all()
    return render_template(
        "accommodation/host/property_documents.html",
        property=prop,
        documents=documents,
        document_types=[dt.value for dt in PropertyDocumentType],
    )


@accommodation_bp.route("/host/document/<int:document_id>/delete", methods=["POST"], endpoint="host_delete_document")
@login_required
def host_delete_document(document_id):
    """Delete a property document."""
    from app.accommodation.models.property_document import PropertyDocument, PropertyDocumentStatus

    doc = PropertyDocument.query.get_or_404(document_id)
    prop = Property.query.get_or_404(doc.property_id)
    host_info = _ensure_host_identity()
    if not host_info or not AccommodationIdentityService.can_manage_property(current_user, prop.owner_user_id, prop.owner_org_id):
        flash("You do not have permission to manage this property.", "danger")
        return redirect(url_for("accommodation.host_dashboard"))

    if doc.status != PropertyDocumentStatus.PENDING:
        flash("Cannot delete a processed document.", "warning")
        return redirect(url_for("accommodation.host_property_documents", property_id=doc.property_id))

    db.session.delete(doc)
    db.session.commit()
    flash("Document deleted.", "success")
    return redirect(url_for("accommodation.host_property_documents", property_id=doc.property_id))


@accommodation_bp.route("/host/dashboard/data", endpoint="host_dashboard_data")
@login_required
def host_dashboard_data():
    host_info = _ensure_host_identity()
    if not host_info:
        return jsonify({"error": "Unauthorized"}), 401

    dashboard_data = HostService.get_dashboard_data(
        owner_user_id=host_info["id"] if host_info["type"] == "individual" else None,
        owner_org_id=host_info["id"] if host_info["type"] == "organisation" else None,
    )

    return jsonify({
        "total_listings": dashboard_data["stats"].get("total_listings", 0),
        "active_listings": dashboard_data["stats"].get("active_listings", 0),
        "pending_review": dashboard_data["stats"].get("pending_review", 0),
        "draft_listings": dashboard_data["stats"].get("draft_listings", 0),
        "total_bookings": dashboard_data.get("total_bookings_count", 0),
        "total_revenue": dashboard_data.get("total_revenue", 0.0),
        "avg_rating": dashboard_data.get("avg_rating", 0.0),
        "total_reviews": dashboard_data.get("total_reviews", 0),
        "avg_response_rate": dashboard_data.get("avg_response_rate", 0),
        "total_views": dashboard_data.get("total_views", 0),
        "conversion_rate": dashboard_data.get("conversion_rate", 0.0),
        "monthly_revenue": dashboard_data.get("monthly_revenue", []),
        "occupancy_rate": dashboard_data["stats"].get("occupancy_rate", 0.0),
    })


@accommodation_bp.route("/host/api/track", methods=['POST'], endpoint="host_api_track")
@login_required
def host_api_track():
    try:
        data = request.get_json(silent=True) or {}
        event_name = data.get('event', 'unknown')
        properties = data.get('properties', {})

        from app.utils.monitoring import track_booking_funnel_event
        track_booking_funnel_event(
            f"host_{event_name}",
            properties
        )
        return jsonify({'ok': True}), 200
    except Exception:
        return jsonify({'ok': False}), 200


@accommodation_bp.route("/host/listings/create", methods=["GET", "POST"], endpoint="host_create_listing")
@login_required
def host_create_listing():
    host_info = _ensure_host_identity()
    if not host_info:
        return redirect(url_for("index"))

    form = PropertyForm()
    _populate_form_choices(form)

    if form.validate_on_submit():
        try:
            HostService.create_property(
                form.data,
                owner_user_id=host_info["id"] if host_info["type"] == "individual" else None,
                owner_org_id=host_info["id"] if host_info["type"] == "organisation" else None,
            )
            db.session.commit()
            flash(
                "Listing submitted for review. We'll notify you once moderation completes.",
                "success",
            )
            return redirect(url_for("accommodation.host_dashboard"))
        except Exception as exc:
            db.session.rollback()
            logger.exception("Failed to create listing")
            flash(f"Could not create listing: {exc}", "danger")

    if request.method == "GET":
        if not form.currency.data:
            form.currency.data = current_app.config.get("DEFAULT_LISTING_CURRENCY", "USD")
        if not form.country.data and getattr(current_user, "profile", None):
            country = (current_user.profile.country or "").strip()
            if country:
                form.country.data = country[:2].upper()

    return render_template(
        "accommodation/host/create_listing.html",
        form=form,
        host_info=host_info,
    )


@accommodation_bp.route("/host/bulk-template", endpoint="host_bulk_template")
@login_required
def host_bulk_template():
    """Download CSV template for bulk property import (organisation hosts only)
    
    Per architecture §8.2: Creates 1 Property + N RoomTypes with total_units count.
    NOT 1000 individual Property rows.
    """
    host_info = _ensure_host_identity()
    if not host_info:
        return redirect(url_for("index"))

    if host_info["type"] != "organisation":
        flash("Bulk import is only available for organisation hosts.", "warning")
        return redirect(url_for("accommodation.host_dashboard"))

    # CSV template with headers - per architecture §8.2
    # Creates: 1 Property + N RoomTypes with total_units count
    csv_content = "location_name,city,country,room_type_name,total_units,base_price_per_night,max_guests,description\n"
    csv_content += "Grand Hotel,Kampala,UG,Deluxe King,50,120,2,Luxury room with king bed\n"
    csv_content += "Grand Hotel,Kampala,UG,Standard Twin,100,85,2,Comfortable twin room\n"
    csv_content += "Grand Hotel,Kampala,UG,Suite,20,200,4,Spacious suite with living area\n"

    from flask import Response
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=afcon360_bulk_properties_template.csv"}
    )


@accommodation_bp.route("/host/listings/<int:property_id>/edit", methods=["GET", "POST"], endpoint="host_edit_listing")
@login_required
def host_edit_listing(property_id: int):
    host_info = _ensure_host_identity()
    if not host_info:
        return redirect(url_for("index"))

    prop = Property.query.get_or_404(property_id)
    if not AccommodationIdentityService.can_manage_property(
        current_user,
        property_owner_user_id=prop.owner_user_id,
        property_owner_org_id=prop.owner_org_id,
    ):
        abort(403)

    form = PropertyForm()
    _populate_form_choices(form)

    if request.method == "GET":
        form.process(
            formdata=None,
            data={
                "title": prop.title,
                "summary": prop.summary,
                "description": prop.description,
                "property_type": enum_value(prop.property_type) if prop.property_type else None,
                "address_line1": prop.address_line1,
                "address_line2": prop.address_line2,
                "city": prop.city,
                "state": prop.state,
                "country": prop.country,
                "postal_code": prop.postal_code,
                "base_price_per_night": prop.base_price_per_night,
                "currency": prop.currency,
                "cleaning_fee": prop.cleaning_fee,
                "service_fee_pct": prop.service_fee_pct,
                "max_guests": prop.max_guests,
                "bedrooms": prop.bedrooms,
                "beds": prop.beds,
                "bathrooms": prop.bathrooms,
                "min_stay_nights": prop.min_stay_nights,
                "max_stay_nights": prop.max_stay_nights,
                "cancellation_policy": prop.cancellation_policy if prop.cancellation_policy else None,
                "check_in_time": prop.check_in_time,
                "check_out_time": prop.check_out_time,
                "instant_book": prop.instant_book,
                "allow_pets": prop.allow_pets,
                "allow_smoking": prop.allow_smoking,
                "allow_events": prop.allow_events,
                "house_rules": prop.house_rules,
                "main_image": prop.main_image,
                "gallery_urls": "\n".join(prop.gallery or []),
                "meta_title": prop.meta_title,
                "meta_description": prop.meta_description,
            },
        )

    if form.validate_on_submit():
        try:
            HostService.update_property(prop, form.data)
            if prop.status in {
                "draft",
                "suspended",
            }:
                prop.status = "pending_review"
            prop.updated_at = datetime.now(timezone.utc)

            db.session.commit()
            flash("Listing updated successfully.", "success")
            return redirect(url_for("accommodation.host_dashboard"))
        except Exception as exc:
            db.session.rollback()
            logger.exception("Failed to update listing")
            flash(f"Could not update listing: {exc}", "danger")

    return render_template(
        "accommodation/host/edit_listing.html",
        form=form,
        property=prop,
        host_info=host_info,
    )


@accommodation_bp.route("/host/calendar", endpoint="host_calendar")
@login_required
def host_calendar():
    host_info = _ensure_host_identity()
    if not host_info:
        return redirect(url_for("index"))
    owner_user_id = host_info["id"] if host_info["type"] == "individual" else None
    owner_org_id = host_info["id"] if host_info["type"] == "organisation" else None

    properties = HostService.get_properties_for_owner(
        owner_user_id=owner_user_id,
        owner_org_id=owner_org_id,
    )

    if not properties:
        flash("Add a property listing before managing availability.", "info")
        return redirect(url_for("accommodation.host_create_listing"))

    month_year = request.args.get("month")
    current_month = _resolve_month(month_year)
    selected_property_id = request.args.get("property_id", type=int) or properties[0]["id"]

    selected_property = next(
        (prop for prop in properties if prop["id"] == selected_property_id),
        properties[0],
    )

    # Optional: scope calendar to a specific room type when multiple exist
    selected_room_type_id = request.args.get("room_type_id", type=int)

    month_start = date(current_month["year"], current_month["month"], 1)
    month_end = date(
        current_month["year"],
        current_month["month"],
        calendar.monthrange(current_month["year"], current_month["month"])[1],
    )

    calendar_payload = HostService.get_property_calendar_snapshot(
        property_id=selected_property["id"],
        start_date=month_start,
        end_date=month_end,
        room_type_id=selected_room_type_id,
    )

    month_label = month_start.strftime("%B %Y")

    return render_template(
        "accommodation/host/calendar.html",
        host_info=host_info,
        properties=properties,
        selected_property_id=selected_property["id"],
        month_context={
            "year": current_month["year"],
            "month": current_month["month"],
            "label": month_label,
        },
        calendar_payload=calendar_payload,
    )


@accommodation_bp.route("/host/calendar/data", methods=["GET"], endpoint="host_calendar_data")
@login_required
def host_calendar_data():
    host_info = _ensure_host_identity()
    if not host_info:
        return jsonify({"error": "Not authorised"}), 403

    property_id = request.args.get("property_id", type=int)
    if not property_id:
        return jsonify({"error": "property_id is required"}), 400

    prop = Property.query.get_or_404(property_id)
    if not AccommodationIdentityService.can_manage_property(
        current_user,
        property_owner_user_id=prop.owner_user_id,
        property_owner_org_id=prop.owner_org_id,
    ):
        return jsonify({"error": "You do not have access to this property"}), 403

    month_year = request.args.get("month")
    month_details = _resolve_month(month_year)
    month_start = date(month_details["year"], month_details["month"], 1)
    month_end = date(
        month_details["year"],
        month_details["month"],
        calendar.monthrange(month_details["year"], month_details["month"])[1],
    )

    payload = HostService.get_property_calendar_snapshot(
        property_id=property_id,
        start_date=month_start,
        end_date=month_end,
    )

    return jsonify(payload)


@accommodation_bp.route("/host/calendar/block", methods=["POST"], endpoint="host_calendar_block")
@login_required
def host_calendar_block():
    host_info = _ensure_host_identity()
    if not host_info:
        return jsonify({"error": "Not authorised"}), 403

    data = request.get_json(silent=True) or {}
    property_id = data.get("property_id")
    if not property_id:
        return jsonify({"error": "property_id is required"}), 400

    prop = Property.query.get_or_404(property_id)
    if not AccommodationIdentityService.can_manage_property(
        current_user,
        property_owner_user_id=prop.owner_user_id,
        property_owner_org_id=prop.owner_org_id,
    ):
        return jsonify({"error": "You do not have access to this property"}), 403

    start_date_raw = data.get("start_date")
    end_date_raw = data.get("end_date", start_date_raw)
    reason_raw = data.get("reason")

    if not start_date_raw:
        return jsonify({"error": "start_date is required"}), 400

    try:
        start_date_obj = date.fromisoformat(start_date_raw)
        end_date_obj = date.fromisoformat(end_date_raw)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    if end_date_obj < start_date_obj:
        return jsonify({"error": "end_date must not be before start_date"}), 400

    if (start_date_obj - date.today()).days < -1:
        return jsonify({"error": "Cannot block dates in the distant past"}), 400

    try:
        from app.accommodation.models.availability import AccommodationBlockedReason
        reason_enum = AccommodationBlockedReason(reason_raw)
    except Exception:
        valid_reasons = ["owner_blocked", "maintenance", "seasonal"]
        return jsonify({"error": f"Invalid reason. Use one of {', '.join(valid_reasons)}"}), 400

    disallowed_reasons = {"booked", "temporary_hold"}
    if reason_enum.value in disallowed_reasons:
        return jsonify({"error": "Reason reserved for system operations"}), 400

    is_available, _, reason = AvailabilityService.is_range_available(
        property_id,
        start_date_obj,
        end_date_obj + timedelta(days=1),
    )
    if not is_available:
        return jsonify({"error": reason or "Dates already reserved"}), 409

    try:
        blocked_count = AvailabilityService.block_dates(
            property_id,
            start_date_obj,
            end_date_obj + timedelta(days=1),
            reason_enum,
            created_by=current_user.id,
        )
    except Exception as exc:
        logger.exception("Failed to block dates")
        return jsonify({"error": f"Failed to block dates: {exc}"}), 500

    return jsonify({
        "message": f"Blocked {blocked_count} night(s)",
        "blocked_count": blocked_count,
    })


@accommodation_bp.route("/host/calendar/unblock", methods=["POST"], endpoint="host_calendar_unblock")
@login_required
def host_calendar_unblock():
    host_info = _ensure_host_identity()
    if not host_info:
        return jsonify({"error": "Not authorised"}), 403

    data = request.get_json(silent=True) or {}
    property_id = data.get("property_id")
    if not property_id:
        return jsonify({"error": "property_id is required"}), 400

    prop = Property.query.get_or_404(property_id)
    if not AccommodationIdentityService.can_manage_property(
        current_user,
        property_owner_user_id=prop.owner_user_id,
        property_owner_org_id=prop.owner_org_id,
    ):
        return jsonify({"error": "You do not have access to this property"}), 403

    start_date_raw = data.get("start_date")
    end_date_raw = data.get("end_date", start_date_raw)

    if not start_date_raw:
        return jsonify({"error": "start_date is required"}), 400

    try:
        start_date_obj = date.fromisoformat(start_date_raw)
        end_date_obj = date.fromisoformat(end_date_raw)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    if end_date_obj < start_date_obj:
        return jsonify({"error": "end_date must not be before start_date"}), 400

    try:
        released = AvailabilityService.unblock_dates(
            property_id,
            start_date_obj,
            end_date_obj + timedelta(days=1),
        )
    except Exception as exc:
        logger.exception("Failed to unblock dates")
        return jsonify({"error": f"Failed to unblock dates: {exc}"}), 500

    return jsonify({
        "message": f"Released {released} night(s)",
        "released_count": released,
    })


@accommodation_bp.route("/host/property/<int:property_id>/manage")
@login_required
@require_module_enabled("accommodation")
def host_property_manage(property_id):
    """Full property management dashboard with rooms, bookings, blocks, and notifications."""
    prop = Property.query.get_or_404(property_id)
    if not AccommodationIdentityService.can_manage_property(
        current_user,
        property_owner_user_id=prop.owner_user_id,
        property_owner_org_id=prop.owner_org_id,
    ):
        abort(403)

    from app.accommodation.models.availability import (
        BlockedDate,
        AccommodationBlockedReason,
    )
    from app.accommodation.models.room import RoomType, InventoryBlock
    from app.accommodation.models.booking import AccommodationBookingStatus
    from datetime import date, timedelta

    room_types = RoomType.query.filter_by(property_id=property_id).all()
    today = date.today()

    # Active bookings
    bookings = (
        AccommodationBooking.query.filter(
            AccommodationBooking.property_id == property_id,
            AccommodationBooking.status.in_(
                [
                    AccommodationBookingStatus.CONFIRMED.value,
                    AccommodationBookingStatus.PENDING.value,
                    AccommodationBookingStatus.PENDING_APPROVAL.value,
                    AccommodationBookingStatus.CHECKED_IN.value,
                ]
            ),
        )
        .order_by(AccommodationBooking.check_in.asc())
        .all()
    )

    # Blocked dates (future only)
    blocked_dates = (
        BlockedDate.query.filter(
            BlockedDate.property_id == property_id,
            BlockedDate.blocked_date >= today,
        )
        .order_by(BlockedDate.blocked_date.asc())
        .all()
    )

    # Temporary holds
    temp_holds = (
        BlockedDate.query.filter(
            BlockedDate.property_id == property_id,
            BlockedDate.reason == AccommodationBlockedReason.TEMPORARY_HOLD.value,
            BlockedDate.blocked_date >= today,
        )
        .order_by(BlockedDate.blocked_date.asc())
        .all()
    )

    # Inventory blocks (room-type level)
    inventory_blocks = (
        InventoryBlock.query.filter(
            InventoryBlock.room_type_id.in_([rt.id for rt in room_types]),
            InventoryBlock.date_range_end >= today,
        )
        .all()
    )

    # Recent history
    history = (
        AccommodationBooking.query.filter(
            AccommodationBooking.property_id == property_id,
            AccommodationBooking.status.in_(
                [
                    AccommodationBookingStatus.CHECKED_OUT.value,
                    AccommodationBookingStatus.CANCELLED.value,
                ]
            ),
        )
        .order_by(AccommodationBooking.check_out.desc())
        .limit(10)
        .all()
    )

    # Occupancy stats
    total_rooms = sum(rt.total_units for rt in room_types)
    booked_rooms = 0
    for rt in room_types:
        booked_rooms += AccommodationBooking.query.filter(
            AccommodationBooking.room_type_id == rt.id,
            AccommodationBooking.check_in <= today,
            AccommodationBooking.check_out > today,
            AccommodationBooking.status.in_(
                [
                    AccommodationBookingStatus.CONFIRMED.value,
                    AccommodationBookingStatus.CHECKED_IN.value,
                ]
            ),
        ).count()
    occupancy_rate = round((booked_rooms / total_rooms * 100), 1) if total_rooms > 0 else 0

    # Notifications
    notifications = _generate_property_notifications(prop, bookings, today)

    return render_template(
        "accommodation/host/property_manage.html",
        property=prop,
        room_types=room_types,
        bookings=bookings,
        blocked_dates=blocked_dates,
        temp_holds=temp_holds,
        inventory_blocks=inventory_blocks,
        notifications=notifications,
        history=history,
        occupancy_rate=occupancy_rate,
        total_rooms=total_rooms,
        booked_rooms=booked_rooms,
        today=today,
    )


@accommodation_bp.route(
    "/host/property/<int:property_id>/room/<int:room_type_id>/availability"
)
@login_required
@require_module_enabled("accommodation")
def host_room_availability(property_id, room_type_id):
    """Room-type availability calendar for the property management dashboard."""
    prop = Property.query.get_or_404(property_id)
    room_type = RoomType.query.get_or_404(room_type_id)

    if not AccommodationIdentityService.can_manage_property(
        current_user,
        property_owner_user_id=prop.owner_user_id,
        property_owner_org_id=prop.owner_org_id,
    ):
        abort(403)

    if room_type.property_id != property_id:
        abort(404)

    start_date = date.today()
    end_date = start_date + timedelta(days=90)

    calendar_data = HostService.get_property_calendar_snapshot(
        property_id=property_id,
        start_date=start_date,
        end_date=end_date,
        room_type_id=room_type_id,
    )

    return render_template(
        "accommodation/host/room_availability.html",
        property=prop,
        room_type=room_type,
        calendar_data=calendar_data,
        start_date=start_date,
        end_date=end_date,
    )


@accommodation_bp.route("/host/property/<int:property_id>/block-date", methods=["POST"])
@login_required
@require_module_enabled("accommodation")
def host_block_date(property_id):
    """Block a single date or date range for a property."""
    prop = Property.query.get_or_404(property_id)
    if not AccommodationIdentityService.can_manage_property(
        current_user,
        property_owner_user_id=prop.owner_user_id,
        property_owner_org_id=prop.owner_org_id,
    ):
        abort(403)

    date_range_start = request.form.get("date_range_start")
    date_range_end = request.form.get("date_range_end")
    reason = request.form.get("reason", "OWNER_BLOCKED")
    room_type_id = request.form.get("room_type_id")

    if not date_range_start:
        flash("Start date is required.", "danger")
        return redirect(
            url_for("accommodation.host_property_manage", property_id=property_id)
        )

    try:
        start = date.fromisoformat(date_range_start)
        end = date.fromisoformat(date_range_end) if date_range_end else start
    except ValueError:
        flash("Invalid date format.", "danger")
        return redirect(
            url_for("accommodation.host_property_manage", property_id=property_id)
        )

    if end < start:
        flash("End date must not be before start date.", "danger")
        return redirect(
            url_for("accommodation.host_property_manage", property_id=property_id)
        )

    # Validate reason
    try:
        AccommodationBlockedReason(reason)
    except ValueError:
        flash("Invalid block reason.", "danger")
        return redirect(
            url_for("accommodation.host_property_manage", property_id=property_id)
        )

    rt_id = int(room_type_id) if room_type_id else None

    blocked_count = 0
    current_date = start
    while current_date <= end:
        existing = BlockedDate.query.filter_by(
            property_id=property_id, blocked_date=current_date
        ).first()
        if not existing:
            blocked = BlockedDate(
                property_id=property_id,
                blocked_date=current_date,
                reason=reason,
                created_by=current_user.id,
                note=f"Blocked by host: {reason}",
                room_type_id=rt_id,
            )
            db.session.add(blocked)
            blocked_count += 1
        current_date += timedelta(days=1)

    db.session.commit()
    flash(f"Successfully blocked {blocked_count} date(s).", "success")
    return redirect(
        url_for("accommodation.host_property_manage", property_id=property_id)
    )


@accommodation_bp.route(
    "/host/property/<int:property_id>/unblock-date/<int:block_id>", methods=["POST"]
)
@login_required
@require_module_enabled("accommodation")
def host_unblock_date(property_id, block_id):
    """Release/unblock a blocked date."""
    prop = Property.query.get_or_404(property_id)
    if not AccommodationIdentityService.can_manage_property(
        current_user,
        property_owner_user_id=prop.owner_user_id,
        property_owner_org_id=prop.owner_org_id,
    ):
        abort(403)

    blocked = BlockedDate.query.get_or_404(block_id)
    if blocked.property_id != property_id:
        abort(404)

    if blocked.reason == AccommodationBlockedReason.BOOKED.value:
        flash("Cannot unblock a date that is booked.", "warning")
        return redirect(
            url_for("accommodation.host_property_manage", property_id=property_id)
        )

    db.session.delete(blocked)
    db.session.commit()
    flash("Date unblocked successfully.", "success")
    return redirect(
        url_for("accommodation.host_property_manage", property_id=property_id)
    )


@accommodation_bp.route(
    "/host/property/<int:property_id>/booking/<int:booking_id>/cancel", methods=["POST"]
)
@login_required
@require_module_enabled("accommodation")
def host_cancel_booking(property_id, booking_id):
    """Cancel a booking (host/admin override)."""
    prop = Property.query.get_or_404(property_id)
    booking = AccommodationBooking.query.get_or_404(booking_id)

    if not AccommodationIdentityService.can_manage_property(
        current_user,
        property_owner_user_id=prop.owner_user_id,
        property_owner_org_id=prop.owner_org_id,
    ):
        abort(403)

    if booking.property_id != property_id:
        abort(404)

    reason = request.form.get("reason", "Host cancellation")

    success, error, refund = BookingService.cancel_booking(
        booking.id,
        cancelled_by_user_id=current_user.id,
        reason=reason,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
    )

    next_url = request.form.get("next") or url_for(
        "accommodation.host_property_manage", property_id=property_id
    )

    if not success:
        flash(error or "Booking could not be cancelled.", "danger")
        return redirect(next_url)

    outcome = (booking.policy_snapshot or {}).get("cancellation_outcome", {})
    refund_msg = f" Refund due: {refund}." if refund else " No refund due."
    fine = outcome.get("fine")
    if fine and Decimal(fine) > 0:
        refund_msg += f" Cancellation fine withheld: {fine}."
    flash(f"Booking #{booking.booking_reference} cancelled.{refund_msg}", "warning")
    return redirect(next_url)


def _generate_property_notifications(property_obj, bookings, today):
    """Generate notification items for the property dashboard."""
    notifications = []
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    # Today's check-ins
    for b in bookings:
        if b.check_in == today:
            notifications.append(
                {
                    "type": "checkin_today",
                    "priority": "critical",
                    "icon": "bi bi-door-open",
                    "title": "Check-in TODAY!",
                    "message": f"{b.guest_name} is checking in today",
                    "booking_id": b.id,
                    "guest_name": b.guest_name,
                    "time": b.check_in.strftime("%b %d, %Y"),
                }
            )

    # Today's check-outs
    for b in bookings:
        if b.check_out == today:
            notifications.append(
                {
                    "type": "checkout_today",
                    "priority": "critical",
                    "icon": "bi bi-box-arrow-right",
                    "title": "Check-out TODAY!",
                    "message": f"{b.guest_name} is checking out today",
                    "booking_id": b.id,
                    "guest_name": b.guest_name,
                    "time": b.check_out.strftime("%b %d, %Y"),
                }
            )

    # Upcoming check-ins (next 3 days)
    for b in bookings:
        if b.check_in and b.check_in > today and (b.check_in - today).days <= 3:
            days_until = (b.check_in - today).days
            notifications.append(
                {
                    "type": "checkin",
                    "priority": "high" if days_until <= 1 else "medium",
                    "icon": "bi bi-calendar-event",
                    "title": f"Check-in in {days_until} day(s)",
                    "message": f"{b.guest_name} arrives on {b.check_in.strftime('%b %d, %Y')}",
                    "booking_id": b.id,
                    "guest_name": b.guest_name,
                    "time": b.check_in.strftime("%b %d, %Y"),
                }
            )

    # Upcoming check-outs (next 2 days)
    for b in bookings:
        if (
            b.check_out
            and b.check_out > today
            and (b.check_out - today).days <= 2
        ):
            days_until = (b.check_out - today).days
            notifications.append(
                {
                    "type": "checkout",
                    "priority": "medium",
                    "icon": "bi bi-box-arrow-left",
                    "title": f"Check-out in {days_until} day(s)",
                    "message": f"{b.guest_name} departs on {b.check_out.strftime('%b %d, %Y')}",
                    "booking_id": b.id,
                    "guest_name": b.guest_name,
                    "time": b.check_out.strftime("%b %d, %Y"),
                }
            )

    # Low availability warnings
    for rt in property_obj.room_types:
        available = rt.available_units
        if available == 0:
            notifications.append(
                {
                    "type": "sold_out",
                    "priority": "high",
                    "icon": "bi bi-fire",
                    "title": f"Sold out: {rt.name}",
                    "message": f"{rt.name} is fully booked",
                    "room_type_id": rt.id,
                    "room_type_name": rt.name,
                }
            )
        elif available <= 2:
            notifications.append(
                {
                    "type": "low_availability",
                    "priority": "medium",
                    "icon": "bi bi-exclamation-triangle",
                    "title": f"Low availability: {rt.name}",
                    "message": f"Only {available} unit(s) available",
                    "room_type_id": rt.id,
                    "room_type_name": rt.name,
                }
            )

    notifications.sort(key=lambda x: priority_order.get(x.get("priority", "low"), 4))
    return notifications[:10]


@accommodation_bp.route("/host/bookings", endpoint="host_bookings")
@login_required
def host_bookings():
    host_info = _ensure_host_identity()
    if not host_info:
        return redirect(url_for("index"))

    booking_type = request.args.get('type', '').strip()
    status_filter = request.args.get('status', '').strip()
    reg_filter = request.args.get('reg_status', '').strip()

    query = AccommodationBooking.query.join(Property, AccommodationBooking.property_id == Property.id)
    if host_info["type"] == "individual":
        query = query.filter(Property.owner_user_id == host_info["id"])
    else:
        query = query.filter(Property.owner_org_id == host_info["id"])

    if booking_type:
        query = query.filter(AccommodationBooking.booking_type == booking_type)
    if status_filter:
        query = query.filter(AccommodationBooking.status == status_filter)

    bookings = query.order_by(AccommodationBooking.created_at.desc()).limit(200).all()

    # Filter by registration status if requested
    if reg_filter == 'complete':
        bookings = [b for b in bookings if b.guest_registrations and all(
            r.status in ('completed', 'skipped') for r in b.guest_registrations
        )]
    elif reg_filter == 'incomplete':
        bookings = [b for b in bookings if not b.guest_registrations or any(
            r.status not in ('completed', 'skipped') for r in b.guest_registrations
        )]

    return render_template(
        "accommodation/host/bookings.html",
        host_info=host_info,
        bookings=bookings,
        current_type=booking_type,
        current_status=status_filter,
        current_reg=reg_filter,
    )


@accommodation_bp.route('/host/booking/<int:booking_id>', endpoint='host_booking_detail')
@login_required
def host_booking_detail(booking_id):
    """Host view of a single booking with guest info and payout."""
    from app.accommodation.models.commission import BookingCommission
    from app.accommodation.services.identity_service import AccommodationIdentityService

    booking = AccommodationBooking.query.get_or_404(booking_id)
    prop = Property.query.get_or_404(booking.property_id)
    host_info = _ensure_host_identity()
    if not host_info or not AccommodationIdentityService.can_manage_property(current_user, prop.owner_user_id, prop.owner_org_id):
        flash("You do not have permission to view this booking.", "danger")
        return redirect(url_for("accommodation.host_bookings"))

    commission = BookingCommission.query.filter_by(booking_id=booking_id).first()
    property_data = search_service.get_property_by_identifier(str(booking.property_id))

    # Booking Pass QR so the host can scan/verify the guest's pass at check-in.
    from app.utils.url import absolute_url_for
    from app.utils.qr import qr_data_uri
    pass_url = ''
    qr_uri = ''
    try:
        pass_url = absolute_url_for('accommodation.guest_pass', reference=booking.booking_reference)
        qr_uri = qr_data_uri(pass_url, box_size=8, border=4)
    except Exception:
        qr_uri = ''

    return render_template(
        "accommodation/host/booking_detail.html",
        booking=booking,
        property=property_data,
        commission=commission,
        qr_uri=qr_uri,
        pass_url=pass_url,
    )


@accommodation_bp.route('/host/booking/<int:booking_id>/check-in', methods=['POST'], endpoint='host_check_in')
@login_required
@limiter.limit("20 per minute")
def host_check_in(booking_id):
    host_info = _ensure_host_identity()
    if not host_info:
        return redirect(url_for('index'))
    adjust_checkin = request.form.get('adjust_checkin_to_today', 'false').lower() == 'true'
    success, error, adjust_info = BookingService.check_in(
        booking_id, current_user.id, adjust_checkin_to_today=adjust_checkin
    )
    if success:
        payout_success, payout_error = MarketplaceService.release_host_payout(booking_id)
        if payout_success:
            msg = 'Guest checked in successfully. Payout released.'
            if adjust_info:
                msg += ' Check-in date adjusted to today.'
            flash(msg, 'success')
        else:
            flash(f'Guest checked in, but payout failed: {payout_error}', 'warning')
    else:
        if error and 'already checked in' in error.lower():
            flash(error, 'warning')
        else:
            flash(error or 'Check-in failed.', 'danger')
    return redirect(url_for('accommodation.host_booking_detail', booking_id=booking_id))

@accommodation_bp.route('/host/booking/<int:booking_id>/check-out', methods=['POST'], endpoint='host_check_out')
@login_required
@limiter.limit("20 per minute")
def host_check_out(booking_id):
    host_info = _ensure_host_identity()
    if not host_info:
        return redirect(url_for('index'))
    adjust_checkout = request.form.get('adjust_checkout_to_today', 'false').lower() == 'true'
    success, error, adjust_info = BookingService.check_out(
        booking_id, current_user.id, adjust_checkout_to_today=adjust_checkout
    )
    if success:
        msg = 'Guest checked out successfully.'
        if adjust_info:
            msg += ' Check-out date adjusted to today; refund for unused nights pending.'
        flash(msg, 'success')
    else:
        flash(error or 'Check-out failed.', 'danger')
    return redirect(url_for('accommodation.host_booking_detail', booking_id=booking_id))


@accommodation_bp.route('/host/booking/<int:booking_id>/modify-dates', methods=['POST'], endpoint='host_modify_booking_dates')
@login_required
@limiter.limit("20 per minute")
def host_modify_booking_dates(booking_id):
    """Host modifies a booking's check-in and/or check-out dates."""
    from app.accommodation.services.identity_service import AccommodationIdentityService
    from app.accommodation.models.booking_price_adjustment import PriceAdjustmentType
    from datetime import datetime as _dt

    booking = AccommodationBooking.query.get_or_404(booking_id)
    prop = Property.query.get_or_404(booking.property_id)
    host_info = _ensure_host_identity()
    if not host_info or not AccommodationIdentityService.can_manage_property(
        current_user, prop.owner_user_id, prop.owner_org_id
    ):
        flash("You do not have permission to modify this booking's dates.", "danger")
        return redirect(url_for("accommodation.host_bookings"))

    new_check_in_str = request.form.get('new_check_in', '').strip()
    new_check_out_str = request.form.get('new_check_out', '').strip()
    reason = request.form.get('reason', '').strip() or None
    notify_guest = request.form.get('notify_guest', 'true').lower() == 'true'

    new_check_in = None
    new_check_out = None
    try:
        if new_check_in_str:
            new_check_in = _dt.strptime(new_check_in_str, '%Y-%m-%d').date()
        if new_check_out_str:
            new_check_out = _dt.strptime(new_check_out_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        flash('Invalid date format. Please use YYYY-MM-DD.', 'danger')
        return redirect(url_for('accommodation.host_booking_detail', booking_id=booking_id))

    if not new_check_in and not new_check_out:
        flash('Please provide at least one new date (check-in or check-out).', 'info')
        return redirect(url_for('accommodation.host_booking_detail', booking_id=booking_id))

    success, error, result = BookingService.modify_booking_dates(
        booking_id=booking.id,
        host_user_id=current_user.id,
        new_check_in=new_check_in,
        new_check_out=new_check_out,
        reason=reason,
        notify_guest=notify_guest,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
    )

    if success:
        msg = 'Booking dates modified successfully.'
        if result:
            delta = result.get('delta_amount', '0')
            refund = result.get('refund_amount', '0')
            owed = result.get('amount_owed', '0')
            if str(delta) != '0':
                msg += f' Price adjustment: {delta}.'
            if str(refund) != '0' and str(refund) != '0.00':
                msg += f' Refund of {refund} pending.'
            if str(owed) != '0' and str(owed) != '0.00':
                msg += f' Amount owed: {owed}.'
            if notify_guest:
                msg += ' Guest notified.'
        flash(msg, 'success')
    else:
        flash(error or 'Failed to modify booking dates.', 'danger')
    return redirect(url_for('accommodation.host_booking_detail', booking_id=booking_id))


@accommodation_bp.route('/host/booking/<int:booking_id>/refund', methods=['POST'], endpoint='host_refund_booking')
@login_required
@limiter.limit("10 per minute")
def host_refund_booking(booking_id):
    """Issue a refund for a booking."""
    from app.accommodation.models.commission import BookingCommission
    from app.accommodation.services.identity_service import AccommodationIdentityService
    from decimal import Decimal

    booking = AccommodationBooking.query.get_or_404(booking_id)
    prop = Property.query.get_or_404(booking.property_id)
    host_info = _ensure_host_identity()
    if not host_info or not AccommodationIdentityService.can_manage_property(current_user, prop.owner_user_id, prop.owner_org_id):
        flash("You do not have permission to refund this booking.", "danger")
        return redirect(url_for("accommodation.host_bookings"))

    refund_amount = Decimal(request.form.get('refund_amount', '0'))
    reason = request.form.get('reason', 'Host issued refund')

    if refund_amount <= 0:
        flash("Refund amount must be greater than zero.", "warning")
        return redirect(url_for("accommodation.host_booking_detail", booking_id=booking_id))

    if refund_amount > booking.total_amount:
        flash("Refund amount cannot exceed booking total.", "warning")
        return redirect(url_for("accommodation.host_booking_detail", booking_id=booking_id))

    success, error = MarketplaceService.refund_guest(booking_id, refund_amount)
    if success:
        flash(f"Refund of ${refund_amount} processed successfully.", "success")
    else:
        flash(f"Refund failed: {error}", "danger")

    return redirect(url_for("accommodation.host_booking_detail", booking_id=booking_id))


@accommodation_bp.route('/host/booking/<int:booking_id>/approve', methods=['POST'], endpoint='host_approve_booking')
@login_required
@limiter.limit("10 per minute")
def host_approve_booking(booking_id):
    """Approve a booking that is pending host approval."""
    from app.accommodation.services.identity_service import AccommodationIdentityService

    booking = AccommodationBooking.query.get_or_404(booking_id)
    prop = Property.query.get_or_404(booking.property_id)
    host_info = _ensure_host_identity()
    if not host_info or not AccommodationIdentityService.can_manage_property(current_user, prop.owner_user_id, prop.owner_org_id):
        flash("You do not have permission to approve this booking.", "danger")
        return redirect(url_for("accommodation.host_bookings"))

    reason = request.form.get('reason', 'Approved by host')
    success, error = BookingService.approve_booking(
        booking_id=booking_id,
        approved_by_user_id=current_user.id,
        reason=reason,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
    )
    if success:
        flash("Booking approved successfully.", "success")
    else:
        flash(f"Failed to approve booking: {error}", "danger")
    return redirect(url_for("accommodation.host_bookings"))


@accommodation_bp.route('/host/booking/<int:booking_id>/reject', methods=['POST'], endpoint='host_reject_booking')
@login_required
@limiter.limit("10 per minute")
def host_reject_booking(booking_id):
    """Reject a booking that is pending host approval."""
    from app.accommodation.services.identity_service import AccommodationIdentityService

    booking = AccommodationBooking.query.get_or_404(booking_id)
    prop = Property.query.get_or_404(booking.property_id)
    host_info = _ensure_host_identity()
    if not host_info or not AccommodationIdentityService.can_manage_property(current_user, prop.owner_user_id, prop.owner_org_id):
        flash("You do not have permission to reject this booking.", "danger")
        return redirect(url_for("accommodation.host_bookings"))

    reason = request.form.get('reason', 'Rejected by host')
    success, error = BookingService.reject_booking(
        booking_id=booking_id,
        rejected_by_user_id=current_user.id,
        reason=reason,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
    )
    if success:
        flash("Booking rejected.", "warning")
    else:
        flash(f"Failed to reject booking: {error}", "danger")
    return redirect(url_for("accommodation.host_bookings"))


@accommodation_bp.route('/host/property/<int:property_id>/rooms', endpoint='host_rooms')
@login_required
def host_rooms(property_id):
    host_info = _ensure_host_identity()
    if not host_info:
        return redirect(url_for('index'))

    prop = Property.query.get_or_404(property_id)
    if not AccommodationIdentityService.can_manage_property(
        current_user,
        property_owner_user_id=prop.owner_user_id,
        property_owner_org_id=prop.owner_org_id,
    ):
        abort(403)

    room_types = RoomType.query.filter_by(property_id=property_id).order_by(
        RoomType.name.asc()
    ).all()

    for room_type in room_types:
        room_type.rooms_sorted = sorted(
            room_type.rooms,
            key=lambda r: (len(r.room_number), r.room_number)
        )

    return render_template(
        'accommodation/host/rooms.html',
        property=prop,
        room_types=room_types,
        host_info=host_info,
    )


@accommodation_bp.route('/host/property/<int:property_id>/rooms/type', methods=['POST'], endpoint='host_room_type_add')
@login_required
def host_room_type_add(property_id):
    host_info = _ensure_host_identity()
    if not host_info:
        return redirect(url_for('index'))

    prop = Property.query.get_or_404(property_id)
    if not AccommodationIdentityService.can_manage_property(
        current_user,
        property_owner_user_id=prop.owner_user_id,
        property_owner_org_id=prop.owner_org_id,
    ):
        abort(403)

    try:
        name = request.form.get('name', '').strip()
        if not name:
            flash('Room type name is required.', 'danger')
            return redirect(url_for('accommodation.host_rooms', property_id=property_id))

        room_type = RoomType(
            property_id=property_id,
            name=name,
            description=request.form.get('description', '').strip() or None,
            short_code=request.form.get('short_code', '').strip() or None,
            max_guests=int(request.form.get('max_guests', 2) or 2),
            bedrooms=int(request.form.get('bedrooms', 1) or 1),
            beds=int(request.form.get('beds', 1) or 1),
            bathrooms=int(request.form.get('bathrooms', 1) or 1),
            base_price_per_night=Decimal(request.form.get('base_price_per_night', '0') or '0'),
            currency=request.form.get('currency', prop.currency or 'USD'),
            cleaning_fee=Decimal(request.form.get('cleaning_fee', '0') or '0'),
            is_active=request.form.get('is_active') != 'off',
        )
        db.session.add(room_type)
        db.session.commit()
        flash(f'Room type "{name}" created.', 'success')
        HostService.sync_room_type_inventory(property_id)
    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to create room type')
        flash(f'Failed to create room type: {str(e)}', 'danger')

    return redirect(url_for('accommodation.host_rooms', property_id=property_id))


@accommodation_bp.route('/host/room-type/<int:room_type_id>/edit', methods=['POST'], endpoint='host_room_type_edit')
@login_required
def host_room_type_edit(room_type_id):
    host_info = _ensure_host_identity()
    if not host_info:
        return redirect(url_for('index'))

    room_type = RoomType.query.get_or_404(room_type_id)
    prop = Property.query.get_or_404(room_type.property_id)
    if not AccommodationIdentityService.can_manage_property(
        current_user,
        property_owner_user_id=prop.owner_user_id,
        property_owner_org_id=prop.owner_org_id,
    ):
        abort(403)

    try:
        room_type.name = request.form.get('name', room_type.name).strip()
        room_type.description = request.form.get('description', '') or None
        room_type.short_code = request.form.get('short_code', '') or None
        room_type.max_guests = int(request.form.get('max_guests', room_type.max_guests) or 2)
        room_type.bedrooms = int(request.form.get('bedrooms', room_type.bedrooms) or 1)
        room_type.beds = int(request.form.get('beds', room_type.beds) or 1)
        room_type.bathrooms = int(request.form.get('bathrooms', room_type.bathrooms) or 1)
        room_type.base_price_per_night = Decimal(request.form.get('base_price_per_night', room_type.base_price_per_night) or '0')
        room_type.currency = request.form.get('currency', room_type.currency or 'USD')
        room_type.cleaning_fee = Decimal(request.form.get('cleaning_fee', room_type.cleaning_fee) or '0')
        room_type.is_active = request.form.get('is_active') != 'off'
        db.session.commit()
        flash('Room type updated.', 'success')
        HostService.sync_room_type_inventory(prop.id)
    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to update room type')
        flash(f'Failed to update room type: {str(e)}', 'danger')

    return redirect(url_for('accommodation.host_rooms', property_id=prop.id))


@accommodation_bp.route('/host/property/<int:property_id>/rooms/add', methods=['POST'], endpoint='host_room_add')
@login_required
def host_room_add(property_id):
    host_info = _ensure_host_identity()
    if not host_info:
        return redirect(url_for('index'))

    prop = Property.query.get_or_404(property_id)
    if not AccommodationIdentityService.can_manage_property(
        current_user,
        property_owner_user_id=prop.owner_user_id,
        property_owner_org_id=prop.owner_org_id,
    ):
        abort(403)

    room_type_id = request.form.get('room_type_id')
    room_type = RoomType.query.get_or_404(int(room_type_id)) if room_type_id else None
    if not room_type or room_type.property_id != property_id:
        flash('Valid room type is required.', 'danger')
        return redirect(url_for('accommodation.host_rooms', property_id=property_id))

    raw_numbers = request.form.get('room_numbers', '').strip()
    prefix = request.form.get('room_prefix', '').strip()
    floor = request.form.get('floor', '').strip() or None
    name = request.form.get('name', '').strip() or None
    notes = request.form.get('notes', '').strip() or None

    numbers = [n.strip() for n in raw_numbers.replace('\n', ',').split(',') if n.strip()]

    created = 0
    try:
        for num in numbers:
            room_number = f"{prefix}{num}" if prefix else num
            existing = Room.query.filter_by(
                property_id=property_id, room_number=room_number
            ).first()
            if existing:
                continue
            room = Room(
                property_id=property_id,
                room_type_id=room_type.id,
                room_number=room_number,
                floor=floor,
                name=name,
                notes=notes,
                status='available',
                is_maintenance=False,
            )
            db.session.add(room)
            created += 1
        db.session.commit()
        if created:
            flash(f'{created} room(s) added to "{room_type.name}".', 'success')
        else:
            flash('No new rooms created (duplicates skipped).', 'warning')
        HostService.sync_room_type_inventory(property_id)
    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to add rooms')
        flash(f'Failed to add rooms: {str(e)}', 'danger')

    return redirect(url_for('accommodation.host_rooms', property_id=property_id))


@accommodation_bp.route('/host/room/<int:room_id>/maintenance', methods=['POST'], endpoint='host_room_maintenance')
@login_required
def host_room_maintenance(room_id):
    host_info = _ensure_host_identity()
    if not host_info:
        return redirect(url_for('index'))

    room = Room.query.get_or_404(room_id)
    prop = Property.query.get_or_404(room.property_id)
    if not AccommodationIdentityService.can_manage_property(
        current_user,
        property_owner_user_id=prop.owner_user_id,
        property_owner_org_id=prop.owner_org_id,
    ):
        abort(403)

    try:
        if request.form.get('action') == 'release':
            room.release_from_maintenance()
            flash(f'Room {room.room_number} taken out of maintenance.', 'success')
        else:
            reason = request.form.get('maintenance_reason', 'Maintenance')
            room.set_maintenance(reason)
            flash(f'Room {room.room_number} set to maintenance.', 'warning')
        db.session.commit()
        HostService.sync_room_type_inventory(prop.id)
    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to update room maintenance')
        flash(f'Failed to update room: {str(e)}', 'danger')

    return redirect(url_for('accommodation.host_rooms', property_id=prop.id))


@accommodation_bp.route('/host/room/<int:room_id>/delete', methods=['POST'], endpoint='host_room_delete')
@login_required
def host_room_delete(room_id):
    host_info = _ensure_host_identity()
    if not host_info:
        return redirect(url_for('index'))

    room = Room.query.get_or_404(room_id)
    prop = Property.query.get_or_404(room.property_id)
    if not AccommodationIdentityService.can_manage_property(
        current_user,
        property_owner_user_id=prop.owner_user_id,
        property_owner_org_id=prop.owner_org_id,
    ):
        abort(403)

    if not room.is_available:
        flash(f'Cannot delete room {room.room_number}: it is currently assigned/maintenance.', 'danger')
        return redirect(url_for('accommodation.host_rooms', property_id=prop.id))

    try:
        db.session.delete(room)
        db.session.commit()
        flash(f'Room {room.room_number} deleted.', 'success')
        HostService.sync_room_type_inventory(prop.id)
    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to delete room')
        flash(f'Failed to delete room: {str(e)}', 'danger')

    return redirect(url_for('accommodation.host_rooms', property_id=prop.id))


# ============================================================================
# ADMIN ROUTES (URL prefix: /admin)
# ============================================================================

@accommodation_bp.route("/admin/main-dashboard", endpoint="admin_main_dashboard")
@login_required
def admin_admin_dashboard():
    """Admin main dashboard for accommodation module"""
    if not can(current_user, "accommodation.manage"):
        flash("Insufficient permissions", "danger")
        return redirect(url_for('index'))
    stats = HostService.get_admin_dashboard_stats()
    return render_template("admin/accommodation_admin_dashboard.html", **stats)


@accommodation_bp.route("/admin/listings", endpoint="admin_listings")
@login_required
def admin_listings():
    """Manage all property listings"""
    if not can(current_user, "accommodation.manage"):
        flash("Insufficient permissions", "danger")
        return redirect(url_for('index'))
    return render_template("accommodation/admin/listings.html")


@accommodation_bp.route("/admin/hosts", endpoint="admin_hosts")
@login_required
def admin_hosts():
    """Manage hosts (verify, suspend)"""
    if not can(current_user, "accommodation.verify_host"):
        flash("Insufficient permissions", "danger")
        return redirect(url_for('index'))
    return render_template("accommodation/admin/hosts.html")


@accommodation_bp.route("/admin/financials/reconciliation", endpoint="admin_financial_reconciliation")
@login_required
def admin_financial_reconciliation():
    """Platform financial reconciliation — payouts, commissions, refunds."""
    from app.accommodation.models.commission import BookingCommission
    from sqlalchemy import func

    if not can(current_user, "accommodation.manage"):
        flash("Insufficient permissions", "danger")
        return redirect(url_for('index'))

    stats = db.session.query(
        func.sum(BookingCommission.total_amount).label('total_booked'),
        func.sum(BookingCommission.commission_amount).label('total_commission'),
        func.sum(BookingCommission.host_payout).label('total_host_payout'),
        func.sum(BookingCommission.refund_amount).label('total_refunded'),
    ).first()

    recent_commissions = BookingCommission.query.order_by(BookingCommission.created_at.desc()).limit(50).all()

    return render_template(
        "accommodation/admin/financials.html",
        stats=stats,
        recent_commissions=recent_commissions,
    )


@accommodation_bp.route("/admin/moderate", endpoint="admin_moderate")
@login_required
@require_moderator
def admin_moderate():
    """Show accommodation items needing moderation"""
    pending_properties = Property.query.filter_by(status="pending_review").all()
    pending_bookings = AccommodationBooking.query.filter_by(status='pending').all()
    pending_reviews = Review.query.filter_by(status="pending").all()
    
    return render_template('accommodation/moderate.html', properties=pending_properties, bookings=pending_bookings, reviews=pending_reviews)


@accommodation_bp.route("/admin/moderate/property/<int:id>", endpoint="admin_moderate_property")
@login_required
@require_moderator
def admin_moderate_property(id):
    """Show single property for moderation review"""
    property_obj = Property.query.get_or_404(id)
    return render_template(
        'accommodation/moderate_property.html',
        **_moderate_property_template_context(property_obj)
    )


@accommodation_bp.route("/admin/moderate/booking/<int:id>", endpoint="admin_moderate_booking")
@login_required
@require_moderator
def admin_moderate_booking(id):
    """Show single booking for moderation review"""
    booking = AccommodationBooking.query.get_or_404(id)
    return render_template('accommodation/moderate_booking.html', booking=booking)


@accommodation_bp.route("/admin/moderate/review/<int:id>", endpoint="admin_moderate_review")
@login_required
@require_moderator
def admin_moderate_review(id):
    """Show single review for moderation review"""
    review = Review.query.get_or_404(id)
    return render_template('accommodation/moderate_review.html', review=review)


@accommodation_bp.route("/admin/moderate/<entity_type>/<int:id>/<action>", methods=['POST'], endpoint="admin_moderate_action")
@login_required
@require_moderator
def admin_moderate_action(entity_type, id, action):
    """Approve, reject, or flag accommodation items"""
    if entity_type == 'property':
        item = Property.query.get_or_404(id)
        redirect_url = url_for('accommodation.admin_moderate_property', id=id)
    elif entity_type == 'booking':
        item = AccommodationBooking.query.get_or_404(id)
        redirect_url = url_for('accommodation.admin_moderate_booking', id=id)
    elif entity_type == 'review':
        item = Review.query.get_or_404(id)
        redirect_url = url_for('accommodation.admin_moderate_review', id=id)
    else:
        flash('Invalid entity type.', 'danger')
        return redirect(url_for('accommodation.admin_moderate'))

    if action == 'approve':
        if entity_type == 'property':
            item.status = "active"
            item.is_verified = True
            item.verified_at = datetime.now(timezone.utc)
            item.verified_by = current_user.id
            db.session.commit()
            flash(f'{entity_type.capitalize()} approved successfully.', 'success')
        elif entity_type == 'booking':
            reason_text = request.form.get('reason', 'Approved by moderator').strip()
            success, error = BookingService.approve_booking(
                booking_id=id,
                approved_by_user_id=current_user.id,
                reason=reason_text,
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            if not success:
                flash(f'Approval failed: {error}', 'danger')
                return redirect(redirect_url)
            db.session.expire_all()
            flash('Booking approved successfully.', 'success')
        elif entity_type == 'review':
            item.status = "approved"
            item.is_published = True
            item.published_at = datetime.now(timezone.utc)
            item.moderated_by = current_user.id
            item.moderated_at = datetime.now(timezone.utc)
            db.session.commit()
            flash(f'{entity_type.capitalize()} approved successfully.', 'success')

    elif action == 'reject':
        reason = request.form.get('reason', '').strip()
        if not reason:
            flash('Rejection reason is required.', 'warning')
            return redirect(redirect_url)

        if entity_type == 'property':
            item.status = "suspended"
            item.verification_notes = reason
            db.session.commit()
            flash(f'{entity_type.capitalize()} rejected successfully.', 'success')
        elif entity_type == 'booking':
            reason_text = reason or 'Rejected by moderator'
            success, error = BookingService.reject_booking(
                booking_id=id,
                rejected_by_user_id=current_user.id,
                reason=reason_text,
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            if not success:
                flash(f'Rejection failed: {error}', 'danger')
                return redirect(redirect_url)
            flash('Booking rejected successfully.', 'warning')
        elif entity_type == 'review':
            item.status = "rejected"
            item.moderation_reason = reason
            item.moderated_by = current_user.id
            item.moderated_at = datetime.now(timezone.utc)
            db.session.commit()
            flash(f'{entity_type.capitalize()} rejected successfully.', 'success')

    elif action == 'flag':
        reason = request.form.get('reason', '').strip()
        priority = request.form.get('priority', 'normal').strip()
        if not reason:
            flash('Flag reason is required.', 'warning')
            return redirect(redirect_url)

        from app.admin.services import create_flag
        entity_type_map = {
            'property': 'accommodation_property',
            'booking': 'accommodation_booking',
            'review': 'accommodation_review'
        }

        ok, flag = create_flag(
            current_user,
            entity_type_map.get(entity_type, entity_type),
            id,
            reason,
            priority
        )

        if ok:
            flash(f'{entity_type.capitalize()} flagged for review (Priority: {priority})', 'warning')
        else:
            flash(f'Failed to flag: {flag}', 'danger')

    return redirect(redirect_url)


@accommodation_bp.route("/admin/moderate/property/<int:id>/flag", methods=['POST'], endpoint="admin_flag_property")
@login_required
@require_moderator
def admin_flag_property(id):
    """Flag a property for moderation review"""
    property = Property.query.get_or_404(id)
    reason = request.form.get('reason', '').strip()
    priority = request.form.get('priority', 'normal').strip()

    if not reason:
        flash('Flag reason is required.', 'warning')
        return redirect(url_for('accommodation.admin_moderate_property', id=id))

    from app.admin.services import create_flag
    ok, flag = create_flag(current_user, 'accommodation_property', id, reason, priority)

    if ok:
        flash(f'Property flagged for review (Priority: {priority})', 'warning')
    else:
        flash(f'Failed to flag: {flag}', 'danger')

    return redirect(url_for('accommodation.admin_moderate_property', id=id))


@accommodation_bp.route("/admin/moderate/review/<int:id>/flag", methods=['POST'], endpoint="admin_flag_review")
@login_required
@require_moderator
def admin_flag_review(id):
    """Flag a review for moderation review"""
    review = Review.query.get_or_404(id)
    reason = request.form.get('reason', '').strip()
    priority = request.form.get('priority', 'normal').strip()

    if not reason:
        flash('Flag reason is required.', 'warning')
        return redirect(url_for('accommodation.admin_moderate_review', id=id))

    from app.admin.services import create_flag
    ok, flag = create_flag(current_user, 'accommodation_review', id, reason, priority)

    if ok:
        flash(f'Review flagged for review (Priority: {priority})', 'warning')
    else:
        flash(f'Failed to flag: {flag}', 'danger')

    return redirect(url_for('accommodation.admin_moderate_review', id=id))


# ============================================================================
# EXPLORE ROUTES
# ============================================================================

@accommodation_bp.route("/explore", endpoint="explore")
@login_required
#@require_role('fan', 'admin', 'owner')
def explore():
    """Explore accommodations with interactive map"""
    return render_template("accommodation/explore.html")


@accommodation_bp.route("/api/explore/search", endpoint="explore_search_api")
@limiter.limit("30 per minute")
def explore_search_api():
    """API for explore page - search properties within map bounds"""
    from flask_login import current_user
    
    # Get query parameters
    min_lat = request.args.get('min_lat', type=float)
    max_lat = request.args.get('max_lat', type=float)
    min_lng = request.args.get('min_lng', type=float)
    max_lng = request.args.get('max_lng', type=float)
    city = request.args.get('city')
    check_in = request.args.get('check_in')
    check_out = request.args.get('check_out')
    guests = request.args.get('guests', type=int, default=2)
    property_type = request.args.get('property_type', 'all')
    sort_by = request.args.get('sort_by', 'relevance')
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    min_rating = request.args.get('min_rating', type=float, default=0)
    page = request.args.get('page', type=int, default=1)
    per_page = 20
    
    # Build query
    query = Property.query.filter(
        Property.status.in_(['active', 'published']),
        Property.is_verified == True,
        Property.is_active == True,
        Property.is_deleted == False
    )
    
    # Geographic bounds filter
    if min_lat is not None and max_lat is not None and min_lng is not None and max_lng is not None:
        query = query.filter(
            Property.latitude >= min_lat,
            Property.latitude <= max_lat,
            Property.longitude >= min_lng,
            Property.longitude <= max_lng
        )
    
    # City filter
    if city:
        query = query.filter(Property.city.ilike(f'%{city}%'))
    
    # Property type filter
    if property_type != 'all':
        try:
            query = query.filter(Property.property_type == AccommodationPropertyType(property_type))
        except ValueError:
            pass  # Invalid property type, ignore
    
    # Price filter
    if min_price is not None:
        query = query.filter(Property.base_price_per_night >= min_price)
    if max_price is not None:
        query = query.filter(Property.base_price_per_night <= max_price)
    
    # Rating filter
    if min_rating > 0:
        query = query.filter(Property.overall_rating >= min_rating)
    
    # Sorting
    if sort_by == 'price_asc':
        query = query.order_by(Property.base_price_per_night.asc())
    elif sort_by == 'price_desc':
        query = query.order_by(Property.base_price_per_night.desc())
    elif sort_by == 'rating':
        query = query.order_by(Property.overall_rating.desc(), Property.total_reviews.desc())
    elif sort_by == 'newest':
        query = query.order_by(Property.created_at.desc())
    else:  # relevance
        query = query.order_by(Property.views_last_24h.desc(), Property.overall_rating.desc())
    
    # Pagination
    total = query.count()
    properties = query.offset((page - 1) * per_page).limit(per_page).all()
    
    # Serialize properties
    properties_data = []
    for prop in properties:
        # Check if wishlisted by current user
        is_wishlisted = False
        if current_user.is_authenticated:
            from app.accommodation.models.wishlist import Wishlist
            wishlist_item = Wishlist.query.filter_by(
                user_id=current_user.id,
                property_id=prop.id
            ).first()
            is_wishlisted = wishlist_item is not None
        
        properties_data.append({
            'id': prop.id,
            'name': prop.title,
            'slug': prop.slug,
            'city': prop.city,
            'country': prop.country,
            'latitude': float(prop.latitude) if prop.latitude else None,
            'longitude': float(prop.longitude) if prop.longitude else None,
            'price': float(prop.base_price_per_night),
            'currency_symbol': '$',  # Could be dynamic based on prop.currency
            'property_type': enum_value(prop.property_type) if prop.property_type else None,
            'rating': float(prop.overall_rating) if prop.overall_rating else None,
            'reviews': prop.total_reviews,
            'images': prop.gallery_images,
            'is_wishlisted': is_wishlisted
        })
    
    return jsonify({
        'success': True,
        'properties': properties_data,
        'total': total,
        'page': page,
        'per_page': per_page,
        'has_more': page * per_page < total
    })


@accommodation_bp.route("/api/explore/wishlist/<int:property_id>", methods=['POST', 'DELETE'], endpoint="explore_wishlist_api")
@login_required
def explore_wishlist_api(property_id):
    """API for toggling wishlist status"""
    from app.accommodation.models.wishlist import Wishlist
    
    property = Property.query.get_or_404(property_id)
    
    if request.method == 'POST':
        # Add to wishlist
        existing = Wishlist.query.filter_by(
            user_id=current_user.id,
            property_id=property_id
        ).first()
        
        if existing:
            return jsonify({'success': True, 'message': 'Already in wishlist'})
        
        wishlist_item = Wishlist(
            user_id=current_user.id,
            property_id=property_id
        )
        db.session.add(wishlist_item)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Added to wishlist'})
    
    elif request.method == 'DELETE':
        # Remove from wishlist
        wishlist_item = Wishlist.query.filter_by(
            user_id=current_user.id,
            property_id=property_id
        ).first_or_404()
        
        db.session.delete(wishlist_item)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Removed from wishlist'})

