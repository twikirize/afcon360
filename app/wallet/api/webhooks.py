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

webhooks_bp = Blueprint('webhooks', __name__, url_prefix='/webhooks')


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
        data = request.get_json()
        event = data.get('event')
        event_data = data.get('data', {})
        
        current_app.logger.info(f"Flutterwave webhook: {event}")
        
        # Handle different event types
        if event == 'charge.completed':
            tx_ref = event_data.get('txRef')
            status = event_data.get('status')
            
            if status == 'successful':
                # Verify the transaction
                result = verify_payment(PaymentProvider.FLUTTERWAVE, tx_ref)
                
                if result.success:
                    # Transaction is verified, deposit processed in service
                    current_app.logger.info(f"Deposit confirmed: {tx_ref}")
                    return jsonify({"status": "success"}), 200
            else:
                # Failed or cancelled
                current_app.logger.warning(f"Payment failed: {tx_ref}, status: {status}")
        
        elif event == 'transfer.completed':
            transfer_ref = event_data.get('reference')
            transfer_status = event_data.get('status')
            
            current_app.logger.info(f"Transfer webhook: {transfer_ref} - {transfer_status}")
            
            # Verify the transfer
            result = verify_payout(PaymentProvider.FLUTTERWAVE, transfer_ref)
            
            if result.success:
                return jsonify({"status": "success"}), 200
        
        elif event == 'transfer.failed':
            transfer_ref = event_data.get('reference')
            reason = event_data.get('complete_message', 'Transfer failed')
            
            current_app.logger.error(f"Transfer failed: {transfer_ref}, reason: {reason}")
            # TODO: Implement reversal logic
            
        return jsonify({"status": "received"}), 200
        
    except Exception as e:
        current_app.logger.error(f"Flutterwave webhook error: {str(e)}")
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
        data = request.get_json()
        event = data.get('event')
        event_data = data.get('data', {})
        
        current_app.logger.info(f"Paystack webhook: {event}")
        
        if event == 'charge.success':
            reference = event_data.get('reference')
            
            # Verify the transaction
            result = verify_payment(PaymentProvider.PAYSTACK, reference)
            
            if result.success:
                current_app.logger.info(f"Payment confirmed: {reference}")
                return jsonify({"status": "success"}), 200
        
        elif event == 'transfer.success':
            reference = event_data.get('reference')
            current_app.logger.info(f"Transfer successful: {reference}")
            
            result = verify_payout(PaymentProvider.PAYSTACK, reference)
            if result.success:
                return jsonify({"status": "success"}), 200
        
        elif event == 'transfer.failed':
            reference = event_data.get('reference')
            reason = event_data.get('complete_message', 'Transfer failed')
            current_app.logger.error(f"Transfer failed: {reference}, reason: {reason}")
            # TODO: Implement reversal
        
        return jsonify({"status": "received"}), 200
        
    except Exception as e:
        current_app.logger.error(f"Paystack webhook error: {str(e)}")
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
        data = request.get_json()
        
        # MTN MOMO webhook structure
        reference = data.get('reference')
        status = data.get('status')
        amount = data.get('amount')
        currency = data.get('currency')
        phone = data.get('payer', {}).get('partyId')
        
        current_app.logger.info(f"MTN MOMO webhook: {reference} - {status}")
        
        if status == 'SUCCESSFUL':
            # Process successful mobile money payment
            # Find user by phone number and credit wallet
            from app.identity.models.user import User
            user = User.query.filter_by(phone=phone).first()
            
            if user:
                wallet_service = WalletService()
                wallet_service.deposit(
                    user_id=user.id,
                    amount=float(amount),
                    currency=currency,
                    client_request_id=reference,
                    metadata={
                        "source": "mtn_momo",
                        "phone": phone,
                        "reference": reference
                    }
                )
                return jsonify({"status": "success"}), 200
        
        return jsonify({"status": "received"}), 200
        
    except Exception as e:
        current_app.logger.error(f"MTN MOMO webhook error: {str(e)}")
        return jsonify({"status": "error"}), 500


@webhooks_bp.route('/airtel-money', methods=['POST'])
def airtel_money_webhook():
    """Handle Airtel Money webhooks"""
    api_key = request.headers.get('X-API-Key', '')
    expected_key = current_app.config.get('AIRTEL_MONEY_API_KEY', '')
    
    if api_key != expected_key:
        return jsonify({"status": "error", "message": "Invalid API key"}), 401
    
    try:
        data = request.get_json()
        reference = data.get('transactionId')
        status = data.get('status')
        
        current_app.logger.info(f"Airtel Money webhook: {reference} - {status}")
        
        # Similar to MTN MOMO handling
        return jsonify({"status": "received"}), 200
        
    except Exception as e:
        current_app.logger.error(f"Airtel Money webhook error: {str(e)}")
        return jsonify({"status": "error"}), 500


@webhooks_bp.route('/generic', methods=['POST'])
def generic_webhook():
    """Generic webhook handler for custom integrations"""
    # This can be used for aggregators, partners, etc.
    api_key = request.headers.get('X-API-Key', '')
    
    # Validate API key against database
    # This would check against partner API keys
    
    try:
        data = request.get_json()
        
        current_app.logger.info(f"Generic webhook received: {data}")
        
        # Process based on event type
        event_type = data.get('event_type')
        
        if event_type == 'deposit':
            # Handle aggregator deposit
            pass
        elif event_type == 'withdrawal':
            # Handle aggregator withdrawal
            pass
        elif event_type == 'reconciliation':
            # Handle reconciliation request
            pass
        
        return jsonify({"status": "received"}), 200
        
    except Exception as e:
        current_app.logger.error(f"Generic webhook error: {str(e)}")
        return jsonify({"status": "error"}), 500


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
