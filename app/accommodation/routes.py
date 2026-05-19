# app/accommodation/routes.py
"""
Consolidated accommodation routes - all routes in one file for optimization
"""

import calendar
import logging
from datetime import date, datetime, timezone, timedelta
from typing import Optional

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import login_required, current_user
from sqlalchemy import text

from app import db
from app.accommodation import accommodation_bp
from app.accommodation.forms import PropertyForm
from app.accommodation.models.property import (
    AccommodationCancellationPolicy,
    AccommodationPropertyStatus,
    AccommodationPropertyType,
    Property,
)
from app.accommodation.models.booking import AccommodationBooking
from app.accommodation.models.review import Review, AccommodationReviewStatus
from app.accommodation.services import search_service
from app.accommodation.services.availability_service import AvailabilityService
from app.accommodation.services.booking_service import BookingService
from app.accommodation.services.host_service import HostService
from app.accommodation.services.identity_service import AccommodationIdentityService
from app.accommodation.services.pricing_service import PricingService
from app.accommodation.services.urgency_service import urgency_service
from app.accommodation.services.wallet_service import WalletService
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

@accommodation_bp.route("/", endpoint="home")
@login_required
@require_role('fan', 'admin', 'owner')
@require_profile_completion
def home():
    """Accommodation home page - OTA-style homepage"""
    ForensicAuditService.log_attempt(
        entity_type="accommodation",
        entity_id=None,
        action="view_home",
        user_id=current_user.id,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    
    # Fetch featured properties (active, verified, with images)
    featured_properties = Property.query.filter(
        Property.status == AccommodationPropertyStatus.ACTIVE,
        Property.is_verified == True,
        Property.is_active == True
    ).order_by(Property.views_last_24h.desc()).limit(8).all()
    
    # Fetch popular destinations (cities with most properties)
    from sqlalchemy import func
    popular_destinations = db.session.query(
        Property.city,
        Property.country,
        func.count(Property.id).label('property_count')
    ).filter(
        Property.status == AccommodationPropertyStatus.ACTIVE,
        Property.is_verified == True,
        Property.is_active == True
    ).group_by(Property.city, Property.country)\
     .order_by(func.count(Property.id).desc())\
     .limit(6).all()
    
    return render_template("accommodation_home.html",
                          featured_properties=featured_properties,
                          popular_destinations=popular_destinations)


@accommodation_bp.route("/detail/<string:public_id>", endpoint="detail")
@login_required
@require_role('fan', 'admin', 'owner')
def detail(public_id):
    """Property detail page by public_id"""
    IDGuard.check_public_id(public_id, "accommodation detail route")
    ForensicAuditService.log_attempt(
        entity_type="accommodation",
        entity_id=public_id,
        action="view_detail",
        user_id=current_user.id,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    return render_template('accommodation/detail.html', public_id=public_id)


@accommodation_bp.route("/host/register", endpoint="host_register")
@login_required
@require_profile_completion
def host_register():
    """Host registration page"""
    flash("Host registration requires KYC Tier 3 verification.", "info")
    return render_template("accommodation/host_register.html")


@accommodation_bp.route("/admin/dashboard", endpoint="admin_dashboard")
@login_required
@require_role('admin', 'owner', 'accommodation_admin')
def admin_dashboard():
    """Accommodation admin dashboard"""
    return render_template("accommodation/admin/dashboard.html")


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
        Property.status == 'active',
        Property.is_verified == True,
        Property.is_active == True,
        func.lower(Property.city).like(f'{q.lower()}%')
    ).group_by(Property.city, Property.country)\
     .order_by(func.count(Property.id).desc())\
     .limit(5).all()

    props = Property.query.filter(
        Property.status == 'active',
        Property.is_verified == True,
        Property.is_active == True,
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
    property_data = search_service.get_property_by_identifier(identifier)

    if property_data is None:
        abort(404)

    if identifier.isdigit():
        property_model = Property.query.get(int(identifier))
    else:
        property_model = Property.query.filter_by(slug=identifier).first()

    if property_model:
        db.session.execute(
            text("UPDATE accommodation_properties SET views_last_24h = views_last_24h + 1 WHERE id = :id"),
            {'id': property_model.id}
        )
        db.session.commit()

    urgency = urgency_service.get_signals(property_model.id) if property_model else {}

    check_in = request.args.get('check_in')
    check_out = request.args.get('check_out')
    guests = request.args.get('guests', 2, type=int)

    availability_status = None
    price_breakdown = None

    if check_in and check_out and property_model:
        try:
            check_in_date = datetime.strptime(check_in, '%Y-%m-%d').date()
            check_out_date = datetime.strptime(check_out, '%Y-%m-%d').date()

            is_available, blocked_dates, error = AvailabilityService.is_range_available(
                property_model.id, check_in_date, check_out_date
            )

            if is_available:
                price_breakdown = PricingService.calculate_total(
                    property_model, check_in_date, check_out_date, guests
                )
                availability_status = "available"
            else:
                availability_status = "unavailable"
        except Exception as e:
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
        urgency=urgency,
        now=datetime.utcnow()
    )


@accommodation_bp.route("/guest/checkout", methods=['GET', 'POST'], endpoint="guest_checkout")
@login_required
def guest_checkout():
    """Booking checkout page"""
    if request.method == 'GET':
        booking_data = request.session.get('pending_booking')
        if not booking_data:
            flash('No booking in progress', 'warning')
            return redirect(url_for('accommodation.guest.search'))

        return render_template(
            "accommodation/guest/checkout.html",
            booking=booking_data
        )

    try:
        data = request.form
        required = ['property_id', 'check_in', 'check_out', 'num_guests', 'guest_name', 'guest_email']
        for field in required:
            if not data.get(field):
                flash(f'Missing required field: {field}', 'danger')
                return redirect(url_for('accommodation.guest.search'))

        check_in = datetime.strptime(data['check_in'], '%Y-%m-%d').date()
        check_out = datetime.strptime(data['check_out'], '%Y-%m-%d').date()

        import hashlib
        import json
        idempotency_data = {
            'user_id': current_user.id,
            'property_id': int(data['property_id']),
            'check_in': data['check_in'],
            'check_out': data['check_out'],
            'num_guests': int(data['num_guests'])
        }
        idempotency_key = hashlib.sha256(
            json.dumps(idempotency_data, sort_keys=True).encode()
        ).hexdigest()

        booking, error = BookingService.create_booking(
            property_id=int(data['property_id']),
            guest_user_id=current_user.id,
            host_user_id=int(data['host_user_id']),
            check_in=check_in,
            check_out=check_out,
            num_guests=int(data['num_guests']),
            guest_name=data['guest_name'],
            guest_email=data['guest_email'],
            guest_phone=data.get('guest_phone'),
            special_requests=data.get('special_requests'),
            idempotency_key=idempotency_key,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            context_type=data.get('context_type'),
            context_id=data.get('context_id'),
            context_metadata=data.get('context_metadata')
        )

        if error:
            flash(error, 'danger')
            return redirect(url_for('accommodation.guest.detail', identifier=data['property_id']))

        success, txn_id, payment_error = WalletService.charge_wallet(
            user_id=current_user.id,
            amount=booking.total_amount,
            description=f"Accommodation booking: {booking.booking_reference}",
            idempotency_key=idempotency_key
        )

        if not success:
            BookingService.cancel_booking(
                booking.id,
                cancelled_by_user_id=current_user.id,
                reason=f"Payment failed: {payment_error}",
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            flash(f'Payment failed: {payment_error}', 'danger')
            return redirect(url_for('accommodation.guest.detail', identifier=data['property_id']))

        success, confirm_error = BookingService.confirm_booking(
            booking.id,
            wallet_transaction_id=txn_id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )

        if not success:
            flash(f'Booking confirmation failed: {confirm_error}', 'danger')
            return redirect(url_for('accommodation.guest.detail', identifier=data['property_id']))

        request.session.pop('pending_booking', None)
        flash(f'Booking confirmed! Your reference: {booking.booking_reference}', 'success')
        return redirect(url_for('accommodation.guest.confirmation', reference=booking.booking_reference))

    except Exception as e:
        logger.exception(f"Checkout error: {e}")
        flash(f'Error processing booking: {str(e)}', 'danger')
        return redirect(url_for('accommodation.guest.search'))


@accommodation_bp.route("/guest/confirmation/<reference>", endpoint="guest_confirmation")
@login_required
def guest_confirmation(reference):
    """Booking confirmation page"""
    booking = BookingService.get_booking_by_reference(reference)

    if not booking:
        flash('Booking not found', 'danger')
        return redirect(url_for('accommodation.guest.my_bookings'))

    if booking.guest_user_id != current_user.id and booking.host_user_id != current_user.id:
        abort(403)

    property_data = search_service.get_property_by_identifier(str(booking.property_id))

    return render_template(
        "accommodation/guest/confirmation.html",
        booking=booking,
        property=property_data
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


@accommodation_bp.route("/guest/booking/<reference>/cancel", methods=['POST'], endpoint="guest_cancel_booking")
@login_required
def guest_cancel_booking(reference):
    """Cancel a booking"""
    booking = BookingService.get_booking_by_reference(reference)

    if not booking:
        flash('Booking not found', 'danger')
        return redirect(url_for('accommodation.guest.my_bookings'))

    if booking.guest_user_id != current_user.id:
        flash('You are not authorized to cancel this booking', 'danger')
        return redirect(url_for('accommodation.guest.my_bookings'))

    reason = request.form.get('reason', 'User requested cancellation')

    success, message, refund = BookingService.cancel_booking(
        booking.id,
        cancelled_by_user_id=current_user.id,
        reason=reason,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
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

    return redirect(url_for('accommodation.guest.my_bookings'))


# ============================================================================
# HOST ROUTES (URL prefix: /host)
# ============================================================================

def _ensure_host_identity():
    """Return host identity data if current user can host; otherwise flash warning"""
    can_host, reason = AccommodationIdentityService.can_host(current_user)
    if not can_host:
        flash(f"Cannot access host tools: {reason}", "warning")
        return None
    return AccommodationIdentityService.get_host_identity(current_user)


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

    return render_template(
        "accommodation/host/dashboard.html",
        host_info=host_info,
        listings=dashboard_data["properties"],
        bookings=dashboard_data["upcoming_bookings"],
        stats=dashboard_data["stats"],
        revenue_summary=dashboard_data["revenue_summary"],
    )


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
            return redirect(url_for("accommodation.host.dashboard"))
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
                "property_type": prop.property_type.value if prop.property_type else None,
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
                "cancellation_policy": prop.cancellation_policy.value if prop.cancellation_policy else None,
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
                AccommodationPropertyStatus.DRAFT,
                AccommodationPropertyStatus.SUSPENDED,
            }:
                prop.status = AccommodationPropertyStatus.PENDING_REVIEW
            prop.updated_at = datetime.now(timezone.utc)

            db.session.commit()
            flash("Listing updated successfully.", "success")
            return redirect(url_for("accommodation.host.dashboard"))
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
        return redirect(url_for("accommodation.host.create_listing"))

    month_year = request.args.get("month")
    current_month = _resolve_month(month_year)
    selected_property_id = request.args.get("property_id", type=int) or properties[0]["id"]

    selected_property = next(
        (prop for prop in properties if prop["id"] == selected_property_id),
        properties[0],
    )

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


@accommodation_bp.route("/host/bookings", endpoint="host_bookings")
@login_required
def host_bookings():
    host_info = _ensure_host_identity()
    if not host_info:
        return redirect(url_for("index"))
    return render_template("accommodation/host/bookings.html", host_info=host_info)


@accommodation_bp.route("/host/earnings", endpoint="host_earnings")
@login_required
def host_earnings():
    host_info = _ensure_host_identity()
    if not host_info:
        return redirect(url_for("index"))
    return render_template("accommodation/host/earnings.html", host_info=host_info)


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
    return render_template("accommodation/admin/dashboard.html")


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


@accommodation_bp.route("/admin/moderate", endpoint="admin_moderate")
@login_required
@require_moderator
def admin_moderate():
    """Show accommodation items needing moderation"""
    pending_properties = Property.query.filter_by(status=AccommodationPropertyStatus.PENDING_REVIEW).all()
    pending_bookings = AccommodationBooking.query.filter_by(status='pending').all()
    pending_reviews = Review.query.filter_by(status=AccommodationReviewStatus.PENDING).all()
    
    return render_template('accommodation/moderate.html', properties=pending_properties, bookings=pending_bookings, reviews=pending_reviews)


@accommodation_bp.route("/admin/moderate/property/<int:id>", endpoint="admin_moderate_property")
@login_required
@require_moderator
def admin_moderate_property(id):
    """Show single property for moderation review"""
    property = Property.query.get_or_404(id)
    return render_template('accommodation/moderate_property.html', property=property)


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
        redirect_url = url_for('accommodation.admin.moderate_property', id=id)
    elif entity_type == 'booking':
        item = AccommodationBooking.query.get_or_404(id)
        redirect_url = url_for('accommodation.admin.moderate_booking', id=id)
    elif entity_type == 'review':
        item = Review.query.get_or_404(id)
        redirect_url = url_for('accommodation.admin.moderate_review', id=id)
    else:
        flash('Invalid entity type.', 'danger')
        return redirect(url_for('accommodation.admin.moderate'))

    if action == 'approve':
        if entity_type == 'property':
            item.status = AccommodationPropertyStatus.ACTIVE
            item.is_verified = True
            item.verified_at = datetime.now(timezone.utc)
            item.verified_by = current_user.id
        elif entity_type == 'booking':
            item.status = 'confirmed'
        elif entity_type == 'review':
            item.status = AccommodationReviewStatus.APPROVED
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
            item.status = AccommodationPropertyStatus.SUSPENDED
            item.verification_notes = reason
        elif entity_type == 'booking':
            item.status = 'cancelled'
            item.cancellation_reason = reason
        elif entity_type == 'review':
            item.status = AccommodationReviewStatus.REJECTED
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
        return redirect(url_for('accommodation.admin.moderate_property', id=id))

    from app.admin.services import create_flag
    ok, flag = create_flag(current_user, 'accommodation_property', id, reason, priority)

    if ok:
        flash(f'Property flagged for review (Priority: {priority})', 'warning')
    else:
        flash(f'Failed to flag: {flag}', 'danger')

    return redirect(url_for('accommodation.admin.moderate_property', id=id))


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
        return redirect(url_for('accommodation.admin.moderate_review', id=id))

    from app.admin.services import create_flag
    ok, flag = create_flag(current_user, 'accommodation_review', id, reason, priority)

    if ok:
        flash(f'Review flagged for review (Priority: {priority})', 'warning')
    else:
        flash(f'Failed to flag: {flag}', 'danger')

    return redirect(url_for('accommodation.admin.moderate_review', id=id))
