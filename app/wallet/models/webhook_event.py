from datetime import datetime, timezone
from sqlalchemy import Column, BigInteger, String, DateTime, JSON, Integer, Text
from app.models.base import ProtectedModel


class WebhookEvent(ProtectedModel):
    __tablename__ = "webhook_events"

    provider = Column(String(64), nullable=False, index=True)
    event_type = Column(String(128), nullable=True)
    payload = Column(JSON, nullable=False)
    # Store the original raw request body as received (TEXT). This preserves
    # the exact byte ordering used by providers for HMAC signatures so the
    # worker can re-verify signatures reliably.
    raw_body = Column(Text, nullable=True)
    signature = Column(String(512), nullable=True)
    status = Column(String(32), nullable=False, default="queued", index=True)
    retry_count = Column(Integer, default=0, nullable=False)
    next_retry_at = Column(DateTime, nullable=True, index=True)
    last_error = Column(Text, nullable=True)
    processed_at = Column(DateTime, nullable=True)

    def mark_processed(self, session=None):
        self.status = "processed"
        self.processed_at = datetime.now(timezone.utc)
        if session:
            session.add(self)

    def mark_failed(self, error: str, session=None):
        self.retry_count = (self.retry_count or 0) + 1
        self.last_error = error
        self.status = "failed"
        if session:
            session.add(self)

