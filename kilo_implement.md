STATUS: Where We Are
Item	Status
User Dashboard Audit	✅ Complete
Phase 1-3 Fixes	✅ Complete
Email Configuration	✅ Working (test email sent successfully)
Contact Organizer Feature	❌ IN PROGRESS - Not Started
Orphaned Blueprints	⏸️ Deferred
N+1 Queries	⏸️ Deferred
Current Block: Nothing blocking. Ready to implement Contact Organizer.

END GOAL: What We Want to Achieve
User Goal: When a user clicks "Contact Organizer" on an event registration, they can send a message to the event organizer.

Organizer Goal: Receive the message BOTH:

In their email inbox (immediate notification)

In their organizer dashboard (permanent record, read/unread tracking)

System Goal: All messages stored in database for audit trail and history.

Flow:

text
User clicks "Contact Organizer" 
       ↓
Types message in modal
       ↓
Clicks Send
       ↓
System saves to database (unread)
       ↓
System sends email to organizer
       ↓
System sends confirmation email to user
       ↓
Organizer sees email + dashboard badge
       ↓
Organizer replies via email OR dashboard
Files to be created/modified:

app/events/models.py - Add OrganizerMessage table

app/events/routes.py - Add 3 new routes

templates/email/organizer_message.html - New email template

templates/email/message_confirmation.html - New email template

templates/events/organizer/messages.html - New dashboard page

templates/user/my_registrations.html - Update JavaScript

app/user/routes.py - Delete old stub

IMPLEMENTATION: How Kilo Should Implement
Follow these steps in order. After each step, report back: "Step X complete"

Step 1: Add Database Model
File: app/events/models.py

Add this at the bottom of the file (before any closing brackets):

python
class OrganizerMessage(db.Model):
    __tablename__ = 'organizer_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(50), unique=True, default=lambda: str(uuid.uuid4()))
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='unread')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    event = db.relationship('Event', backref='messages')
    user = db.relationship('User', backref='organizer_messages')
Also ensure at top of file: import uuid and from datetime import datetime if not already there.

Step 2: Run Database Migration
bash
flask db migrate -m "Add organizer_messages table"
flask db upgrade
Step 3: Create Email Template 1 (Organizer Notification)
File: templates/email/organizer_message.html

html
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
</head>
<body style="font-family: Arial, sans-serif; padding: 20px;">
    <h2 style="color: #667eea;">New Message from an Attendee</h2>
    
    <p><strong>Event:</strong> {{ event_name }}</p>
    <p><strong>From:</strong> {{ user_name }} ({{ user_email }})</p>
    
    <div style="background: #f7fafc; padding: 15px; border-left: 4px solid #667eea; margin: 20px 0;">
        <p><strong>Message:</strong></p>
        <p>{{ message }}</p>
    </div>
    
    <p>Reply directly to <a href="mailto:{{ user_email }}">{{ user_email }}</a> to respond.</p>
    
    <hr style="margin: 30px 0;">
    <p style="color: #718096; font-size: 12px;">Sent via AFCON360</p>
</body>
</html>
Step 4: Create Email Template 2 (User Confirmation)
File: templates/email/message_confirmation.html

html
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
</head>
<body style="font-family: Arial, sans-serif; padding: 20px;">
    <h2 style="color: #48bb78;">Message Sent Successfully</h2>
    
    <p>Dear {{ user_name }},</p>
    
    <p>Your message to the organizer of <strong>{{ event_name }}</strong> has been sent.</p>
    
    <p>The organizer will respond to you via email.</p>
    
    <p>Thank you for using AFCON360.</p>
    
    <hr style="margin: 30px 0;">
    <p style="color: #718096; font-size: 12px;">Sent via AFCON360</p>
</body>
</html>
Step 5: Add Contact Route to Event Blueprint
File: app/events/routes.py

Add these imports at the top (if not already present):

python
from flask_mail import Message
from app.extensions import mail
Add this route (anywhere after the existing routes):

python
@events_bp.route("/<int:event_id>/contact-organizer", methods=['POST'])
@login_required
def contact_organizer(event_id):
    """Send a message to event organizer"""
    try:
        from app.events.models import Event, OrganizerMessage
        from app.identity.models.user import User
        
        data = request.get_json()
        message_text = data.get('message')
        
        if not message_text:
            return jsonify({'success': False, 'error': 'Message is required'}), 400
        
        event = Event.query.get(event_id)
        if not event:
            return jsonify({'success': False, 'error': 'Event not found'}), 404
        
        # Save message to database
        new_message = OrganizerMessage(
            event_id=event_id,
            user_id=current_user.id,
            message=message_text,
            status='unread'
        )
        db.session.add(new_message)
        db.session.commit()
        
        # Send email to organizer
        organizer = User.query.get(event.organizer_id) if event.organizer_id else None
        if organizer and organizer.email:
            msg = Message(
                subject=f"[AFCON360] New message about {event.name}",
                recipients=[organizer.email],
                reply_to=current_user.email
            )
            msg.html = render_template('email/organizer_message.html',
                event_name=event.name,
                user_name=current_user.username or current_user.email,
                user_email=current_user.email,
                message=message_text
            )
            mail.send(msg)
        
        # Send confirmation to user
        confirm_msg = Message(
            subject=f"[AFCON360] Your message to {event.name} was sent",
            recipients=[current_user.email]
        )
        confirm_msg.html = render_template('email/message_confirmation.html',
            event_name=event.name,
            user_name=current_user.username or current_user.email
        )
        mail.send(confirm_msg)
        
        return jsonify({'success': True, 'message': 'Message sent to organizer'})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error contacting organizer: {e}")
        return jsonify({'success': False, 'error': 'Failed to send message'}), 500
Step 6: Add Mark-as-Read Route
File: app/events/routes.py

python
@events_bp.route("/messages/<int:message_id>/read", methods=['POST'])
@login_required
def mark_message_read(message_id):
    """Mark a message as read (organizer only)"""
    try:
        from app.events.models import OrganizerMessage
        
        message = OrganizerMessage.query.get(message_id)
        if not message:
            return jsonify({'success': False, 'error': 'Message not found'}), 404
        
        # Verify user is the event organizer
        if message.event.organizer_id != current_user.id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        message.status = 'read'
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
Step 7: Add Messages Dashboard Route
File: app/events/routes.py

python
@events_bp.route("/organizer/messages")
@login_required
def organizer_messages():
    """View messages from attendees (organizer only)"""
    from app.events.models import OrganizerMessage, Event
    
    messages = OrganizerMessage.query.join(Event)\
        .filter(Event.organizer_id == current_user.id)\
        .order_by(OrganizerMessage.created_at.desc())\
        .all()
    
    return render_template('events/organizer/messages.html', messages=messages)
Step 8: Create Messages Dashboard Template
File: templates/events/organizer/messages.html

html
{% extends "base.html" %}

{% block title %}Messages - Organizer Dashboard{% endblock %}

{% block content %}
<div class="container py-4">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h1>Messages from Attendees</h1>
        <a href="{{ url_for('events.organizer_dashboard') }}" class="btn btn-outline-secondary">
            <i class="fas fa-arrow-left"></i> Back to Dashboard
        </a>
    </div>
    
    {% if messages %}
        {% for msg in messages %}
        <div class="card mb-3 {% if msg.status == 'unread' %}border-primary{% endif %}">
            <div class="card-body">
                <div class="d-flex justify-content-between align-items-start">
                    <div>
                        <strong>{{ msg.user.username or msg.user.email }}</strong>
                        <span class="text-muted mx-2">•</span>
                        <small class="text-muted">{{ msg.created_at.strftime('%Y-%m-%d %H:%M') }}</small>
                    </div>
                    {% if msg.status == 'unread' %}
                    <span class="badge bg-primary">Unread</span>
                    {% endif %}
                </div>
                <div class="mt-2">
                    <strong>Event:</strong> {{ msg.event.name }}
                </div>
                <div class="mt-3 p-3 bg-light rounded">
                    {{ msg.message }}
                </div>
                <div class="mt-3">
                    <a href="mailto:{{ msg.user.email }}" class="btn btn-sm btn-primary">
                        <i class="fas fa-reply"></i> Reply by Email
                    </a>
                    {% if msg.status == 'unread' %}
                    <button onclick="markAsRead({{ msg.id }})" class="btn btn-sm btn-outline-secondary">
                        <i class="fas fa-check"></i> Mark as Read
                    </button>
                    {% endif %}
                </div>
            </div>
        </div>
        {% endfor %}
    {% else %}
        <div class="text-center py-5">
            <i class="fas fa-inbox fa-3x text-muted mb-3"></i>
            <p class="text-muted">No messages yet.</p>
        </div>
    {% endif %}
</div>

<script>
function markAsRead(messageId) {
    fetch(`/events/messages/${messageId}/read`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': document.querySelector('input[name="csrf_token"]')?.value || ''
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            location.reload();
        }
    });
}
</script>
{% endblock %}
Step 9: Update Frontend JavaScript
File: templates/user/my_registrations.html

Find the sendContactMessage function (around line 370-380) and replace it with:

javascript
function sendContactMessage(event) {
    event.preventDefault();
    const message = document.getElementById('contactMessage').value;
    const eventId = currentEventId;
    
    // Show sending indicator
    const submitBtn = event.target.querySelector('button[type="submit"]');
    const originalText = submitBtn.innerHTML;
    submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sending...';
    submitBtn.disabled = true;
    
    fetch(`/events/${eventId}/contact-organizer`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': document.querySelector('input[name="csrf_token"]')?.value || ''
        },
        body: JSON.stringify({ message: message })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert('✓ Message sent to organizer!');
            closeContactModal();
        } else {
            alert('✗ Error: ' + data.error);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('✗ Failed to send message. Please try again.');
    })
    .finally(() => {
        submitBtn.innerHTML = originalText;
        submitBtn.disabled = false;
    });
}
Step 10: Delete Old Stub from User Routes
File: app/user/routes.py

Find and DELETE the old contact_organizer() function (around lines 177-190). It should look like:

python
@user_bp.route("/contact-organizer", methods=['POST'])
@login_required
def contact_organizer():
    """Send a message to an event organizer"""
    try:
        data = request.get_json()
        ...
        return jsonify({'success': True, 'message': 'Message sent to organizer'})
Delete the entire function. It's replaced by the event blueprint version.

Step 11: Add Messages Link to Organizer Dashboard (Optional)
File: templates/events/organizer/organizer_dashboard.html

Add this card/link somewhere on the organizer dashboard:

html
<a href="{{ url_for('events.organizer_messages') }}" class="dashboard-card">
    <i class="fas fa-envelope"></i>
    <h3>Messages</h3>
    <p>View messages from attendees</p>
</a>
GO / NO-GO
Kilo, you have the complete implementation plan.

Step	Description	Status
1	Add model to models.py	⏸️
2	Run migration	⏸️
3	Create email template 1	⏸️
4	Create email template 2	⏸️
5	Add contact route	⏸️
6	Add mark-as-read route	⏸️
7	Add messages dashboard route	⏸️
8	Create messages template	⏸️
9	Update frontend JS	⏸️
10	Delete old stub	⏸️
11	Add dashboard link (optional)	⏸️
Execute Step 1 through Step 10 in order. Report after each step.

GO.