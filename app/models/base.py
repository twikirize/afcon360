# app/models/base.py
"""
DEVELOPER SAFETY GUARD - SQLAlchemy Model Conventions

RULES FOR THIS PROJECT:
1. NEVER name @property the same as a Column field
2. All computed fields must use suffix:
   - _flag
   - _status
   - _computed
3. SQLAlchemy Column names are DB source of truth
4. Properties are derived only

Violations can cause:
- ORM mapping conflicts
- Runtime attribute errors
- Data integrity issues
- Debugging nightmares
"""

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
        default=datetime.utcnow,  # ← Python-side: populates before INSERT
        server_default=func.now(),  # ← DB-side: fallback for raw SQL inserts
        index=True
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,  # ← Python-side: populates before INSERT
        server_default=func.now(),
        onupdate=datetime.utcnow,  # ← Python-side onupdate too, for consistency
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
        # String/UUID identifier columns that end in _id but are NOT foreign keys.
        # Add any new non-FK _id columns here rather than hardcoding inline.
        NON_FK_STRING_IDS = {
            'session_id',  # Session.session_id — UUID string
            'public_id',  # User.public_id — UUID for public exposure/Flask-Login
            'key_id',  # APIKey.key_id — string key identifier
            'device_id',  # Session.device_id — string device identifier
            'resource_id',  # AuditLog.resource_id — UUID string
        }

        # Check if this is an _id field that needs validation
        if name.endswith('_id') and name != 'id' and value is not None:
            # First, check if it's in the NON_FK_STRING_IDS list
            if name in NON_FK_STRING_IDS:
                # Skip validation - these are internal string identifiers, not public IDs or FKs
                pass
            else:
                # Import SQLAlchemy types here to avoid circular imports
                from sqlalchemy import String, Text, BigInteger
                # Get column if table exists
                column = None
                if hasattr(self.__class__, '__table__') and self.__class__.__table__ is not None:
                    column = self.__class__.__table__.columns.get(name)

                IDGuard.enable()
                if column is not None and isinstance(column.type, (String, Text)):
                    # String/Text type: treat as public ID
                    IDGuard.check_public_id(
                        value,
                        f"Assignment in {self.__class__.__name__}.__setattr__"
                    )
                else:
                    # BigInteger type, column not found, or no table: treat as internal FK
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

# SQLite BIGINT auto-increment fix
@event.listens_for(BaseModel, 'before_insert', propagate=True)
def fix_sqlite_autoincrement(mapper, connection, target):
    """Manually set ID for SQLite since it doesn't support BIGINT auto-increment"""
    if connection.engine.name != 'sqlite':
        return

    # Get primary key column
    pk_col = mapper.primary_key[0]
    pk_name = pk_col.name

    # Check if ID is None (needs generation)
    if getattr(target, pk_name) is None:
        table_name = mapper.local_table.name
        # Get current max ID
        result = connection.execute(
            f"SELECT COALESCE(MAX({pk_name}), 0) FROM {table_name}"
        ).scalar()
        # Set new ID
        setattr(target, pk_name, result + 1)

# Global Event Listener to force updated_at update
@event.listens_for(BaseModel, 'before_update', propagate=True)
def _set_updated_at(mapper, connection, target):
    if hasattr(target, 'updated_at'):
        target.updated_at = datetime.utcnow()
