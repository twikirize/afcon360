# app/identity/models/organisation_catalogues.py
"""
Organisation classification catalogue tables.

These tables are the database-backed source of truth for the *organisation
type* options shown on organisation onboarding (and any further consumer of
the classification vocabulary). `Organisation` keeps its classification
String columns + existing fields; these config tables drive the form options
and the route/template catalogues so the values presented cannot drift from
what the domain accepts.

FROZEN CONTRACT (see catalog_data for the canonical values):
  * ``organisation_categories``  — the 8 top-level category groups.
  * ``organisation_types``       — the 39 canonical type codes, each mapped
    to exactly one category via ``category_code`` (1:1 with the frozen
    ``OrganizationType`` enum values).

Models intentionally use distinct names to avoid colliding with the existing
``OrganizationType`` enum in ``organization_types.py``.
"""

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.extensions import db
from app.models.base import BaseModel


class OrganisationCategory(BaseModel):
    """Top-level organisation category group (e.g. Hospitality & Tourism)."""

    __tablename__ = "organisation_categories"
    __table_args__ = (
        UniqueConstraint("code", name="uq_organisation_category_code"),
    )

    code = Column(String(50), nullable=False, index=True)
    label = Column(String(120), nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    types = relationship(
        "OrganisationTypeCatalogue",
        back_populates="category",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<OrganisationCategory {self.code}>"


class OrganisationTypeCatalogue(BaseModel):
    """Canonical organisation type code (e.g. `hotel`), grouped by category."""

    __tablename__ = "organisation_types"
    __table_args__ = (
        UniqueConstraint("code", name="uq_organisation_type_code"),
    )

    code = Column(String(40), nullable=False, index=True)
    label = Column(String(120), nullable=False)
    category_code = Column(
        String(50),
        ForeignKey("organisation_categories.code", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    category = relationship("OrganisationCategory", back_populates="types")

    def __repr__(self):
        return f"<OrganisationTypeCatalogue {self.code}>"