# app/geo/models.py
"""
AFCON360 GEO - durable location observation history (roadmap GEO-15).

Domain-neutral observation records. GEO owns the geographic storage and
retrieval boundary; it does NOT own what an observation MEANS
(online/available/dispatchable/trip/booking stay with the producing
domain, here Transport).

One row = one immutable geographic fact: WHERE (latitude-first) + WHEN.
Two timestamps are kept apart on purpose:

- ``observed_at`` — the source observation time. The current Transport
  producer stamps server-receive time and forwards no trusted device
  timestamp, so ``observed_at`` IS the server-receive time unless a
  future producer provides better provenance. It is never refreshed by
  reads; a stale observation stays historically truthful.
- ``recorded_at`` — when this row was written. Lets readers prove that
  reading current state does not rewrite history.

Identity boundary: rows carry the domain's ``public_ref`` (driver
``driver_code``, vehicle ``license_plate``) plus this row's own
``public_id``. Internal integer IDs are never emitted. ``public_ref``
is a logical cross-domain reference (no db-level FK): GEO must keep
serving history even if the producing domain later removes its record.

Retention: no location-observation retention policy exists in the
project (RETENTION_POLICY = PENDING PRODUCT/COMPLIANCE DECISION).
Rows are therefore never auto-purged; any future cleanup must use the
sanctioned soft-delete mechanism, never raw DELETE.
"""

import uuid as uuid_lib
from datetime import datetime, timezone

from app.extensions import db
from app.models.base import BaseModel


class LocationObservation(BaseModel):
    """One immutable location observation for one entity's history."""

    __tablename__ = "geo_location_observations"
    __table_args__ = (
        # Chronological lookup by entity: the retrieval contract.
        db.Index(
            "ix_geo_obs_entity_ref_time",
            "entity_type",
            "public_ref",
            "observed_at",
        ),
        # Retention-pruning scan order (no policy yet; index is ready).
        db.Index("ix_geo_obs_recorded", "recorded_at"),
    )

    public_id = db.Column(
        db.String(64),
        unique=True,
        nullable=False,
        index=True,
        default=lambda: str(uuid_lib.uuid4()),
    )

    # 'driver' | 'vehicle' (validated app-side against ENTITY_TYPES;
    # no CHECK constraint: Alembic autogenerate cannot detect them).
    entity_type = db.Column(db.String(16), nullable=False)

    # Domain public reference (driver_code / license_plate). Logical
    # reference only — never an internal ID, never a db-level FK.
    public_ref = db.Column(db.String(64), nullable=False)

    # Latitude-first coordinates, re-validated by the writer.
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    accuracy = db.Column(db.Float, nullable=True)

    # Source observation time (currently server-receive time — see
    # module docstring). Never refreshed by reads.
    observed_at = db.Column(db.DateTime(timezone=True), nullable=False)

    # Row-write time. Distinct from observed_at by design.
    recorded_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    source = db.Column(
        db.String(64), nullable=False, default="transport-tracking"
    )


__all__ = ["LocationObservation"]
