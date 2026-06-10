You're absolutely right! Let me write a complete, streamlined solution that handles ALL scenarios and matches Booking.com/Airbnb quality.

Complete Booking & Accommodation Management Flow
The Big Picture - All Scenarios Covered
text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           COMPLETE BOOKING ECOSYSTEM                            │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  I. BOOKING CREATION (Who can book?)                                            │
│  ┌────────────────────────────────────────────────────────────────────────┐     │
│  │                                                                         │     │
│  │  A. SELF-BOOKING      B. BOOK FOR OTHER    C. MULTI-ROOM     D. EVENT   │     │
│  │  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐   ┌────────┐ │     │
│  │  │ I book for  │      │ I book for  │      │ I book 5    │   │Organizer│ │     │
│  │  │ MYSELF      │      │ my PARENTS  │      │ ROOMS for   │   │assigns  │ │     │
│  │  │ I stay      │      │ They stay   │      │ my group    │   │to me    │ │     │
│  │  └─────────────┘      └─────────────┘      └─────────────┘   └────────┘ │     │
│  │                                                                         │     │
│  └────────────────────────────────────────────────────────────────────────┘     │
│                                                                                  │
│  II. WHERE IT APPEARS (User sees accommodation as GUEST)                        │
│  ┌────────────────────────────────────────────────────────────────────────┐     │
│  │                                                                         │     │
│  │  MY ACCOMMODATION DASHBOARD                                             │     │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │     │
│  │  │ 🛏️ WHERE I'M STAYING (Guest view)                               │   │     │
│  │  │                                                                  │   │     │
│  │  │ • Self-booked (I booked for myself)                             │   │     │
│  │  │ • Booked for me (Someone else booked for me)                    │   │     │
│  │  │ • Assigned to me (Event organizer assigned)                     │   │     │
│  │  └─────────────────────────────────────────────────────────────────┘   │     │
│  │                                                                         │     │
│  │  MY BOOKINGS (Booker view - what I paid for)                           │     │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │     │
│  │  │ 💳 WHAT I BOOKED (Booker view)                                  │   │     │
│  │  │                                                                  │   │     │
│  │  │ • Bookings I made for myself (shows in both sections)           │   │     │
│  │  │ • Bookings I made for others (I paid, they stay)                │   │     │
│  │  │ • Multi-room bookings (all rooms I reserved)                    │   │     │
│  │  └─────────────────────────────────────────────────────────────────┘   │     │
│  │                                                                         │     │
│  └────────────────────────────────────────────────────────────────────────┘     │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
Database Schema Enhancements
Add to AccommodationBooking model
python
# app/accommodation/models/booking.py - ADD THESE FIELDS

class AccommodationBooking(BaseModel):
    # ... existing fields ...
    
    # ==========================================
    # NEW: Multi-guest / Third-party booking fields
    # ==========================================
    
    # Who is the primary guest staying (can be different from booker)
    primary_guest_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    primary_guest_name = Column(String(255), nullable=True)
    primary_guest_email = Column(String(255), nullable=True)
    primary_guest_phone = Column(String(50), nullable=True)
    
    # Who paid/booked (always the logged-in user who created the booking)
    booked_by_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    
    # Booking type classification
    booking_type = Column(String(30), nullable=False, default='self')  # self, third_party, group, event_assigned
    
    # Group bookings (multiple rooms for same trip)
    group_booking_id = Column(String(100), nullable=True, index=True)  # UUID shared across multiple bookings
    group_size = Column(Integer, nullable=True)  # Total people in group
    room_number = Column(Integer, nullable=True)  # Which room in group (1,2,3...)
    
    # Special instructions for the guest
    guest_instructions = Column(Text, nullable=True)
    
    # ==========================================
    # NEW: Indexes for performance
    # ==========================================
    __table_args__ = (
        # ... existing indexes ...
        Index("idx_booking_primary_guest", "primary_guest_id", "primary_guest_email"),
        Index("idx_booking_booked_by", "booked_by_user_id"),
        Index("idx_booking_group", "group_booking_id"),
        Index("idx_booking_type", "booking_type"),
    )
Add to EventAssignment model (already exists, confirm fields)
python
# app/events/models.py - EventAssignment already has:
# - accommodation_booking_id (FK to booking)
# - community_host_id (FK to property)
# - attendee_id (who stays)
# - assigned_by_id (who assigned)
Complete Routes Implementation
1. Main "My Accommodation" Route
python
# app/accommodation/routes.py - ADD THIS

@accommodation_bp.route("/my-accommodation")
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
    
    current_user_id = current_user.id
    current_user_email = current_user.email
    
    # ============================================================
    # SECTION 1: WHERE I'M STAYING (Guest View)
    # ============================================================
    
    guest_stays = []
    
    # 1A. Self-booked stays (I booked for myself, I am the guest)
    self_booked = AccommodationBooking.query.filter(
        AccommodationBooking.guest_user_id == current_user_id,
        AccommodationBooking.status.in_(['confirmed', 'checked_in']),
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
            'cancellation_policy': booking.accommodation_property.cancellation_policy.value if booking.accommodation_property else None,
            'host_contact': {
                'name': booking.accommodation_property.owner_display_name if booking.accommodation_property else None,
                'phone': booking.accommodation_property.owner_user.phone if booking.accommodation_property and booking.accommodation_property.owner_user else None,
                'email': booking.accommodation_property.owner_user.email if booking.accommodation_property and booking.accommodation_property.owner_user else None,
            } if booking.accommodation_property else None,
            'address': booking.accommodation_property.full_address if booking.accommodation_property else None,
            'images': booking.accommodation_property.gallery[:3] if booking.accommodation_property and booking.accommodation_property.gallery else [],
        })
    
    # 1B. Booked for me by someone else (third-party booking where I am primary guest)
    third_party_for_me = AccommodationBooking.query.filter(
        and_(
            or_(
                AccommodationBooking.primary_guest_id == current_user_id,
                AccommodationBooking.primary_guest_email == current_user_email
            ),
            AccommodationBooking.booking_type == 'third_party',
            AccommodationBooking.status.in_(['confirmed', 'checked_in']),
            AccommodationBooking.is_deleted == False
        )
    ).all()
    
    for booking in third_party_for_me:
        booker = User.query.get(booking.booked_by_user_id)
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
            'cancellation_policy': booking.accommodation_property.cancellation_policy.value if booking.accommodation_property else None,
            'host_contact': {
                'name': booking.accommodation_property.owner_display_name if booking.accommodation_property else None,
                'phone': booking.accommodation_property.owner_user.phone if booking.accommodation_property and booking.accommodation_property.owner_user else None,
                'email': booking.accommodation_property.owner_user.email if booking.accommodation_property and booking.accommodation_property.owner_user else None,
            } if booking.accommodation_property else None,
            'address': booking.accommodation_property.full_address if booking.accommodation_property else None,
            'images': booking.accommodation_property.gallery[:3] if booking.accommodation_property and booking.accommodation_property.gallery else [],
            'guest_instructions': booking.guest_instructions,
        })
    
    # 1C. Assigned to me by event organizer
    assignments = EventAssignment.query.filter_by(
        attendee_id=current_user_id,
        status='active'
    ).all()
    
    for assignment in assignments:
        event = Event.query.get(assignment.event_id)
        if not event:
            continue
        
        # Check if hotel booking
        if assignment.accommodation_booking_id:
            booking = AccommodationBooking.query.get(assignment.accommodation_booking_id)
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
                    'can_cancel': False,
                    'host_contact': {
                        'name': booking.accommodation_property.owner_display_name,
                        'phone': booking.accommodation_property.owner_user.phone if booking.accommodation_property.owner_user else None,
                        'email': booking.accommodation_property.owner_user.email if booking.accommodation_property.owner_user else None,
                    },
                    'address': booking.accommodation_property.full_address,
                    'images': booking.accommodation_property.gallery[:3] if booking.accommodation_property.gallery else [],
                })
        
        # Check if community host
        elif assignment.community_host_id:
            property_obj = Property.query.get(assignment.community_host_id)
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
                    'images': property_obj.gallery[:3] if property_obj.gallery else [],
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
            guest_user = User.query.get(booking.primary_guest_id)
            guest_name = guest_user.username if guest_user else booking.primary_guest_name
            guest_email = guest_user.email if guest_user else booking.primary_guest_email
        elif booking.guest_user_id:
            guest_user = User.query.get(booking.guest_user_id)
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
            'property_image': booking.accommodation_property.main_image if booking.accommodation_property else None,
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
            now=datetime.utcnow()
        )
    
    return render_template(
        'accommodation/my_accommodation.html',
        guest_stays=guest_stays,
        my_bookings=my_bookings,
        group_bookings=group_bookings,
        now=datetime.utcnow()
    )
2. Enhanced Checkout Route (Support Book for Others + Multi-Room)
python
# app/accommodation/routes.py - MODIFY guest_checkout

@accommodation_bp.route("/guest/checkout", methods=['GET', 'POST'])
@login_required
def guest_checkout():
    """Enhanced checkout supporting self-booking, book-for-others, and multi-room"""
    
    if request.method == 'GET':
        booking_data = request.session.get('pending_booking')
        if not booking_data:
            flash('No booking in progress', 'warning')
            return redirect(url_for('accommodation.guest_search'))
        
        return render_template(
            "accommodation/guest/checkout.html",
            booking=booking_data
        )
    
    try:
        data = request.form
        
        # ============================================================
        # Parse booking type
        # ============================================================
        booking_type = data.get('booking_type', 'self')  # self, third_party, group
        
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
            from app.identity.models.user import User
            guest_user = User.query.filter_by(email=primary_guest_email).first()
            if guest_user:
                primary_guest_id = guest_user.id
                guest_user_id = guest_user.id
            else:
                guest_user_id = None  # Guest not registered
            
        elif booking_type == 'group':
            # Part of a group booking (multiple rooms)
            group_booking_id = data.get('group_booking_id') or str(uuid.uuid4())
            room_number = int(data.get('room_number', 1))
            total_rooms = int(data.get('total_rooms', 1))
            
            # Guest info for this room
            primary_guest_name = data.get('guest_name')
            primary_guest_email = data.get('guest_email')
            primary_guest_phone = data.get('guest_phone')
            primary_guest_id = None
            
            guest_user = User.query.filter_by(email=primary_guest_email).first()
            if guest_user:
                primary_guest_id = guest_user.id
                guest_user_id = guest_user.id
            else:
                guest_user_id = None
        
        # ============================================================
        # Validate required fields
        # ============================================================
        required = ['property_id', 'check_in', 'check_out', 'num_guests']
        if booking_type == 'third_party':
            required.extend(['primary_guest_name', 'primary_guest_email'])
        
        for field in required:
            if not data.get(field):
                flash(f'Missing required field: {field}', 'danger')
                return redirect(url_for('accommodation.guest_search'))
        
        check_in = datetime.strptime(data['check_in'], '%Y-%m-%d').date()
        check_out = datetime.strptime(data['check_out'], '%Y-%m-%d').date()
        
        # ============================================================
        # Create booking with enhanced fields
        # ============================================================
        import hashlib
        import json
        import uuid
        
        idempotency_data = {
            'user_id': current_user.id,
            'property_id': int(data['property_id']),
            'check_in': data['check_in'],
            'check_out': data['check_out'],
            'num_guests': int(data['num_guests']),
            'booking_type': booking_type,
            'primary_guest_email': primary_guest_email if booking_type == 'third_party' else current_user.email,
        }
        idempotency_key = hashlib.sha256(
            json.dumps(idempotency_data, sort_keys=True).encode()
        ).hexdigest()
        
        # Get property to verify owner
        from app.accommodation.models.property import Property
        property_obj = Property.query.get(int(data['property_id']))
        if not property_obj:
            flash('Property not found', 'danger')
            return redirect(url_for('accommodation.guest_search'))
        
        # Determine host_user_id (property owner)
        host_user_id = property_obj.owner_user_id or property_obj.owner_org_id
        
        booking, error = BookingService.create_booking(
            property_id=int(data['property_id']),
            guest_user_id=guest_user_id if guest_user_id else None,
            host_user_id=host_user_id,
            check_in=check_in,
            check_out=check_out,
            num_guests=int(data['num_guests']),
            guest_name=primary_guest_name,
            guest_email=primary_guest_email,
            guest_phone=primary_guest_phone,
            special_requests=data.get('special_requests'),
            idempotency_key=idempotency_key,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            context_type=data.get('context_type'),
            context_id=data.get('context_id'),
            context_metadata=data.get('context_metadata'),
            # NEW FIELDS:
            booked_by_user_id=current_user.id,
            primary_guest_id=primary_guest_id,
            primary_guest_name=primary_guest_name,
            primary_guest_email=primary_guest_email,
            primary_guest_phone=primary_guest_phone,
            booking_type=booking_type,
            group_booking_id=data.get('group_booking_id') if booking_type == 'group' else None,
            room_number=int(data.get('room_number', 1)) if booking_type == 'group' else None,
            guest_instructions=data.get('guest_instructions'),
        )
        
        if error:
            flash(error, 'danger')
            return redirect(url_for('accommodation.guest_detail', identifier=data['property_id']))
        
        # ============================================================
        # Process payment
        # ============================================================
        success, txn_id, payment_error = WalletService.charge_wallet(
            user_id=current_user.id,
            amount=booking.total_amount,
            description=f"Accommodation booking: {booking.booking_reference} - for {primary_guest_name}",
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
            return redirect(url_for('accommodation.guest_detail', identifier=data['property_id']))
        
        success, confirm_error = BookingService.confirm_booking(
            booking.id,
            wallet_transaction_id=txn_id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        if not success:
            flash(f'Booking confirmation failed: {confirm_error}', 'danger')
            return redirect(url_for('accommodation.guest_detail', identifier=data['property_id']))
        
        request.session.pop('pending_booking', None)
        
        # ============================================================
        # Send notifications
        # ============================================================
        # Notify the guest (if different from booker)
        if booking_type == 'third_party' and primary_guest_email != current_user.email:
            # Send email to guest with booking details
            send_booking_notification_to_guest(booking, primary_guest_name, primary_guest_email)
        
        # For group bookings, offer to book another room
        if booking_type == 'group' and room_number < total_rooms:
            flash(f'Room {room_number} of {total_rooms} booked successfully! Would you like to book another room for your group?', 'info')
            return redirect(url_for('accommodation.guest_detail', identifier=data['property_id'], 
                                    check_in=data['check_in'], check_out=data['check_out'],
                                    group_booking_id=group_booking_id, room_number=room_number + 1, total_rooms=total_rooms))
        
        # Final confirmation
        if booking_type == 'third_party':
            flash(f'Booking confirmed for {primary_guest_name}! They will receive an email with details.', 'success')
        elif booking_type == 'group':
            flash(f'All {total_rooms} rooms booked successfully for your group!', 'success')
        else:
            flash(f'Booking confirmed! Your reference: {booking.booking_reference}', 'success')
        
        return redirect(url_for('accommodation.guest_confirmation', reference=booking.booking_reference))
        
    except Exception as e:
        logger.exception(f"Checkout error: {e}")
        flash(f'Error processing booking: {str(e)}', 'danger')
        return redirect(url_for('accommodation.guest_search'))
3. Update BookingService.create_booking
python
# app/accommodation/services/booking_service.py - MODIFY create_booking method

@staticmethod
def create_booking(
    property_id: int,
    guest_user_id: int,
    host_user_id: int,
    check_in: date,
    check_out: date,
    num_guests: int,
    guest_name: str,
    guest_email: str,
    guest_phone: str = None,
    special_requests: str = None,
    idempotency_key: str = None,
    ip_address: str = None,
    user_agent: str = None,
    context_type: 'BookingContextType' = None,
    context_id: str = None,
    context_metadata: dict = None,
    # NEW PARAMETERS
    booked_by_user_id: int = None,
    primary_guest_id: int = None,
    primary_guest_name: str = None,
    primary_guest_email: str = None,
    primary_guest_phone: str = None,
    booking_type: str = 'self',
    group_booking_id: str = None,
    room_number: int = None,
    guest_instructions: str = None,
) -> Tuple[Optional[AccommodationBooking], Optional[str]]:
    
    # ... existing code ...
    
    # Create booking with new fields
    booking = AccommodationBooking(
        property_id=property_id,
        guest_user_id=guest_user_id if guest_user_id else None,
        host_user_id=host_user_id,
        check_in=check_in,
        check_out=check_out,
        num_nights=pricing['nights'],
        num_guests=num_guests,
        nightly_rate=pricing['nightly_rate'],
        cleaning_fee=pricing['cleaning_fee'],
        service_fee=pricing['service_fee'],
        total_amount=pricing['total'],
        currency=property.currency,
        guest_name=guest_name,
        guest_email=guest_email,
        guest_phone=guest_phone,
        special_requests=special_requests,
        context_type=context_type or BookingContextType.NONE,
        context_id=context_id,
        context_metadata=context_metadata or {},
        idempotency_key=idempotency_key,
        status=AccommodationBookingStatus.PENDING.value,
        payment_status=AccommodationPaymentStatus.PENDING.value,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        # NEW FIELDS
        booked_by_user_id=booked_by_user_id or guest_user_id,  # Default to guest if not specified
        primary_guest_id=primary_guest_id,
        primary_guest_name=primary_guest_name or guest_name,
        primary_guest_email=primary_guest_email or guest_email,
        primary_guest_phone=primary_guest_phone or guest_phone,
        booking_type=booking_type,
        group_booking_id=group_booking_id,
        room_number=room_number,
        guest_instructions=guest_instructions,
    )
    
    # ... rest of existing code ...
4. Enhanced Checkout Template
html
{# templates/accommodation/guest/checkout.html - ADD BOOKING TYPE OPTIONS #}

{% extends "base.html" %}

{% block content %}
<div class="container py-4">
    <div class="row">
        <div class="col-lg-8">
            <div class="card shadow-sm mb-4">
                <div class="card-header bg-white">
                    <h4 class="mb-0">Complete Your Booking</h4>
                </div>
                <div class="card-body">
                    <form method="POST" id="checkout-form" action="{{ safe_url('accommodation.guest_checkout') }}">
                        <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
                        
                        <!-- ============================================================ -->
                        <!-- STEP 1: WHO IS THIS BOOKING FOR? -->
                        <!-- ============================================================ -->
                        <h5 class="mb-3">Who is this booking for?</h5>
                        <div class="mb-4">
                            <div class="row">
                                <div class="col-md-4">
                                    <div class="booking-type-card" onclick="selectBookingType('self')">
                                        <div class="form-check">
                                            <input type="radio" name="booking_type" value="self" id="bookingSelf" class="form-check-input" checked>
                                            <label class="form-check-label fw-bold" for="bookingSelf">
                                                <i class="fas fa-user"></i> Myself
                                            </label>
                                        </div>
                                        <p class="small text-muted mt-2 mb-0">I will be staying at this property</p>
                                    </div>
                                </div>
                                <div class="col-md-4">
                                    <div class="booking-type-card" onclick="selectBookingType('third_party')">
                                        <div class="form-check">
                                            <input type="radio" name="booking_type" value="third_party" id="bookingThirdParty" class="form-check-input">
                                            <label class="form-check-label fw-bold" for="bookingThirdParty">
                                                <i class="fas fa-users"></i> Someone Else
                                            </label>
                                        </div>
                                        <p class="small text-muted mt-2 mb-0">I'm booking for family/friend</p>
                                    </div>
                                </div>
                                <div class="col-md-4">
                                    <div class="booking-type-card" onclick="selectBookingType('group')">
                                        <div class="form-check">
                                            <input type="radio" name="booking_type" value="group" id="bookingGroup" class="form-check-input">
                                            <label class="form-check-label fw-bold" for="bookingGroup">
                                                <i class="fas fa-hotel"></i> Multiple Rooms
                                            </label>
                                        </div>
                                        <p class="small text-muted mt-2 mb-0">Book multiple rooms for a group</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <!-- ============================================================ -->
                        <!-- STEP 2: GUEST DETAILS (for third-party booking) -->
                        <!-- ============================================================ -->
                        <div id="thirdPartySection" style="display: none;">
                            <h5 class="mb-3 mt-4">Guest Details (Who is staying)</h5>
                            <div class="row mb-4">
                                <div class="col-md-6 mb-3">
                                    <label class="form-label">Guest Full Name *</label>
                                    <input type="text" name="primary_guest_name" class="form-control" placeholder="Full name of person staying">
                                </div>
                                <div class="col-md-6 mb-3">
                                    <label class="form-label">Guest Email *</label>
                                    <input type="email" name="primary_guest_email" class="form-control" placeholder="Email for booking confirmation">
                                </div>
                                <div class="col-md-6 mb-3">
                                    <label class="form-label">Guest Phone</label>
                                    <input type="tel" name="primary_guest_phone" class="form-control" placeholder="Phone number">
                                </div>
                                <div class="col-12">
                                    <label class="form-label">Special Instructions for Guest</label>
                                    <textarea name="guest_instructions" class="form-control" rows="2" placeholder="Any special instructions for the guest? (e.g., door code, parking instructions)"></textarea>
                                </div>
                            </div>
                        </div>
                        
                        <!-- ============================================================ -->
                        <!-- STEP 3: GROUP BOOKING DETAILS -->
                        <!-- ============================================================ -->
                        <div id="groupSection" style="display: none;">
                            <h5 class="mb-3 mt-4">Group Booking Details</h5>
                            <div class="row mb-4">
                                <div class="col-md-4 mb-3">
                                    <label class="form-label">Total Rooms Needed</label>
                                    <input type="number" name="total_rooms" id="totalRooms" class="form-control" min="1" max="20" value="2">
                                </div>
                                <div class="col-md-4 mb-3">
                                    <label class="form-label">Room Number (this booking)</label>
                                    <input type="number" name="room_number" id="roomNumber" class="form-control" min="1" value="1" readonly>
                                </div>
                                <div class="col-md-4 mb-3">
                                    <label class="form-label">Guests in this Room</label>
                                    <input type="number" name="num_guests" class="form-control" value="{{ booking.num_guests }}" min="1" max="{{ booking.max_guests }}">
                                </div>
                            </div>
                        </div>
                        
                        <!-- ============================================================ -->
                        <!-- STEP 4: YOUR CONTACT INFO (Booker) -->
                        <!-- ============================================================ -->
                        <h5 class="mb-3 mt-4">Your Contact Information</h5>
                        <div class="row mb-4">
                            <div class="col-md-6 mb-3">
                                <label class="form-label">Your Name</label>
                                <input type="text" class="form-control" value="{{ current_user.username or current_user.email }}" disabled>
                            </div>
                            <div class="col-md-6 mb-3">
                                <label class="form-label">Your Email</label>
                                <input type="email" class="form-control" value="{{ current_user.email }}" disabled>
                            </div>
                            <div class="col-md-6 mb-3">
                                <label class="form-label">Your Phone (for booking confirmation)</label>
                                <input type="tel" name="guest_phone" class="form-control" value="{{ current_user.phone or '' }}">
                                <small class="text-muted">We'll send booking updates here</small>
                            </div>
                        </div>
                        
                        <!-- ============================================================ -->
                        <!-- STEP 5: BOOKING DETAILS (from property) -->
                        <!-- ============================================================ -->
                        <h5 class="mb-3">Booking Details</h5>
                        <div class="bg-light p-3 rounded mb-4">
                            <div class="row">
                                <div class="col-md-6 mb-2">
                                    <strong>Property:</strong> {{ booking.name }}
                                </div>
                                <div class="col-md-6 mb-2">
                                    <strong>Location:</strong> {{ booking.city }}
                                </div>
                                <div class="col-md-4 mb-2">
                                    <strong>Check-in:</strong> {{ booking.check_in }}
                                </div>
                                <div class="col-md-4 mb-2">
                                    <strong>Check-out:</strong> {{ booking.check_out }}
                                </div>
                                <div class="col-md-4 mb-2">
                                    <strong>Guests:</strong> <span id="guestCountDisplay">{{ booking.num_guests }}</span>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Hidden fields -->
                        <input type="hidden" name="property_id" value="{{ booking.property_id }}">
                        <input type="hidden" name="host_user_id" value="{{ booking.host_user_id }}">
                        <input type="hidden" name="check_in" value="{{ booking.check_in }}">
                        <input type="hidden" name="check_out" value="{{ booking.check_out }}">
                        <input type="hidden" name="group_booking_id" id="groupBookingId" value="">
                        
                        <!-- Special Requests -->
                        <h5 class="mb-3">Special Requests</h5>
                        <div class="mb-4">
                            <textarea name="special_requests" class="form-control" rows="3"
                                      placeholder="Any special requests? (e.g., late check-in, dietary requirements)"></textarea>
                            <small class="text-muted">We'll pass these on to the host</small>
                        </div>
                        
                        <!-- Terms -->
                        <div class="form-check mb-4">
                            <input type="checkbox" class="form-check-input" id="terms" required>
                            <label class="form-check-label" for="terms">
                                I agree to the <a href="#" target="_blank">terms and conditions</a> and
                                <a href="#" target="_blank">cancellation policy</a>
                            </label>
                        </div>
                        
                        <button type="submit" class="btn btn-primary btn-lg w-100" id="submit-btn">
                            Confirm and Pay
                        </button>
                    </form>
                </div>
            </div>
        </div>
        
        <!-- Price Summary (same as before) -->
        <div class="col-lg-4">
            <div class="card shadow-sm sticky-top" style="top: 20px;">
                <div class="card-header bg-white">
                    <h5 class="mb-0">Price Summary</h5>
                </div>
                <div class="card-body">
                    <div class="d-flex justify-content-between mb-2">
                        <span>${{ "%.2f"|format(booking.nightly_rate) }} × {{ booking.nights }} nights</span>
                        <span>${{ "%.2f"|format(booking.subtotal) }}</span>
                    </div>
                    <div class="d-flex justify-content-between mb-2">
                        <span>Cleaning fee</span>
                        <span>${{ "%.2f"|format(booking.cleaning_fee) }}</span>
                    </div>
                    <div class="d-flex justify-content-between mb-2">
                        <span>Service fee</span>
                        <span>${{ "%.2f"|format(booking.service_fee) }}</span>
                    </div>
                    <hr>
                    <div class="d-flex justify-content-between mb-0">
                        <strong>Total</strong>
                        <strong class="text-primary">${{ "%.2f"|format(booking.total) }}</strong>
                    </div>
                    <small class="text-muted">Paid from your AFCON360 wallet</small>
                </div>
            </div>
        </div>
    </div>
</div>

<script>
let groupBookingId = null;

function selectBookingType(type) {
    // Update radio buttons
    document.getElementById('bookingSelf').checked = (type === 'self');
    document.getElementById('bookingThirdParty').checked = (type === 'third_party');
    document.getElementById('bookingGroup').checked = (type === 'group');
    
    // Show/hide sections
    document.getElementById('thirdPartySection').style.display = type === 'third_party' ? 'block' : 'none';
    document.getElementById('groupSection').style.display = type === 'group' ? 'block' : 'none';
    
    // Generate group ID if needed
    if (type === 'group' && !groupBookingId) {
        groupBookingId = 'group_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        document.getElementById('groupBookingId').value = groupBookingId;
    }
}

// Update guest count display
document.querySelector('[name="num_guests"]')?.addEventListener('change', function() {
    document.getElementById('guestCountDisplay').innerText = this.value;
});

// Update room number when total rooms changes
document.getElementById('totalRooms')?.addEventListener('change', function() {
    let roomNumberInput = document.getElementById('roomNumber');
    let currentRoom = parseInt(roomNumberInput.value);
    let totalRooms = parseInt(this.value);
    
    if (currentRoom > totalRooms) {
        roomNumberInput.value = totalRooms;
    }
    roomNumberInput.max = totalRooms;
    roomNumberInput.readOnly = false;
});
</script>

<style>
.booking-type-card {
    border: 2px solid #e0e0e0;
    border-radius: 12px;
    padding: 1rem;
    cursor: pointer;
    transition: all 0.3s ease;
}
.booking-type-card:hover {
    border-color: #667eea;
    background-color: #f8f9ff;
}
.booking-type-card:has(input:checked) {
    border-color: #667eea;
    background-color: #f0f4ff;
}
</style>
{% endblock %}
5. Navigation Updates
Update base.html - User Dropdown
html
<!-- In base.html, under user dropdown menu -->
<ul class="drop-menu drop-menu--right" role="menu">
    <!-- ... existing items ... -->
    
    <!-- NEW: My Accommodation -->
    <li><a class="drop-item" href="{{ safe_url('accommodation.my_accommodation') }}">
        <i class="fas fa-bed me-2"></i>My Accommodation
    </a></li>
    
    <li><a class="drop-item" href="{{ safe_url('accommodation.guest_my_bookings') }}">
        <i class="fas fa-calendar-alt me-2"></i>My Bookings
    </a></li>
    
    <!-- ... rest ... -->
</ul>
Update base.html - Mobile Drawer
html
<!-- In mobile drawer nav -->
<a class="drawer-link" href="{{ safe_url('accommodation.my_accommodation') }}">
    <i class="fas fa-bed me-2"></i>My Accommodation
</a>
<a class="drawer-link" href="{{ safe_url('accommodation.guest_my_bookings') }}">
    <i class="fas fa-calendar-alt me-2"></i>My Bookings
</a>
Update base_user_dashboard.html - Sidebar
html
<!-- In dashboard sidebar nav-menu -->
<a href="#" class="nav-item" data-pane-url="{{ safe_url('accommodation.my_accommodation') }}">
    <i class="fas fa-bed"></i>
    <span>My Accommodation</span>
</a>

<a href="#" class="nav-item" data-pane-url="{{ safe_url('accommodation.guest_my_bookings') }}">
    <i class="fas fa-calendar-alt"></i>
    <span>My Bookings</span>
</a>
6. New Templates
my_accommodation.html (Full Page)
html
{# templates/accommodation/my_accommodation.html #}
{% extends "base.html" %}

{% block title %}My Accommodation - AFCON360{% endblock %}

{% block content %}
<div class="container py-4">
    <h1 class="h2 mb-4">My Accommodation</h1>
    
    <!-- Tabs for Guest View vs Booker View -->
    <ul class="nav nav-tabs mb-4" id="accommodationTabs" role="tablist">
        <li class="nav-item" role="presentation">
            <button class="nav-link active" id="staying-tab" data-bs-toggle="tab" data-bs-target="#staying" type="button" role="tab">
                <i class="fas fa-bed"></i> Where I'm Staying ({{ guest_stays|length }})
            </button>
        </li>
        <li class="nav-item" role="presentation">
            <button class="nav-link" id="bookings-tab" data-bs-toggle="tab" data-bs-target="#bookings" type="button" role="tab">
                <i class="fas fa-credit-card"></i> What I Booked ({{ my_bookings|length }})
            </button>
        </li>
    </ul>
    
    <div class="tab-content">
        <!-- TAB 1: Where I'm Staying -->
        <div class="tab-pane fade show active" id="staying" role="tabpanel">
            {% if guest_stays %}
                {% for stay in guest_stays %}
                <div class="card mb-4 shadow-sm">
                    <div class="row g-0">
                        <div class="col-md-3">
                            {% if stay.images and stay.images[0] %}
                                <img src="{{ stay.images[0] }}" class="img-fluid rounded-start" style="height: 200px; width: 100%; object-fit: cover;" alt="{{ stay.property_name }}">
                            {% else %}
                                <div class="bg-light rounded-start d-flex align-items-center justify-content-center" style="height: 200px;">
                                    <i class="fas fa-hotel fa-3x text-muted"></i>
                                </div>
                            {% endif %}
                        </div>
                        <div class="col-md-9">
                            <div class="card-body">
                                <div class="d-flex justify-content-between align-items-start">
                                    <div>
                                        <h5 class="card-title">{{ stay.property_name }}</h5>
                                        <p class="text-muted small">
                                            <i class="fas fa-map-marker-alt"></i> {{ stay.address or 'Address available at check-in' }}
                                        </p>
                                    </div>
                                    <span class="badge bg-{{ 'success' if stay.status == 'confirmed' else 'warning' }} px-3 py-2">
                                        {{ stay.status|upper }}
                                    </span>
                                </div>
                                
                                <!-- Stay Details -->
                                <div class="row mt-3">
                                    <div class="col-md-6">
                                        <p class="mb-1"><strong>📅 Dates:</strong> {{ stay.check_in.strftime('%b %d, %Y') }} - {{ stay.check_out.strftime('%b %d, %Y') }}</p>
                                        <p class="mb-1"><strong>👥 Guests:</strong> {{ stay.guests }} guest{% if stay.guests > 1 %}s{% endif %}</p>
                                        <p class="mb-1"><strong>🏷️ Nights:</strong> {{ stay.nights }}</p>
                                    </div>
                                    <div class="col-md-6">
                                        {% if stay.type == 'self_booked' %}
                                            <p class="mb-1"><strong>👤 Booked by:</strong> {{ stay.booked_by_name }} (me)</p>
                                            <p class="mb-1"><strong>💰 Total paid:</strong> {{ stay.currency }} {{ "%.2f"|format(stay.total_amount) }}</p>
                                            {% if stay.can_cancel %}
                                                <button class="btn btn-sm btn-outline-danger mt-2" onclick="cancelBooking('{{ stay.booking_reference }}')">
                                                    <i class="fas fa-times"></i> Cancel Booking
                                                </button>
                                            {% endif %}
                                        {% elif stay.type == 'booked_for_me' %}
                                            <p class="mb-1"><strong>👤 Booked by:</strong> {{ stay.booked_by_name }} (for me)</p>
                                            <p class="mb-1 text-muted"><i class="fas fa-info-circle"></i> This booking was made for you</p>
                                        {% elif stay.type.startswith('event_assigned') %}
                                            <p class="mb-1"><strong>🎟️ Event:</strong> {{ stay.event_name }}</p>
                                            <p class="mb-1"><strong>👤 Assigned by:</strong> {{ stay.booked_by_name }}</p>
                                            {% if stay.type == 'event_assigned_community' %}
                                                <p class="mb-1"><strong>🏠 Host:</strong> {{ stay.host_contact.name if stay.host_contact else 'Community Host' }}</p>
                                                {% if stay.is_free %}
                                                    <span class="badge bg-success">Free Stay</span>
                                                {% else %}
                                                    <p class="mb-1"><strong>💰 Rate:</strong> {{ stay.currency }} {{ "%.2f"|format(stay.price_per_night) }}/night</p>
                                                {% endif %}
                                            {% endif %}
                                        {% endif %}
                                    </div>
                                </div>
                                
                                <!-- Host Contact (if available) -->
                                {% if stay.host_contact and stay.host_contact.name %}
                                <hr>
                                <div class="row">
                                    <div class="col-12">
                                        <p class="mb-1"><strong>🏠 Host Information:</strong></p>
                                        <p class="mb-1 small">Name: {{ stay.host_contact.name }}</p>
                                        {% if stay.host_contact.phone %}
                                            <p class="mb-1 small">Phone: <a href="tel:{{ stay.host_contact.phone }}">{{ stay.host_contact.phone }}</a></p>
                                        {% endif %}
                                        {% if stay.host_contact.email %}
                                            <p class="mb-1 small">Email: <a href="mailto:{{ stay.host_contact.email }}">{{ stay.host_contact.email }}</a></p>
                                        {% endif %}
                                    </div>
                                </div>
                                {% endif %}
                                
                                <!-- House Rules / Special Instructions -->
                                {% if stay.house_rules %}
                                <hr>
                                <p class="mb-1"><strong>📋 House Rules:</strong></p>
                                <p class="small text-muted">{{ stay.house_rules }}</p>
                                {% endif %}
                                
                                {% if stay.guest_instructions %}
                                <div class="alert alert-info mt-2">
                                    <i class="fas fa-info-circle"></i> <strong>Guest Instructions:</strong> {{ stay.guest_instructions }}
                                </div>
                                {% endif %}
                                
                                <!-- Action Buttons -->
                                <div class="mt-3">
                                    <a href="{{ url_for('accommodation.guest_detail', identifier=stay.property_id) }}" class="btn btn-sm btn-outline-primary">
                                        <i class="fas fa-info-circle"></i> View Property
                                    </a>
                                    {% if stay.type == 'event_assigned_community' %}
                                        <button class="btn btn-sm btn-outline-success" onclick="contactHost('{{ stay.host_contact.email if stay.host_contact else '' }}')">
                                            <i class="fas fa-envelope"></i> Contact Host
                                        </button>
                                    {% endif %}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                {% endfor %}
            {% else %}
                <div class="text-center py-5">
                    <i class="fas fa-bed fa-3x text-muted mb-3"></i>
                    <h3>No Upcoming Stays</h3>
                    <p class="text-muted">You don't have any upcoming accommodation.</p>
                    <a href="{{ url_for('accommodation.guest_search') }}" class="btn btn-primary">
                        <i class="fas fa-search"></i> Find a Place to Stay
                    </a>
                </div>
            {% endif %}
        </div>
        
        <!-- TAB 2: What I Booked -->
        <div class="tab-pane fade" id="bookings" role="tabpanel">
            {% if my_bookings %}
                <!-- Group Bookings Summary -->
                {% if group_bookings %}
                <div class="alert alert-info mb-4">
                    <i class="fas fa-hotel"></i> <strong>Group Booking:</strong> You have booked 
                    {% for group_id, group in group_bookings.items() %}
                        {{ group.rooms|length }} room{% if group.rooms|length > 1 %}s{% endif %} for your group
                    {% endfor %}
                </div>
                {% endif %}
                
                {% for booking in my_bookings %}
                <div class="card mb-3 shadow-sm">
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-start">
                            <div>
                                <h5 class="card-title">{{ booking.property_name }}</h5>
                                <p class="text-muted small">
                                    <i class="fas fa-calendar-alt"></i> {{ booking.check_in.strftime('%b %d, %Y') }} - {{ booking.check_out.strftime('%b %d, %Y') }}
                                </p>
                            </div>
                            <span class="badge bg-{{ 'success' if booking.status == 'confirmed' else 'warning' }}">
                                {{ booking.status|upper }}
                            </span>
                        </div>
                        
                        <div class="row mt-2">
                            <div class="col-md-6">
                                <p class="mb-1"><strong>👥 Guests:</strong> {{ booking.guests }}</p>
                                <p class="mb-1"><strong>💰 Total:</strong> {{ booking.currency }} {{ "%.2f"|format(booking.total_amount) }}</p>
                                {% if booking.paid_at %}
                                    <p class="mb-1"><small>Paid on {{ booking.paid_at.strftime('%b %d, %Y') }}</small></p>
                                {% endif %}
                            </div>
                            <div class="col-md-6">
                                {% if booking.type == 'for_other' %}
                                    <p class="mb-1"><strong>👤 Guest:</strong> {{ booking.guest_name }}</p>
                                    <p class="mb-1"><strong>📧 Guest Email:</strong> {{ booking.guest_email }}</p>
                                    {% if booking.guest_phone %}
                                        <p class="mb-1"><strong>📞 Guest Phone:</strong> {{ booking.guest_phone }}</p>
                                    {% endif %}
                                {% else %}
                                    <p class="mb-1 text-muted"><i class="fas fa-check-circle text-success"></i> Booking for myself</p>
                                {% endif %}
                                
                                {% if booking.is_group_booking %}
                                    <p class="mb-1"><strong>🏨 Room {{ booking.room_number }} of group</strong></p>
                                {% endif %}
                            </div>
                        </div>
                        
                        <div class="mt-3">
                            <a href="{{ url_for('accommodation.guest_detail', identifier=booking.property_id) }}" class="btn btn-sm btn-outline-primary">
                                View Property
                            </a>
                            <a href="{{ url_for('accommodation.guest_confirmation', reference=booking.booking_reference) }}" class="btn btn-sm btn-outline-secondary">
                                View Details
                            </a>
                            {% if booking.can_cancel %}
                                <button class="btn btn-sm btn-outline-danger" onclick="cancelBooking('{{ booking.booking_reference }}')">
                                    Cancel Booking
                                </button>
                            {% endif %}
                        </div>
                    </div>
                </div>
                {% endfor %}
            {% else %}
                <div class="text-center py-5">
                    <i class="fas fa-credit-card fa-3x text-muted mb-3"></i>
                    <h3>No Bookings Yet</h3>
                    <p class="text-muted">You haven't made any accommodation bookings.</p>
                    <a href="{{ url_for('accommodation.guest_search') }}" class="btn btn-primary">
                        <i class="fas fa-search"></i> Find a Place to Stay
                    </a>
                </div>
            {% endif %}
        </div>
    </div>
</div>

<script>
function cancelBooking(bookingRef) {
    if (confirm('Are you sure you want to cancel this booking? Refund will be calculated based on cancellation policy.')) {
        fetch(`/accommodation/guest/booking/${bookingRef}/cancel`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                location.reload();
            } else {
                alert('Error: ' + data.error);
            }
        });
    }
}

function contactHost(email) {
    if (email) {
        window.location.href = `mailto:${email}`;
    } else {
        alert('Host contact information will be provided at check-in.');
    }
}
</script>
{% endblock %}
Summary of What We've Built
Feature	Status	Description
Self-booking	✅	User books for themselves
Book for others	✅	User books for family/friends (guest receives email)
Multi-room group booking	✅	Book 1-20 rooms for a group, sequential booking flow
Event organizer assignment	✅	Organizer assigns accommodation to attendees
Unified "My Accommodation"	✅	Shows all stays where user is guest (regardless of source)
"What I Booked" section	✅	Shows all bookings user paid for
Host contact info	✅	Shows host name, phone, email when available
Cancellation	✅	For self-booked stays only
Pane loading	✅	Supports ?_pane=1 for dashboard integration
Navigation	✅	Added to user dropdown, mobile drawer, dashboard sidebar