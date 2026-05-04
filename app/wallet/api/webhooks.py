"""
Webhook API for payment providers and external integrations
Handles callbacks from Flutterwave, Paystack, MTN Mobile Money, etc.
"""

from flask import Blueprint, request, jsonify, current_app
import hmac
import hashlib
import json

from app.wallet.services.payment_gateway import (
    PaymentProvider, handle_provider_webhook, verify_payment, verify_payout,
    deposit_with_card, deposit_with_mobile_money
)
from app.wallet.services.wallet_service import WalletService
from app.wallet.exceptions import PaymentError
from app.extensions import db
from app.wallet.models.webhook_event import WebhookEvent

webhooks_bp = Blueprint('webhooks', __name__, url_prefix='/webhooks')


def _scrub_sensitive(obj):
    """Recursively redact obvious PII (card numbers, CVVs, PANs, long numeric account numbers).
    Replace sensitive values with a marker so DB-stored payloads don't contain PAN/CVV data.
    """
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            lk = k.lower()
            if any(sub in lk for sub in ("card", "cvv", "pan")):
                out[k] = "[REDACTED]"
            elif "number" in lk and isinstance(v, str) and sum(c.isdigit() for c in v) >= 8:
                out[k] = "[REDACTED]"
            else:
                out[k] = _scrub_sensitive(v)
        return out
    if isinstance(obj, list):
        return [_scrub_sensitive(i) for i in obj]
    return obj

def verify_flutterwave_signature(payload: bytes, signature: str) -> bool:
    """Verify Flutterwave webhook signature"""
    secret = current_app.config.get('FLUTTERWAVE_SECRET_KEY', '')
    if not secret:
        return False
    
    expected_hash = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_hash, signature)


def verify_paystack_signature(payload: bytes, signature: str) -> bool:
    """Verify Paystack webhook signature"""
    secret = current_app.config.get('PAYSTACK_SECRET_KEY', '')
    if not secret:
        return False
    
    expected_hash = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha512
    ).hexdigest()
    
    return hmac.compare_digest(expected_hash, signature)


@webhooks_bp.route('/flutterwave', methods=['POST'])
def flutterwave_webhook():
    """Handle Flutterwave webhooks"""
    signature = request.headers.get('verif-hash', '')
    payload = request.get_data()
    
    # Verify signature
    if not verify_flutterwave_signature(payload, signature):
        current_app.logger.warning("Invalid Flutterwave webhook signature")
        return jsonify({"status": "error", "message": "Invalid signature"}), 401
    
    try:
        data = request.get_json() or {}
        event = data.get('event')
        raw_body = payload.decode('utf-8', errors='replace') if payload else None


        # Optional: encrypt raw payload before persisting when a key is configured.
        # We prefix stored encrypted values with 'ENCRYPTED:' so the worker can
        # detect and decrypt them at processing time. If encryption fails we
        # fallback to storing the plaintext to avoid dropping events.
        enc_key = current_app.config.get('WEBHOOK_PAYLOAD_ENCRYPTION_KEY')
        if raw_body and enc_key:
            try:
                from cryptography.fernet import Fernet
                f = Fernet(enc_key if isinstance(enc_key, bytes) else enc_key.encode())
                token = f.encrypt(raw_body.encode('utf-8'))
                raw_body = 'ENCRYPTED:' + token.decode('utf-8')
            except Exception:
                current_app.logger.exception('Failed to encrypt webhook raw_body; storing plaintext')
        data_scrubbed = _scrub_sensitive(data)

        # Enqueue webhook for background processing (store scrubbed JSON and raw body)
        we = WebhookEvent(
            provider='flutterwave',
            event_type=event,
            payload=data_scrubbed,
            raw_body=raw_body,
            signature=signature,
            status='queued'
        )
        db.session.add(we)
        db.session.commit()

        current_app.logger.info(f"Enqueued Flutterwave webhook: {event} id={we.id}")
        return jsonify({"status": "accepted", "id": we.id}), 202
    except Exception as e:
        current_app.logger.error(f"Flutterwave webhook enqueue error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@webhooks_bp.route('/paystack', methods=['POST'])
def paystack_webhook():
    """Handle Paystack webhooks"""
    signature = request.headers.get('x-paystack-signature', '')
    payload = request.get_data()
    
    # Verify signature
    if not verify_paystack_signature(payload, signature):
        current_app.logger.warning("Invalid Paystack webhook signature")
        return jsonify({"status": "error", "message": "Invalid signature"}), 401
    
    try:
        data = request.get_json() or {}
        event = data.get('event')
        raw_body = payload.decode('utf-8', errors='replace') if payload else None
        enc_key = current_app.config.get('WEBHOOK_PAYLOAD_ENCRYPTION_KEY')
        if raw_body and enc_key:
            try:
                from cryptography.fernet import Fernet
                f = Fernet(enc_key if isinstance(enc_key, bytes) else enc_key.encode())
                token = f.encrypt(raw_body.encode('utf-8'))
                raw_body = 'ENCRYPTED:' + token.decode('utf-8')
            except Exception:
                current_app.logger.exception('Failed to encrypt webhook raw_body; storing plaintext')
        data_scrubbed = _scrub_sensitive(data)

        we = WebhookEvent(
            provider='paystack',
            event_type=event,
            payload=data_scrubbed,
            raw_body=raw_body,
            signature=signature,
            status='queued'
        )
        db.session.add(we)
        db.session.commit()

        current_app.logger.info(f"Enqueued Paystack webhook: {event} id={we.id}")
        return jsonify({"status": "accepted", "id": we.id}), 202
    except Exception as e:
        current_app.logger.error(f"Paystack webhook enqueue error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@webhooks_bp.route('/mtn-momo', methods=['POST'])
def mtn_momo_webhook():
    """Handle MTN Mobile Money webhooks"""
    # MTN MOMO uses API key authentication
    api_key = request.headers.get('X-API-Key', '')
    expected_key = current_app.config.get('MTN_MOMO_API_KEY', '')
    
    if api_key != expected_key:
        return jsonify({"status": "error", "message": "Invalid API key"}), 401
    
    try:
        data = request.get_json() or {}
        event = data.get('event') or data.get('status')
        raw_body = request.get_data().decode('utf-8', errors='replace')
        enc_key = current_app.config.get('WEBHOOK_PAYLOAD_ENCRYPTION_KEY')
        if raw_body and enc_key:
            try:
                from cryptography.fernet import Fernet
                f = Fernet(enc_key if isinstance(enc_key, bytes) else enc_key.encode())
                token = f.encrypt(raw_body.encode('utf-8'))
                raw_body = 'ENCRYPTED:' + token.decode('utf-8')
            except Exception:
                current_app.logger.exception('Failed to encrypt webhook raw_body; storing plaintext')
        data_scrubbed = _scrub_sensitive(data)

        we = WebhookEvent(
            provider='mtn_momo',
            event_type=event,
            payload=data_scrubbed,
            raw_body=raw_body,
            signature=api_key,
            status='queued'
        )
        db.session.add(we)
        db.session.commit()

        current_app.logger.info(f"Enqueued MTN MOMO webhook id={we.id}")
        return jsonify({"status": "accepted", "id": we.id}), 202
    except Exception as e:
        current_app.logger.error(f"MTN MOMO webhook enqueue error: {str(e)}")
        return jsonify({"status": "error"}), 500


@webhooks_bp.route('/airtel-money', methods=['POST'])
def airtel_money_webhook():
    """Handle Airtel Money webhooks"""
    api_key = request.headers.get('X-API-Key', '')
    expected_key = current_app.config.get('AIRTEL_MONEY_API_KEY', '')
    
    if api_key != expected_key:
        return jsonify({"status": "error", "message": "Invalid API key"}), 401
    
    try:
        data = request.get_json() or {}
        event = data.get('status') or data.get('event')
        raw_body = request.get_data().decode('utf-8', errors='replace')
        enc_key = current_app.config.get('WEBHOOK_PAYLOAD_ENCRYPTION_KEY')
        if raw_body and enc_key:
            try:
                from cryptography.fernet import Fernet
                f = Fernet(enc_key if isinstance(enc_key, bytes) else enc_key.encode())
                token = f.encrypt(raw_body.encode('utf-8'))
                raw_body = 'ENCRYPTED:' + token.decode('utf-8')
            except Exception:
                current_app.logger.exception('Failed to encrypt webhook raw_body; storing plaintext')
        data_scrubbed = _scrub_sensitive(data)

        we = WebhookEvent(
            provider='airtel_money',
            event_type=event,
            payload=data_scrubbed,
            raw_body=raw_body,
            signature=api_key,
            status='queued'
        )
        db.session.add(we)
        db.session.commit()

        current_app.logger.info(f"Enqueued Airtel Money webhook id={we.id}")
        return jsonify({"status": "accepted", "id": we.id}), 202
    except Exception as e:
        current_app.logger.error(f"Airtel webhook enqueue error: {str(e)}")
        return jsonify({"status": "error"}), 500


@webhooks_bp.route('/generic', methods=['POST'])
def generic_webhook():
    """Generic webhook handler for custom integrations"""
    # This can be used for aggregators, partners, etc.
    api_key = request.headers.get('X-API-Key', '')
    
    # Validate API key against database
    # This would check against partner API keys
    
    try:
        data = request.get_json() or {}
        raw_body = request.get_data().decode('utf-8', errors='replace')
        data_scrubbed = _scrub_sensitive(data)

        we = WebhookEvent(
            provider='generic',
            event_type=data.get('event_type'),
            payload=data_scrubbed,
            raw_body=raw_body,
            signature=api_key,
            status='queued'
        )
        db.session.add(we)
        db.session.commit()

        current_app.logger.info(f"Enqueued generic webhook id={we.id}")
        return jsonify({"status": "accepted", "id": we.id}), 202
    except Exception as e:
        current_app.logger.error(f"Generic webhook enqueue error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@webhooks_bp.route('/health', methods=['GET'])
def webhook_health():
    """Health check endpoint for webhook status"""
    from app.wallet.services.payment_gateway import get_provider_status
    status = get_provider_status()
    
    return jsonify({
        "status": "healthy",
        "providers": {
            "flutterwave": bool(current_app.config.get('FLUTTERWAVE_SECRET_KEY')),
            "paystack": bool(current_app.config.get('PAYSTACK_SECRET_KEY')),
            "mtn_momo": bool(current_app.config.get('MTN_MOMO_API_KEY')),
            "airtel_money": bool(current_app.config.get('AIRTEL_MONEY_API_KEY'))
        }
    }), 200


__all__ = ['webhooks_bp']
