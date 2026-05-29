# app/events/routes_community_hosts.py
"""
Community Host Registration Routes
- Hosts can register to offer accommodation for events
- Organizers can approve/reject applications
"""

from flask import render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app.events import events_bp
from app.events.services import EventService
from app.events.models import Event
from app.accommodation.models.property import Property, AccommodationPropertyType, AccommodationPropertyStatus
from app.extensions import db
from app.auth.decorators import require_role
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
    
    # Check if user is already a community host for this event
    existing_host = Property.query.filter(
        Property.owner_user_id == current_user.id,
        Property.property_type == AccommodationPropertyType.COMMUNITY_HOST,
        Property.event_metadata['event_id'].astext == str(event.id)
    ).first()
    
    if existing_host:
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
        
        # Create property as COMMUNITY_HOST
        from slugify import slugify
        base_slug = slugify(data['title'])
        unique_slug = base_slug
        counter = 1
        while Property.query.filter_by(slug=unique_slug).first():
            unique_slug = f"{base_slug}-{counter}"
            counter += 1
        
        is_free = data.get('is_free') == 'on' or data.get('price_per_night') == '0'
        price = 0 if is_free else float(data.get('price_per_night', 0))
        
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
            latitude=data.get('latitude', type=float) if data.get('latitude') else None,
            longitude=data.get('longitude', type=float) if data.get('longitude') else None,
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
            is_active=False,  # Needs organizer approval
            is_verified=False,
            status=AccommodationPropertyStatus.PENDING_REVIEW,
            event_metadata={
                'event_id': event.id,
                'event_slug': event.slug,
                'event_name': event.name,
                'registration_status': 'pending',  # pending, approved, rejected
                'registered_at': db.func.now(),
                'is_free': is_free
            }
        )
        
        db.session.add(property)
        db.session.commit()
        
        flash('Your community host registration has been submitted. The event organizer will review and approve it.', 'success')
        return redirect(url_for('events.landing', identifier=slug))
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Community host registration error: {e}")
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
    
    # Find all community hosts with event_metadata for this event
    # Using JSON query for PostgreSQL
    from sqlalchemy import cast, String
    from sqlalchemy.sql import text
    
    hosts = Property.query.filter(
        Property.property_type == AccommodationPropertyType.COMMUNITY_HOST,
        Property.event_metadata['event_id'].astext == str(event.id)
    ).order_by(Property.created_at.desc()).all()
    
    hosts_data = []
    for host in hosts:
        metadata = host.event_metadata or {}
        hosts_data.append({
            'id': host.id,
            'title': host.title,
            'description': host.description[:200] if host.description else '',
            'address': host.address_line1,
            'city': host.city,
            'max_guests': host.max_guests,
            'price_per_night': float(host.base_price_per_night) if host.base_price_per_night else 0,
            'is_free': host.base_price_per_night == 0,
            'host_name': host.owner_display_name,
            'host_email': host.owner_user.email if host.owner_user else None,
            'host_phone': host.owner_user.phone if host.owner_user else None,
            'main_image': host.main_image,
            'status': metadata.get('registration_status', 'pending'),
            'registered_at': metadata.get('registered_at'),
            'approved_at': metadata.get('approved_at'),
            'rejected_at': metadata.get('rejected_at'),
            'rejection_reason': metadata.get('rejection_reason'),
            'created_at': host.created_at.isoformat() if host.created_at else None
        })
    
    return jsonify({'success': True, 'hosts': hosts_data})


@events_bp.route("/api/<slug>/community-hosts/<int:host_id>/approve", methods=['POST'])
@login_required
def api_community_host_approve(slug, host_id):
    """
    Organizer approves a community host application.
    """
    event = EventService.get_event_model(slug)
    if not event or (event.organizer_id != current_user.id and not current_user.has_global_role('admin')):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    host = Property.query.get_or_404(host_id)
    
    # Verify this host belongs to this event
    metadata = host.event_metadata or {}
    if metadata.get('event_id') != event.id:
        return jsonify({'success': False, 'error': 'Host not registered for this event'}), 400
    
    try:
        # Update host status
        host.status = AccommodationPropertyStatus.ACTIVE
        host.is_active = True
        host.is_verified = True
        
        # Update metadata
        metadata['registration_status'] = 'approved'
        metadata['approved_at'] = db.func.now()
        metadata['approved_by'] = current_user.id
        host.event_metadata = metadata
        
        db.session.commit()
        
        # TODO: Send email notification to host
        
        logger.info(f"Community host {host.id} approved for event {event.slug} by user {current_user.id}")
        
        return jsonify({'success': True, 'message': 'Host approved successfully'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error approving host: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@events_bp.route("/api/<slug>/community-hosts/<int:host_id>/reject", methods=['POST'])
@login_required
def api_community_host_reject(slug, host_id):
    """
    Organizer rejects a community host application.
    """
    event = EventService.get_event_model(slug)
    if not event or (event.organizer_id != current_user.id and not current_user.has_global_role('admin')):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    host = Property.query.get_or_404(host_id)
    
    # Verify this host belongs to this event
    metadata = host.event_metadata or {}
    if metadata.get('event_id') != event.id:
        return jsonify({'success': False, 'error': 'Host not registered for this event'}), 400
    
    data = request.get_json()
    reason = data.get('reason', 'No reason provided')
    
    try:
        # Update host status
        host.status = AccommodationPropertyStatus.REJECTED
        host.is_active = False
        
        # Update metadata
        metadata['registration_status'] = 'rejected'
        metadata['rejected_at'] = db.func.now()
        metadata['rejected_by'] = current_user.id
        metadata['rejection_reason'] = reason
        host.event_metadata = metadata
        
        db.session.commit()
        
        # TODO: Send email notification to host
        
        logger.info(f"Community host {host.id} rejected for event {event.slug} by user {current_user.id}")
        
        return jsonify({'success': True, 'message': 'Host rejected'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error rejecting host: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@events_bp.route("/api/<slug>/community-hosts/<int:host_id>/delete", methods=['DELETE'])
@login_required
def api_community_host_delete(slug, host_id):
    """
    Organizer deletes a community host application (soft delete).
    """
    event = EventService.get_event_model(slug)
    if not event or (event.organizer_id != current_user.id and not current_user.has_global_role('admin')):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    host = Property.query.get_or_404(host_id)
    
    # Verify this host belongs to this event
    metadata = host.event_metadata or {}
    if metadata.get('event_id') != event.id:
        return jsonify({'success': False, 'error': 'Host not registered for this event'}), 400
    
    try:
        host.soft_delete()
        db.session.commit()
        
        logger.info(f"Community host {host.id} deleted for event {event.slug} by user {current_user.id}")
        
        return jsonify({'success': True, 'message': 'Host deleted'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting host: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
