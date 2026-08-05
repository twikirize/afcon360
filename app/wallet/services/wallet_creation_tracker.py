"""
Wallet Creation Tracker - Traceable wallet creation lifecycle with anti-hijacking.

Features:
- Step-by-step tracking (session + database)
- Session binding (prevent hijacking)
- IP address tracking
- User-agent tracking
- Audit trail (persisted to database for admin visibility)
- Ownership verification
"""
from enum import Enum
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from flask import session, request, current_app
import logging

logger = logging.getLogger(__name__)


class WalletCreationEvent(str, Enum):
    """Valid wallet creation events."""
    INITIATED = "initiated"
    EMAIL_VERIFIED = "email_verified"
    TERMS_ACCEPTED = "terms_accepted"
    KYC_CHECKED = "kyc_checked"
    ACCOUNT_CREATED = "account_created"
    ACCOUNT_VERIFIED = "account_verified"
    ACTIVATION_PENDING = "activation_pending"
    ACTIVATED = "activated"
    COMPLETED = "completed"
    FAILED = "failed"


class WalletCreationTracker:
    """
    Track wallet creation lifecycle with anti-hijacking safeguards.

    Features:
    - Step-by-step tracking (session + database)
    - Session binding (prevent hijacking)
    - IP address tracking
    - User-agent tracking
    - Audit trail (persisted to database for admin visibility)
    - Ownership verification
    """

    SESSION_KEY = "wallet_creation"

    @classmethod
    def _get_session_data(cls) -> Dict[str, Any]:
        """Get or create session data for wallet creation."""
        if cls.SESSION_KEY not in session:
            session[cls.SESSION_KEY] = {
                "steps": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "session_id": session.get("_id", "unknown"),
                "ip": request.remote_addr if request else "unknown",
                "user_agent": request.user_agent.string if request and request.user_agent else "unknown",
                "user_id": None,
                "account_id": None,
                "status": "not_started"
            }
        return session[cls.SESSION_KEY]

    @classmethod
    def _persist_to_db(cls, user_id: int, event: WalletCreationEvent,
                       account_id: Optional[str] = None,
                       metadata: Optional[Dict] = None):
        """Persist a creation event to the database for admin visibility."""
        try:
            from app.wallet.models.creation_tracker import WalletCreationEventModel
            from app.extensions import db

            db_event = WalletCreationEventModel(
                user_id=user_id,
                account_id=account_id,
                event=event.value,
                step_order=len(cls._get_session_data().get("steps", [])) + 1,
                step_metadata=metadata or {},
                session_id=session.get("_id", "unknown"),
                ip_address=request.remote_addr if request else None,
                user_agent=request.user_agent.string if request and request.user_agent else None
            )
            db.session.add(db_event)
            logger.info(f"Persisted tracker event: {event.value} for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to persist tracker event: {e}")

    @classmethod
    def log_step(cls, user_id: int, event: WalletCreationEvent, metadata: Optional[Dict] = None):
        """Log a wallet creation step (session + database)."""
        try:
            data = cls._get_session_data()

            if isinstance(event, str):
                try:
                    event = WalletCreationEvent(event.lower())
                except ValueError:
                    logger.error(f"Invalid wallet creation event: {event}")
                    return

            if not data.get("user_id"):
                data["user_id"] = user_id

            step = {
                "event": event.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "user_id": user_id,
                "metadata": metadata or {}
            }

            data["steps"].append(step)
            data["last_updated"] = datetime.now(timezone.utc).isoformat()
            data["status"] = event.value

            session.modified = True

            cls._persist_to_db(user_id, event, metadata=metadata)

            logger.info(f"Wallet creation step: {event.value} for user {user_id}")

        except Exception as e:
            logger.error(f"Failed to log wallet creation step: {e}")

    @classmethod
    def record_account_created(cls, user_id: int, account_id: str):
        """Record that the account was created."""
        data = cls._get_session_data()
        data["account_id"] = account_id
        data["user_id"] = user_id
        session.modified = True

        cls.log_step(user_id, WalletCreationEvent.ACCOUNT_CREATED, {"account_id": account_id})

    @classmethod
    def record_activation(cls, user_id: int, account_id: str):
        """Record that the wallet was activated."""
        cls.log_step(user_id, WalletCreationEvent.ACTIVATED, {"account_id": account_id})

        data = cls._get_session_data()
        data["status"] = "activated"
        session.modified = True

    @classmethod
    def record_completion(cls, user_id: int, account_id: str):
        """Record that the wallet creation is complete."""
        cls.log_step(user_id, WalletCreationEvent.COMPLETED, {"account_id": account_id})

        data = cls._get_session_data()
        data["status"] = "completed"
        session.modified = True

    @classmethod
    def from_session(cls) -> Optional[Dict[str, Any]]:
        """Get wallet creation data from session."""
        if cls.SESSION_KEY not in session:
            return None
        return session[cls.SESSION_KEY]

    @classmethod
    def get_creation_status(cls, user_id: int) -> Dict[str, Any]:
        """Get the current wallet creation status for a user."""
        data = cls.from_session()
        if not data:
            return {
                "has_started": False,
                "is_complete": False,
                "is_activated": False,
                "current_step": None,
                "steps": []
            }

        steps = data.get("steps", [])

        return {
            "has_started": len(steps) > 0,
            "is_complete": data.get("status") == "completed",
            "is_activated": data.get("status") == "activated",
            "current_step": steps[-1].get("event") if steps else None,
            "steps": steps,
            "created_at": data.get("created_at"),
            "last_updated": data.get("last_updated"),
            "account_id": data.get("account_id"),
            "session_id": data.get("session_id"),
            "ip": data.get("ip"),
            "user_agent": data.get("user_agent")
        }

    @classmethod
    def get_events_for_account(cls, account_id: str) -> List[Dict[str, Any]]:
        """Get all persisted creation events for an account (admin view)."""
        try:
            from app.wallet.models.creation_tracker import WalletCreationEventModel

            events = WalletCreationEventModel.query.filter_by(
                account_id=account_id
            ).order_by(WalletCreationEventModel.created_at.asc()).all()

            return [
                {
                    "event": e.event,
                    "timestamp": e.created_at.isoformat() if e.created_at else None,
                    "step_order": e.step_order,
                    "metadata": e.step_metadata or {},
                    "ip_address": e.ip_address,
                    "user_agent": e.user_agent,
                    "session_id": e.session_id
                }
                for e in events
            ]
        except Exception as e:
            logger.error(f"Failed to get events for account {account_id}: {e}")
            return []

    @classmethod
    def get_events_for_user(cls, user_id: int) -> List[Dict[str, Any]]:
        """Get all persisted creation events for a user (admin view)."""
        try:
            from app.wallet.models.creation_tracker import WalletCreationEventModel

            events = WalletCreationEventModel.query.filter_by(
                user_id=user_id
            ).order_by(WalletCreationEventModel.created_at.asc()).all()

            return [
                {
                    "event": e.event,
                    "timestamp": e.created_at.isoformat() if e.created_at else None,
                    "step_order": e.step_order,
                    "metadata": e.step_metadata or {},
                    "account_id": str(e.account_id) if e.account_id else None,
                    "ip_address": e.ip_address,
                    "user_agent": e.user_agent,
                    "session_id": e.session_id
                }
                for e in events
            ]
        except Exception as e:
            logger.error(f"Failed to get events for user {user_id}: {e}")
            return []

    @classmethod
    def verify_account_ownership(cls, account_id: str, user_id: int) -> bool:
        """Verify that the created account belongs to the current user."""
        from app.wallet.models.ledger import AccountModel
        from app.identity.models.user import User

        try:
            if isinstance(user_id, str):
                user = User.query.filter_by(public_id=user_id).first()
                if not user:
                    return False
                internal_id = user.id
            else:
                internal_id = user_id

            account = AccountModel.query.filter_by(
                id=account_id,
                user_id=internal_id
            ).first()

            if account:
                logger.info(f"Account ownership verified: {account_id} belongs to user {internal_id}")
                return True

            logger.warning(f"Account ownership verification failed: {account_id} does not belong to user {internal_id}")
            return False

        except Exception as e:
            logger.error(f"Account ownership verification error: {e}")
            return False

    @classmethod
    def clear(cls):
        """Clear wallet creation session data."""
        if cls.SESSION_KEY in session:
            session.pop(cls.SESSION_KEY)
            session.modified = True
            logger.info("Wallet creation session cleared")

    @classmethod
    def is_valid_session(cls, user_id: int) -> bool:
        """Check if the current session is valid for the user (anti-hijacking)."""
        data = cls.from_session()
        if not data:
            return False

        session_user_id = data.get("user_id")
        if session_user_id and session_user_id != user_id:
            logger.warning(f"Session hijacking attempt: session user {session_user_id} != current user {user_id}")
            return False

        return True
