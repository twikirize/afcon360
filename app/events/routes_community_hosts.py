# app/events/routes_community_hosts.py
"""Community Host Registration Routes - Refactored with proper relationships"""

from flask import render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from decimal import Decimal
from datetime import datetime, timezone

from app.events import events_bp
from app.events.services import EventService
from app.events.models import Event, EventHostRegistration
from app.accommodation.models.property import Property, AccommodationPropertyType, AccommodationPropertyStatus
from app.extensions import db
from slugify import slugify
import logging

logger = logging.getLogger(__name__)


@events_bp.route("/<slug>/community-hosts/register", methods=['GET', 'POST'])
@login_required
def community_host_register(slug):
    """
    Community host registration page.
    Hosts offer free or paid accommodation for an event.
    """
    event = EventService.get_event_model(slug)
    if not event:
        flash('Event not found', 'danger')
        return redirect(url_for('events.list'))
    
    # Check if user is already registered as a host for this event
    existing_registration = EventHostRegistration.query.filter_by(
        event_id=event.id,
        host_user_id=current_user.id
    ).first()
    
    if existing_registration:
        flash('You have already registered as a community host for this event.', 'info')
        return redirect(url_for('events.landing', identifier=slug))
    
    if request.method == 'GET':
        return render_template('events/community_host/register.html', event=event)
    
    # POST: Handle registration
    try:
        data = request.form
        
        # Validate required fields
        required = ['title', 'address_line1', 'city', 'max_guests']
        for field in required:
            if not data.get(field):
                flash(f'Missing required field: {field}', 'danger')
                return redirect(url_for('events.community_host_register', slug=slug))
        
        # Check if user already has a property (reuse existing if possible)
        existing_property = Property.query.filter_by(
            owner_user_id=current_user.id,
            property_type=AccommodationPropertyType.COMMUNITY_HOST,
            is_deleted=False
        ).first()
        
        if existing_property:
            property = existing_property
        else:
            # Create new property
            base_slug = slugify(data['title'])
            unique_slug = base_slug
            counter = 1
            while Property.query.filter_by(slug=unique_slug).first():
                unique_slug = f"{base_slug}-{counter}"
                counter += 1
            
            is_free = data.get('is_free') == 'on' or data.get('price_per_night') == '0'
            price = Decimal('0') if is_free else Decimal(str(data.get('price_per_night', 0)))
            
            property = Property(
                owner_user_id=current_user.id,
                owner_org_id=None,
                title=data['title'],
                slug=unique_slug,
                description=data.get('description', ''),
                summary=data.get('summary', '')[:500],
                property_type=AccommodationPropertyType.COMMUNITY_HOST,
                address_line1=data['address_line1'],
                address_line2=data.get('address_line2'),
                city=data['city'],
                state=data.get('state'),
                country=data.get('country', 'UG'),
                postal_code=data.get('postal_code'),
                latitude=float(data['latitude']) if data.get('latitude') else None,
                longitude=float(data['longitude']) if data.get('longitude') else None,
                max_guests=int(data['max_guests']),
                bedrooms=int(data.get('bedrooms', 1)),
                beds=int(data.get('beds', 1)),
                bathrooms=float(data.get('bathrooms', 1)),
                base_price_per_night=price,
                currency=data.get('currency', 'USD'),
                min_stay_nights=int(data.get('min_stay_nights', 1)),
                max_stay_nights=int(data.get('max_stay_nights')) if data.get('max_stay_nights') else None,
                check_in_time=data.get('check_in_time', '14:00'),
                check_out_time=data.get('check_out_time', '11:00'),
                house_rules=data.get('house_rules'),
                main_image=data.get('main_image'),
                gallery=data.get('gallery_urls', '').split('\n') if data.get('gallery_urls') else [],
                is_active=False,
                is_verified=False,
                status=AccommodationPropertyStatus.PENDING_REVIEW,
            )
            db.session.add(property)
            db.session.flush()
        
        # Create host registration for this event
        is_free = data.get('is_free') == 'on' or data.get('price_per_night') == '0'
        price = Decimal('0') if is_free else Decimal(str(data.get('price_per_night', 0)))
        
        host_registration = EventHostRegistration(
            event_id=event.id,
            property_id=property.id,
            host_user_id=current_user.id,
            status='pending',
            price_per_night=price if not is_free else None,
            currency=data.get('currency', 'USD'),
            is_free=is_free,
            max_guests=int(data['max_guests']) if data.get('max_guests') else None,
            special_instructions=data.get('special_instructions'),
            registered_at=datetime.now(timezone.utc)
        )
        
        db.session.add(host_registration)
        db.session.commit()
        
        flash('Your community host registration has been submitted. The event organizer will review and approve it.', 'success')
        return redirect(url_for('events.landing', identifier=slug))
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Community host registration error: {e}", exc_info=True)
        flash(f'Registration failed: {str(e)}', 'danger')
        return redirect(url_for('events.community_host_register', slug=slug))


@events_bp.route("/<slug>/community-hosts")
@login_required
def community_hosts_list(slug):
    """
    Organizer view: List all community host applications for an event.
    """
    event = EventService.get_event_model(slug)
    if not event:
        flash('Event not found', 'danger')
        return redirect(url_for('events.my_events'))
    
    # Check permission: organizer or admin
    if event.organizer_id != current_user.id and not current_user.has_global_role('admin'):
        flash('You do not have permission to manage community hosts', 'danger')
        return redirect(url_for('events.landing', identifier=slug))
    
    return render_template('events/organizer/community_hosts.html', event=event)


@events_bp.route("/api/<slug>/community-hosts")
@login_required
def api_community_hosts_list(slug):
    """
    API: Get all community host applications for an event.
    """
    event = EventService.get_event_model(slug)
    if not event or (event.organizer_id != current_user.id and not current_user.has_global_role('admin')):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    # Get host registrations for this event
    registrations = EventHostRegistration.query.filter_by(
        event_id=event.id
    ).order_by(EventHostRegistration.registered_at.desc()).all()
    
    hosts_data = []
    for reg in registrations:
        property = reg.property
        hosts_data.append({
            'id': reg.id,
            'property_id': property.id,
            'title': property.title,
            'description': property.description[:200] if property.description else '',
            'address': property.address_line1,
            'city': property.city,
            'max_guests': reg.max_guests or property.max_guests,
            'price_per_night': float(reg.price_per_night) if reg.price_per_night else 0,
            'is_free': reg.is_free,
            'host_name': property.owner_display_name,
            'host_email': property.owner_user.email if property.owner_user else None,
            'host_phone': property.owner_user.phone if property.owner_user else None,
            'main_image': property.main_image,
            'status': reg.status,
            'registered_at': reg.registered_at.isoformat() if reg.registered_at else None,
            'approved_at': reg.approved_at.isoformat() if reg.approved_at else None,
            'rejected_at': reg.rejected_at.isoformat() if reg.rejected_at else None,
            'rejection_reason': reg.rejection_reason,
            'created_at': property.created_at.isoformat() if property.created_at else None
        })
    
    return jsonify({'success': True, 'hosts': hosts_data})


@events_bp.route("/api/<slug>/community-hosts/<int:registration_id>/approve", methods=['POST'])
@login_required
def api_community_host_approve(slug, registration_id):
    """
    Organizer approves a community host application.
    """
    event = EventService.get_event_model(slug)
    if not event or (event.organizer_id != current_user.id and not current_user.has_global_role('admin')):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    registration = EventHostRegistration.query.get_or_404(registration_id)
    
    if registration.event_id != event.id:
        return jsonify({'success': False, 'error': 'Registration not for this event'}), 400
    
    try:
        registration.status = 'approved'
        registration.approved_at = datetime.now(timezone.utc)
        registration.approved_by_id = current_user.id
        
        # Also update property status
        property = registration.property
        property.status = AccommodationPropertyStatus.ACTIVE
        property.is_active = True
        property.is_verified = True
        
        db.session.commit()
        
        logger.info(f"Community host {registration.property_id} approved for event {event.slug} by user {current_user.id}")
        
        return jsonify({'success': True, 'message': 'Host approved successfully'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error approving host: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@events_bp.route("/api/<slug>/community-hosts/<int:registration_id>/reject", methods=['POST'])
@login_required
def api_community_host_reject(slug, registration_id):
    """
    Organizer rejects a community host application.
    """
    event = EventService.get_event_model(slug)
    if not event or (event.organizer_id != current_user.id and not current_user.has_global_role('admin')):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    registration = EventHostRegistration.query.get_or_404(registration_id)
    
    if registration.event_id != event.id:
        return jsonify({'success': False, 'error': 'Registration not for this event'}), 400
    
    data = request.get_json()
    reason = data.get('reason', 'No reason provided')
    
    try:
        registration.status = 'rejected'
        registration.rejected_at = datetime.now(timezone.utc)
        registration.rejection_reason = reason
        
        # Property remains but is not active for this event
        db.session.commit()
        
        logger.info(f"Community host {registration.property_id} rejected for event {event.slug} by user {current_user.id}")
        
        return jsonify({'success': True, 'message': 'Host rejected'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error rejecting host: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@events_bp.route("/api/<slug>/community-hosts/<int:registration_id>/delete", methods=['DELETE'])
@login_required
def api_community_host_delete(slug, registration_id):
    """
    Organizer deletes a community host application (soft delete).
    """
    event = EventService.get_event_model(slug)
    if not event or (event.organizer_id != current_user.id and not current_user.has_global_role('admin')):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    registration = EventHostRegistration.query.get_or_404(registration_id)
    
    if registration.event_id != event.id:
        return jsonify({'success': False, 'error': 'Registration not for this event'}), 400
    
    try:
        db.session.delete(registration)
        db.session.commit()
        
        logger.info(f"Community host registration {registration_id} deleted for event {event.slug} by user {current_user.id}")
        
        return jsonify({'success': True, 'message': 'Host registration deleted'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting host: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
