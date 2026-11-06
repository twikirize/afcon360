"""
Twilio Configuration Routes for Owner Settings
These should be integrated into app/admin/owner/routes.py after test_oci_email function
"""

from flask import jsonify, redirect, url_for, flash, request, current_user
from flask_login import login_required

# These should be added to app/admin/owner/routes.py after test_oci_email function

# @owner_bp.route('/settings/twilio-config', methods=['POST'])
# @owner_login_required
# @audit_owner_action('updated_twilio_config', 'settings')
def save_twilio_config():
    """Save Twilio SMS/WhatsApp configuration"""
    try:
        from app.models.system_config import SystemConfig

        SystemConfig.set('TWILIO_ACCOUNT_SID', request.form.get('TWILIO_ACCOUNT_SID', ''),
                         value_type='str', category='sms', description='Twilio Account SID')
        SystemConfig.set('TWILIO_AUTH_TOKEN', request.form.get('TWILIO_AUTH_TOKEN', ''),
                         value_type='str', category='sms', description='Twilio Auth Token')
        SystemConfig.set('TWILIO_FROM_NUMBER', request.form.get('TWILIO_FROM_NUMBER', ''),
                         value_type='str', category='sms', description='Twilio verified sender phone number')
        SystemConfig.set('TWILIO_MESSAGING_SERVICE_SID', request.form.get('TWILIO_MESSAGING_SERVICE_SID', ''),
                         value_type='str', category='sms', description='Twilio Messaging Service SID')
        SystemConfig.set('TWILIO_WHATSAPP_FROM', request.form.get('TWILIO_WHATSAPP_FROM', ''),
                         value_type='str', category='sms', description='Twilio WhatsApp sender')
        SystemConfig.set('TWILIO_WHATSAPP_ENABLED', request.form.get('TWILIO_WHATSAPP_ENABLED', 'false').lower() == 'true',
                         value_type='bool', category='sms', description='Enable WhatsApp via Twilio')
        SystemConfig.set('TWILIO_SMS_ENABLED', request.form.get('TWILIO_SMS_ENABLED', 'false').lower() == 'true',
                         value_type='bool', category='sms', description='Enable SMS via Twilio')

        flash("✅ Twilio configuration saved successfully", "success")
        return redirect(url_for('admin.owner.settings'))
    except Exception as e:
        current_app.logger.error(f"Error saving Twilio config: {e}")
        flash("❌ Error saving Twilio configuration", "danger")
        return redirect(url_for('admin.owner.settings'))


# @owner_bp.route('/settings/twilio-sms/test', methods=['POST'])
# @owner_login_required
# @audit_owner_action('tested_twilio_sms', 'settings')
def test_twilio_sms():
    """Send a test SMS via Twilio"""
    try:
        from app.notifications.channel_handlers.twilio_sms import TwilioSmsHandler

        handler = TwilioSmsHandler()

        if not handler.account_sid or not handler.auth_token:
            return jsonify({'success': False, 'error': 'Twilio credentials not configured'}), 400

        if not handler.from_number and not handler.messaging_service_sid:
            return jsonify({'success': False, 'error': 'No from_number or messaging_service_sid configured'}), 400

        class TestNotification:
            subject = 'AFCON360 Twilio SMS Test'
            body = 'This is a test SMS from AFCON360 Twilio SMS configuration.'
            html_body = '<h2>AFCON360 Twilio SMS Test</h2><p>This is a test SMS from AFCON360 Twilio configuration.</p>'

        test_phone = current_user.phone
        if not test_phone:
            return jsonify({'success': False, 'error': 'Owner phone number not set'}), 400

        result = handler.deliver(TestNotification(), {'phone': test_phone, 'user_id': current_user.id})

        if result.get('success'):
            return jsonify({'success': True, 'message': f'Test SMS sent to {test_phone}'})
        else:
            return jsonify({'success': False, 'error': result.get('response_body')}), 500

    except Exception as e:
        current_app.logger.error(f"Error sending test Twilio SMS: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# @owner_bp.route('/settings/twilio-whatsapp/test', methods=['POST'])
# @owner_login_required
# @audit_owner_action('tested_twilio_whatsapp', 'settings')
def test_twilio_whatsapp():
    """Send a test WhatsApp message via Twilio"""
    try:
        from app.notifications.channel_handlers.twilio_sms import TwilioWhatsAppHandler

        handler = TwilioWhatsAppHandler()

        if not handler.account_sid or not handler.auth_token:
            return jsonify({'success': False, 'error': 'Twilio credentials not configured'}), 400

        if not handler.whatsapp_from:
            return jsonify({'success': False, 'error': 'WhatsApp from number not configured'}), 400

        class TestNotification:
            subject = 'AFCON360 Twilio WhatsApp Test'
            body = 'This is a test WhatsApp message from AFCON360 Twilio WhatsApp configuration.'
            html_body = '<h2>AFCON360 Twilio WhatsApp Test</h2><p>This is a test WhatsApp from AFCON360 Twilio configuration.</p>'

        test_phone = current_user.phone
        if not test_phone:
            return jsonify({'success': False, 'error': 'Owner phone number not set'}), 400

        result = handler.deliver(TestNotification(), {'phone': test_phone, 'user_id': current_user.id})

        if result.get('success'):
            return jsonify({'success': True, 'message': f'Test WhatsApp sent to {test_phone}'})
        else:
            return jsonify({'success': False, 'error': result.get('response_body')}), 500

    except Exception as e:
        current_app.logger.error(f"Error sending test Twilio WhatsApp: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500