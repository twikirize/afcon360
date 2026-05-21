Now let's move to Phase 3: Community Host Registration.

Phase 3: Community Host Registration - Complete Implementation
What This Phase Does
Community hosts can:

Register to offer accommodation for a specific event (free or paid)

Event organizer approves/rejects applications

Approved hosts appear in the organizer's inventory for assignment

File 1: app/events/routes_community_hosts.py (NEW)
python
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
File 2: templates/events/community_host/register.html (NEW)
html
{# templates/events/community_host/register.html #}
{% extends "base.html" %}

{% block title %}Offer Community Hosting - {{ event.name }}{% endblock %}

{% block content %}
<div class="container py-4">
    <div class="row justify-content-center">
        <div class="col-md-8">
            <div class="card shadow-sm">
                <div class="card-header bg-white">
                    <h4 class="mb-0">
                        <i class="fas fa-hand-holding-heart text-primary me-2"></i>
                        Offer Community Hosting
                    </h4>
                    <p class="text-muted mb-0 small">For: {{ event.name }} · {{ event.city }}, {{ event.country }}</p>
                </div>
                <div class="card-body">
                    <div class="alert alert-info">
                        <i class="fas fa-info-circle me-2"></i>
                        <strong>What is Community Hosting?</strong><br>
                        Community hosts are local residents who offer accommodation to event attendees out of goodwill.
                        You can offer free stays or set a symbolic price. All hosts are reviewed and approved by event organizers.
                    </div>
                    
                    <form method="POST" id="hostForm">
                        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                        
                        <!-- Basic Info -->
                        <h5 class="mb-3">Property Information</h5>
                        <div class="row mb-3">
                            <div class="col-12">
                                <label class="form-label fw-bold">Listing Title *</label>
                                <input type="text" name="title" class="form-control" required 
                                       placeholder="e.g., Cozy Room in Kampala, Near Stadium">
                                <div class="form-text">Give your space a descriptive name</div>
                            </div>
                        </div>
                        
                        <div class="row mb-3">
                            <div class="col-12">
                                <label class="form-label">Short Summary</label>
                                <input type="text" name="summary" class="form-control" maxlength="500"
                                       placeholder="Brief description of your space (max 500 chars)">
                            </div>
                        </div>
                        
                        <div class="row mb-3">
                            <div class="col-12">
                                <label class="form-label">Full Description *</label>
                                <textarea name="description" class="form-control" rows="4" required
                                          placeholder="Describe your space, amenities, neighborhood, etc."></textarea>
                            </div>
                        </div>
                        
                        <!-- Location -->
                        <h5 class="mb-3 mt-4">Location</h5>
                        <div class="row mb-3">
                            <div class="col-md-8">
                                <label class="form-label fw-bold">Address Line 1 *</label>
                                <input type="text" name="address_line1" class="form-control" required>
                            </div>
                            <div class="col-md-4">
                                <label class="form-label fw-bold">Address Line 2</label>
                                <input type="text" name="address_line2" class="form-control">
                            </div>
                        </div>
                        
                        <div class="row mb-3">
                            <div class="col-md-4">
                                <label class="form-label fw-bold">City *</label>
                                <input type="text" name="city" class="form-control" required>
                            </div>
                            <div class="col-md-3">
                                <label class="form-label">State/Region</label>
                                <input type="text" name="state" class="form-control">
                            </div>
                            <div class="col-md-3">
                                <label class="form-label fw-bold">Country *</label>
                                <select name="country" class="form-select" required>
                                    <option value="UG">Uganda</option>
                                    <option value="KE">Kenya</option>
                                    <option value="TZ">Tanzania</option>
                                </select>
                            </div>
                            <div class="col-md-2">
                                <label class="form-label">Postal Code</label>
                                <input type="text" name="postal_code" class="form-control">
                            </div>
                        </div>
                        
                        <!-- Capacity -->
                        <h5 class="mb-3 mt-4">Guest Capacity</h5>
                        <div class="row mb-3">
                            <div class="col-md-3">
                                <label class="form-label fw-bold">Max Guests *</label>
                                <input type="number" name="max_guests" class="form-control" min="1" max="20" value="2" required>
                            </div>
                            <div class="col-md-3">
                                <label class="form-label">Bedrooms</label>
                                <input type="number" name="bedrooms" class="form-control" min="0" max="10" value="1">
                            </div>
                            <div class="col-md-3">
                                <label class="form-label">Beds</label>
                                <input type="number" name="beds" class="form-control" min="0" max="20" value="1">
                            </div>
                            <div class="col-md-3">
                                <label class="form-label">Bathrooms</label>
                                <input type="number" name="bathrooms" class="form-control" step="0.5" min="0" max="10" value="1">
                            </div>
                        </div>
                        
                        <!-- Pricing -->
                        <h5 class="mb-3 mt-4">Pricing</h5>
                        <div class="row mb-3">
                            <div class="col-md-6">
                                <div class="form-check mb-2">
                                    <input type="checkbox" name="is_free" class="form-check-input" id="isFreeCheck" onchange="togglePrice()">
                                    <label class="form-check-label fw-bold" for="isFreeCheck">
                                        ❤️ This is a FREE offering (no charge)
                                    </label>
                                </div>
                            </div>
                            <div class="col-md-6" id="priceField">
                                <label class="form-label fw-bold">Price per night</label>
                                <div class="input-group">
                                    <span class="input-group-text">$</span>
                                    <input type="number" name="price_per_night" class="form-control" step="1" min="0" value="0">
                                    <span class="input-group-text">USD</span>
                                </div>
                                <div class="form-text">You can set a symbolic price (e.g., $20) to cover utilities</div>
                            </div>
                        </div>
                        
                        <!-- Stay Requirements -->
                        <h5 class="mb-3 mt-4">Stay Requirements</h5>
                        <div class="row mb-3">
                            <div class="col-md-4">
                                <label class="form-label fw-bold">Minimum nights</label>
                                <input type="number" name="min_stay_nights" class="form-control" min="1" max="30" value="1">
                            </div>
                            <div class="col-md-4">
                                <label class="form-label">Maximum nights</label>
                                <input type="number" name="max_stay_nights" class="form-control" min="1" max="90" placeholder="Optional">
                            </div>
                            <div class="col-md-4">
                                <label class="form-label">Check-in time</label>
                                <input type="text" name="check_in_time" class="form-control" placeholder="e.g., 14:00">
                            </div>
                        </div>
                        
                        <!-- House Rules -->
                        <h5 class="mb-3 mt-4">House Rules</h5>
                        <div class="row mb-3">
                            <div class="col-12">
                                <textarea name="house_rules" class="form-control" rows="3"
                                          placeholder="e.g., No smoking, Quiet hours after 10pm, No pets, etc."></textarea>
                            </div>
                        </div>
                        
                        <!-- Photos -->
                        <h5 class="mb-3 mt-4">Photos</h5>
                        <div class="row mb-3">
                            <div class="col-md-6">
                                <label class="form-label">Main Photo URL</label>
                                <input type="url" name="main_image" class="form-control" placeholder="https://...">
                            </div>
                            <div class="col-md-6">
                                <label class="form-label">Gallery URLs (one per line)</label>
                                <textarea name="gallery_urls" class="form-control" rows="3" 
                                          placeholder="https://...&#10;https://..."></textarea>
                            </div>
                        </div>
                        
                        <!-- Terms -->
                        <div class="alert alert-warning mt-4">
                            <div class="form-check">
                                <input type="checkbox" class="form-check-input" id="termsCheck" required>
                                <label class="form-check-label" for="termsCheck">
                                    I confirm that I am offering accommodation in good faith for event attendees.
                                    I understand that my listing will be reviewed by the event organizer before being published.
                                </label>
                            </div>
                        </div>
                        
                        <div class="d-grid gap-2 d-md-flex justify-content-md-end mt-4">
                            <a href="{{ url_for('events.landing', identifier=event.slug) }}" class="btn btn-outline-secondary me-md-2">
                                Cancel
                            </a>
                            <button type="submit" class="btn btn-primary">
                                <i class="fas fa-paper-plane"></i> Submit Registration
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </div>
</div>

<script>
function togglePrice() {
    const isFree = document.getElementById('isFreeCheck').checked;
    const priceField = document.getElementById('priceField');
    const priceInput = document.querySelector('input[name="price_per_night"]');
    
    if (isFree) {
        priceField.style.opacity = '0.5';
        priceInput.disabled = true;
        priceInput.value = '0';
    } else {
        priceField.style.opacity = '1';
        priceInput.disabled = false;
    }
}
</script>

<style>
.form-label {
    font-size: 14px;
}
</style>
{% endblock %}
File 3: templates/events/organizer/community_hosts.html (NEW)
html
{# templates/events/organizer/community_hosts.html #}
{% extends "base.html" %}

{% block title %}Community Hosts - {{ event.name }}{% endblock %}

{% block content %}
<div class="container-fluid py-4">
    <div class="row mb-4 align-items-center">
        <div class="col">
            <h1>
                <i class="fas fa-hand-holding-heart text-primary me-2"></i>
                Community Hosts
            </h1>
            <p class="text-muted mb-0">
                {{ event.name }} · Manage community host applications
            </p>
        </div>
        <div class="col text-end">
            <a href="{{ url_for('events.organizer_dashboard', identifier=event.slug) }}" class="btn btn-outline-secondary">
                <i class="fas fa-arrow-left"></i> Back to Dashboard
            </a>
        </div>
    </div>

    <!-- Stats -->
    <div class="row mb-4 g-3">
        <div class="col-md-3">
            <div class="card text-white bg-primary">
                <div class="card-body">
                    <h3 class="mb-0" id="totalCount">0</h3>
                    <p class="mb-0">Total Applications</p>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card text-white bg-warning">
                <div class="card-body">
                    <h3 class="mb-0" id="pendingCount">0</h3>
                    <p class="mb-0">Pending Review</p>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card text-white bg-success">
                <div class="card-body">
                    <h3 class="mb-0" id="approvedCount">0</h3>
                    <p class="mb-0">Approved</p>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card text-white bg-danger">
                <div class="card-body">
                    <h3 class="mb-0" id="rejectedCount">0</h3>
                    <p class="mb-0">Rejected</p>
                </div>
            </div>
        </div>
    </div>

    <!-- Host List -->
    <div class="card shadow-sm">
        <div class="card-header bg-white">
            <h5 class="mb-0">Host Applications</h5>
        </div>
        <div class="card-body p-0">
            <div id="hostsList" class="list-group list-group-flush">
                <div class="text-center p-4">
                    <div class="spinner-border text-primary"></div>
                    <p class="mt-2">Loading hosts...</p>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- Approval Modal -->
<div class="modal fade" id="approveModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">Approve Community Host</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
                <p>Approve <strong id="approveHostName"></strong> as a community host for this event?</p>
                <p class="text-muted small">Approved hosts will appear in your accommodation inventory and can be assigned to attendees.</p>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                <button type="button" class="btn btn-success" onclick="confirmApprove()">Approve</button>
            </div>
        </div>
    </div>
</div>

<!-- Reject Modal -->
<div class="modal fade" id="rejectModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">Reject Community Host</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
                <p>Reject <strong id="rejectHostName"></strong>'s application?</p>
                <div class="mb-3">
                    <label class="form-label">Reason (optional)</label>
                    <textarea id="rejectReason" class="form-control" rows="3" placeholder="Explain why this application is being rejected..."></textarea>
                </div>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                <button type="button" class="btn btn-danger" onclick="confirmReject()">Reject</button>
            </div>
        </div>
    </div>
</div>

<style>
.host-card {
    transition: all 0.2s;
}
.host-card:hover {
    background-color: #f8f9fa;
}
.status-badge {
    font-size: 11px;
    padding: 4px 10px;
    border-radius: 20px;
}
.status-pending {
    background-color: #ffc107;
    color: #333;
}
.status-approved {
    background-color: #28a745;
    color: white;
}
.status-rejected {
    background-color: #dc3545;
    color: white;
}
.host-avatar {
    width: 60px;
    height: 60px;
    border-radius: 50%;
    background-color: #e9ecef;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 24px;
}
</style>

<script>
let currentEventSlug = '{{ event.slug }}';
let hosts = [];
let selectedHostId = null;
let selectedHostName = null;

async function loadHosts() {
    try {
        const response = await fetch(`/events/api/${currentEventSlug}/community-hosts`);
        const data = await response.json();
        if (data.success) {
            hosts = data.hosts;
            renderHosts();
            updateStats();
        }
    } catch (error) {
        console.error('Error loading hosts:', error);
        document.getElementById('hostsList').innerHTML = `
            <div class="text-center p-4 text-danger">
                <i class="fas fa-exclamation-triangle fa-2x"></i>
                <p>Error loading hosts</p>
            </div>
        `;
    }
}

function renderHosts() {
    const container = document.getElementById('hostsList');
    
    if (hosts.length === 0) {
        container.innerHTML = `
            <div class="text-center p-4 text-muted">
                <i class="fas fa-info-circle fa-2x"></i>
                <p>No community host applications yet.</p>
                <small>Share the registration link with community members who want to offer accommodation.</small>
            </div>
        `;
        return;
    }
    
    container.innerHTML = hosts.map(host => `
        <div class="list-group-item host-card p-3">
            <div class="row align-items-center">
                <div class="col-auto">
                    <div class="host-avatar">
                        ${host.main_image ? 
                            `<img src="${host.main_image}" style="width: 60px; height: 60px; border-radius: 50%; object-fit: cover;">` :
                            '<i class="fas fa-user-friends"></i>'
                        }
                    </div>
                </div>
                <div class="col">
                    <div class="d-flex justify-content-between align-items-start">
                        <div>
                            <h5 class="mb-1">${escapeHtml(host.title)}</h5>
                            <div class="small text-muted">
                                <i class="fas fa-user"></i> ${escapeHtml(host.host_name)} · 
                                <i class="fas fa-map-marker-alt"></i> ${escapeHtml(host.city)}
                            </div>
                            <div class="mt-1">
                                <span class="badge ${host.is_free ? 'bg-success' : 'bg-primary'}">
                                    ${host.is_free ? 'FREE' : `$${host.price_per_night}/night`}
                                </span>
                                <span class="badge bg-secondary">${host.max_guests} guests</span>
                            </div>
                            ${host.description ? `<div class="small text-muted mt-1">${escapeHtml(host.description)}</div>` : ''}
                        </div>
                        <div class="text-end">
                            <span class="status-badge status-${host.status}">
                                ${host.status === 'pending' ? '⏳ Pending' : host.status === 'approved' ? '✓ Approved' : '✗ Rejected'}
                            </span>
                            ${host.status === 'pending' ? `
                                <div class="mt-2">
                                    <button class="btn btn-sm btn-success me-1" onclick="showApproveModal(${host.id}, '${escapeHtml(host.title)}')">
                                        <i class="fas fa-check"></i> Approve
                                    </button>
                                    <button class="btn btn-sm btn-danger" onclick="showRejectModal(${host.id}, '${escapeHtml(host.title)}')">
                                        <i class="fas fa-times"></i> Reject
                                    </button>
                                </div>
                            ` : ''}
                            ${host.status === 'approved' ? `
                                <div class="small text-muted mt-2">
                                    Approved on ${host.approved_at ? new Date(host.approved_at).toLocaleDateString() : 'recently'}
                                </div>
                            ` : ''}
                            ${host.status === 'rejected' && host.rejection_reason ? `
                                <div class="small text-danger mt-2">
                                    Reason: ${escapeHtml(host.rejection_reason)}
                                </div>
                            ` : ''}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `).join('');
}

function updateStats() {
    const total = hosts.length;
    const pending = hosts.filter(h => h.status === 'pending').length;
    const approved = hosts.filter(h => h.status === 'approved').length;
    const rejected = hosts.filter(h => h.status === 'rejected').length;
    
    document.getElementById('totalCount').innerText = total;
    document.getElementById('pendingCount').innerText = pending;
    document.getElementById('approvedCount').innerText = approved;
    document.getElementById('rejectedCount').innerText = rejected;
}

function showApproveModal(hostId, hostName) {
    selectedHostId = hostId;
    selectedHostName = hostName;
    document.getElementById('approveHostName').innerText = hostName;
    new bootstrap.Modal(document.getElementById('approveModal')).show();
}

function confirmApprove() {
    const modal = bootstrap.Modal.getInstance(document.getElementById('approveModal'));
    modal.hide();
    
    fetch(`/events/api/${currentEventSlug}/community-hosts/${selectedHostId}/approve`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            loadHosts();
            alert('✓ Host approved successfully');
        } else {
            alert('Error: ' + data.error);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Network error');
    });
}

function showRejectModal(hostId, hostName) {
    selectedHostId = hostId;
    selectedHostName = hostName;
    document.getElementById('rejectHostName').innerText = hostName;
    document.getElementById('rejectReason').value = '';
    new bootstrap.Modal(document.getElementById('rejectModal')).show();
}

function confirmReject() {
    const reason = document.getElementById('rejectReason').value;
    const modal = bootstrap.Modal.getInstance(document.getElementById('rejectModal'));
    modal.hide();
    
    fetch(`/events/api/${currentEventSlug}/community-hosts/${selectedHostId}/reject`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
        },
        body: JSON.stringify({ reason: reason })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            loadHosts();
            alert('Host rejected');
        } else {
            alert('Error: ' + data.error);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Network error');
    });
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

document.addEventListener('DOMContentLoaded', function() {
    loadHosts();
});
</script>
{% endblock %}
Step 4: Add Navigation Links
Add to organizer dashboard - already have "Manage Accommodation", add "Community Hosts":

html
<div class="col-6">
    <a href="{{ url_for('events.community_hosts_list', slug=event.slug) }}" 
       class="card text-center text-decoration-none p-3 hover-shadow-sm border">
        <i class="fas fa-hand-holding-heart fa-2x mb-2 text-success"></i>
        <div class="small fw-bold text-dark">Community Hosts</div>
    </a>
</div>
Add to event landing page (for hosts to register):

html
{% if current_user.is_authenticated %}
<div class="mt-4 p-3 bg-light rounded">
    <h5><i class="fas fa-hand-holding-heart"></i> Community Hosting</h5>
    <p>Offer free or paid accommodation to event attendees.</p>
    <a href="{{ url_for('events.community_host_register', slug=event.slug) }}" class="btn btn-outline-success">
        Register as Community Host
    </a>
</div>
{% endif %}
Phase 4: Attendee "My Accommodation" Page (Coming Next)
After Phase 3 is complete, Phase 4 will show attendees their assigned accommodation.

Summary for Codium
Send this prompt:

text
Implement Phase 3: Community Host Registration for the AFCON360 platform.

Create these 3 new files:

1. app/events/routes_community_hosts.py - [PASTE FULL CODE ABOVE]

2. templates/events/community_host/register.html - [PASTE FULL CODE ABOVE]

3. templates/events/organizer/community_hosts.html - [PASTE FULL CODE ABOVE]

Add navigation links to:
- templates/events/organizer/organizer_dashboard.html - Add "Community Hosts" card
- templates/events/public/landing.html - Add "Register as Community Host" button for authenticated users

DO NOT delete or modify any existing Phase 1 or Phase 2 files.

After implementation, run: flask db upgrade (no new migration needed - community_host_id already exists)

markdown
# AFCON360 - Complete System Context for Codium

## 🎯 PROJECT VISION

AFCON360 is a unified platform for AFCON 2027 happening across Uganda, Kenya, and Tanzania. It allows travelers to book accommodation, arrange transport, and manage event tickets all in one place.

**The Bigger Vision:** After AFCON 2027, this platform will expand across Africa and globally, becoming a super-app for major events (World Cup, Olympics, pilgrimages, crusades).

**Unique Differentiator:** Community Hosts - people who offer free or low-cost accommodation out of goodwill (church members hosting pilgrims, locals hosting event attendees).

---

## 🏗️ SYSTEM ARCHITECTURE
┌─────────────────────────────────────────────────────────────┐
│ PRESENTATION LAYER │
│ Templates: accommodation/, events/, wallet/, transport/ │
└─────────────────────────────────────────────────────────────┘
│
┌─────────────────────────────────────────────────────────────┐
│ APPLICATION LAYER │
│ Routes: accommodation/routes.py, events/routes.py │
│ Routes: events/routes_accommodation.py (Phase 2) │
│ Routes: events/routes_community_hosts.py (Phase 3) │
└─────────────────────────────────────────────────────────────┘
│
┌─────────────────────────────────────────────────────────────┐
│ SERVICE LAYER │
│ BookingService, AvailabilityService, EventService │
│ search_service, pricing_service, host_service │
└─────────────────────────────────────────────────────────────┘
│
┌─────────────────────────────────────────────────────────────┐
│ DATA LAYER │
│ Models: Property, AccommodationBooking, Event, │
│ EventRegistration, EventAssignment │
└─────────────────────────────────────────────────────────────┘

text

---

## 📁 CRITICAL FILES (DO NOT DELETE)

### Accommodation Module
| File | Purpose |
|------|---------|
| `app/accommodation/models/property.py` | Property types (HOTEL, INDIVIDUAL, COMMUNITY_HOST) |
| `app/accommodation/models/booking.py` | Booking with event_id, context_type |
| `app/accommodation/services/search_service.py` | Public search (EXCLUDES community hosts) |
| `app/accommodation/routes/explore_routes.py` | Phase 1 - Map-first search |
| `templates/accommodation/explore.html` | Phase 1 - Map UI |

### Events Module
| File | Purpose |
|------|---------|
| `app/events/models.py` | Event, EventRegistration, EventAssignment |
| `app/events/services.py` | Event CRUD, registration, assignment |
| `app/events/routes.py` | Event landing, organizer dashboard |
| `app/events/routes_accommodation.py` | Phase 2 - Organizer assignment UI |
| `app/events/routes_community_hosts.py` | Phase 3 - Host registration/approval |

### Templates
| File | Purpose |
|------|---------|
| `templates/accommodation/explore.html` | Public map search |
| `templates/events/organizer/accommodation_manage.html` | Organizer assigns attendees |
| `templates/events/organizer/community_hosts.html` | Organizer approves hosts |
| `templates/events/community_host/register.html` | Hosts offer accommodation |

---

## 🔑 KEY ENUMS & CONSTANTS

### AccommodationPropertyType (property.py)
```python
ENTIRE_PLACE = "entire_place"    # Airbnb-style, shown in public search
PRIVATE_ROOM = "private_room"    # Shown in public search
SHARED_ROOM = "shared_room"      # Shown in public search
HOTEL_ROOM = "hotel_room"        # Shown in public search
COMMUNITY_HOST = "community_host" # NOT shown in public search! Event-only
BookingContextType (booking.py)
python
NONE = "none"      # Standalone booking (public)
EVENT = "event"    # Booked for an event
GROUP = "group"    # Group booking
ORGANIZER = "organizer"  # Organizer booking on behalf
ASSIGNED = "assigned"    # Assigned to attendee
EventStatus (constants.py)
python
DRAFT → PENDING_APPROVAL → APPROVED → PUBLISHED → COMPLETED → ARCHIVED
                                    ↓
                              SUSPENDED, PAUSED, CANCELLED
🔄 COMPLETE WORKFLOWS
Workflow 1: Public User Books Accommodation
text
User → /accommodation/explore → Search (map) → Select property → Checkout → Booking created (event_id=NULL)
Workflow 2: Event Organizer Manages Accommodation (Phase 2)
text
Organizer → Event dashboard → "Manage Accommodation"
         → See attendees needing accommodation
         → See available inventory (hotel rooms + approved community hosts)
         → Select attendee → Select inventory → Assign
         → EventAssignment created with accommodation_booking_id or community_host_id
Workflow 3: Community Host Registration (Phase 3)
text
Host → Event landing page → "Register as Community Host"
     → Fill form (title, address, capacity, price: free or paid)
     → Property created with type=COMMUNITY_HOST, status=PENDING_REVIEW
     → Organizer → "Community Hosts" page → Approve/Reject
     → Upon approval: status=ACTIVE, appears in organizer's inventory
Workflow 4: Standalone Accommodation Search (Phase 1)
text
User → /accommodation/explore → Map view → Filter by type (HOTEL, INDIVIDUAL only)
     → COMMUNITY_HOST properties are EXCLUDED from all public search results
⚡ CRITICAL RULES FOR CODIUM
Rule 1: NEVER Delete Existing Code
Always add new code, never delete existing functionality

When modifying a file, use ADDITIVE changes only

Rule 2: Community Hosts Are NEVER Public
In search_service.py, always filter out COMMUNITY_HOST

In explore_routes.py, exclude community hosts from API results

Community hosts appear ONLY in event organizer views

Rule 3: Use Existing Patterns
Follow the same error handling pattern (try/except with db.rollback)

Follow the same permission checks (event.organizer_id == current_user.id)

Follow the same JSON response format ({'success': True/False, ...})

Rule 4: Maintain Loose Coupling
Events module does NOT directly import accommodation models (uses signals)

Accommodation module can have optional event_id fields (nullable)

Use try/except ImportError when importing cross-module

Rule 5: Always Include CSRF Protection
html
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
javascript
headers: { 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content }
Rule 6: Database Migrations
After adding columns, inform user to run:

bash
flask db migrate -m "Description of change"
flask db upgrade
📋 PHASE STATUS
Phase	Feature	Status	Files
1	Map-first public search	✅ COMPLETE	explore_routes.py, explore.html
2	Organizer accommodation management	✅ COMPLETE	routes_accommodation.py, accommodation_manage.html
3	Community host registration	⏳ IN PROGRESS	routes_community_hosts.py, register.html, community_hosts.html
4	Attendee "My Accommodation" page	❌ NOT STARTED	assignment_routes.py, my_accommodation.html
🚀 HOW TO USE THIS DOCUMENT
When asking Codium to implement a new feature:

Reference this document: "Refer to CONTEXT_FOR_CODIUM.md"

Specify which Phase you're working on

List the specific files to create/modify

State any special rules

Example prompt:

text
Refer to CONTEXT_FOR_CODIUM.md. Implement Phase 4: Attendee "My Accommodation" page.

Create:
- app/accommodation/routes/assignment_routes.py
- templates/accommodation/guest/my_accommodation.html

Rules: Show assigned accommodation (hotel or community host), include host contact info for community hosts.
🔗 USEFUL ENDPOINTS
Endpoint	Purpose
/accommodation/explore	Public map search
/events/<slug>/accommodation	Organizer assignment UI
/events/<slug>/community-hosts	Organizer host approval
/events/<slug>/community-hosts/register	Host registration form
/accommodation/my-accommodation	Attendee view (Phase 4)
📝 NOTES FOR CODIUM
You are helping build a production system for AFCON 2027

The system must handle high traffic (50,000+ concurrent users)

Community hosting is the unique differentiator from Airbnb/Booking.com

Always prioritize data integrity over convenience

Never hard-delete records (use soft delete with is_deleted flag)

Always add audit logging for sensitive actions

Last Updated: May 20, 2026
Version: 1.0
Maintainer: AFCON360 Development Team

text

---

## How to Use This with Codium

Now, whenever you give Codium a task, **reference this context file**:

### Example Prompt for Phase 4:
Refer to CONTEXT_FOR_CODIUM.md (in project root).

Implement Phase 4: Attendee "My Accommodation" page.

WHAT THIS DOES:
Attendees can see what accommodation they've been assigned to (hotel or community host).

CREATE THESE FILES:

app/accommodation/routes/assignment_routes.py

GET /accommodation/my-accommodation - render page

GET /api/accommodation/my-accommodation - JSON endpoint

templates/accommodation/guest/my_accommodation.html

Show assigned hotel or community host

For community host: show host name, contact info, address

For hotel: show hotel name, room number (if available), check-in instructions

Include map link for location

MODIFY THESE FILES (ADDITIVE ONLY):

app/accommodation/init.py - register new blueprint

templates/base.html - add "My Accommodation" link in user menu (if authenticated)

RULES:

Use existing EventAssignment model

Query assignments where attendee_id = current_user.id

JOIN with Property and AccommodationBooking as needed

DO NOT delete any existing code

DO NOT modify Phase 1, 2, or 3 files except to add links

After implementation, tell me to test at /accommodation/my-accommodation

text

---

**This context file will keep Codium aligned with your vision.** Save it to your project root and reference it in every prompt. 🎯