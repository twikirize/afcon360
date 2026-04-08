# app/models/base.py
from datetime import datetime
from sqlalchemy import Column, BigInteger, DateTime, Boolean, event
from sqlalchemy.sql import func
from app.extensions import db
from app.utils.id_guard import IDGuard

class TimestampMixin:
    """Mixin for models that require created_at and updated_at timestamps"""
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        index=True
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        index=True
    )

class BaseModel(TimestampMixin, db.Model):
    """
    Enterprise Base Model for AFCON 360
    - BIGINT Primary Keys
    - Automatic Timestamps
    - Soft Delete Support
    - Runtime ID Protection
    """
    __abstract__ = True

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Soft Delete Fields
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True)

    def soft_delete(self):
        """Mark record as deleted without removing from DB"""
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
        db.session.add(self)
        db.session.commit()

    def restore(self):
        """Restore a soft-deleted record"""
        self.is_deleted = False
        self.deleted_at = None
        db.session.add(self)
        db.session.commit()

    def __setattr__(self, name, value):
        """Intercept attribute assignment to catch ID type mistakes in development"""
        # session_id and user_id in ServerSession are intentional UUID strings.
        # We skip the IDGuard BIGINT check for these specific cases.
        is_excluded = name == 'session_id' or \
                     (self.__class__.__name__ == 'ServerSession' and name == 'user_id')

        if name.endswith('_id') and name != 'id' and not is_excluded and value is not None:
            # Enable guard only in non-production
            IDGuard.enable()
            IDGuard.check_fk_assignment(
                self.__class__.__name__,
                name,
                value,
                f"Assignment in {self.__class__.__name__}.__setattr__"
            )
        super().__setattr__(name, value)

    def save(self):
        """Save with automatic type validation"""
        db.session.add(self)
        db.session.commit()
        return self

class ProtectedModel(BaseModel):
    """Alias for legacy compatibility"""
    __abstract__ = True

# Global Event Listener to force updated_at update
@event.listens_for(BaseModel, 'before_update', propagate=True)
def _set_updated_at(mapper, connection, target):
    if hasattr(target, 'updated_at'):
        target.updated_at = datetime.utcnow()
