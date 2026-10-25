# app/audit/models.py
"""
Audit domain — canonical audit log model.

app/audit/models.AuditLog is the SINGLE SOURCE OF TRUTH for the platform
audit trail. app/models/audit.py (ActivityLog, table `activity_logs`) has
been retired; its capabilities live here:

  * log_instance()  — ActivityLog-style writer (target/actor instances)
  * .changes        — read-only alias for meta["changes"]
  * .target_type /
    .target_id      — read-only aliases for resource_type / resource_id
  * .actor /
    .actor_id       — read/write aliases for user / user_id

The `audit_logs` schema is UNCHANGED by this merge. Do not reintroduce a
parallel audit model — see app/models/__init__.py.
"""
import logging
from datetime import datetime

from app.extensions import db
from app.utils.id_kinds import IDKind
from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

logger = logging.getLogger(__name__)


class AuditLog(BaseModel):
    """
    Immutable audit log for compliance. Do NOT delete or modify entries
    programmatically. Avoid storing secrets or full PII in meta.

    Capability model:
      - `meta` (JSON, not null, default {}) is the canonical structured
        detail store. `changes` / `correlation_id` are folded into it via
        AuditLog.log(changes=..., meta={...}) and read back through
        read-only properties.
      - Writers never commit; the caller owns the transaction.
      - Two writer entry points: log() (explicit ids) and log_instance()
        (instance-based, ActivityLog ergonomics).
    """
    __tablename__ = "audit_logs"

    # FK to internal PKs
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    org_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="SET NULL"), nullable=True, index=True)

    action = Column(String(128), nullable=False, index=True)
    resource_type = Column(String(64), index=True)
    resource_id = Column(String(128), index=True, info={"id_kind": IDKind.EXTERNAL_STRING_ID})

    ip_address = Column(String(64), index=True)
    user_agent = Column(String(512))
    device_id = Column(String(128), index=True, info={"id_kind": IDKind.EXTERNAL_STRING_ID})
    meta = Column(JSON, nullable=False, default=dict)

    # Relationships
    user = relationship("User", lazy="joined")
    organisation = relationship("Organisation", lazy="joined")

    # ------------------------------------------------------------------
    # Read-time aliases (retired ActivityLog API surface)
    #
    # These are @property aliases — NOT columns. Per app/models/base.py
    # convention, only `_flag`/`_status`/`_computed` suffixes apply to
    # *new* computed fields; these are pure renames for compatibility.
    # ------------------------------------------------------------------
    @property
    def actor(self):
        return self.user

    @actor.setter
    def actor(self, value):
        self.user = value

    @property
    def actor_id(self):
        return self.user_id

    @actor_id.setter
    def actor_id(self, value):
        self.user_id = value

    @property
    def target_type(self):
        return self.resource_type

    @property
    def target_id(self):
        return self.resource_id

    @property
    def changes(self):
        return (self.meta or {}).get("changes")

    @property
    def correlation_id(self):
        return (self.meta or {}).get("correlation_id")

    # ------------------------------------------------------------------
    # Writers
    # ------------------------------------------------------------------
    @staticmethod
    def log(user_id=None, action=None, resource_type=None, resource_id=None,
            meta=None, ip_address=None, user_agent=None, org_id=None,
            device_id=None, changes=None, db_session=None):
        """
        Create an audit log entry WITHOUT committing.
        Caller must handle transaction commit/rollback.

        `changes` (ActivityLog compatibility) is folded into meta["changes"];
        `meta` remains the canonical structured-detail store, so callers that
        want both can pass both.

        Returns the entry (ActivityLog compatibility). Safe to ignore —
        existing callers that treat this as returning None are unaffected.
        """
        try:
            session = db_session or db.session
            merged_meta = dict(meta or {})
            if changes is not None:
                merged_meta["changes"] = changes
            entry = AuditLog(
                user_id=user_id,
                org_id=org_id,
                action=action,
                resource_type=resource_type,
                resource_id=str(resource_id) if resource_id is not None else None,
                ip_address=ip_address,
                user_agent=user_agent,
                device_id=device_id,
                meta=merged_meta,
            )
            session.add(entry)
            logger.info(f"Audit log entry created: {action} by user {user_id}")
            return entry
        except Exception as e:
            logger.error(f"Failed to create audit log entry: {e}")
            raise

    @classmethod
    def log_instance(cls, action, target, actor=None, changes=None, meta=None,
                     request=None, org_id=None, device_id=None, db_session=None):
        """
        ActivityLog-style writer: derive resource_type/resource_id from the
        target instance, and user_id from the actor instance.

        target:  ORM instance — resource_id prefers .public_id, falls back to .id
        actor:   ORM instance — user_id from .id; org_id from .org_id if not set
        request: optional Flask request — populates ip_address / user_agent
        """
        return cls.log(
            user_id=getattr(actor, "id", None) if actor is not None else None,
            org_id=org_id or (getattr(actor, "org_id", None) if actor is not None else None),
            action=action,
            resource_type=target.__class__.__name__.upper() if target is not None else None,
            resource_id=(
                getattr(target, "public_id", None) or getattr(target, "id", None)
            ) if target is not None else None,
            meta=meta,
            changes=changes,
            ip_address=getattr(request, "remote_addr", None) if request is not None else None,
            user_agent=(request.headers.get("User-Agent") if request is not None else None),
            device_id=device_id,
            db_session=db_session,
        )

    @staticmethod
    def recent_audits(limit=50, action=None):
        """Most recent audit entries, newest first.

        `action` optionally filters to a single action name (e.g.
        'MODULE_TOGGLE'), letting admin surfaces show the trail for one
        feature without writing their own query.
        """
        query = AuditLog.query
        if action is not None:
            query = query.filter(AuditLog.action == action)
        return query.order_by(AuditLog.created_at.desc()).limit(limit).all()