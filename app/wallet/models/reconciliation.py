from datetime import datetime
from sqlalchemy import Column, BigInteger, String, DateTime, JSON, Text
from app.models.base import ProtectedModel


class ReconciliationRun(ProtectedModel):
    __tablename__ = "reconciliation_runs"

    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    summary = Column(JSON, nullable=True)
    status = Column(String(32), default="running", nullable=False)
    notes = Column(Text, nullable=True)

    def mark_completed(self, summary: dict, session=None):
        self.completed_at = datetime.utcnow()
        self.summary = summary
        self.status = "completed"
        if session:
            session.add(self)


class ReconciliationIssue(ProtectedModel):
    __tablename__ = "reconciliation_issues"

    run_id = Column(BigInteger, nullable=False, index=True)
    issue_type = Column(String(64), nullable=False)
    details = Column(JSON, nullable=True)
    resolved = Column(String(8), default="no", nullable=False)

