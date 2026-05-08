# app/tasks/webhook_processor.py
"""
Celery task that consumes queued WebhookEvents and processes them.

The webhook routes (webhooks.py) only ENQUEUE events.
THIS file is the only place that credits/debits wallets from webhooks.

CRITICAL IDEMPOTENCY RULE:
    The idempotency middleware only protects HTTP requests.
    This worker runs OUTSIDE that context, so we do our own
    provider_reference check before crediting any wallet.
    Without this, a requeued event would double-credit a deposit.

Retry schedule (exponential backoff):
    Attempt 1 → immediate
    Attempt 2 → 2 min
    Attempt 3 → 4 min
    Attempt 4 → 8 min
    Attempt 5 → 16 min
    Attempt 6+ → dead_letter (never retried again)
"""

import json
import hmac
import hashlib
import logging
from datetime import datetime, timezone, timedelta

from celery import shared_task
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5


# ---------------------------------------------------------------------------
# Main scheduled task - runs every 60 seconds via Celery beat
# ---------------------------------------------------------------------------

@shared_task(name="wallet.process_webhook_events", bind=True, max_retries=0)
def process_webhook_events(self):
    """
    Poll webhook_events table and process anything queued or due for retry.
    Scheduled every 60 seconds by Celery beat.
    """
    from app import create_app
    from app.extensions import db
    from app.wallet.models.webhook_event import WebhookEvent

    app = create_app()
    with app.app_context():
        now = datetime.now(timezone.utc)

        # Fetch events eligible for processing
        # status=queued → process immediately
        # status=failed AND next_retry_at <= now AND retry_count < MAX_ATTEMPTS → retry
        events = WebhookEvent.query.filter(
            db.or_(
                WebhookEvent.status == "queued",
                db.and_(
                    WebhookEvent.status == "failed",
                    WebhookEvent.retry_count < MAX_ATTEMPTS,
                    db.or_(
                        WebhookEvent.next_retry_at == None,
                        WebhookEvent.next_retry_at <= now
                    )
                )
            )
        ).with_for_update(skip_locked=True).limit(50).all()

        if not events:
            return {"processed": 0}

        processed = failed = dead_lettered = 0

        for event in events:
            # Mark as processing immediately to prevent another worker
            # picking it up (skip_locked handles concurrent workers,
            # but this is an extra safety net)
            event.status = "processing"
            db.session.commit()

            try:
                _process_single_event(event, db)
                event.status = "processed"
                event.processed_at = datetime.now(timezone.utc)
                db.session.commit()
                processed += 1

            except Exception as e:
                db.session.rollback()
                error_msg = str(e)
                logger.error(
                    f"Webhook event {event.id} ({event.provider}/{event.event_type}) "
                    f"failed attempt {event.retry_count + 1}: {error_msg}"
                )

                event.retry_count = (event.retry_count or 0) + 1
                event.last_error = error_msg[:2000]  # cap length

                if event.retry_count >= MAX_ATTEMPTS:
                    event.status = "dead_letter"
                    dead_lettered += 1
                    logger.critical(
                        f"Webhook event {event.id} moved to dead_letter "
                        f"after {event.retry_count} attempts"
                    )
                else:
                    event.status = "failed"
                    # Exponential backoff: 2^attempt minutes
                    backoff_minutes = 2 ** event.retry_count
                    event.next_retry_at = datetime.now(timezone.utc) + timedelta(minutes=backoff_minutes)
                    failed += 1

                try:
                    db.session.commit()
                except SQLAlchemyError:
                    db.session.rollback()
                else:
                    # If this event was moved to dead_letter, alert the owner
                    # and increment a Redis counter so dashboards can surface
                    # the problem. Wrap everything in try/except - a broken
                    # notification must never prevent the dead_letter state
                    # from being saved.
                    if event.status == "dead_letter":
                        try:
                            _alert_owner_dead_letter(event)
                        except Exception:
                            logger.exception(
                                "Failed to send dead-letter alert for webhook event %s",
                                event.id
                            )

        return {
            "processed": processed,
            "failed": failed,
            "dead_lettered": dead_lettered
        }


# ---------------------------------------------------------------------------
# Single event dispatcher
# ---------------------------------------------------------------------------

def _process_single_event(event, db):
    """
    Route a single WebhookEvent to the correct handler.
    Raises on any failure so the caller can handle retry logic.
    """
    provider = event.provider
    payload = event.payload  # already a dict (stored as JSON)

    if provider == "flutterwave":
        _handle_flutterwave(event, payload, db)
    elif provider == "paystack":
        _handle_paystack(event, payload, db)
    elif provider == "mtn_momo":
        _handle_mtn_momo(event, payload, db)
    elif provider == "airtel_money":
        _handle_airtel_money(event, payload, db)
    else:
        # Unknown provider - log and mark processed so it doesn't loop forever
        logger.warning(f"Unknown webhook provider '{provider}' for event {event.id}")


# ---------------------------------------------------------------------------
# Provider handlers
# ---------------------------------------------------------------------------

def _handle_flutterwave(event, payload, db):
    """Process a Flutterwave webhook event."""
    from flask import current_app

    # Re-verify signature before touching money
    # signature was stored at enqueue time
    if event.signature:
        secret = current_app.config.get("FLUTTERWAVE_SECRET_KEY", "")
        # Use the original raw_body stored at enqueue time if available. This
        # preserves the exact byte ordering used by the provider when signing
        # the payload. If the raw body was encrypted at enqueue time, decrypt
        # it using the configured key. Fall back to re-serialising the JSON
        # if raw_body is missing or decryption fails (older events).
        raw_payload = None
        raw_body_val = getattr(event, "raw_body", None)
        if raw_body_val:
            try:
                if isinstance(raw_body_val, str) and raw_body_val.startswith('ENCRYPTED:'):
                    key = current_app.config.get('WEBHOOK_PAYLOAD_ENCRYPTION_KEY')
                    if key:
                        try:
                            from cryptography.fernet import Fernet
                            f = Fernet(key if isinstance(key, bytes) else key.encode())
                            token = raw_body_val.split('ENCRYPTED:', 1)[1]
                            raw_payload = f.decrypt(token.encode())
                        except Exception:
                            current_app.logger.exception('Failed to decrypt webhook raw_body; falling back to JSON')
                if raw_payload is None:
                    raw_payload = raw_body_val.encode()
            except Exception:
                raw_payload = None

        if raw_payload is None:
            raw_payload = json.dumps(payload, separators=(",", ":")).encode()
        expected = hmac.new(secret.encode(), raw_payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, event.signature):
            raise ValueError("Flutterwave signature re-verification failed")

    event_type = event.event_type or payload.get("event", "")

    if event_type == "charge.completed":
        data = payload.get("data", {})
        status = data.get("status", "").lower()
        if status == "successful":
            tx_ref = data.get("txRef") or data.get("tx_ref")
            amount = data.get("amount")
            currency = data.get("currency", "USD")
            _credit_wallet_safe(
                provider_reference=tx_ref,
                provider="flutterwave",
                amount=amount,
                currency=currency,
                payload=payload,
                db=db
            )

    elif event_type == "transfer.completed":
        reference = payload.get("data", {}).get("reference")
        logger.info(f"Flutterwave transfer completed: {reference}")
        # Payout confirmed - update payout record if you have one
        _mark_payout_complete(reference, "flutterwave", db)


def _handle_paystack(event, payload, db):
    """Process a Paystack webhook event."""
    from flask import current_app

    # Re-verify signature
    if event.signature:
        secret = current_app.config.get("PAYSTACK_SECRET_KEY", "")
        # Prefer stored raw_body when available for reliable signature checks.
        # Support decrypting values stored with the ENCRYPTED: prefix.
        raw_payload = None
        raw_body_val = getattr(event, "raw_body", None)
        if raw_body_val:
            try:
                if isinstance(raw_body_val, str) and raw_body_val.startswith('ENCRYPTED:'):
                    key = current_app.config.get('WEBHOOK_PAYLOAD_ENCRYPTION_KEY')
                    if key:
                        try:
                            from cryptography.fernet import Fernet
                            f = Fernet(key if isinstance(key, bytes) else key.encode())
                            token = raw_body_val.split('ENCRYPTED:', 1)[1]
                            raw_payload = f.decrypt(token.encode())
                        except Exception:
                            current_app.logger.exception('Failed to decrypt webhook raw_body; falling back to JSON')
                if raw_payload is None:
                    raw_payload = raw_body_val.encode()
            except Exception:
                raw_payload = None

        if raw_payload is None:
            raw_payload = json.dumps(payload, separators=(",", ":")).encode()
        expected = hmac.new(secret.encode(), raw_payload, hashlib.sha512).hexdigest()
        if not hmac.compare_digest(expected, event.signature):
            raise ValueError("Paystack signature re-verification failed")

    event_type = event.event_type or payload.get("event", "")

    if event_type == "charge.success":
        data = payload.get("data", {})
        reference = data.get("reference")
        # Paystack sends amount in kobo (smallest unit)
        amount_kobo = data.get("amount", 0)
        amount = amount_kobo / 100
        currency = data.get("currency", "NGN")
        _credit_wallet_safe(
            provider_reference=reference,
            provider="paystack",
            amount=amount,
            currency=currency,
            payload=payload,
            db=db
        )

    elif event_type == "transfer.success":
        reference = payload.get("data", {}).get("reference")
        _mark_payout_complete(reference, "paystack", db)

    elif event_type == "transfer.failed":
        reference = payload.get("data", {}).get("reference")
        reason = payload.get("data", {}).get("complete_message", "Transfer failed")
        _mark_payout_failed(reference, "paystack", reason, db)


def _handle_mtn_momo(event, payload, db):
    """Process an MTN MoMo webhook event."""
    status = payload.get("status") or payload.get("event")
    reference = payload.get("financialTransactionId") or payload.get("referenceId")
    amount = payload.get("amount")
    currency = payload.get("currency", "UGX")

    if status in ("SUCCESSFUL", "success"):
        _credit_wallet_safe(
            provider_reference=reference,
            provider="mtn_momo",
            amount=amount,
            currency=currency,
            payload=payload,
            db=db
        )


def _handle_airtel_money(event, payload, db):
    """Process an Airtel Money webhook event."""
    status = payload.get("status") or payload.get("transaction", {}).get("status")
    reference = (
        payload.get("transaction", {}).get("id")
        or payload.get("referenceId")
    )
    amount = (
        payload.get("transaction", {}).get("amount")
        or payload.get("amount")
    )
    currency = (
        payload.get("transaction", {}).get("currency")
        or payload.get("currency", "UGX")
    )

    if status in ("TS", "SUCCESS", "success"):
        _credit_wallet_safe(
            provider_reference=reference,
            provider="airtel_money",
            amount=amount,
            currency=currency,
            payload=payload,
            db=db
        )


# ---------------------------------------------------------------------------
# Core wallet credit - the only place a webhook credits a wallet
# ---------------------------------------------------------------------------

def _credit_wallet_safe(
    provider_reference: str,
    provider: str,
    amount,
    currency: str,
    payload: dict,
    db
):
    """
    Credit a wallet from a webhook event.

    IDEMPOTENCY: Checks TransactionModel for existing provider_reference
    BEFORE crediting. This is the safety net that prevents double-credits
    when a webhook event is retried.

    The user_id is resolved from the provider_reference stored in
    our own transaction record (created when the payment was initiated).
    """
    from flask import current_app
    from decimal import Decimal
    from app.wallet.models.transaction import TransactionModel, TransactionStatus
    from app.wallet.services.wallet_service import WalletService

    if not provider_reference:
        logger.warning(f"No provider_reference in {provider} webhook - skipping credit")
        return

    if amount is None:
        logger.warning(f"No amount in {provider} webhook ref={provider_reference} - skipping")
        return

    amount = Decimal(str(amount))

    # -----------------------------------------------------------------------
    # IDEMPOTENCY CHECK
    # Look up the transaction we created when the user initiated the payment.
    # This holds the user_id and is our proof the payment was expected.
    # If already COMPLETED, do nothing - this is a duplicate webhook delivery.
    # -----------------------------------------------------------------------
    existing_tx = TransactionModel.query.filter_by(
        client_request_id=provider_reference
    ).first()

    if existing_tx:
        if existing_tx.status == TransactionStatus.COMPLETED:
            logger.info(
                f"Webhook duplicate - {provider} ref={provider_reference} "
                f"already credited as tx={existing_tx.id}. Skipping."
            )
            return
        user_id = existing_tx.user_id
    else:
        # No matching initiated transaction found.
        # This can happen if the payment was initiated outside our system
        # or the initiation record was lost. Log and skip - we cannot
        # safely credit an unknown user.
        logger.error(
            f"No initiated transaction found for {provider} ref={provider_reference}. "
            f"Cannot credit wallet. Manual review required."
        )
        # Don't raise - let the event be marked processed so it doesn't
        # loop. The error log is the alert.
        return

    # Credit the wallet
    try:
        wallet_svc = WalletService()
        result = wallet_svc.deposit(
            user_id=user_id,
            amount=amount,
            currency=currency,
            client_request_id=provider_reference,  # idempotency key
            metadata={"webhook_provider": provider, "raw_payload": payload},
            payment_provider=provider,
            external_reference=provider_reference
        )
        logger.info(
            f"Wallet credited: user={user_id} amount={amount} {currency} "
            f"provider={provider} ref={provider_reference} "
            f"tx={result.get('transaction_id')}"
        )
    except Exception as e:
        # Re-raise so the caller marks this event for retry
        logger.error(
            f"Failed to credit wallet for {provider} ref={provider_reference}: {e}"
        )
        raise


def _alert_owner_dead_letter(event):
    """Notify the application owner (email + SMS) and increment Redis counter
    when a webhook event exhausts retries and is moved to dead_letter.

    This function intentionally swallows any exceptions; notification
    failures must never affect the persisted dead_letter state.
    """
    from app.extensions import redis_client

    # Build alert message
    message = (
        f"AFCON360 ALERT: Webhook event {event.id} ({event.provider}/{event.event_type}) "
        f"has failed {MAX_ATTEMPTS} times and is now in dead_letter. "
        "Manual review required at /admin/webhooks/failed"
    )

    try:
        # Find an owner or super_admin user using a pure DB join for performance.
        from app.identity.models.user import User, UserRole
        from app.identity.models.roles_permission import Role
        from app.extensions import db

        try:
            owner = (
                db.session.query(User)
                .join(UserRole, User.roles)
                .join(Role, UserRole.role)
                .filter(Role.name.in_(["owner", "super_admin"]))
                .order_by(Role.level.asc())
                .first()
            )
        except Exception:
            # If DB-level join fails (e.g. tests without DB), fall back to
            # scanning the in-memory query API to locate an owner. This keeps
            # testability while preferring the fast DB path in production.
            try:
                users = User.query.all()
                owner = next((u for u in users if getattr(u, 'is_super_admin', lambda: False)()), None)
            except Exception:
                owner = None

        # Send SMS and email if we found an owner
        if owner:
            try:
                if getattr(owner, "phone", None) and getattr(owner, "phone_verified", False):
                    try:
                        from app.services.sms_service import send_sms
                        send_sms(owner.phone, message)
                    except Exception:
                        logger.exception("Failed to send dead-letter SMS to owner %s", owner.id)

                if getattr(owner, "email", None) and getattr(owner, "email_verified", False):
                    try:
                        from app.transport.services.notification_service import NotificationService
                        NotificationService.send_email(
                            to=owner.email,
                            subject="AFCON360 ALERT: Webhook dead-letter",
                            body=message,
                        )
                    except Exception:
                        logger.exception("Failed to send dead-letter email to owner %s", owner.id)
            except Exception:
                logger.exception("Owner notification failed for webhook event %s", event.id)

        # Increment Redis counter so dashboards/alerts can surface counts
        try:
            # redis_client exposes Redis commands via __getattr__ in LazyRedis
            from app import extensions as ext
            try:
                ext.redis_client.incr("dead_letter_count")
            except Exception:
                logger.exception("Failed to increment dead_letter_count in Redis")

            # Also emit a metric via configured metrics client (e.g. StatsD)
            try:
                metrics = getattr(ext, 'metrics_client', None)
                if metrics and hasattr(metrics, 'increment'):
                    metrics.increment('dead_letter_count')
            except Exception:
                logger.exception("Failed to emit dead_letter_count metric")
        except Exception:
            logger.exception("Failed to record dead_letter observability signals")

    except Exception:
        # Catch-all - notifications are best-effort
        logger.exception("Unexpected error while alerting owner for dead_letter event %s", event.id)


def _mark_payout_complete(reference: str, provider: str, db):
    """Mark a payout transaction as completed."""
    if not reference:
        return
    from app.wallet.models.transaction import TransactionModel, TransactionStatus, TransactionType
    tx = TransactionModel.query.filter_by(
        client_request_id=reference,
    ).first()
    if tx and tx.tx_type == TransactionType.WITHDRAW:
        tx.status = TransactionStatus.COMPLETED
        db.session.commit()
        logger.info(f"Payout completed: {provider} ref={reference}")


def _mark_payout_failed(reference: str, provider: str, reason: str, db):
    """Mark a payout transaction as failed."""
    if not reference:
        return
    from app.wallet.models.transaction import TransactionModel, TransactionStatus, TransactionType
    tx = TransactionModel.query.filter_by(
        client_request_id=reference,
    ).first()
    if tx and tx.tx_type == TransactionType.WITHDRAW:
        tx.status = TransactionStatus.FAILED
        db.session.commit()
        logger.error(f"Payout failed: {provider} ref={reference} reason={reason}")

