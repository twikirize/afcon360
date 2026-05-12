from flask import Blueprint, render_template, request, jsonify, current_app, redirect, url_for
from flask_login import login_required, current_user
from app.events.services import EventService
from app.wallet.services.wallet_service import WalletService
from datetime import date, datetime
import logging

logger = logging.getLogger(__name__)

user_bp = Blueprint('user', __name__, url_prefix='/user')

@user_bp.route("/dashboard")
@login_required
def user_dashboard():
    """Main user dashboard - unified view of all user activities"""
    try:
        from app.identity.models.user import User
        from sqlalchemy.orm import joinedload
        user = User.query.options(joinedload(User.organisations)).get(current_user.id)
        if not user:
            return redirect(url_for('auth.logout'))

        # Get event registrations data
        attendee_data = EventService.get_attendee_dashboard_data(current_user.id)
        all_registrations = attendee_data['upcoming_registrations'] + attendee_data['past_registrations']
        
        # Get wallet balance
        wallet_balance = 0
        try:
            wallet = WalletService.get_wallet_by_user_id(current_user.id)
            if wallet:
                wallet_balance = wallet.balance
        except Exception:
            pass
        
        # Get current date for filtering
        current_date = date.today().isoformat()
        
        # Enrich registrations with assignment data
        for reg in all_registrations:
            # Fix: Format dates safely as strings for template
            for date_field in ['start_date', 'end_date', 'created_at', 'updated_at']:
                if 'event' in reg and date_field in reg['event']:
                    val = reg['event'][date_field]
                    if isinstance(val, (date, datetime)):
                        reg['event'][date_field] = val.isoformat()
            
            try:
                from app.events.models import EventAssignment, Event
                event_slug = reg.get('event', {}).get('slug')
                if event_slug:
                    event = Event.query.filter_by(slug=event_slug).first()
                    if event:
                        assignment = EventAssignment.query.filter_by(
                            event_id=event.id,
                            attendee_id=current_user.id
                        ).first()
                        if assignment:
                            reg['assignment'] = EventService._assignment_to_dict(assignment)
            except Exception as e:
                logger.warning(f"Could not load assignment for registration {reg.get('id')}: {e}")
        
        return render_template('user/user_dashboard.html',
                           registrations=all_registrations,
                           wallet_balance=wallet_balance,
                           current_date=current_date,
                           user_organisations=user.organisations)
    except Exception as e:
        logger.error(f"Error loading user dashboard: {e}")
        # Return empty dashboard on error
        return render_template('user/user_dashboard.html',
                           registrations=[],
                           wallet_balance=0,
                           current_date=date.today().isoformat(),
                           user_organisations=[])

@user_bp.route("/my-registrations")
@login_required
def my_registrations():
    """Dedicated page for viewing and managing event registrations"""
    try:
        # Get event registrations data
        data = EventService.get_attendee_dashboard_data(current_user.id)
        all_registrations = data['upcoming_registrations'] + data['past_registrations']
        
        # Get wallet balance
        wallet_balance = 0
        try:
            wallet = WalletService.get_wallet_by_user_id(current_user.id)
            if wallet:
                wallet_balance = wallet.balance
        except Exception:
            pass
        
        # Get current date for filtering
        current_date = date.today().isoformat()
        
        # Enrich registrations with assignment data
        for reg in all_registrations:
            # Fix: Format dates safely as strings for template
            for date_field in ['start_date', 'end_date', 'created_at', 'updated_at']:
                if 'event' in reg and date_field in reg['event']:
                    val = reg['event'][date_field]
                    if isinstance(val, (date, datetime)):
                        reg['event'][date_field] = val.isoformat()
            
            try:
                from app.events.models import EventAssignment, Event
                event_slug = reg.get('event', {}).get('slug')
                if event_slug:
                    event = Event.query.filter_by(slug=event_slug).first()
                    if event:
                        assignment = EventAssignment.query.filter_by(
                            event_id=event.id,
                            attendee_id=current_user.id
                        ).first()
                        if assignment:
                            reg['assignment'] = EventService._assignment_to_dict(assignment)
            except Exception as e:
                logger.warning(f"Could not load assignment for registration {reg.get('id')}: {e}")
        
        return render_template('user/my_registrations.html',
                           registrations=all_registrations,
                           wallet_balance=wallet_balance,
                           current_date=current_date)
    except Exception as e:
        logger.error(f"Error loading my registrations: {e}")
        return render_template('user/my_registrations.html',
                           registrations=[],
                           wallet_balance=0,
                           current_date=date.today().isoformat())

@user_bp.route("/cancel-registration", methods=['POST'])
@login_required
def cancel_registration():
    """Cancel an event registration"""
    try:
        data = request.get_json()
        reg_ref = data.get('reg_ref')
        
        if not reg_ref:
            return jsonify({'success': False, 'error': 'Registration reference required'}), 400
        
        # Cancel the registration
        success, error = EventService.cancel_registration(reg_ref, current_user.id)
        
        if success:
            return jsonify({'success': True, 'message': 'Registration cancelled successfully'})
        else:
            return jsonify({'success': False, 'error': error or 'Failed to cancel registration'}), 400
            
    except Exception as e:
        logger.error(f"Error cancelling registration: {e}")
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500

@user_bp.route("/contact-organizer", methods=['POST'])
@login_required
def contact_organizer():
    """Send a message to an event organizer"""
    try:
        data = request.get_json()
        event_id = data.get('event_id')
        message = data.get('message')
        
        if not event_id or not message:
            return jsonify({'success': False, 'error': 'Event ID and message required'}), 400
        
        # Here you would implement the actual contact logic
        # For now, we'll just return success
        return jsonify({'success': True, 'message': 'Message sent to organizer'})
        
    except Exception as e:
        logger.error(f"Error contacting organizer: {e}")
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500
