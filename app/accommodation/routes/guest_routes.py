# app/accommodation/routes/guest_routes.py
"""
Guest-facing routes - Search, detail, and booking
"""

from flask import render_template, abort, request, jsonify, redirect, url_for, flash, session
from flask_login import login_required, current_user
from app.accommodation.routes import guest
from app.accommodation.services import search_service
from app.accommodation.services.booking_service import BookingService
from app.accommodation.services.availability_service import AvailabilityService
from app.accommodation.services.pricing_service import PricingService
from app.accommodation.services.wallet_service import WalletService
from app.accommodation.models.property import Property
import logging

logger = logging.getLogger(__name__)


@guest.route("/", endpoint="search")
def search():
    """Accommodation search page"""
    city = request.args.get('city')
    check_in = request.args.get('check_in')
    check_out = request.args.get('check_out')
    guests = request.args.get('guests', 2, type=int)

    properties = search_service.search_properties(
        city=city,
        check_in=check_in,
        check_out=check_out,
        guests=guests
    )

    return render_template(
        "accommodation/guest/search.html",
        properties=properties,
        city=city,
        check_in=check_in,
        check_out=check_out,
        guests=guests
    )


@guest.route("/api/search", endpoint="api_search")
def api_search():
    """JSON API for accommodation search"""
    city = request.args.get('city')
    check_in = request.args.get('check_in')
    check_out = request.args.get('check_out')
    guests = request.args.get('guests', 2, type=int)

    properties = search_service.search_properties(
        city=city,
        check_in=check_in,
        check_out=check_out,
        guests=guests
    )

    return jsonify({
        "success": True,
        "properties": properties,
        "count": len(properties)
    })


@guest.route("/<identifier>", endpoint="detail")
def detail(identifier):
    """Property detail page"""
    property_data = search_service.get_property_by_identifier(identifier)

    if property_data is None:
        abort(404)

    # Get the actual Property model for availability checks
    if identifier.isdigit():
        property_model = Property.query.get(int(identifier))
    else:
        property_model = Property.query.filter_by(slug=identifier).first()

    # Check availability for selected dates from URL
    check_in = request.args.get('check_in')
    check_out = request.args.get('check_out')
    guests = request.args.get('guests', 2, type=int)

    availability_status = None
    price_breakdown = None

    if check_in and check_out and property_model:
        from datetime import datetime
        try:
            check_in_date = datetime.strptime(check_in, '%Y-%m-%d').date()
            check_out_date = datetime.strptime(check_out, '%Y-%m-%d').date()

            # Check availability
            is_available, blocked_dates, error = AvailabilityService.is_range_available(
                property_model.id, check_in_date, check_out_date
            )

            if is_available:
                # Calculate price
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
        selected_guests=guests
    )


@guest.route("/checkout", methods=['GET', 'POST'], endpoint="checkout")
@login_required
def checkout():
    """Booking checkout page"""
    if request.method == 'GET':
        # Get booking data from session
        booking_data = session.get('pending_booking')
        if not booking_data:
            flash('No booking in progress', 'warning')
            return redirect(url_for('accommodation.guest.search'))

        return render_template(
            "accommodation/guest/checkout.html",
            booking=booking_data
        )

    # POST - Process booking
    try:
        data = request.form

        # Validate required fields
        required = ['property_id', 'check_in', 'check_out', 'num_guests', 'guest_name', 'guest_email']
        for field in required:
            if not data.get(field):
                flash(f'Missing required field: {field}', 'danger')
                return redirect(url_for('accommodation.guest.search'))

        from datetime import datetime
        check_in = datetime.strptime(data['check_in'], '%Y-%m-%d').date()
        check_out = datetime.strptime(data['check_out'], '%Y-%m-%d').date()

        # Generate idempotency key
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

        # Create booking
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
            # NEW: Get context from form or session
            context_type=data.get('context_type'),  # From hidden form field
            context_id=data.get('context_id'),
            context_metadata=data.get('context_metadata')  # Could be JSON string
        )

        if error:
            flash(error, 'danger')
            return redirect(url_for('accommodation.guest.detail', identifier=data['property_id']))

        # Process payment
        success, txn_id, payment_error = WalletService.charge_wallet(
            user_id=current_user.id,
            amount=booking.total_amount,
            description=f"Accommodation booking: {booking.booking_reference}",
            idempotency_key=idempotency_key
        )

        if not success:
            # Cancel booking if payment fails
            BookingService.cancel_booking(
                booking.id,
                cancelled_by_user_id=current_user.id,
                reason=f"Payment failed: {payment_error}",
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            flash(f'Payment failed: {payment_error}', 'danger')
            return redirect(url_for('accommodation.guest.detail', identifier=data['property_id']))

        # Confirm booking
        success, confirm_error = BookingService.confirm_booking(
            booking.id,
            wallet_transaction_id=txn_id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )

        if not success:
            flash(f'Booking confirmation failed: {confirm_error}', 'danger')
            return redirect(url_for('accommodation.guest.detail', identifier=data['property_id']))

        # Clear session
        session.pop('pending_booking', None)

        # Redirect to confirmation
        flash(f'Booking confirmed! Your reference: {booking.booking_reference}', 'success')
        return redirect(url_for('accommodation.guest.confirmation', reference=booking.booking_reference))

    except Exception as e:
        logger.exception(f"Checkout error: {e}")
        flash(f'Error processing booking: {str(e)}', 'danger')
        return redirect(url_for('accommodation.guest.search'))


@guest.route("/confirmation/<reference>", endpoint="confirmation")
@login_required
def confirmation(reference):
    """Booking confirmation page"""
    booking = BookingService.get_booking_by_reference(reference)

    if not booking:
        flash('Booking not found', 'danger')
        return redirect(url_for('accommodation.guest.my_bookings'))

    # Security check - only the guest or host can view
    if booking.guest_user_id != current_user.id and booking.host_user_id != current_user.id:
        abort(403)

    # Get property details
    property_data = search_service.get_property_by_identifier(str(booking.property_id))

    return render_template(
        "accommodation/guest/confirmation.html",
        booking=booking,
        property=property_data
    )


@guest.route("/my-bookings", endpoint="my_bookings")
@login_required
def my_bookings():
    """User's booking history"""
    bookings = BookingService.get_user_bookings(current_user.id)

    # Enrich bookings with property data
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


@guest.route("/booking/<reference>/cancel", methods=['POST'], endpoint="cancel_booking")
@login_required
def cancel_booking(reference):
    """Cancel a booking"""
    booking = BookingService.get_booking_by_reference(reference)

    if not booking:
        flash('Booking not found', 'danger')
        return redirect(url_for('accommodation.guest.my_bookings'))

    # Only guest can cancel
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
            # Process refund to wallet
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


# Keep legacy routes for backward compatibility
@guest.route("/old/", endpoint="old_home")
def old_home():
    """Legacy hardcoded route"""
    from app.accommodation.services import search_service as old_svc
    hotels = old_svc.list_hotels()
    return render_template("accommodation_home.html", hotels=hotels)


@guest.route("/old/<hotel_id>", endpoint="old_detail")
def old_detail(hotel_id):
    """Legacy hardcoded detail route"""
    from app.accommodation.services import search_service as old_svc
    hotel = old_svc.get_hotel(hotel_id)
    if hotel is None:
        abort(404)
    return render_template("accommodation_detail.html", hotel=hotel)