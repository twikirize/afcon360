# app/user/routes.py
"""
User Routes - Smart Dashboard with module-aware rendering
No breaking changes - only additive improvements
"""

from flask import Blueprint, render_template, request, jsonify, current_app, redirect, url_for, g
from flask_login import login_required, current_user
from datetime import date, datetime, timedelta
import logging
from sqlalchemy import func, desc

from app.events.services import EventService
from app.wallet.services.wallet_service import WalletService
from app.auth.kyc_compliance import calculate_kyc_tier
from app.auth.onboarding_routes import onboarding_completed

logger = logging.getLogger(__name__)

user_bp = Blueprint('user', __name__, url_prefix='/user')


# ============================================================================
# SMART DASHBOARD CORE - Module Activity Detection
# ============================================================================

class SmartDashboard:
    """
    Intelligent dashboard that shows ONLY what the user actually uses.
    Learns from user behavior and adapts the UI.
    """

    @staticmethod
    def detect_user_modules(user_id: int) -> dict:
        """Detect which modules the user has ACTUALLY used."""
        from app.identity.models.user import User
        from app.events.models import EventRegistration
        from app.wallet.models.ledger import AccountModel
        from app.wallet.models.transaction import TransactionModel
        from app.accommodation.models.booking import AccommodationBooking
        from app.transport.models import Booking as TransportBooking
        from app.tourism.models import TourismListing

        # Get user object first
        user = User.query.get(user_id)
        if not user:
            return {}

        # Get user's public_id for queries that need it
        public_id = user.public_id

        # Initialize activity tracking
        activity = {
            # Events
            'has_events': False,
            'event_count': 0,
            'upcoming_events': [],
            'past_events': [],

            # Wallet
            'has_wallet': False,
            'wallet_balance': 0,
            'wallet_currency': 'UGX',
            'recent_transactions': [],

            # Accommodation
            'has_accommodation': False,
            'accommodation_count': 0,
            'upcoming_stays': [],
            'past_stays': [],

            # Transport
            'has_transport': False,
            'transport_count': 0,
            'upcoming_trips': [],
            'past_trips': [],

            # Tourism
            'has_tourism': False,
            'tourism_count': 0,

            # KYC
            'kyc_status': 'pending',
            'kyc_tier': 0,
            'kyc_tier_name': 'Unregistered',
            'kyc_progress': 0,

            # Profile
            'profile_completion': 0,

            # Activity
            'recent_activity': [],
        }

        # ──────────────────────────────────────────────────────────────────
        # 1. EVENTS
        # ──────────────────────────────────────────────────────────────────
        try:
            registrations = EventRegistration.query.filter_by(
                user_id=user_id
            ).all()

            activity['event_count'] = len(registrations)
            activity['has_events'] = activity['event_count'] > 0

            today = date.today()
            for reg in registrations:
                event = reg.event
                if event:
                    reg_dict = {
                        'id': reg.id,
                        'registration_ref': reg.registration_ref,
                        'ticket_number': reg.ticket_number,
                        'ticket_type': reg.ticket_type,
                        'status': reg.status,
                        'qr_token_hint': reg.qr_token[:8] + '...' if reg.qr_token else None,
                        'event': {
                            'id': event.public_id,
                            'slug': event.slug,
                            'name': event.name,
                            'city': event.city,
                            'venue': event.venue,
                            'start_date': event.start_date.isoformat() if event.start_date else None,
                            'end_date': event.end_date.isoformat() if event.end_date else None,
                        }
                    }

                    if event.end_date and event.end_date >= today:
                        activity['upcoming_events'].append(reg_dict)
                    else:
                        activity['past_events'].append(reg_dict)

            # Sort upcoming by date
            activity['upcoming_events'].sort(
                key=lambda x: x['event']['start_date'] or '9999-12-31'
            )

        except Exception as e:
            logger.warning(f"Event detection failed: {e}")

        # ──────────────────────────────────────────────────────────────────
        # 2. WALLET
        # ──────────────────────────────────────────────────────────────────
        try:
            from app.wallet.models.ledger import AccountModel
            from app.wallet.models.transaction import TransactionModel

            account = AccountModel.query.filter_by(user_id=user_id).first()
            activity['has_wallet'] = account is not None

            if account:
                activity['wallet_currency'] = account.currency or 'UGX'

                # Get balance via service
                try:
                    service = WalletService()
                    balance_data = service.get_balance(user_id)
                    activity['wallet_balance'] = float(balance_data.get('balance', 0))
                except:
                    # Fallback to direct query
                    from decimal import Decimal
                    from app.wallet.models.ledger import LedgerEntryModel

                    credit = db.session.query(func.sum(LedgerEntryModel.amount)).filter(
                        LedgerEntryModel.account_id == account.id,
                        LedgerEntryModel.entry_type == 'credit'
                    ).scalar() or Decimal('0')

                    debit = db.session.query(func.sum(LedgerEntryModel.amount)).filter(
                        LedgerEntryModel.account_id == account.id,
                        LedgerEntryModel.entry_type == 'debit'
                    ).scalar() or Decimal('0')

                    activity['wallet_balance'] = float(credit - debit)

                # Recent transactions
                transactions = TransactionModel.query.filter(
                    db.or_(
                        TransactionModel.user_id == user_id,
                        TransactionModel.recipient_user_id == user_id
                    )
                ).order_by(desc(TransactionModel.created_at)).limit(5).all()

                for tx in transactions:
                    is_sender = tx.user_id == user_id
                    activity['recent_transactions'].append({
                        'id': tx.id,
                        'type': tx.tx_type.value if hasattr(tx.tx_type, 'value') else str(tx.tx_type),
                        'amount': float(tx.amount),
                        'currency': tx.currency,
                        'status': tx.status.value if hasattr(tx.status, 'value') else str(tx.status),
                        'is_incoming': not is_sender and tx.tx_type.value == 'transfer',
                        'counterparty': tx.recipient_username if is_sender else tx.sender_username,
                        'description': tx.tx_metadata.get('description', '') if tx.tx_metadata else '',
                        'created_at': tx.created_at.isoformat() if tx.created_at else None,
                    })

        except Exception as e:
            logger.warning(f"Wallet detection failed: {e}")

        # ──────────────────────────────────────────────────────────────────
        # 3. ACCOMMODATION
        # ──────────────────────────────────────────────────────────────────
        try:
            from app.accommodation.models.booking import AccommodationBooking

            bookings = AccommodationBooking.query.filter(
                db.or_(
                    AccommodationBooking.booked_by_user_id == user_id,
                    AccommodationBooking.guest_user_id == user_id,
                    AccommodationBooking.primary_guest_id == user_id
                ),
                AccommodationBooking.is_deleted == False
            ).all()

            activity['accommodation_count'] = len(bookings)
            activity['has_accommodation'] = activity['accommodation_count'] > 0

            today = date.today()
            for booking in bookings:
                property_obj = booking.accommodation_property
                booking_dict = {
                    'id': booking.id,
                    'booking_reference': booking.booking_reference,
                    'property_name': property_obj.title if property_obj else 'Property',
                    'property_id': booking.property_id,
                    'check_in': booking.check_in.isoformat() if booking.check_in else None,
                    'check_out': booking.check_out.isoformat() if booking.check_out else None,
                    'nights': booking.num_nights,
                    'guests': booking.num_guests,
                    'status': booking.status,
                    'total_amount': float(booking.total_amount),
                    'currency': booking.currency,
                    'is_guest': booking.guest_user_id == user_id,
                    'is_booker': booking.booked_by_user_id == user_id,
                }

                if booking.check_in and booking.check_in >= today:
                    activity['upcoming_stays'].append(booking_dict)
                else:
                    activity['past_stays'].append(booking_dict)

            activity['upcoming_stays'].sort(key=lambda x: x['check_in'] or '9999-12-31')

        except Exception as e:
            logger.warning(f"Accommodation detection failed: {e}")

        # ──────────────────────────────────────────────────────────────────
        # 4. TRANSPORT
        # ──────────────────────────────────────────────────────────────────
        try:
            from app.transport.models import Booking as TransportBooking

            trips = TransportBooking.query.filter(
                db.or_(
                    TransportBooking.user_id == user_id,
                    TransportBooking.customer_id == user_id
                )
            ).order_by(desc(TransportBooking.created_at)).all()

            activity['transport_count'] = len(trips)
            activity['has_transport'] = activity['transport_count'] > 0

            now = datetime.now()
            for trip in trips:
                trip_dict = {
                    'id': trip.id,
                    'booking_reference': trip.booking_reference if hasattr(trip,
                                                                           'booking_reference') else f"TRP-{trip.id}",
                    'pickup_location': getattr(trip, 'pickup_location', 'Pickup'),
                    'dropoff_location': getattr(trip, 'dropoff_location', 'Destination'),
                    'pickup_time': trip.pickup_time.isoformat() if hasattr(trip,
                                                                           'pickup_time') and trip.pickup_time else None,
                    'status': trip.status if hasattr(trip, 'status') else 'confirmed',
                    'vehicle_type': getattr(trip, 'vehicle_type', 'Standard'),
                    'total_amount': float(trip.total_amount) if hasattr(trip, 'total_amount') else 0,
                    'currency': getattr(trip, 'currency', 'UGX'),
                }

                if trip_dict['pickup_time']:
                    pickup_dt = datetime.fromisoformat(trip_dict['pickup_time'].replace('Z', '+00:00')) if 'T' in \
                                                                                                           trip_dict[
                                                                                                               'pickup_time'] else None
                    if pickup_dt and pickup_dt >= now:
                        activity['upcoming_trips'].append(trip_dict)
                    else:
                        activity['past_trips'].append(trip_dict)

            activity['upcoming_trips'].sort(key=lambda x: x['pickup_time'] or '9999-12-31T23:59:59')

        except ImportError:
            logger.debug("Transport module not available")
        except Exception as e:
            logger.warning(f"Transport detection failed: {e}")

        # ──────────────────────────────────────────────────────────────────
        # 5. TOURISM
        # ──────────────────────────────────────────────────────────────────
        try:
            from app.tourism.models import TourismBooking

            tourism_bookings = TourismBooking.query.filter_by(
                user_id=user_id
            ).count()

            activity['tourism_count'] = tourism_bookings
            activity['has_tourism'] = tourism_bookings > 0

        except ImportError:
            logger.debug("Tourism module not available")
        except Exception as e:
            logger.warning(f"Tourism detection failed: {e}")

        # ──────────────────────────────────────────────────────────────────
        # 6. KYC & PROFILE
        # ──────────────────────────────────────────────────────────────────
        try:
            from app.profile.models import get_profile_by_user

            profile = get_profile_by_user(public_id)
            if profile:
                activity['kyc_status'] = profile.verification_status
                activity['profile_completion'] = profile.get_completion_percentage()

                # Get KYC tier info
                kyc_info = calculate_kyc_tier(user_id)
                activity['kyc_tier'] = kyc_info.get('tier', 0)
                activity['kyc_tier_name'] = kyc_info.get('tier_name', 'Unregistered')
                activity['kyc_progress'] = kyc_info.get('progress_percentage', 0)

        except Exception as e:
            logger.warning(f"KYC detection failed: {e}")

        # ──────────────────────────────────────────────────────────────────
        # 7. RECENT ACTIVITY (from audit logs)
        # ──────────────────────────────────────────────────────────────────
        try:
            from app.audit.comprehensive_audit import SecurityEventLog, DataAccessLog

            # Get recent security events
            security_events = SecurityEventLog.query.filter_by(
                user_id=user_id
            ).order_by(desc(SecurityEventLog.created_at)).limit(3).all()

            for event in security_events:
                activity['recent_activity'].append({
                    'type': 'security',
                    'action': event.event_type,
                    'description': event.description[:100] if event.description else event.event_type,
                    'created_at': event.created_at.isoformat() if event.created_at else None,
                    'icon': '🔐',
                })

            # Get recent data access
            data_events = DataAccessLog.query.filter_by(
                accessed_by=user_id
            ).order_by(desc(DataAccessLog.created_at)).limit(3).all()

            for event in data_events:
                activity['recent_activity'].append({
                    'type': 'data',
                    'action': event.operation,
                    'description': f"{event.operation} {event.entity_type}",
                    'created_at': event.created_at.isoformat() if event.created_at else None,
                    'icon': '📄',
                })

            # Sort by date
            activity['recent_activity'].sort(
                key=lambda x: x['created_at'] or '2000-01-01',
                reverse=True
            )
            activity['recent_activity'] = activity['recent_activity'][:10]

        except Exception as e:
            logger.warning(f"Activity detection failed: {e}")

        return activity

    @staticmethod
    def get_quick_actions(activity: dict, modules: dict) -> list:
        """Return contextual quick actions based on user activity."""
        actions = []

        # Primary actions based on what user actually uses
        if activity.get('has_events'):
            actions.append({
                'id': 'events',
                'label': 'My Events',
                'icon': '🎫',
                'url': url_for('events.my_registrations'),
                'priority': 1,
            })

        if activity.get('has_wallet'):
            actions.append({
                'id': 'wallet',
                'label': 'Wallet',
                'icon': '💰',
                'url': url_for('wallet.wallet_dashboard'),
                'priority': 1,
            })

        if activity.get('has_accommodation'):
            actions.append({
                'id': 'accommodation',
                'label': 'My Stays',
                'icon': '🏨',
                'url': url_for('accommodation.guest_my_bookings'),
                'priority': 2,
            })

        if activity.get('has_transport'):
            actions.append({
                'id': 'transport',
                'label': 'My Trips',
                'icon': '🚗',
                'url': url_for('transport.my_bookings'),
                'priority': 2,
            })

        # Always add discover actions for modules they HAVEN'T used
        if not activity.get('has_accommodation') and modules.get('accommodation'):
            actions.append({
                'id': 'discover_accommodation',
                'label': 'Find a Stay',
                'icon': '🏨',
                'url': url_for('accommodation.guest_search'),
                'priority': 3,
                'is_discovery': True,
            })

        if not activity.get('has_transport') and modules.get('transport'):
            actions.append({
                'id': 'discover_transport',
                'label': 'Book Transport',
                'icon': '🚗',
                'url': url_for('transport.home'),
                'priority': 3,
                'is_discovery': True,
            })

        if not activity.get('has_events') and modules.get('events'):
            actions.append({
                'id': 'discover_events',
                'label': 'Browse Events',
                'icon': '🎫',
                'url': url_for('events.list'),
                'priority': 3,
                'is_discovery': True,
            })

        if not activity.get('has_tourism') and modules.get('tourism'):
            actions.append({
                'id': 'discover_tourism',
                'label': 'Explore Uganda',
                'icon': '🌍',
                'url': url_for('tourism.home'),
                'priority': 3,
                'is_discovery': True,
            })

        # Sort by priority
        actions.sort(key=lambda x: x['priority'])

        return actions[:8]  # Max 8 actions

    @staticmethod
    def get_needs_attention(activity: dict) -> list:
        """Identify items that need user attention."""
        needs = []

        # KYC needs attention
        if activity.get('kyc_status') == 'pending' and activity.get('profile_completion', 0) > 50:
            needs.append({
                'id': 'kyc_pending',
                'title': 'KYC Verification Pending',
                'description': 'Complete your KYC to unlock full features',
                'action_url': url_for('kyc.index'),
                'action_label': 'Verify Now',
                'priority': 1,
                'icon': '🪪',
            })
        elif activity.get('kyc_status') == 'rejected':
            needs.append({
                'id': 'kyc_rejected',
                'title': 'KYC Verification Failed',
                'description': 'Please resubmit your documents',
                'action_url': url_for('kyc.index'),
                'action_label': 'Re-submit',
                'priority': 1,
                'icon': '⚠️',
            })

        # Profile completion
        profile_completion = activity.get('profile_completion', 0)
        if profile_completion < 100 and profile_completion > 0:
            needs.append({
                'id': 'profile_incomplete',
                'title': 'Complete Your Profile',
                'description': f"{profile_completion}% complete - add missing info",
                'action_url': url_for('profile.edit_profile'),
                'action_label': 'Update Profile',
                'priority': 2,
                'icon': '📝',
            })

        # No wallet but eligible
        if not activity.get('has_wallet') and activity.get('kyc_tier', 0) >= 1:
            needs.append({
                'id': 'create_wallet',
                'title': 'Activate Your Wallet',
                'description': 'Create a wallet to make payments and receive funds',
                'action_url': url_for('wallet.wallet_create_page'),
                'action_label': 'Activate',
                'priority': 2,
                'icon': '💳',
            })

        return sorted(needs, key=lambda x: x['priority'])

    @staticmethod
    def get_welcome_message(activity: dict, user) -> str:
        """Return personalized welcome message."""
        name = user.first_name or user.username or user.email.split('@')[0]

        if not any([
            activity.get('has_events'),
            activity.get('has_wallet'),
            activity.get('has_accommodation'),
            activity.get('has_transport')
        ]):
            return f"Welcome to AFCON360, {name}! Ready to experience the tournament?"

        if activity.get('has_events'):
            upcoming_count = len(activity.get('upcoming_events', []))
            if upcoming_count > 0:
                return f"Welcome back, {name}! You have {upcoming_count} upcoming event{'s' if upcoming_count != 1 else ''}."

        return f"Welcome back, {name}!"

    @staticmethod
    def should_show_milestone(activity: dict) -> dict:
        """Check if user has reached a milestone."""
        milestones = []

        event_count = activity.get('event_count', 0)
        if event_count == 1:
            milestones.append({'message': '🎉 Your first event registration!', 'icon': '🎫'})
        elif event_count == 10:
            milestones.append({'message': '🏆 You\'re a super fan! 10 events registered!', 'icon': '🏆'})

        transaction_count = len(activity.get('recent_transactions', []))
        if transaction_count == 1:
            milestones.append({'message': '💰 Your first wallet transaction!', 'icon': '💰'})

        stay_count = activity.get('accommodation_count', 0)
        if stay_count == 1:
            milestones.append({'message': '🏨 Booked your first stay!', 'icon': '🏨'})

        trip_count = activity.get('transport_count', 0)
        if trip_count == 1:
            milestones.append({'message': '🚗 Booked your first ride!', 'icon': '🚗'})

        return milestones[0] if milestones else None


# ============================================================================
# ROUTES
# ============================================================================

@user_bp.route("/dashboard")
@login_required
@onboarding_completed
def user_dashboard():
    """Main user dashboard - Smart, adaptive, and fast."""
    from app.identity.models.user import User
    from sqlalchemy.orm import joinedload

    try:
        user = User.query.options(joinedload(User.organisations)).get(current_user.id)
        if not user:
            return redirect(url_for('auth.logout'))

        modules = current_app.config.get('MODULE_FLAGS', {})

        # Get smart dashboard data
        activity = SmartDashboard.detect_user_modules(current_user.id)
        quick_actions = SmartDashboard.get_quick_actions(activity, modules)
        needs_attention = SmartDashboard.get_needs_attention(activity)
        welcome_message = SmartDashboard.get_welcome_message(activity, user)
        milestone = SmartDashboard.should_show_milestone(activity)

        # Get wallet balance separately for display
        wallet_balance = activity.get('wallet_balance', 0)
        wallet_currency = activity.get('wallet_currency', 'UGX')

        # Get current date
        current_date = date.today().isoformat()

        # Get user's organizations for context switcher
        user_organisations = user.organisations if hasattr(user, 'organisations') else []

        # Get KYC info
        kyc_info = {
            'tier': activity.get('kyc_tier', 0),
            'tier_name': activity.get('kyc_tier_name', 'Unregistered'),
            'status': activity.get('kyc_status', 'pending'),
            'progress_percentage': activity.get('kyc_progress', 0),
        }

        # Tourism listings for discovery section (only if module enabled)
        tourism_listings = []
        if modules.get('tourism') and not activity.get('has_tourism'):
            try:
                from app.tourism.models import TourismListing
                tourism_listings = TourismListing.query.filter_by(
                    status='published', is_deleted=False
                ).order_by(TourismListing.created_at.desc()).limit(3).all()
            except Exception as e:
                logger.debug(f"Tourism listings fetch error: {e}")

        return render_template(
            'user/user_dashboard.html',
            # Smart data
            activity=activity,
            quick_actions=quick_actions,
            needs_attention=needs_attention,
            welcome_message=welcome_message,
            milestone=milestone,

            # Legacy variables (for backward compatibility)
            registrations=activity.get('upcoming_events', []) + activity.get('past_events', []),
            upcoming_count=len(activity.get('upcoming_events', [])),
            wallet_balance=wallet_balance,
            wallet_currency=wallet_currency,
            current_date=current_date,
            user_organisations=user_organisations,
            kyc_info=kyc_info,
            tourism_listings=tourism_listings,
            modules=modules,

            # Additional data
            upcoming_stays=activity.get('upcoming_stays', []),
            upcoming_trips=activity.get('upcoming_trips', []),
            recent_transactions=activity.get('recent_transactions', []),
            recent_activity=activity.get('recent_activity', []),
            profile_completion=activity.get('profile_completion', 0),
        )

    except Exception as e:
        logger.error(f"Error loading user dashboard: {e}", exc_info=True)
        modules = current_app.config.get('MODULE_FLAGS', {})

        return render_template(
            'user/user_dashboard.html',
            activity={},
            quick_actions=[],
            needs_attention=[],
            welcome_message="Welcome back!",
            milestone=None,
            registrations=[],
            upcoming_count=0,
            wallet_balance=0,
            wallet_currency='UGX',
            current_date=date.today().isoformat(),
            user_organisations=[],
            kyc_info={},
            tourism_listings=[],
            modules=modules,
            upcoming_stays=[],
            upcoming_trips=[],
            recent_transactions=[],
            recent_activity=[],
            profile_completion=0,
        )


@user_bp.route("/api/dashboard/data")
@login_required
def dashboard_api_data():
    """JSON API for dashboard data - supports AJAX refresh."""
    try:
        activity = SmartDashboard.detect_user_modules(current_user.id)
        modules = current_app.config.get('MODULE_FLAGS', {})
        quick_actions = SmartDashboard.get_quick_actions(activity, modules)
        needs_attention = SmartDashboard.get_needs_attention(activity)

        return jsonify({
            'success': True,
            'activity': activity,
            'quick_actions': quick_actions,
            'needs_attention': needs_attention,
        })
    except Exception as e:
        logger.error(f"Dashboard API error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@user_bp.route("/my-registrations")
@login_required
@onboarding_completed
def my_registrations():
    """Dedicated page for viewing and managing event registrations."""
    try:
        data = EventService.get_attendee_dashboard_data(current_user.id)
        all_registrations = data['upcoming_registrations'] + data['past_registrations']

        wallet_balance = 0
        try:
            wallet = WalletService.get_wallet_by_user_id(current_user.id)
            if wallet:
                wallet_balance = wallet.balance
        except Exception:
            pass

        current_date = date.today().isoformat()

        return render_template(
            'user/my_registrations.html',
            registrations=all_registrations,
            wallet_balance=wallet_balance,
            current_date=current_date
        )
    except Exception as e:
        logger.error(f"Error loading my registrations: {e}")
        return render_template(
            'user/my_registrations.html',
            registrations=[],
            wallet_balance=0,
            current_date=date.today().isoformat()
        )


@user_bp.route("/cancel-registration", methods=['POST'])
@login_required
def cancel_registration():
    """Cancel an event registration."""
    try:
        data = request.get_json()
        reg_ref = data.get('reg_ref')

        if not reg_ref:
            return jsonify({'success': False, 'error': 'Registration reference required'}), 400

        success, error = EventService.cancel_registration(reg_ref, current_user.id)

        if success:
            # Clear dashboard cache
            from app.extensions import cache
            cache.delete(f"user_dashboard_{current_user.id}")
            return jsonify({'success': True, 'message': 'Registration cancelled successfully'})
        else:
            return jsonify({'success': False, 'error': error or 'Failed to cancel registration'}), 400

    except Exception as e:
        logger.error(f"Error cancelling registration: {e}")
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500

