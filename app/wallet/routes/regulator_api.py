# app/wallet/routes/regulator_api.py
"""
Regulator and Aggregator API Routes

Provides secure, compliant API endpoints for:
- Regulatory bodies accessing compliance data
- Payment aggregators receiving transaction events
- Legal data sharing with audit trails
- Encrypted data transmission
"""

import json
import hashlib
import hmac
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app
from functools import wraps

from app.wallet.services.regulator_service import RegulatorService
from app.audit.comprehensive_audit import AuditService


regulator_api = Blueprint('regulator_api', __name__, url_prefix='/api/v1/regulator')


def require_regulator_auth(f):
    """Decorator to require regulator authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        access_code = request.headers.get('X-Access-Code')
        
        if not access_code:
            return jsonify({
                'success': False,
                'error': 'Access code required',
                'error_code': 'MISSING_ACCESS_CODE'
            }), 401
        
        # Validate access code
        regulator_service = RegulatorService()
        validation = regulator_service.validate_access_code(
            access_code,
            request.remote_addr,
            request.user_agent.string if request.user_agent else ''
        )
        
        if not validation['valid']:
            return jsonify({
                'success': False,
                'error': validation['error'],
                'error_code': 'INVALID_ACCESS_CODE'
            }), 401
        
        # Store permissions in request context
        request.regulator_permissions = validation['permissions']
        request.regulator_access_code = access_code
        
        return f(*args, **kwargs)
    
    return decorated_function


def verify_webhook_signature(f):
    """Decorator to verify webhook signatures"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        signature = request.headers.get('X-Webhook-Signature')
        aggregator_id = request.headers.get('X-Aggregator-ID')
        
        if not signature or not aggregator_id:
            return jsonify({
                'success': False,
                'error': 'Missing signature or aggregator ID',
                'error_code': 'MISSING_HEADERS'
            }), 401
        
        # Get webhook configuration
        regulator_service = RegulatorService()
        webhook_config = regulator_service._get_webhook_config(aggregator_id)
        
        if not webhook_config:
            return jsonify({
                'success': False,
                'error': 'Unknown aggregator',
                'error_code': 'UNKNOWN_AGGREGATOR'
            }), 401
        
        # Verify signature
        payload = request.get_json()
        expected_signature = regulator_service._generate_webhook_signature(
            payload, webhook_config['secret_key']
        )
        
        if not hmac.compare_digest(signature, expected_signature):
            return jsonify({
                'success': False,
                'error': 'Invalid signature',
                'error_code': 'INVALID_SIGNATURE'
            }), 401
        
        return f(*args, **kwargs)
    
    return decorated_function


@regulator_api.route('/generate-access', methods=['POST'])
def generate_access_code():
    """Generate new access code for regulator"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['regulator_id', 'permissions', 'duration_hours']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}',
                    'error_code': 'MISSING_FIELD'
                }), 400
        
        # Generate access code
        regulator_service = RegulatorService()
        result = regulator_service.generate_access_code(
            regulator_id=data['regulator_id'],
            permissions=data['permissions'],
            duration_hours=data.get('duration_hours', 24),
            created_by=data.get('created_by', 1)
        )
        
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"Generate access code error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'error_code': 'INTERNAL_ERROR'
        }), 500


@regulator_api.route('/validate-access', methods=['POST'])
def validate_access_code():
    """Validate access code"""
    try:
        data = request.get_json()
        
        if 'access_code' not in data:
            return jsonify({
                'success': False,
                'error': 'Access code required',
                'error_code': 'MISSING_ACCESS_CODE'
            }), 400
        
        regulator_service = RegulatorService()
        result = regulator_service.validate_access_code(
            data['access_code'],
            request.remote_addr,
            request.user_agent.string if request.user_agent else ''
        )
        
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"Validate access code error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'error_code': 'INTERNAL_ERROR'
        }), 500


@regulator_api.route('/reports/<report_type>', methods=['GET'])
@require_regulator_auth
def get_compliance_report(report_type):
    """Get compliance report"""
    try:
        # Check permissions
        if f"report_{report_type}" not in request.regulator_permissions:
            return jsonify({
                'success': False,
                'error': f'Insufficient permissions for {report_type} report',
                'error_code': 'INSUFFICIENT_PERMISSIONS'
            }), 403
        
        # Get date range from query parameters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if start_date:
            start_date = datetime.fromisoformat(start_date)
        else:
            start_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        
        if end_date:
            end_date = datetime.fromisoformat(end_date)
        else:
            end_date = datetime.now(timezone.utc)
        
        # Generate report
        regulator_service = RegulatorService()
        result = regulator_service.generate_compliance_report(
            report_type=report_type,
            start_date=start_date,
            end_date=end_date,
            regulator_id=request.headers.get('X-Regulator-ID', 'unknown'),
            access_code=request.regulator_access_code
        )
        
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"Get compliance report error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'error_code': 'INTERNAL_ERROR'
        }), 500


@regulator_api.route('/reports/types', methods=['GET'])
@require_regulator_auth
def get_report_types():
    """Get available report types"""
    try:
        # Check permissions
        if 'report_list' not in request.regulator_permissions:
            return jsonify({
                'success': False,
                'error': 'Insufficient permissions for report list',
                'error_code': 'INSUFFICIENT_PERMISSIONS'
            }), 403
        
        report_types = {
            'daily': {
                'name': 'Daily Transaction Report',
                'description': 'All transactions for a specific day',
                'required_permissions': ['report_daily']
            },
            'weekly': {
                'name': 'Weekly Transaction Report',
                'description': 'Weekly summary with daily breakdown',
                'required_permissions': ['report_weekly']
            },
            'monthly': {
                'name': 'Monthly Transaction Report',
                'description': 'Monthly summary with gateway breakdown',
                'required_permissions': ['report_monthly']
            },
            'aml': {
                'name': 'AML Compliance Report',
                'description': 'Anti-Money Laundering compliance data',
                'required_permissions': ['report_aml']
            },
            'kyc': {
                'name': 'KYC Compliance Report',
                'description': 'Know Your Customer compliance data',
                'required_permissions': ['report_kyc']
            },
            'suspicious': {
                'name': 'Suspicious Activity Report',
                'description': 'Flagged suspicious transactions',
                'required_permissions': ['report_suspicious']
            },
            'compliance': {
                'name': 'Full Compliance Report',
                'description': 'Comprehensive compliance package',
                'required_permissions': ['report_compliance']
            }
        }
        
        return jsonify({
            'success': True,
            'report_types': report_types
        })
        
    except Exception as e:
        current_app.logger.error(f"Get report types error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'error_code': 'INTERNAL_ERROR'
        }), 500


@regulator_api.route('/aggregator/setup', methods=['POST'])
def setup_aggregator_webhook():
    """Setup webhook for payment aggregator"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['aggregator_id', 'webhook_url', 'secret_key', 'events']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}',
                    'error_code': 'MISSING_FIELD'
                }), 400
        
        # Setup webhook
        regulator_service = RegulatorService()
        result = regulator_service.setup_aggregator_webhook(
            aggregator_id=data['aggregator_id'],
            webhook_url=data['webhook_url'],
            secret_key=data['secret_key'],
            events=data['events']
        )
        
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"Setup aggregator webhook error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'error_code': 'INTERNAL_ERROR'
        }), 500


@regulator_api.route('/aggregator/webhook', methods=['POST'])
@verify_webhook_signature
def aggregator_webhook():
    """Receive webhook from payment aggregator"""
    try:
        # Get aggregator ID from headers
        aggregator_id = request.headers.get('X-Aggregator-ID')
        
        # Get event type
        event_type = request.headers.get('X-Event-Type', 'transaction')
        
        # Get event data
        event_data = request.get_json()
        
        # Process webhook event
        regulator_service = RegulatorService()
        success = regulator_service.send_aggregator_event(
            aggregator_id=aggregator_id,
            event_type=event_type,
            event_data=event_data
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Webhook received successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to process webhook',
                'error_code': 'WEBHOOK_PROCESSING_ERROR'
            }), 500
        
    except Exception as e:
        current_app.logger.error(f"Aggregator webhook error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'error_code': 'INTERNAL_ERROR'
        }), 500


@regulator_api.route('/aggregator/events', methods=['POST'])
@require_regulator_auth
def send_aggregator_event():
    """Send event to aggregator"""
    try:
        # Check permissions
        if 'aggregator_manage' not in request.regulator_permissions:
            return jsonify({
                'success': False,
                'error': 'Insufficient permissions for aggregator management',
                'error_code': 'INSUFFICIENT_PERMISSIONS'
            }), 403
        
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['aggregator_id', 'event_type', 'event_data']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}',
                    'error_code': 'MISSING_FIELD'
                }), 400
        
        # Send event
        regulator_service = RegulatorService()
        success = regulator_service.send_aggregator_event(
            aggregator_id=data['aggregator_id'],
            event_type=data['event_type'],
            event_data=data['event_data']
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Event sent successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to send event',
                'error_code': 'EVENT_SENDING_ERROR'
            }), 500
        
    except Exception as e:
        current_app.logger.error(f"Send aggregator event error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'error_code': 'INTERNAL_ERROR'
        }), 500


@regulator_api.route('/status', methods=['GET'])
def api_status():
    """Get API status and health"""
    try:
        return jsonify({
            'success': True,
            'status': 'healthy',
            'version': '1.0.0',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'endpoints': {
                'generate_access': '/api/v1/regulator/generate-access',
                'validate_access': '/api/v1/regulator/validate-access',
                'reports': '/api/v1/regulator/reports/<report_type>',
                'report_types': '/api/v1/regulator/reports/types',
                'aggregator_setup': '/api/v1/regulator/aggregator/setup',
                'aggregator_webhook': '/api/v1/regulator/aggregator/webhook',
                'aggregator_events': '/api/v1/regulator/aggregator/events',
                'status': '/api/v1/regulator/status'
            },
            'authentication': {
                'type': 'Access Code',
                'header': 'X-Access-Code',
                'validation': 'HMAC-SHA256'
            },
            'webhook_authentication': {
                'type': 'HMAC-SHA256',
                'signature_header': 'X-Webhook-Signature',
                'aggregator_header': 'X-Aggregator-ID'
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"API status error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'error_code': 'INTERNAL_ERROR'
        }), 500


@regulator_api.route('/documentation', methods=['GET'])
def api_documentation():
    """Get API documentation"""
    try:
        documentation = {
            'title': 'AFCON360 Regulator API',
            'version': '1.0.0',
            'base_url': request.url_root,
            'authentication': {
                'type': 'Access Code',
                'description': 'Use time-limited access codes generated by system owner',
                'header': 'X-Access-Code',
                'example': 'X-Access-Code: REG-ABC123DEF456'
            },
            'endpoints': [
                {
                    'path': '/generate-access',
                    'method': 'POST',
                    'description': 'Generate new access code for regulator',
                    'parameters': {
                        'regulator_id': 'string (required)',
                        'permissions': 'array (required)',
                        'duration_hours': 'integer (optional, default: 24)',
                        'created_by': 'integer (optional, default: 1)'
                    },
                    'example': {
                        'regulator_id': 'bank_of_uganda',
                        'permissions': ['report_daily', 'report_weekly'],
                        'duration_hours': 48
                    }
                },
                {
                    'path': '/reports/<report_type>',
                    'method': 'GET',
                    'description': 'Get compliance report',
                    'parameters': {
                        'report_type': 'string (required)',
                        'start_date': 'string (optional, ISO format)',
                        'end_date': 'string (optional, ISO format)'
                    },
                    'headers': {
                        'X-Access-Code': 'string (required)',
                        'X-Regulator-ID': 'string (optional)'
                    },
                    'example': {
                        'report_type': 'daily',
                        'start_date': '2025-05-01T00:00:00Z',
                        'end_date': '2025-05-01T23:59:59Z'
                    }
                }
            ],
            'webhooks': {
                'description': 'Aggregators can receive real-time transaction events',
                'setup': {
                    'endpoint': '/aggregator/setup',
                    'method': 'POST',
                    'description': 'Configure webhook URL and events'
                },
                'receive': {
                    'endpoint': '/aggregator/webhook',
                    'method': 'POST',
                    'description': 'Receive webhook events from aggregators',
                    'authentication': 'HMAC-SHA256 signature'
                }
            },
            'security': {
                'encryption': 'AES-256 for sensitive data',
                'signatures': 'HMAC-SHA256 for webhooks',
                'rate_limiting': 'Configurable per regulator',
                'audit_logging': 'All access logged and audited'
            },
            'compliance': {
                'data_retention': '7 years for transaction data',
                'access_logging': 'All regulator access logged',
                'encryption_standards': 'AES-256, TLS 1.3',
                'audit_trail': 'Complete audit trail for all operations'
            }
        }
        
        return jsonify(documentation)
        
    except Exception as e:
        current_app.logger.error(f"API documentation error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'error_code': 'INTERNAL_ERROR'
        }), 500


# Error handlers
@regulator_api.errorhandler(400)
def bad_request(error):
    return jsonify({
        'success': False,
        'error': 'Bad request',
        'error_code': 'BAD_REQUEST'
    }), 400


@regulator_api.errorhandler(401)
def unauthorized(error):
    return jsonify({
        'success': False,
        'error': 'Unauthorized',
        'error_code': 'UNAUTHORIZED'
    }), 401


@regulator_api.errorhandler(403)
def forbidden(error):
    return jsonify({
        'success': False,
        'error': 'Forbidden',
        'error_code': 'FORBIDDEN'
    }), 403


@regulator_api.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': 'Not found',
        'error_code': 'NOT_FOUND'
    }), 404


@regulator_api.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'error': 'Internal server error',
        'error_code': 'INTERNAL_ERROR'
    }), 500
