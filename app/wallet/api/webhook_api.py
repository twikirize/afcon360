"""
app/wallet/api/webhook_api.py
Payment provider webhook endpoints with full audit and reconciliation.
"""

from flask import Blueprint, request, jsonify, current_app
from decimal import Decimal
from datetime import datetime
import hmac
import hashlib
import uuid
from typing import Dict, Any, Optional

from app.extensions import db
from app.wallet.services.wallet_service import WalletService
from app.audit.comprehensive_audit import AuditService, TransactionType, APICallStatus, AuditSeverity

webhook_bp = Blueprint('webhook_api', __name__, url_prefix='/api/webhooks')


# ============================================================================
# FLUTTERWAVE WEBHOOK
# ============================================================================

@webhook_bp.route('/flutterwave', methods=['POST'])
def flutterwave_webhook():
    """
    Handle Flutterwave payment webhook.

    Flutterwave sends webhooks for:
    - charge.completed (successful payment)
    - transfer.completed (successful payout)
    - refund.completed (refund processed)

    POST /api/webhooks/flutterwave
    """
    payload = request.get_data()
    signature = request.headers.get('verif-hash')

    # Verify signature
    if not verify_flutterwave_signature(payload, signature):
        current_app.logger.warning(f"Invalid Flutterwave webhook signature from {request.remote_addr}")
        return jsonify({"status": "error", "message": "Invalid signature"}), 401

    try:
        data = request.get_json()
        event = data.get('event')

        current_app.logger.info(f"Flutterwave webhook received: {event}")

        # Route to appropriate handler
        if event == 'charge.completed':
            return handle_flutterwave_charge_completed(data)
        elif event == 'transfer.completed':
            return handle_flutterwave_transfer_completed(data)
        elif event == 'refund.completed':
            return handle_flutterwave_refund_completed(data)
        else:
            current_app.logger.info(f"Unhandled Flutterwave event: {event}")
            return jsonify({"status": "ignored", "event": event}), 200

    except Exception as e:
        current_app.logger.error(f"Flutterwave webhook error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Internal error"}), 500


def handle_flutterwave_charge_completed(data: Dict) -> tuple:
    """
    Handle successful charge webhook from Flutterwave.

    This is called when a customer successfully completes payment.
    """
    tx_ref = data.get('data', {}).get('tx_ref')
    status = data.get('data', {}).get('status')
    amount = data.get('data', {}).get('amount')
    currency = data.get('data', {}).get('currency')
    flutterwave_ref = data.get('data', {}).get('flw_ref')

    # Extract user_id from tx_ref (format: DEP-XXX-user_id or user_id)
    user_id = extract_user_id_from_reference(tx_ref)

    if not user_id:
        current_app.logger.error(f"Could not extract user_id from tx_ref: {tx_ref}")
        return jsonify({"status": "error", "message": "Invalid transaction reference"}), 400

    # Check if already processed (idempotency)
    from app.wallet.models import Transaction as TransactionModel
    existing = TransactionModel.query.filter_by(client_request_id=tx_ref).first()
    if existing:
        current_app.logger.info(f"Duplicate webhook for tx_ref: {tx_ref}, already processed")
        return jsonify({"status": "already_processed"}), 200

    # Log the webhook receipt
    audit_id = f"WH-{uuid.uuid4().hex[:12].upper()}"
    try:
        AuditService.api_call(
            service_name="flutterwave",
            endpoint="/webhook/charge.completed",
            method="POST",
            request_id=audit_id,
            correlation_id=tx_ref,
            status=APICallStatus.SUCCESS,
            response_status=200,
            initiated_by=user_id,
            response_body={"event": "charge.completed", "status": status}
        )
    except Exception as e:
        current_app.logger.error(f"Failed to log webhook audit: {e}")

    # Only process successful charges
    if status != 'successful':
        current_app.logger.warning(f"Flutterwave charge not successful: {status} for {tx_ref}")
        return jsonify({"status": "ignored", "charge_status": status}), 200

    # Process the deposit
    try:
        wallet_service = WalletService()

        result = wallet_service.deposit(
            user_id=user_id,
            amount=Decimal(str(amount)),
            currency=currency,
            idempotency_key=tx_ref,
            payment_method="card_transfer",
            payment_provider="flutterwave",
            external_reference=flutterwave_ref,
            metadata={
                "webhook_received_at": datetime.utcnow().isoformat(),
                "flutterwave_data": data.get('data', {})
            }
        )

        # Log successful processing
        AuditService.security(
            event_type="webhook_deposit_processed",
            severity=AuditSeverity.INFO,
            description=f"Flutterwave webhook processed deposit {tx_ref}",
            user_id=user_id,
            metadata={
                "tx_ref": tx_ref,
                "amount": amount,
                "currency": currency,
                "flutterwave_ref": flutterwave_ref,
                "transaction_id": result.get('transaction_id')
            }
        )

        return jsonify({
            "status": "success",
            "message": "Deposit processed",
            "transaction_id": result.get('transaction_id')
        }), 200

    except Exception as e:
        current_app.logger.error(f"Failed to process deposit from webhook: {e}", exc_info=True)

        # Log failure for manual reconciliation
        try:
            AuditService.security(
                event_type="webhook_deposit_failed",
                severity=AuditSeverity.CRITICAL,
                description=f"Failed to process deposit from Flutterwave webhook: {str(e)}",
                user_id=user_id,
                metadata={
                    "tx_ref": tx_ref,
                    "amount": amount,
                    "currency": currency,
                    "error": str(e)
                }
            )
        except Exception:
            pass

        return jsonify({"status": "error", "message": "Processing failed"}), 500


def handle_flutterwave_transfer_completed(data: Dict) -> tuple:
    """
    Handle successful transfer (payout) webhook from Flutterwave.
    """
    transfer_id = data.get('data', {}).get('id')
    reference = data.get('data', {}).get('reference')
    status = data.get('data', {}).get('status')
    amount = data.get('data', {}).get('amount')
    currency = data.get('data', {}).get('currency')

    current_app.logger.info(f"Flutterwave transfer completed: {reference}, status: {status}")

    # Update payout request status if reference matches
    from app.wallet.models import PayoutRequest
    payout = PayoutRequest.query.filter_by(request_ref=reference).first()

    if payout:
        # Update payout metadata with transfer confirmation
        payout.metadata = payout.metadata or {}
        payout.metadata['flutterwave_transfer_id'] = transfer_id
        payout.metadata['flutterwave_status'] = status
        payout.metadata['webhook_updated_at'] = datetime.utcnow().isoformat()
        db.session.commit()

        AuditService.security(
            event_type="flutterwave_transfer_update",
            severity=AuditSeverity.INFO,
            description=f"Flutterwave transfer {reference} status: {status}",
            user_id=payout.agent_id,
            metadata={
                "transfer_id": transfer_id,
                "reference": reference,
                "status": status,
                "amount": amount,
                "currency": currency
            }
        )

    return jsonify({"status": "success"}), 200


def handle_flutterwave_refund_completed(data: Dict) -> tuple:
    """Handle refund completed webhook."""
    refund_id = data.get('data', {}).get('id')
    transaction_id = data.get('data', {}).get('transaction_id')

    current_app.logger.info(f"Flutterwave refund completed: {refund_id} for transaction {transaction_id}")

    # TODO: Implement refund handling logic
    # - Find original transaction
    # - Create refund transaction
    # - Update wallet balance

    return jsonify({"status": "success"}), 200


# ============================================================================
# PAYSTACK WEBHOOK
# ============================================================================

@webhook_bp.route('/paystack', methods=['POST'])
def paystack_webhook():
    """
    Handle Paystack payment webhook.

    Paystack sends webhooks for:
    - charge.success (successful payment)
    - transfer.success (successful payout)
    - refund.success (refund processed)

    POST /api/webhooks/paystack
    """
    payload = request.get_data()
    signature = request.headers.get('x-paystack-signature')

    # Verify signature
    if not verify_paystack_signature(payload, signature):
        current_app.logger.warning(f"Invalid Paystack webhook signature from {request.remote_addr}")
        return jsonify({"status": "error", "message": "Invalid signature"}), 401

    try:
        data = request.get_json()
        event = data.get('event')

        current_app.logger.info(f"Paystack webhook received: {event}")

        # Route to appropriate handler
        if event == 'charge.success':
            return handle_paystack_charge_success(data)
        elif event == 'transfer.success':
            return handle_paystack_transfer_success(data)
        elif event == 'refund.success':
            return handle_paystack_refund_success(data)
        else:
            current_app.logger.info(f"Unhandled Paystack event: {event}")
            return jsonify({"status": "ignored", "event": event}), 200

    except Exception as e:
        current_app.logger.error(f"Paystack webhook error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Internal error"}), 500


def handle_paystack_charge_success(data: Dict) -> tuple:
    """
    Handle successful charge webhook from Paystack.

    This is called when a customer successfully completes payment.
    """
    event_data = data.get('data', {})
    reference = event_data.get('reference')
    amount_in_kobo = event_data.get('amount', 0)
    currency = event_data.get('currency', 'NGN')
    status = event_data.get('status')

    # Convert from kobo/cents to main currency
    amount = Decimal(str(amount_in_kobo / 100))

    # Extract user_id from metadata
    user_id = event_data.get('metadata', {}).get('user_id')

    if not user_id:
        current_app.logger.error(f"Could not extract user_id from Paystack metadata for reference: {reference}")
        return jsonify({"status": "error", "message": "Missing user_id"}), 400

    # Check if already processed (idempotency)
    from app.wallet.models import Transaction as TransactionModel
    existing = TransactionModel.query.filter_by(client_request_id=reference).first()
    if existing:
        current_app.logger.info(f"Duplicate Paystack webhook for reference: {reference}, already processed")
        return jsonify({"status": "already_processed"}), 200

    # Log the webhook receipt
    audit_id = f"WH-{uuid.uuid4().hex[:12].upper()}"
    try:
        AuditService.api_call(
            service_name="paystack",
            endpoint="/webhook/charge.success",
            method="POST",
            request_id=audit_id,
            correlation_id=reference,
            status=APICallStatus.SUCCESS,
            response_status=200,
            initiated_by=user_id,
            response_body={"event": "charge.success", "status": status}
        )
    except Exception as e:
        current_app.logger.error(f"Failed to log webhook audit: {e}")

    # Only process successful charges
    if status != 'success':
        current_app.logger.warning(f"Paystack charge not successful: {status} for {reference}")
        return jsonify({"status": "ignored", "charge_status": status}), 200

    # Process the deposit
    try:
        wallet_service = WalletService()

        result = wallet_service.deposit(
            user_id=user_id,
            amount=amount,
            currency=currency,
            idempotency_key=reference,
            payment_method="card_transfer",
            payment_provider="paystack",
            external_reference=reference,
            metadata={
                "webhook_received_at": datetime.utcnow().isoformat(),
                "paystack_data": event_data,
                "authorization": event_data.get('authorization', {}).get('authorization_code')
            }
        )

        # Log successful processing
        AuditService.security(
            event_type="webhook_deposit_processed",
            severity=AuditSeverity.INFO,
            description=f"Paystack webhook processed deposit {reference}",
            user_id=user_id,
            metadata={
                "reference": reference,
                "amount": float(amount),
                "currency": currency,
                "transaction_id": result.get('transaction_id')
            }
        )

        return jsonify({
            "status": "success",
            "message": "Deposit processed",
            "transaction_id": result.get('transaction_id')
        }), 200

    except Exception as e:
        current_app.logger.error(f"Failed to process deposit from Paystack webhook: {e}", exc_info=True)

        # Log failure for manual reconciliation
        try:
            AuditService.security(
                event_type="webhook_deposit_failed",
                severity=AuditSeverity.CRITICAL,
                description=f"Failed to process deposit from Paystack webhook: {str(e)}",
                user_id=user_id,
                metadata={
                    "reference": reference,
                    "amount": float(amount),
                    "currency": currency,
                    "error": str(e)
                }
            )
        except Exception:
            pass

        return jsonify({"status": "error", "message": "Processing failed"}), 500


def handle_paystack_transfer_success(data: Dict) -> tuple:
    """
    Handle successful transfer (payout) webhook from Paystack.
    """
    event_data = data.get('data', {})
    reference = event_data.get('reference')
    transfer_code = event_data.get('transfer_code')
    amount_in_kobo = event_data.get('amount', 0)
    currency = event_data.get('currency')
    status = event_data.get('status')

    amount = Decimal(str(amount_in_kobo / 100))

    current_app.logger.info(f"Paystack transfer completed: {reference}, status: {status}")

    # Update payout request status if reference matches
    from app.wallet.models import PayoutRequest
    payout = PayoutRequest.query.filter_by(request_ref=reference).first()

    if payout:
        # Update payout metadata with transfer confirmation
        payout.metadata = payout.metadata or {}
        payout.metadata['paystack_transfer_code'] = transfer_code
        payout.metadata['paystack_status'] = status
        payout.metadata['webhook_updated_at'] = datetime.utcnow().isoformat()
        db.session.commit()

        AuditService.security(
            event_type="paystack_transfer_update",
            severity=AuditSeverity.INFO,
            description=f"Paystack transfer {reference} status: {status}",
            user_id=payout.agent_id,
            metadata={
                "transfer_code": transfer_code,
                "reference": reference,
                "status": status,
                "amount": float(amount),
                "currency": currency
            }
        )

    return jsonify({"status": "success"}), 200


def handle_paystack_refund_success(data: Dict) -> tuple:
    """Handle refund success webhook."""
    event_data = data.get('data', {})
    refund_id = event_data.get('id')
    transaction_reference = event_data.get('transaction_reference')

    current_app.logger.info(f"Paystack refund completed: {refund_id} for transaction {transaction_reference}")

    # TODO: Implement refund handling logic

    return jsonify({"status": "success"}), 200


# ============================================================================
# MTN MOMO WEBHOOK (Mobile Money)
# ============================================================================

@webhook_bp.route('/mtn-momo', methods=['POST'])
def mtn_momo_webhook():
    """
    Handle MTN Mobile Money payment webhook.

    POST /api/webhooks/mtn-momo
    """
    payload = request.get_data()
    signature = request.headers.get('x-mtn-signature')

    # Verify signature
    if not verify_mtn_momo_signature(payload, signature):
        current_app.logger.warning(f"Invalid MTN MoMo webhook signature from {request.remote_addr}")
        return jsonify({"status": "error", "message": "Invalid signature"}), 401

    try:
        data = request.get_json()
        status = data.get('status')

        current_app.logger.info(f"MTN MoMo webhook received: status={status}")

        if status == 'SUCCESSFUL':
            return handle_mtn_momo_payment_success(data)
        else:
            return handle_mtn_momo_payment_failed(data)

    except Exception as e:
        current_app.logger.error(f"MTN MoMo webhook error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Internal error"}), 500


def handle_mtn_momo_payment_success(data: Dict) -> tuple:
    """
    Handle successful MTN MoMo payment webhook.
    """
    transaction_id = data.get('transaction_id')
    amount = data.get('amount')
    currency = data.get('currency', 'UGX')
    reference = data.get('reference')

    # Extract user_id from reference
    user_id = extract_user_id_from_reference(reference)

    if not user_id:
        current_app.logger.error(f"Could not extract user_id from MTN reference: {reference}")
        return jsonify({"status": "error", "message": "Invalid reference"}), 400

    # Check if already processed
    from app.wallet.models import Transaction as TransactionModel
    existing = TransactionModel.query.filter_by(client_request_id=reference).first()
    if existing:
        return jsonify({"status": "already_processed"}), 200

    # Process the deposit
    try:
        wallet_service = WalletService()

        result = wallet_service.deposit(
            user_id=user_id,
            amount=Decimal(str(amount)),
            currency=currency,
            idempotency_key=reference,
            payment_method="mobile_money",
            payment_provider="mtn_momo",
            external_reference=transaction_id,
            metadata={
                "webhook_received_at": datetime.utcnow().isoformat(),
                "mtn_data": data
            }
        )

        return jsonify({
            "status": "success",
            "message": "Deposit processed",
            "transaction_id": result.get('transaction_id')
        }), 200

    except Exception as e:
        current_app.logger.error(f"Failed to process MTN MoMo deposit: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Processing failed"}), 500


def handle_mtn_momo_payment_failed(data: Dict) -> tuple:
    """Handle failed MTN MoMo payment webhook."""
    transaction_id = data.get('transaction_id')
    reason = data.get('reason', 'Unknown')

    current_app.logger.warning(f"MTN MoMo payment failed: {transaction_id}, reason: {reason}")

    # Log failed payment
    try:
        AuditService.security(
            event_type="mobile_money_payment_failed",
            severity=AuditSeverity.WARNING,
            description=f"MTN MoMo payment failed: {reason}",
            metadata={
                "transaction_id": transaction_id,
                "reason": reason,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    except Exception:
        pass

    return jsonify({"status": "success"}), 200


# ============================================================================
# AIRTEL MONEY WEBHOOK
# ============================================================================

@webhook_bp.route('/airtel-money', methods=['POST'])
def airtel_money_webhook():
    """
    Handle Airtel Money payment webhook.

    POST /api/webhooks/airtel-money
    """
    payload = request.get_data()
    signature = request.headers.get('x-airtel-signature')

    # Verify signature
    if not verify_airtel_signature(payload, signature):
        current_app.logger.warning(f"Invalid Airtel webhook signature from {request.remote_addr}")
        return jsonify({"status": "error", "message": "Invalid signature"}), 401

    try:
        data = request.get_json()
        transaction_status = data.get('transaction', {}).get('status')

        current_app.logger.info(f"Airtel webhook received: status={transaction_status}")

        if transaction_status == 'success':
            return handle_airtel_payment_success(data)
        else:
            return handle_airtel_payment_failed(data)

    except Exception as e:
        current_app.logger.error(f"Airtel webhook error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Internal error"}), 500


def handle_airtel_payment_success(data: Dict) -> tuple:
    """Handle successful Airtel Money payment webhook."""
    transaction_data = data.get('transaction', {})
    transaction_id = transaction_data.get('id')
    amount = transaction_data.get('amount')
    currency = transaction_data.get('currency', 'UGX')
    reference = transaction_data.get('reference')

    user_id = extract_user_id_from_reference(reference)

    if not user_id:
        return jsonify({"status": "error", "message": "Invalid reference"}), 400

    # Check if already processed
    from app.wallet.models import Transaction as TransactionModel
    existing = TransactionModel.query.filter_by(client_request_id=reference).first()
    if existing:
        return jsonify({"status": "already_processed"}), 200

    try:
        wallet_service = WalletService()

        result = wallet_service.deposit(
            user_id=user_id,
            amount=Decimal(str(amount)),
            currency=currency,
            idempotency_key=reference,
            payment_method="mobile_money",
            payment_provider="airtel_money",
            external_reference=transaction_id,
            metadata={
                "webhook_received_at": datetime.utcnow().isoformat(),
                "airtel_data": data
            }
        )

        return jsonify({
            "status": "success",
            "transaction_id": result.get('transaction_id')
        }), 200

    except Exception as e:
        current_app.logger.error(f"Failed to process Airtel deposit: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Processing failed"}), 500


def handle_airtel_payment_failed(data: Dict) -> tuple:
    """Handle failed Airtel Money payment webhook."""
    transaction_data = data.get('transaction', {})
    transaction_id = transaction_data.get('id')
    error = data.get('error', {}).get('message', 'Unknown')

    current_app.logger.warning(f"Airtel payment failed: {transaction_id}, error: {error}")

    return jsonify({"status": "success"}), 200


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def verify_flutterwave_signature(payload: bytes, signature: str) -> bool:
    """Verify Flutterwave webhook signature."""
    secret = current_app.config.get('FLUTTERWAVE_SECRET_KEY')
    if not secret:
        current_app.logger.warning("FLUTTERWAVE_SECRET_KEY not configured, skipping signature verification")
        return True

    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or '')


def verify_paystack_signature(payload: bytes, signature: str) -> bool:
    """Verify Paystack webhook signature."""
    secret = current_app.config.get('PAYSTACK_SECRET_KEY')
    if not secret:
        current_app.logger.warning("PAYSTACK_SECRET_KEY not configured, skipping signature verification")
        return True

    expected = hmac.new(secret.encode(), payload, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature or '')


def verify_mtn_momo_signature(payload: bytes, signature: str) -> bool:
    """Verify MTN MoMo webhook signature."""
    secret = current_app.config.get('MTN_MOMO_SECRET_KEY')
    if not secret:
        current_app.logger.warning("MTN_MOMO_SECRET_KEY not configured, skipping signature verification")
        return True

    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or '')


def verify_airtel_signature(payload: bytes, signature: str) -> bool:
    """Verify Airtel webhook signature."""
    secret = current_app.config.get('AIRTEL_SECRET_KEY')
    if not secret:
        current_app.logger.warning("AIRTEL_SECRET_KEY not configured, skipping signature verification")
        return True

    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or '')


def extract_user_id_from_reference(reference: str) -> Optional[int]:
    """
    Extract user ID from transaction reference.

    Supported formats:
    - DEP-XXX-user_id (from our system)
    - user_id-timestamp
    - Plain user_id
    """
    if not reference:
        return None

    # Format: DEP-XXX-12345
    if reference.startswith('DEP-'):
        parts = reference.split('-')
        if len(parts) >= 3:
            try:
                return int(parts[-1])
            except ValueError:
                pass

    # Format: 12345-20240101
    if '-' in reference:
        try:
            return int(reference.split('-')[0])
        except ValueError:
            pass

    # Try direct conversion
    try:
        return int(reference)
    except ValueError:
        return None


# ============================================================================
# HEALTH CHECK ENDPOINT
# ============================================================================

@webhook_bp.route('/health', methods=['GET'])
def webhook_health():
    """
    Health check endpoint for webhook monitoring.

    GET /api/webhooks/health
    """
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "configured_providers": [
            p for p in ['flutterwave', 'paystack', 'mtn_momo', 'airtel_money']
            if current_app.config.get(f'{p.upper()}_SECRET_KEY')
        ]
    }), 200