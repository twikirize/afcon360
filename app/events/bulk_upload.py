"""
Bulk event registration via Excel/CSV upload
"""
from flask import Blueprint, request, render_template, jsonify, session, current_app
from flask_login import login_required, current_user
from app.extensions import db
from app.events.constants import MAX_BULK_GROUP_SIZE
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
    import pandas as pd
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