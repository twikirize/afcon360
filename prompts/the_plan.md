AFCON360 Events — Registration System Refactor
Complete Implementation Guide for Kilo (CLI Agent)
Version: 1.0
Author: AFCON360 Engineering Team
Target: Flask/SQLAlchemy event management platform


NOTE: This guide is a work-in-progress.
NOTE:THE USER/ME WILL DO DB MIGRATION AND UPGRADE MANUALLY SO IGNORE THAT  INSTRUCTION, I WILL ALSO CREATE THE  bulk_upload.py file
and fil lit so just also consider it as done same as 

📋 TABLE OF CONTENTS
Phase 0 - Critical Bugfixes (Already Completed)

Phase 1 - Model & Constants Consistency

Phase 2 - User-Facing Views

Phase 3 - Organizer & Admin Views

Phase 4 - Validation & Authorization

Phase 5 - Bulk Import (Excel/CSV)

Phase 6 - Future: AttendeeGroup (Optional)

Testing & Verification

Deployment Checklist

PHASE 0: CRITICAL BUGFIXES ✅ (COMPLETED)
The following items have been completed and verified:

0.1 - Added group_index parameter to register_for_event_optimistic()

0.2 - Created attendee_accounts.py and fixed _get_or_create_attendee_user

0.3 - Wired free path group_index values (0 for self, 1..N for others)

0.4 - Single group_booking_id generation site

0.5 - Added error handling + compensating refund logic

Proceed to Phase 1.

PHASE 1: MODEL & CONSTANTS CONSISTENCY {#phase-1}
1.1 - Add BookingType Enum to constants.py
File: app/events/constants.py

Action: Add after EventStatus class

python
class BookingType(str, Enum):
    """
    Who the registration is for, relative to who submitted the form.
    
    SELF: The registrant is booking for themselves (user_id == attendee)
    THIRD_PARTY: The registrant is booking for someone else (booked_by_user_id != attendee)
    GROUP: The registrant is part of a group booking (includes self + others)
    """
    SELF = "self"
    THIRD_PARTY = "third_party"
    GROUP = "group"
    
    @classmethod
    def values(cls) -> List[str]:
        return [bt.value for bt in cls]
    
    @classmethod
    def is_valid(cls, value: str) -> bool:
        return value in cls.values()
    
    @classmethod
    def choices(cls):
        return [(bt.value, bt.value.replace('_', ' ').title()) for bt in cls]
1.2 - Replace String Literals Throughout Codebase
File: app/events/models.py

python
# Add import
from app.events.constants import BookingType

# Update column default (around line 686)
booking_type = Column(String(30), default=BookingType.SELF.value, nullable=False, index=True)
File: app/events/services.py

python
# Add import
from app.events.constants import BookingType

# Replace all occurrences:
# 'self' → BookingType.SELF.value
# 'third_party' → BookingType.THIRD_PARTY.value
# 'group' → BookingType.GROUP.value

# Example in register_for_event:
if booking_type == BookingType.SELF.value:
    # handle self
elif booking_type == BookingType.THIRD_PARTY.value:
    # handle third party
File: app/events/payment_service.py

python
# Add import
from app.events.constants import BookingType

# Replace string literals similarly
File: app/events/routes.py

python
# Add import
from app.events.constants import BookingType

# Add validation at route boundary (in register POST handler)
booking_type = data.get('booking_type', BookingType.SELF.value)
if not BookingType.is_valid(booking_type):
    return jsonify({'success': False, 'error': f'Invalid booking_type: {booking_type}'}), 400
1.3 - Deprecate registered_by Column
File: app/events/models.py

python
# Add property that delegates to booking_type
class EventRegistration(BaseModel):
    # ... existing code ...
    
    @property
    def registered_by_display(self) -> str:
        """Deprecated - use booking_type instead. Maintained for backward compatibility."""
        import warnings
        warnings.warn(
            "registered_by is deprecated, use booking_type",
            DeprecationWarning,
            stacklevel=2
        )
        return self.booking_type
File: templates/events/attendee/my_registrations.html

jinja
{# Find line with: r.booking_type == 'self' or r.registered_by == 'self' #}

{# CHANGE TO: #}
{% if r.booking_type == 'self' %}
File: app/events/services.py

python
# In _registration_to_dict, still include registered_by for API compat
result['registered_by'] = registration.booking_type  # Not the column, but the value
1.4 - Document attendee_user_id Redundancy
File: app/events/models.py

python
# Update docstring for attendee_user_id (around line 692)

attendee_user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), 
                          nullable=True, index=True)
"""
REDUNDANT FIELD: Currently always equals user_id for third_party/group bookings,
NULL for self bookings. Reserved for future "transfer ticket" feature where
a registration can be reassigned to a different attendee without changing
the original user_id (which remains for audit trail).

Do not use this field for current business logic - use user_id and booking_type.
"""
1.5 - Add group_label Column (Migration Required)
File: app/events/models.py

python
# Add to EventRegistration class, near group_booking_id (around line 690)

# Optional, registrant-supplied label for cross-batch grouping
# (e.g., "Acme Corp - Marketing Team")
group_label = Column(String(150), nullable=True, index=True)
Create Alembic Migration:

bash
flask db revision -m "add group_label to event_registrations"
Edit the generated migration file:

python
# In the generated migration file (e.g., migrations/versions/xxxx_add_group_label.py)

def upgrade():
    op.add_column('event_registrations', sa.Column('group_label', sa.String(150), nullable=True))
    op.create_index('idx_reg_group_label', 'event_registrations', ['group_label'])

def downgrade():
    op.drop_index('idx_reg_group_label', table_name='event_registrations')
    op.drop_column('event_registrations', 'group_label')
Update services to accept group_label:

File: app/events/services.py

python
# Update register_for_event signature
def register_for_event(cls, identifier: str, user_id: int, data: Dict,
                       booking_type: str = BookingType.SELF.value,
                       attendee_email: str = None,
                       attendee_name: str = None,
                       attendee_phone: str = None,
                       group_booking_id: str = None,
                       group_index: Optional[int] = None,
                       group_label: Optional[str] = None) -> Tuple[Optional[Dict], Optional[str], Optional[str]]:
    # ... existing code ...
    
    # Forward to optimistic
    return cls.register_for_event_optimistic(
        ...,
        group_label=group_label
    )

# Update optimistic signature
def register_for_event_optimistic(cls, ..., group_label: Optional[str] = None):

# In Registration constructor:
registration = Registration(
    ...,
    group_label=group_label
)
Update routes to pass group_label:

File: app/events/routes.py

python
# In register POST handler
group_label = data.get('group_label', '').strip() or None

# Pass to EventService.register_for_event
Update _registration_to_dict:

File: app/events/services.py

python
# In _registration_to_dict method
result['group_label'] = registration.group_label
1.6 - Standardize group_index Semantics
Rule (implemented in Phase 0.3):

group_index = 0 → The booker is attending (their own row)

group_index = 1, 2, 3... → Additional attendees in submission order

Pure third-party (booker not attending) → No group_index = 0 row

Add helper for consistent ordering:

File: app/events/services.py

python
@classmethod
def get_group_registrations_ordered(cls, group_booking_id: str) -> List[Dict]:
    """Get all registrations in a group, ordered by group_index (0 first, then 1..N)"""
    Registration = cls._get_registration_class()
    registrations = Registration.query.filter_by(
        group_booking_id=group_booking_id
    ).order_by(
        func.coalesce(Registration.group_index, 0).asc()
    ).all()
    return [cls._registration_to_dict(r) for r in registrations]
PHASE 2: USER-FACING VIEWS {#phase-2}
2.1 - Fix Confirmation Page Group View
File: app/events/routes.py

Find registration_confirmation function (around line 900)

python
@events_bp.route("/registration-confirmation/<reg_ref>")
@login_required
def registration_confirmation(reg_ref):
    """Show registration confirmation with QR code"""
    try:
        from app.events.models import EventRegistration
        from sqlalchemy import func
        
        registration = EventRegistration.query.filter_by(registration_ref=reg_ref).first()
        
        # Permission check
        if not registration:
            flash('Registration not found', 'danger')
            return redirect(url_for('events.my_registrations'))
        
        # Only attendee, booker, or organizer can view
        from app.events.permissions import can_manage_registration
        if not can_manage_registration(current_user, registration):
            flash('You do not have permission to view this registration', 'danger')
            return redirect(url_for('events.my_registrations'))
        
        # Try to get group data from session first (for immediate feedback)
        session_data = session.get('last_registration')
        group_registrations = None
        group_errors = []
        
        if session_data and session_data.get('registration', {}).get('registration_ref') == reg_ref:
            group_registrations = session_data.get('group_registrations')
            group_errors = session_data.get('errors', [])
        
        # If not in session, reconstruct from database
        if group_registrations is None and registration.group_booking_id:
            siblings = EventRegistration.query.filter_by(
                group_booking_id=registration.group_booking_id
            ).order_by(
                func.coalesce(EventRegistration.group_index, 0).asc()
            ).all()
            
            if len(siblings) > 1:
                group_registrations = [
                    EventService._registration_to_dict(r) for r in siblings
                ]
        
        # Generate QR code
        qr_code = EventService._generate_qr_code(registration.qr_token, registration.registration_ref)
        event = EventService.get_event(registration.event.slug)
        
        mail_configured = bool(current_app.config.get('MAIL_SERVER'))
        
        return render_template(
            'events/attendee/registration_confirmation.html',
            registration=EventService._registration_to_dict(registration),
            qr_code=qr_code,
            event=event,
            group_registrations=group_registrations,
            errors=group_errors,
            mail_configured=mail_configured
        )
    except Exception as e:
        logger.error(f"registration_confirmation error: {e}")
        flash('An error occurred while loading the confirmation page.', 'danger')
        return redirect(url_for('events.my_registrations'))
2.2 - Add "Registrations You've Made for Others" Section
File: app/events/services.py

python
@classmethod
def get_registrations_made_for_others(cls, user_id: int) -> List[Dict]:
    """
    Get all registrations where this user booked for someone else.
    Returns registrations where booked_by_user_id == user_id AND user_id != user_id.
    """
    Registration = cls._get_registration_class()
    
    rows = Registration.query.filter(
        Registration.booked_by_user_id == user_id,
        Registration.user_id != user_id
    ).order_by(
        Registration.group_booking_id,
        func.coalesce(Registration.group_index, 0).asc()
    ).all()
    
    return [cls._registration_to_dict(r) for r in rows]

@classmethod
def group_registrations_by_batch(cls, registrations: List[Dict]) -> List[Dict]:
    """
    Group a list of registration dicts by group_booking_id.
    Returns list of {group_booking_id, group_label, event, attendees: [...]}
    """
    groups = {}
    for reg in registrations:
        gid = reg.get('group_booking_id')
        if not gid:
            # Individual registrations become their own "group"
            gid = f"single_{reg['id']}"
        
        if gid not in groups:
            groups[gid] = {
                'group_booking_id': reg.get('group_booking_id'),
                'group_label': reg.get('group_label'),
                'event': reg.get('event'),
                'attendees': []
            }
        groups[gid]['attendees'].append(reg)
    
    # Sort attendees within each group by group_index
    for gid in groups:
        groups[gid]['attendees'].sort(key=lambda x: x.get('group_index', 0))
    
    return list(groups.values())
File: app/events/routes.py

Find my_registrations function (around line 286)

python
@events_bp.route("/my-registrations")
@login_required
def my_registrations():
    """Attendee Dashboard - Detailed view of user's event registrations"""
    try:
        from app.user.routes import _enrich_registrations, _split_registrations, _get_wallet
        
        data = EventService.get_attendee_dashboard_data(current_user.id)
        all_regs = data['upcoming_registrations'] + data['past_registrations']
        _enrich_registrations(all_regs)
        upcoming_regs, past_regs = _split_registrations(all_regs)
        
        # NEW: Get registrations made for others
        managed_regs = EventService.get_registrations_made_for_others(current_user.id)
        managed_groups = EventService.group_registrations_by_batch(managed_regs)
        
        # Registrations managed by the user (booked for others)
        from app.events.models import EventRegistration as RegModel
        managed_q = RegModel.query.filter(
            RegModel.booked_by_user_id == current_user.id
        ).order_by(RegModel.created_at.desc()).all()
        managed_regs = []
        for r in managed_q:
            # Skip pure self-registrations to avoid duplication
            if r.user_id == current_user.id and (r.booking_type == 'self' or r.registered_by == 'self'):
                continue
            try:
                managed_regs.append(EventService._registration_to_dict(r))
            except Exception:
                pass

        wallet = _get_wallet()
        from datetime import date
        today = date.today().isoformat()

        return render_template(
            'user/my_registrations.html',
            registrations=all_regs,
            upcoming_registrations=upcoming_regs,
            past_registrations=past_regs,
            managed_registrations=managed_regs,
            managed_groups=managed_groups,  # ← ADD THIS
            upcoming_count=len(upcoming_regs),
            attended_count=sum(1 for r in past_regs if r.get('status') == 'checked_in'),
            total_spent="%.2f" % sum(
                (r.get('registration_fee') or 0) for r in all_regs
                if r.get('status') != 'cancelled'
            ),
            wallet=wallet,
            wallet_balance=wallet.balance if wallet else 0.0,
            current_date=today,
        )
    except Exception as exc:
        logger.error("Error loading my registrations (events bp): %s", exc)
        from datetime import date
        return render_template(
            'user/my_registrations.html',
            registrations=[], upcoming_registrations=[], past_registrations=[],
            upcoming_count=0, attended_count=0, total_spent="0.00",
            wallet=None, wallet_balance=0,
            current_date=date.today().isoformat(),
        )
File: templates/user/my_registrations.html

Add after Past Events section:

jinja
{# ── Registrations You've Made for Others ── #}
{% if managed_groups %}
<div class="card shadow-sm mb-4">
    <div class="card-header bg-info text-white">
        <h4 class="mb-0">
            <i class="fas fa-user-friends me-2"></i>
            Registrations You've Made for Others
        </h4>
        <small>These are tickets you purchased for other people</small>
    </div>
    <div class="card-body">
        {% for group in managed_groups %}
        <div class="card mb-3 border">
            <div class="card-header bg-light">
                <div class="d-flex justify-content-between align-items-center flex-wrap">
                    <div>
                        <strong>{{ group.event.name }}</strong>
                        {% if group.group_label %}
                        <span class="badge bg-secondary ms-2">{{ group.group_label }}</span>
                        {% endif %}
                    </div>
                    <div>
                        <span class="badge bg-info">{{ group.attendees|length }} attendee(s)</span>
                        {% if group.group_booking_id %}
                        <span class="badge bg-secondary ms-1">Group Booking</span>
                        {% endif %}
                    </div>
                </div>
                <small class="text-muted">
                    {% if group.group_booking_id %}
                    Reference: {{ group.group_booking_id[:8] }}...
                    {% endif %}
                </small>
            </div>
            <div class="card-body p-0">
                <div class="table-responsive">
                    <table class="table table-sm mb-0">
                        <thead class="table-light">
                            <tr>
                                <th width="50">#</th>
                                <th>Name</th>
                                <th>Email</th>
                                <th>Ticket Type</th>
                                <th>Status</th>
                                <th width="120">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for attendee in group.attendees %}
                            <tr>
                                <td>
                                    {% if attendee.group_index is not none %}
                                        {{ attendee.group_index }}
                                    {% else %}
                                        —
                                    {% endif %}
                                </td>
                                <td>{{ attendee.full_name }}</td>
                                <td>{{ attendee.email }}</td>
                                <td>{{ attendee.ticket_type|default('General')|title }}</td>
                                <td>
                                    {% if attendee.status == 'checked_in' %}
                                        <span class="badge bg-success">✓ Checked In</span>
                                    {% elif attendee.status == 'confirmed' %}
                                        <span class="badge bg-primary">Confirmed</span>
                                    {% elif attendee.status == 'cancelled' %}
                                        <span class="badge bg-danger">Cancelled</span>
                                    {% else %}
                                        <span class="badge bg-secondary">{{ attendee.status }}</span>
                                    {% endif %}
                                </td>
                                <td>
                                    <a href="{{ safe_url('events.registration_confirmation', reg_ref=attendee.registration_ref) }}"
                                       class="btn btn-sm btn-outline-primary">
                                        <i class="fas fa-qrcode"></i> View
                                    </a>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        {% endfor %}
    </div>
</div>
{% endif %}
PHASE 3: ORGANIZER & ADMIN VIEWS {#phase-3}
3.1 - Create Shared Partial for Group Display
File: templates/events/_partials/attendee_group_cell.html (CREATE NEW)

jinja
{% macro group_cell(registration) %}
    {% if registration.group_booking_id and registration.group_size and registration.group_size > 1 %}
    <span class="badge bg-info" title="Group ID: {{ registration.group_booking_id }}">
        <i class="fas fa-users"></i>
        Group of {{ registration.group_size }}
        {% if registration.group_label %}
        <br><small>{{ registration.group_label|truncate(20) }}</small>
        {% endif %}
    </span>
    {% else %}
    <span class="badge bg-secondary">Individual</span>
    {% endif %}
{% endmacro %}

{% macro booked_by_cell(registration, booker_names) %}
    {% if registration.booking_type != 'self' and registration.booked_by_user_id %}
        {{ booker_names.get(registration.booked_by_user_id, 'Unknown') }}
    {% else %}
        —
    {% endif %}
{% endmacro %}
3.2 - Update Organizer Attendees Route
File: app/events/routes.py

Find event_attendees function (around line 800)

python
@events_bp.route("/event/<identifier>/attendees")
@login_required
def event_attendees(identifier):
    """Show attendees for an event (organizer only)"""
    event = EventService.get_event(identifier)
    if not event:
        return render_template('events/public/not_found.html', event_slug=identifier), 404

    # Check if user is organizer or system admin
    if event.get('organizer_id') != current_user.id and not is_system_admin(current_user):
        flash('You do not have permission to view attendees', 'danger')
        return redirect(url_for('events.landing', identifier=identifier))

    registrations = EventService.get_registrations_by_event(identifier)
    
    # Enrich with group info
    for reg in registrations:
        if reg.get('group_booking_id'):
            # Count siblings in this event
            sibling_count = sum(1 for r in registrations 
                               if r.get('group_booking_id') == reg['group_booking_id'])
            reg['group_size'] = sibling_count
        else:
            reg['group_size'] = 1
    
    # Get booker names for third-party registrations
    booker_ids = set(r.get('booked_by_user_id') for r in registrations if r.get('booked_by_user_id'))
    booker_names = {}
    if booker_ids:
        from app.identity.models.user import User
        bookers = User.query.filter(User.id.in_(booker_ids)).all()
        booker_names = {b.id: b.username or b.email for b in bookers}
    
    for reg in registrations:
        if reg.get('booked_by_user_id'):
            reg['booked_by_name'] = booker_names.get(reg['booked_by_user_id'], 'Unknown')
    
    # Get distinct groups for filter
    distinct_groups = {}
    for reg in registrations:
        if reg.get('group_booking_id'):
            gid = reg['group_booking_id']
            if gid not in distinct_groups:
                distinct_groups[gid] = reg.get('group_label', gid[:8])
    
    stats = {
        'total': len(registrations),
        'checked_in': len([r for r in registrations if r.get('status') == 'checked_in']),
        'confirmed': len([r for r in registrations if r.get('status') == 'confirmed']),
        'cancelled': len([r for r in registrations if r.get('status') == 'cancelled']),
    }

    return render_template(
        'events/organizer/attendees.html',
        event=event,
        registrations=registrations,
        stats=stats,
        booker_names=booker_names,
        distinct_groups=distinct_groups.items()
    )
3.3 - Update Organizer Attendees Template
File: templates/events/organizer/attendees.html

Add to the top (import partial):

jinja
{% from "events/_partials/attendee_group_cell.html" import group_cell, booked_by_cell %}
Update the table headers:

jinja
<table class="table table-hover">
    <thead>
        <tr>
            <th>Name</th>
            <th>Email</th>
            <th>Group</th>
            <th>Booked By</th>
            <th>Ticket Type</th>
            <th>Status</th>
            <th>Checked In</th>
            <th>Actions</th>
        </tr>
    </thead>
    <tbody>
        {% for reg in registrations %}
        <tr data-group-id="{{ reg.group_booking_id or '' }}"
            data-group-label="{{ (reg.group_label or '')|lower }}"
            data-booking-type="{{ reg.booking_type or 'self' }}">
            <td>{{ reg.full_name }}</td>
            <td>{{ reg.email }}</td>
            <td>{{ group_cell(reg) }}</td>
            <td>{{ booked_by_cell(reg, booker_names) }}</td>
            <td>{{ reg.ticket_type|default('General')|title }}</td>
            <td>
                {% if reg.status == 'checked_in' %}
                <span class="badge bg-success">Checked In</span>
                {% elif reg.status == 'confirmed' %}
                <span class="badge bg-primary">Confirmed</span>
                {% elif reg.status == 'cancelled' %}
                <span class="badge bg-danger">Cancelled</span>
                {% else %}
                <span class="badge bg-secondary">{{ reg.status }}</span>
                {% endif %}
            </td>
            <td>
                {% if reg.checked_in_at %}
                {{ reg.checked_in_at[:16]|replace('T', ' ') }}
                {% else %}
                —
                {% endif %}
            </td>
            <td>
                <button class="btn btn-sm btn-success checkin-btn" 
                        data-qr="{{ reg.qr_token_hint }}"
                        data-name="{{ reg.full_name }}"
                        {% if reg.status == 'checked_in' %}disabled{% endif %}>
                    <i class="fas fa-check"></i> Check In
                </button>
            </td>
        </tr>
        {% endfor %}
    </tbody>
</table>
Add group filter above table:

jinja
<div class="row mb-3">
    <div class="col-md-3">
        <select id="groupFilter" class="form-select">
            <option value="">All Attendees</option>
            <option value="individual">Individual Only</option>
            <option value="group">Groups Only</option>
            <optgroup label="Specific Groups">
                {% for group_id, group_label in distinct_groups %}
                <option value="{{ group_id }}">{{ group_label|truncate(30) }}</option>
                {% endfor %}
            </optgroup>
        </select>
    </div>
    <div class="col-md-3">
        <select id="bookingTypeFilter" class="form-select">
            <option value="">All Booking Types</option>
            <option value="self">Self Registration</option>
            <option value="third_party">Booked for Someone Else</option>
            <option value="group">Group Registration</option>
        </select>
    </div>
</div>
Add filter JavaScript:

javascript
<script>
document.getElementById('groupFilter').addEventListener('change', function() {
    const value = this.value;
    const rows = document.querySelectorAll('#attendeeTable tbody tr');
    
    rows.forEach(row => {
        const groupId = row.dataset.groupId;
        
        if (value === '') {
            row.style.display = '';
        } else if (value === 'individual' && !groupId) {
            row.style.display = '';
        } else if (value === 'group' && groupId) {
            row.style.display = '';
        } else if (value === groupId) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
        }
    });
});

document.getElementById('bookingTypeFilter').addEventListener('change', function() {
    const value = this.value;
    const rows = document.querySelectorAll('#attendeeTable tbody tr');
    
    rows.forEach(row => {
        const bookingType = row.dataset.bookingType;
        
        if (value === '' || bookingType === value) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
        }
    });
});
</script>
3.4 - Apply Same to Admin Attendees List
File: templates/events/admin/attendees_list.html

Add same import and filters as Phase 3.3

PHASE 4: VALIDATION & AUTHORIZATION {#phase-4}
4.1 - Server-Side Group Size Cap
File: app/events/constants.py

python
# Add after other constants
MAX_INLINE_GROUP_SIZE = 25  # Maximum attendees per inline form submission
MAX_BULK_GROUP_SIZE = 500    # Maximum for bulk upload (Phase 5)
File: app/events/routes.py

In register POST handler, after building attendees list:

python
from app.events.constants import MAX_INLINE_GROUP_SIZE

if booking_type == 'group':
    # Count total attendees (including booker if attending)
    total_attendees = 0
    if not existing_primary:  # Booker attending
        total_attendees = 1 + len(group_attendees)
    else:
        total_attendees = len(group_attendees)
    
    if total_attendees > MAX_INLINE_GROUP_SIZE:
        return jsonify({
            'success': False,
            'error': f"Groups larger than {MAX_INLINE_GROUP_SIZE} must use bulk upload. "
                     f"Please use the 'Import from spreadsheet' option."
        }), 400
4.2 - Centralized can_manage_registration
File: app/events/permissions.py

python
from app.auth.helpers import is_system_admin as auth_is_system_admin

def can_manage_registration(user, registration, event=None) -> bool:
    """
    True if user may view/cancel/modify this registration.
    
    Permissions hierarchy:
    1. System admin → always True
    2. Event organizer → True for any registration in their event
    3. The attendee themselves → True for their own registration
    4. The person who booked it → True for registrations they paid for
    
    Returns False for anonymous users.
    """
    if not user or not user.is_authenticated:
        return False
    
    # System admin can manage anything
    if auth_is_system_admin(user):
        return True
    
    # Event organizer can manage all registrations for their event
    if event and hasattr(event, 'organizer_id') and event.organizer_id == user.id:
        return True
    
    # If we have registration but no event, try to get event
    if not event and registration and hasattr(registration, 'event'):
        event = registration.event
        if event and event.organizer_id == user.id:
            return True
    
    # Attendee or booker
    return (registration.user_id == user.id or 
            registration.booked_by_user_id == user.id)
Apply to cancel_registration route:

File: app/events/routes.py

python
from app.events.permissions import can_manage_registration

@events_bp.route("/registration/<reg_ref>/cancel", methods=['POST'])
@login_required
def cancel_registration(reg_ref):
    """Cancel a registration"""
    from app.events.models import EventRegistration
    
    registration = EventRegistration.query.filter_by(registration_ref=reg_ref).first()
    if not registration:
        return jsonify({'success': False, 'error': 'Registration not found'}), 404
    
    # Use centralized permission check
    if not can_manage_registration(current_user, registration):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    success, error = EventService.cancel_registration(reg_ref, current_user.id)
    if success:
        return jsonify({'success': True, 'message': 'Registration cancelled successfully'})
    else:
        return jsonify({'success': False, 'error': error}), 400
4.3 - Discount Codes Per-Seat Consistency
File: app/events/routes.py (Free Path)

python
# In free event group branch
discount_code = data.get('discount_code', '').strip() or None

for attendee in group_attendees:
    attendee_data = {
        'ticket_type_id': data.get('ticket_type_id'),
        'full_name': attendee_name,
        'email': attendee_email,
        'phone': attendee_phone
    }
    
    # Copy discount code to each attendee
    if discount_code:
        attendee_data['discount_code'] = discount_code
    
    reg, qr, err = EventService.register_for_event(
        identifier, 
        current_user.id, 
        attendee_data,  # ← Pass enriched data
        booking_type="third_party",
        attendee_email=attendee_email,
        attendee_name=attendee_name,
        attendee_phone=attendee_phone,
        group_booking_id=group_booking_id,
        group_index=idx
    )
File: app/events/payment_service.py (Paid Path)

python
def process_ticket_purchase(self, user_id: int, event_id: int, ticket_type_id: int,
                           quantity: int = 1, payment_method: str = "wallet",
                           mobile_money_operator: Optional[str] = None,
                           mobile_money_phone: Optional[str] = None,
                           group_attendees: Optional[List[Dict]] = None,
                           create_primary_for_payer: bool = True,
                           group_booking_id: Optional[str] = None,
                           discount_code: Optional[str] = None) -> Dict:
    """Process ticket purchase with payment integration"""
    
    # Get event and ticket type
    event = Event.query.get(event_id)
    ticket_type = TicketType.query.get(ticket_type_id)
    
    # Check for discount code BEFORE calculating price
    discount_amount = Decimal('0.00')
    if discount_code:
        from app.events.services import EventService
        discount_result, error = EventService.validate_discount_code(
            event.slug, discount_code, ticket_type_id
        )
        if error:
            return {"success": False, "error": f"Invalid discount code: {error}"}
        if discount_result:
            discount_amount = discount_result
    
    # Calculate total price with discount
    unit_price = Decimal(str(ticket_type.price))
    effective_unit_price = max(unit_price - discount_amount, Decimal('0.00'))
    total_price = effective_unit_price * quantity
    
    # Store discount info for per-row recording
    discount_info = {
        'code': discount_code,
        'amount_per_seat': float(discount_amount)
    }
    
    # ... rest of payment processing ...
    
    # Pass to _create_registrations
    registrations = self._create_registrations(
        user_id=user_id,
        event_id=event_id,
        ticket_type_id=ticket_type_id,
        quantity=quantity,
        payment_reference=payment_result.get("payment_reference"),
        group_attendees=group_attendees,
        create_primary_for_payer=create_primary_for_payer,
        group_booking_id=group_booking_id,
        discount_info=discount_info  # ← ADD
    )
Update _create_single_registration to use discount:

python
def _create_single_registration(self, user_id: int, event_id: int, ticket_type_id: int,
                                payment_reference: str, attendee_data: Optional[Dict] = None,
                                booked_by_user_id: Optional[int] = None,
                                booking_type: str = "self",
                                group_booking_id: Optional[str] = None,
                                group_index: Optional[int] = None,
                                discount_info: Optional[Dict] = None) -> Dict:
    
    # Get ticket type for pricing
    ticket_type = TicketType.query.get(ticket_type_id)
    base_price = float(ticket_type.price)
    
    # Apply discount if present
    registration_fee = base_price
    discount_code_applied = None
    discount_amount = 0.0
    
    if discount_info and discount_info.get('amount_per_seat'):
        registration_fee = max(base_price - discount_info['amount_per_seat'], 0)
        discount_code_applied = discount_info.get('code')
        discount_amount = discount_info['amount_per_seat']
    
    registration = EventRegistration(
        # ... other fields ...
        registration_fee=registration_fee,
        discount_code_applied=discount_code_applied,
        discount_amount=discount_amount,
        # ... rest of fields ...
    )
PHASE 5: BULK IMPORT (EXCEL/CSV) {#phase-5}
5.1 - Create Bulk Upload Blueprint
File: app/events/bulk_upload.py (CREATE NEW)

python
"""
Bulk event registration via Excel/CSV upload
"""
from flask import Blueprint, request, render_template, jsonify, session, current_app
from flask_login import login_required, current_user
from app.extensions import db
from app.events.constants import MAX_BULK_GROUP_SIZE
import pandas as pd
import io
import uuid
import logging

logger = logging.getLogger(__name__)

bulk_bp = Blueprint('event_bulk', __name__, url_prefix='/events/bulk')


@bulk_bp.route('/<identifier>/template')
@login_required
def download_template(identifier):
    """Download Excel template for bulk registration"""
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Attendees"
    
    # Headers
    headers = ['Full Name', 'Email Address', 'Phone Number', 'Nationality']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="E6E6E6", end_color="E6E6E6", fill_type="solid")
    
    # Example row
    ws.cell(row=2, column=1, value="John Doe")
    ws.cell(row=2, column=2, value="john@example.com")
    ws.cell(row=2, column=3, value="+256 700 123 456")
    ws.cell(row=2, column=4, value="Ugandan")
    
    # Adjust column widths
    for col in range(1, 5):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = 25
    
    # Save to response
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    from flask import send_file
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'attendee_template_{identifier}.xlsx'
    )


@bulk_bp.route('/<identifier>/upload', methods=['POST'])
@login_required
def upload_bulk(identifier):
    """Upload and validate bulk registration file"""
    try:
        from app.events.services import EventService
        from app.events.models import Event
        
        event = Event.query.filter_by(slug=identifier).first()
        if not event:
            return jsonify({'success': False, 'error': 'Event not found'}), 404
        
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        # Parse file
        if file.filename.endswith('.xlsx'):
            df = pd.read_excel(file)
        elif file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            return jsonify({'success': False, 'error': 'Unsupported file type. Use .xlsx or .csv'}), 400
        
        # Validate columns
        expected_columns = ['Full Name', 'Email Address', 'Phone Number', 'Nationality']
        missing_columns = [col for col in expected_columns if col not in df.columns]
        if missing_columns:
            return jsonify({
                'success': False, 
                'error': f'Missing columns: {", ".join(missing_columns)}'
            }), 400
        
        # Parse attendees
        attendees = []
        errors = []
        
        for idx, row in df.iterrows():
            name = str(row.get('Full Name', '')).strip()
            email = str(row.get('Email Address', '')).strip().lower()
            phone = str(row.get('Phone Number', '')).strip()
            nationality = str(row.get('Nationality', '')).strip()
            
            if not name or not email:
                errors.append(f"Row {idx + 2}: Missing name or email")
                continue
            
            if '@' not in email or '.' not in email:
                errors.append(f"Row {idx + 2}: Invalid email address")
                continue
            
            attendees.append({
                'name': name,
                'email': email,
                'phone': phone if phone and phone != 'nan' else None,
                'nationality': nationality if nationality and nationality != 'nan' else None
            })
        
        if len(attendees) > MAX_BULK_GROUP_SIZE:
            return jsonify({
                'success': False,
                'error': f'File contains {len(attendees)} attendees. Maximum is {MAX_BULK_GROUP_SIZE}.'
            }), 400
        
        # Store in session for preview
        session['bulk_attendees'] = attendees
        session['bulk_errors'] = errors
        
        return jsonify({
            'success': True,
            'total': len(attendees),
            'errors': errors,
            'preview': attendees[:10]
        })
        
    except Exception as e:
        logger.error(f"Bulk upload error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@bulk_bp.route('/<identifier>/confirm', methods=['POST'])
@login_required
def confirm_bulk(identifier):
    """Confirm and process bulk registration"""
    try:
        from app.events.services import EventService
        from app.events.models import Event
        
        event = Event.query.filter_by(slug=identifier).first()
        if not event:
            return jsonify({'success': False, 'error': 'Event not found'}), 404
        
        attendees = session.get('bulk_attendees', [])
        if not attendees:
            return jsonify({'success': False, 'error': 'No attendees to register'}), 400
        
        # Get ticket type from request
        data = request.get_json()
        ticket_type_id = data.get('ticket_type_id')
        group_label = data.get('group_label', '').strip() or None
        
        # Validate ticket type
        from app.events.models import TicketType
        ticket_type = TicketType.query.filter_by(id=ticket_type_id, event_id=event.id).first()
        if not ticket_type:
            return jsonify({'success': False, 'error': 'Invalid ticket type'}), 400
        
        # Check capacity
        if ticket_type.capacity and ticket_type.capacity > 0:
            from app.events.services import SoldOutException
            available = ticket_type.capacity - (ticket_type.available_seats or 0)
            if available < len(attendees):
                return jsonify({
                    'success': False,
                    'error': f'Only {available} tickets available, but {len(attendees)} requested'
                }), 400
        
        # Generate group booking ID
        group_booking_id = str(uuid.uuid4())
        
        # Process registrations
        registrations = []
        errors = []
        
        for idx, attendee in enumerate(attendees, start=1):
            registration_data = {
                'ticket_type_id': ticket_type_id,
                'full_name': attendee['name'],
                'email': attendee['email'],
                'phone': attendee.get('phone', ''),
                'nationality': attendee.get('nationality', '')
            }
            
            # Create or find attendee user
            from app.events.attendee_accounts import find_or_create_attendee_user
            attendee_user_id, error = find_or_create_attendee_user(
                attendee['email'], 
                attendee['name'], 
                attendee.get('phone')
            )
            
            if error:
                errors.append(f"{attendee['name']}: {error}")
                continue
            
            # Register for event
            reg, qr, err = EventService.register_for_event(
                identifier,
                current_user.id,
                registration_data,
                booking_type="third_party",
                attendee_email=attendee['email'],
                attendee_name=attendee['name'],
                attendee_phone=attendee.get('phone'),
                group_booking_id=group_booking_id,
                group_index=idx,
                group_label=group_label
            )
            
            if err:
                errors.append(f"{attendee['name']}: {err}")
            else:
                registrations.append(reg)
        
        # Clear session data
        session.pop('bulk_attendees', None)
        session.pop('bulk_errors', None)
        
        if not registrations:
            return jsonify({'success': False, 'error': f'Failed to register any attendees: {"; ".join(errors)}'}), 400
        
        # Store in session for confirmation
        first_reg = EventService._get_registration_class().query.filter_by(
            registration_ref=registrations[0]['registration_ref']
        ).first()
        
        if first_reg:
            qr_code = EventService._generate_qr_code(first_reg.qr_token, first_reg.registration_ref)
            session['last_registration'] = {
                'registration': registrations[0],
                'qr_code': qr_code,
                'event': EventService.get_event(identifier),
                'group_registrations': registrations,
                'errors': errors
            }
        
        return jsonify({
            'success': True,
            'registered': len(registrations),
            'errors': errors,
            'redirect': f'/events/registration-confirmation/{registrations[0]["registration_ref"]}'
        })
        
    except Exception as e:
        logger.error(f"Bulk confirm error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
5.2 - Register Blueprint
File: app/events/__init__.py

python
# Add to existing __init__.py
from app.events.bulk_upload import bulk_bp

def init_app(app):
    # ... existing code ...
    app.register_blueprint(bulk_bp)
PHASE 6: FUTURE - ATTENDEE GROUP MODEL (OPTIONAL) {#phase-6}
*This phase is optional and should only be implemented if organizers need managed cohorts after Phase 1-5 are live.*

6.1 - Create AttendeeGroup Models
File: app/events/models.py (Add after EventAssignment)

python
class AttendeeGroup(BaseModel):
    """Organizer-managed cohort for grouping registrations across batches"""
    __tablename__ = "event_attendee_groups"
    __table_args__ = (
        Index("idx_attendee_group_event", "event_id"),
        UniqueConstraint("event_id", "name", name="uq_group_event_name"),
    )
    
    event_id = Column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    created_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    created_by = relationship("User", foreign_keys=[created_by_id])
    event = relationship("Event", backref="attendee_groups")


class AttendeeGroupMember(BaseModel):
    """Membership between a group and a registration"""
    __tablename__ = "event_attendee_group_members"
    __table_args__ = (
        Index("idx_group_member_group", "group_id"),
        Index("idx_group_member_registration", "registration_id"),
        UniqueConstraint("group_id", "registration_id", name="uq_group_member"),
    )
    
    group_id = Column(BigInteger, ForeignKey("event_attendee_groups.id", ondelete="CASCADE"), nullable=False)
    registration_id = Column(BigInteger, ForeignKey("event_registrations.id", ondelete="CASCADE"), nullable=False)
    
    group = relationship("AttendeeGroup", backref="members")
    registration = relationship("EventRegistration", backref="group_memberships")
6.2 - Migration
bash
flask db revision -m "add attendee_group tables"
TESTING & VERIFICATION {#testing}
Test File Creation
File: tests/test_group_registration.py (CREATE NEW)

python
import pytest
from app import create_app, db
from app.events.models import Event, EventRegistration, TicketType
from app.events.constants import BookingType

class TestGroupRegistration:
    
    def setup_method(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()
        
        with self.app.app_context():
            db.create_all()
            
            self.event = Event(
                slug="test-event",
                name="Test Event", 
                city="Kampala",
                organizer_id=1,
                status="published"
            )
            db.session.add(self.event)
            db.session.flush()
            
            self.ticket_type = TicketType(
                event_id=self.event.id,
                name="General",
                price=0,
                capacity=100
            )
            db.session.add(self.ticket_type)
            db.session.commit()
    
    def teardown_method(self):
        with self.app.app_context():
            db.drop_all()
    
    def test_group_registration_sets_correct_indices(self):
        """Group of 3 → group_index = 0,1,2"""
        with self.app.app_context():
            from app.events.services import EventService
            
            data = {
                'ticket_type_id': self.ticket_type.id,
                'full_name': 'Test User',
                'email': 'test@example.com'
            }
            
            registration, qr, error = EventService.register_for_event(
                'test-event', 1, data,
                booking_type=BookingType.GROUP.value,
                group_index=0
            )
            
            assert registration is not None
            assert registration['group_index'] == 0
    
    def test_can_manage_registration_organizer(self):
        """Event organizer can cancel any registration"""
        from app.events.permissions import can_manage_registration
        from app.identity.models.user import User
        
        with self.app.app_context():
            organizer = User(id=999, email='organizer@test.com')
            organizer.is_authenticated = True
            
            registration = EventRegistration(
                event_id=self.event.id,
                user_id=100,
                booking_type='self'
            )
            
            # This should pass when event.organizer_id == organizer.id
            # Implementation depends on how you set up the test event
Running Tests
bash
# Run all tests
pytest tests/test_group_registration.py -v

# Run specific test
pytest tests/test_group_registration.py::TestGroupRegistration::test_group_registration_sets_correct_indices -v

# Run with coverage
pytest tests/test_group_registration.py --cov=app.events --cov-report=term
DEPLOYMENT CHECKLIST {#deployment}
Pre-Deployment
All Phase 0-5 changes committed

Migrations created and tested on staging

group_label column added

BookingType enum implemented

can_manage_registration function added

Bulk upload blueprint registered

Tests passing

Deployment Steps
bash
# 1. Backup database
pg_dump afcon360_prod > backup_$(date +%Y%m%d).sql

# 2. Run migrations
flask db upgrade

# 3. Deploy code
git pull origin main
# or however you deploy

# 4. Clear Redis cache (if needed)
redis-cli FLUSHDB

# 5. Restart workers
sudo systemctl restart gunicorn
sudo systemctl restart celery

# 6. Verify
curl http://localhost:5000/events/health
Rollback Plan
bash
# 1. Revert code
git revert HEAD

# 2. Downgrade migrations
flask db downgrade -1

# 3. Restart services
sudo systemctl restart gunicorn
Monitoring Queries
sql
-- Check for any registrations with user_id=1 (should be zero after fix)
SELECT COUNT(*) FROM event_registrations WHERE user_id = 1 AND created_at > NOW() - INTERVAL '1 day';

-- Check group_index distribution
SELECT group_index, COUNT(*) FROM event_registrations WHERE group_index IS NOT NULL GROUP BY group_index ORDER BY group_index;

-- Check group_label usage
SELECT group_label, COUNT(DISTINCT group_booking_id) as groups, COUNT(*) as registrations 
FROM event_registrations WHERE group_label IS NOT NULL GROUP BY group_label;
SUMMARY FOR KILO
Phases completed: Phase 0 ✅

Remaining phases to implement:

Phase	Priority	Estimated Time
Phase 1	High	2-3 hours
Phase 2	High	2-3 hours
Phase 3	Medium	3-4 hours
Phase 4	Medium	2 hours
Phase 5	Low (after P1-P4)	3-4 hours
Phase 6	Optional	N/A
Start with Phase 1.1 (BookingType enum). Each phase builds on the previous.

Ready to proceed.