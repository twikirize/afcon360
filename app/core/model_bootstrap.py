"""Design-2 PostgreSQL model-bootstrap schema path for AFCON360.

``db.create_all()`` is a separately identified PostgreSQL *model-bootstrap*
path.  A database provisioned this way carries a dedicated, non-Alembic
marker table and is NEVER stamped or represented as Alembic ``head``.
H3/Alembic remains the authoritative installation and upgrade path.

See ``docs/transport/fixes/B0-FROZEN-BASELINE-ENUM-INVENTORY-AND-PLAN.md``
Addendum B, Design 2.

States
------
``EMPTY``
    No marker, no ``alembic_version``, no application tables.
``MODEL_BOOTSTRAP_BUILDING``
    Marker row status ``building``: an earlier bootstrap started and did not
    finish.  The database is left exactly as the failed run found it.
``MODEL_BOOTSTRAP_COMPLETE``
    Marker row status ``complete`` with a schema fingerprint.
``MIGRATION_BUILT_AT_HEAD``
    ``alembic_version`` equals the single migration head; no marker.
``MIGRATION_BUILT_NOT_AT_HEAD``
    ``alembic_version`` differs from the head (or is ambiguous).
``UNMARKED_NONEMPTY``
    Application tables exist but neither marker nor ``alembic_version`` does.
``CONTRADICTORY``
    Marker and ``alembic_version`` are both present.

Only ``EMPTY`` is bootstrapped.  Every other state stops with diagnostics:
this path never repairs, drops, re-stamps or migrates an existing database.

Enum ownership
--------------
PostgreSQL ``CREATE TYPE`` has no ``IF NOT EXISTS`` (verified: PostgreSQL 15
manual, ``CREATE TYPE``), so each type may have exactly one creation owner:

* Group A -- declared with ``create_type=False`` in the models, so SQLAlchemy
  will not create them.  This module creates them explicitly from the
  reviewed inventory below, then refuses an incompatible existing type.
* Group B -- left to ``db.create_all()``.

The inventory below is the reviewed source of truth.  A model change that
adds, removes or reorders an enum is rejected until the inventory is
updated, so ownership can never drift silently.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import sqlalchemy as sa
from sqlalchemy import Column, Float, MetaData, Table, Text, select
from sqlalchemy.dialects.postgresql import OID

__all__ = [
    "MARKER_TABLE",
    "MARKER_KEY",
    "STATE_EMPTY",
    "STATE_MODEL_BOOTSTRAP_BUILDING",
    "STATE_MODEL_BOOTSTRAP_COMPLETE",
    "STATE_MIGRATION_BUILT_AT_HEAD",
    "STATE_MIGRATION_BUILT_NOT_AT_HEAD",
    "STATE_UNMARKED_NONEMPTY",
    "STATE_CONTRADICTORY",
    "ModelBootstrapError",
    "EnumSpec",
    "MarkerRow",
    "DatabaseState",
    "BootstrapResult",
    "collect_enum_specs",
    "partition_enum_ownership",
    "labels_identical",
    "compute_schema_fingerprint",
    "build_enum_type_block",
    "classify_database_state",
    "bootstrap_model_schema",
    "validate_model_bootstrap",
]

# --------------------------------------------------------------------------
# Marker
# --------------------------------------------------------------------------

MARKER_TABLE = "afcon360_model_bootstrap"
MARKER_KEY = "afcon360-model-bootstrap"
STATUS_BUILDING = "building"
STATUS_COMPLETE = "complete"

STATE_EMPTY = "empty"
STATE_MODEL_BOOTSTRAP_BUILDING = "model_bootstrap_building"
STATE_MODEL_BOOTSTRAP_COMPLETE = "model_bootstrap_complete"
STATE_MIGRATION_BUILT_AT_HEAD = "migration_built_at_head"
STATE_MIGRATION_BUILT_NOT_AT_HEAD = "migration_built_not_at_head"
STATE_UNMARKED_NONEMPTY = "unmarked_nonempty"
STATE_CONTRADICTORY = "contradictory"

_STATES_REQUIRING_STOP = (
    STATE_MODEL_BOOTSTRAP_BUILDING,
    STATE_MIGRATION_BUILT_AT_HEAD,
    STATE_MIGRATION_BUILT_NOT_AT_HEAD,
    STATE_UNMARKED_NONEMPTY,
    STATE_CONTRADICTORY,
)

# PostgreSQL system catalogs, declared rather than reflected so that catalog
# reads stay on the SQLAlchemy expression API and emit no reflection noise.
_PG_CATALOG_METADATA = MetaData()
_PG_ENUM = Table(
    "pg_enum",
    _PG_CATALOG_METADATA,
    Column("enumtypid", OID, nullable=False),
    Column("enumsortorder", Float, nullable=False),
    Column("enumlabel", Text, nullable=False),
    schema="pg_catalog",
)
_PG_TYPE = Table(
    "pg_type",
    _PG_CATALOG_METADATA,
    Column("oid", OID, primary_key=True),
    Column("typname", Text, nullable=False),
    Column("typnamespace", OID, nullable=False),
    schema="pg_catalog",
)
_PG_NAMESPACE = Table(
    "pg_namespace",
    _PG_CATALOG_METADATA,
    Column("oid", OID, primary_key=True),
    Column("nspname", Text, nullable=False),
    schema="pg_catalog",
)

_MARKER_METADATA = MetaData()
MARKER_TABLE_OBJ = Table(
    MARKER_TABLE,
    _MARKER_METADATA,
    Column("marker", Text, primary_key=True, nullable=False),
    Column("status", Text, nullable=False),
    Column("fingerprint", Text, nullable=False),
    Column("created_at", sa.DateTime(timezone=True), nullable=False,
           server_default=sa.func.now()),
    Column("updated_at", sa.DateTime(timezone=True), nullable=False,
           server_default=sa.func.now()),
)

_ALEMBIC_METADATA = MetaData()
ALEMBIC_VERSION_TABLE = Table(
    "alembic_version",
    _ALEMBIC_METADATA,
    Column("version_num", Text, primary_key=True, nullable=False),
)

_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]*$")

# --------------------------------------------------------------------------
# Reviewed enum inventory (Addendum B, section B.1.3)
#
# Group A: declared create_type=False; this module is the sole creation owner.
# Group B: left to db.create_all(); this module must never create them.
# --------------------------------------------------------------------------

GROUP_A_EXPECTED = {
    'apicallstatus': ('SUCCESS', 'FAILURE', 'TIMEOUT', 'RATE_LIMITED',),
    'auditseverity': ('INFO', 'WARNING', 'CRITICAL', 'SECURITY',),
    'compensationmodel': ('REVENUE_SPLIT', 'FIXED_RENTAL', 'HYBRID', 'FIXED_FEE', 'PERCENTAGE', 'PER_KM', 'PER_HOUR', 'DAILY_RATE', 'WEEKLY_RATE', 'MONTHLY_RATE', 'REVENUE_SHARE',),
    'compliance_decision': ('allowed', 'blocked', 'conditional',),
    'compliance_enforcement_level': ('optional', 'conditional', 'mandatory',),
    'compliancestatus': ('PENDING_REVIEW', 'UNDER_REVIEW', 'APPROVED', 'SUSPENDED', 'REVOKED', 'BLACKLISTED',),
    'contractstatus': ('DRAFT', 'ACTIVE', 'SUSPENDED', 'TERMINATED', 'EXPIRED', 'PENDING_SIGNATURE',),
    'currency': ('USD', 'EUR', 'GBP', 'XOF', 'XAF', 'NGN', 'KES', 'GHS', 'ZAR', 'UGX',),
    'dataaccesstype': ('READ', 'EXPORT', 'DELETE', 'MODIFY',),
    'doc_verification_status': ('pending', 'verified', 'rejected',),
    'entity_type': ('organisation', 'individual',),
    'gateway_environment': ('SANDBOX', 'PRODUCTION',),
    'gender_enum': ('male', 'female', 'other', 'unspecified',),
    'id_type_enum': ('passport', 'national_id', 'driver_license', 'other',),
    'incidentseverity': ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL',),
    'ind_document_type': ('id_card', 'passport', 'driver_license', 'proof_of_address',),
    'ind_verification_status': ('pending', 'verified', 'rejected', 'expired', 'suspended',),
    'kyb_doc_status': ('pending', 'verified', 'rejected',),
    'kyc_level_enum': ('basic', 'enhanced', 'government',),
    'org_change_source': ('system', 'user', 'admin',),
    'org_change_type': ('create', 'update', 'delete', 'verify', 'suspend',),
    'org_kyb_check_status': ('pending', 'passed', 'failed', 'manual_review',),
    'org_kyb_check_type': ('identity', 'tax', 'license', 'ubo', 'sanctions',),
    'org_lifecycle_state': ('draft', 'registered', 'approved', 'suspended', 'closed',),
    'org_verification_status': ('unverified', 'pending', 'verified', 'rejected', 'suspended', 'expired',),
    'payment_gateway_provider': ('FLUTTERWAVE', 'PAYSTACK', 'MTN_MOMO', 'AIRTEL_MONEY', 'VISA', 'MASTERCARD', 'PAYPAL', 'ALIPAY', 'WECHAT_PAY', 'BANK_TRANSFER', 'STRIPE', 'MPESA',),
    'paymentstatus': ('PENDING', 'AUTHORIZED', 'CAPTURED', 'PARTIALLY_CAPTURED', 'REFUNDED', 'PARTIALLY_REFUNDED', 'FAILED', 'CANCELLED',),
    'propertydocumentstatus': ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED',),
    'propertydocumenttype': ('ID_DOCUMENT', 'BUSINESS_LICENSE', 'TAX_CERTIFICATE', 'PROPERTY_DEED', 'INSURANCE_CERTIFICATE', 'OTHER',),
    'providertype': ('INDIVIDUAL_DRIVER', 'HOTEL_FLEET', 'TOUR_OPERATOR', 'TRANSPORT_COMPANY', 'EXTERNAL_PLATFORM',),
    'risk_tier': ('low', 'medium', 'high',),
    'rvpcr_status_enum': ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED', 'EXPIRED',),
    'servicetype': ('AIRPORT_ARRIVAL', 'AIRPORT_DEPARTURE', 'STADIUM_SHUTTLE', 'HOTEL_TRANSFER', 'CITY_TOUR', 'ON_DEMAND', 'SCHEDULED_ROUTE', 'CUSTOM_TOUR',),
    'transactiontype': ('DEPOSIT', 'WITHDRAWAL', 'TRANSFER', 'REFUND', 'FEE', 'REVERSAL', 'CURRENCY_EXCHANGE', 'COMMISSION', 'PAYOUT', 'EXCHANGE',),
    'ubo_type': ('individual', 'corporate',),
    'vehicleclass': ('ECONOMY', 'COMFORT', 'PREMIUM', 'LUXURY', 'VAN', 'BUS',),
    'verification_status_enum': ('pending', 'verified', 'rejected', 'suspended',),
    'verificationtier': ('PENDING', 'BASIC_VERIFIED', 'PLATFORM_VERIFIED', 'EVENT_CERTIFIED',),
    'window_mode_enum': ('CALENDAR', 'ROLLING',),
}

GROUP_B_EXPECTED = {
    'applicationstatus': ('PENDING', 'UNDER_REVIEW', 'APPROVED', 'REJECTED', 'WITHDRAWN', 'EXPIRED',),
    'compliancecasepriority': ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW',),
    'compliancecasestatus': ('OPEN', 'IN_REVIEW', 'PENDING_INFO', 'APPROVED', 'REJECTED', 'ESCALATED', 'CLOSED',),
    'compliancecasetype': ('KYC_REVIEW', 'KYB_REVIEW', 'AML_ALERT', 'PAYOUT_REVIEW', 'DATA_REQUEST', 'FLAG_ESCALATION', 'LICENSE_REVIEW', 'OTHER',),
    'compliancereporttype': ('KYC_SUMMARY', 'AML_SUMMARY', 'PAYOUT_SUMMARY', 'CASE_HISTORY', 'AUDIT_TRAIL', 'RISK_ASSESSMENT', 'REGULATORY_FILING',),
    'datasubjectrequeststatus': ('PENDING', 'VERIFIED', 'PROCESSING', 'COMPLETED', 'REJECTED', 'EXPIRED',),
    'datasubjectrequesttype': ('ACCESS', 'DELETION', 'RECTIFICATION', 'PORTABILITY', 'OBJECTION',),
    'marketplacelistingstatus': ('DRAFT', 'ACTIVE', 'PAUSED', 'FILLED', 'EXPIRED', 'CLOSED',),
}


class ModelBootstrapError(RuntimeError):
    """Raised when the model-bootstrap path must refuse to act."""


# --------------------------------------------------------------------------
# Data carriers
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class EnumSpec:
    """One PostgreSQL enum type declared by the application models."""

    name: str
    labels: Tuple[str, ...]
    create_type: Optional[bool]


@dataclass(frozen=True)
class MarkerRow:
    marker: str
    status: str
    fingerprint: str


@dataclass(frozen=True)
class DatabaseState:
    """Read-only classification of a database against the Design-2 states."""

    code: str
    revision: Optional[str] = None
    marker_status: Optional[str] = None
    marker_fingerprint: Optional[str] = None
    app_table_count: int = 0
    heads: Tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return self.code == STATE_EMPTY

    @property
    def is_model_bootstrap(self) -> bool:
        return self.code in (
            STATE_MODEL_BOOTSTRAP_BUILDING,
            STATE_MODEL_BOOTSTRAP_COMPLETE,
        )

    @property
    def is_migration_built(self) -> bool:
        return self.code == STATE_MIGRATION_BUILT_AT_HEAD

    def describe(self) -> str:
        """An operator-facing, actionable description of this state."""
        tables = f"{self.app_table_count} application table(s)"
        if self.code == STATE_EMPTY:
            return "database is empty and ready for model bootstrap."
        if self.code == STATE_MODEL_BOOTSTRAP_COMPLETE:
            return (
                "database was provisioned by the model-bootstrap path "
                f"(fingerprint {self.marker_fingerprint}). It is NOT an "
                "Alembic-upgraded database and must never be stamped head."
            )
        if self.code == STATE_MODEL_BOOTSTRAP_BUILDING:
            return (
                "an earlier model bootstrap did not complete (marker status "
                f"'{self.marker_status}'). The partial schema is left "
                "untouched; drop and recreate this database before retrying. "
                "This path never repairs a partial schema."
            )
        if self.code == STATE_MIGRATION_BUILT_AT_HEAD:
            return (
                "database is migration-built at Alembic head "
                f"{self.revision}; do not model-bootstrap it."
            )
        if self.code == STATE_MIGRATION_BUILT_NOT_AT_HEAD:
            return (
                "database is migration-built but not at the head "
                f"(revision(s) {self.revision or 'none'}; expected "
                f"{', '.join(self.heads) or 'unknown'}). Apply the reviewed "
                "Alembic migrations instead of model-bootstrapping."
            )
        if self.code == STATE_UNMARKED_NONEMPTY:
            return (
                f"database already has {tables} but carries neither the "
                "model-bootstrap marker nor alembic_version, so its origin "
                "and completeness cannot be established. It is left "
                "untouched; drop and recreate it deliberately if that is "
                "intended."
            )
        if self.code == STATE_CONTRADICTORY:
            return (
                "database carries both the model-bootstrap marker and "
                "alembic_version, which cannot both be true. It is left "
                "untouched; resolve manually before proceeding."
            )
        return f"unrecognised database state '{self.code}'."


@dataclass(frozen=True)
class BootstrapResult:
    """Outcome of a successful bootstrap or validation run."""

    state_code: str
    fingerprint: str
    tables: int
    group_a_types: int
    group_b_types: int
    stamped_alembic: bool = False

    @property
    def created(self) -> bool:
        return self.state_code == STATE_EMPTY


# --------------------------------------------------------------------------
# Enum inspection over model metadata
# --------------------------------------------------------------------------


def _unwrap_enum(column_type: object) -> Optional[sa.Enum]:
    """Return the ``Enum`` behind *column_type*, following ``impl`` wrappers."""
    seen = set()
    current = column_type
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, sa.Enum):
            return current
        current = getattr(current, "impl", None)
    return None


def _iter_enum_types(metadata: MetaData) -> Iterable[sa.Enum]:
    """Yield every ``Enum`` type reachable from *metadata*.

    Column types may wrap the enum (for example a TypeDecorator or the
    PostgreSQL ENUM adapter), so ``impl`` is followed rather than assuming the
    column type itself is the enum.
    """
    for table in metadata.sorted_tables:
        for column in table.columns:
            enum = _unwrap_enum(column.type)
            if enum is not None:
                yield enum


def collect_enum_specs(metadata: MetaData) -> List[EnumSpec]:
    """Return the de-duplicated enum types declared by the models."""
    ordered: Dict[str, EnumSpec] = {}
    for enum in _iter_enum_types(metadata):
        labels = tuple(str(value) for value in enum.enums)
        spec = EnumSpec(
            name=str(enum.name),
            labels=labels,
            create_type=getattr(enum, "create_type", None),
        )
        previous = ordered.get(spec.name)
        if previous is not None and previous != spec:
            raise ModelBootstrapError(
                "enum type "
                f"'{spec.name}' is declared more than once with conflicting "
                "definitions: "
                f"{previous.labels} (create_type={previous.create_type}) vs "
                f"{spec.labels} (create_type={spec.create_type}). A type may "
                "have exactly one definition and one creation owner."
            )
        ordered[spec.name] = spec
    return [ordered[name] for name in sorted(ordered)]


def partition_enum_ownership(
    specs: Sequence[EnumSpec],
) -> Tuple[Dict[str, Tuple[str, ...]], Dict[str, Tuple[str, ...]]]:
    """Split *specs* into Group A (bootstrap-owned) and Group B.

    ``create_type=False`` means SQLAlchemy will not create the type, so this
    module must.  Anything else is left to ``db.create_all()``.  A name that
    appears in both groups is rejected.
    """
    group_a: Dict[str, Tuple[str, ...]] = {}
    group_b: Dict[str, Tuple[str, ...]] = {}
    for spec in specs:
        if spec.create_type is False:
            group_a[spec.name] = spec.labels
        else:
            group_b[spec.name] = spec.labels
    overlap = sorted(set(group_a) & set(group_b))
    if overlap:
        raise ModelBootstrapError(
            "enum types claimed by two creation owners: "
            f"{', '.join(overlap)}. Each type needs exactly one owner."
        )
    return group_a, group_b


def assert_inventory_ownership(
    group_a: Mapping[str, Tuple[str, ...]],
    group_b: Mapping[str, Tuple[str, ...]],
) -> None:
    """Reject drift between the models and the reviewed 47-type inventory."""
    problems: List[str] = []

    expected_a = set(GROUP_A_EXPECTED)
    expected_b = set(GROUP_B_EXPECTED)
    actual_a = set(group_a)
    actual_b = set(group_b)

    for missing in sorted(expected_a - actual_a):
        problems.append(f"group A type '{missing}' is no longer declared by the models")
    for missing in sorted(expected_b - actual_b):
        problems.append(f"group B type '{missing}' is no longer declared by the models")
    for unexpected in sorted(actual_a - expected_a):
        problems.append(
            f"type '{unexpected}' is declared create_type=False but is not in "
            "the reviewed group A inventory"
        )
    for unexpected in sorted(actual_b - expected_b):
        problems.append(
            f"type '{unexpected}' is not in the reviewed group B inventory"
        )

    for name in sorted(actual_a & expected_a):
        if tuple(group_a[name]) != GROUP_A_EXPECTED[name]:
            problems.append(
                f"group A type '{name}' label order changed: "
                f"{tuple(group_a[name])} vs reviewed {GROUP_A_EXPECTED[name]}"
            )
    for name in sorted(actual_b & expected_b):
        if tuple(group_b[name]) != GROUP_B_EXPECTED[name]:
            problems.append(
                f"group B type '{name}' label order changed: "
                f"{tuple(group_b[name])} vs reviewed {GROUP_B_EXPECTED[name]}"
            )

    if problems:
        raise ModelBootstrapError(
            "model enum ownership has drifted from the reviewed inventory in "
            "Addendum B section B.1.3 (39 group A + 8 group B = 47). Update "
            "the inventory deliberately before bootstrapping: "
            + "; ".join(problems)
        )


def labels_identical(actual: Sequence[str], expected: Sequence[str]) -> bool:
    """Exact, order- and case-sensitive label comparison."""
    return list(actual) == list(expected)


# --------------------------------------------------------------------------
# Schema fingerprint
# --------------------------------------------------------------------------


def _type_token(column_type: object) -> str:
    enum = _unwrap_enum(column_type)
    if enum is not None:
        return f"enum:{enum.name}"
    return f"{type(column_type).__name__}:{column_type}"


def _index_signature(table, index) -> str:
    """Content-based, name-optional signature for an index."""
    column_names = ",".join(column.name for column in index.columns)
    return f"{table.name}:{index.name or ''}:{column_names}:{bool(index.unique)}"


def _constraint_signature(table, constraint) -> str:
    """Content-based signature for a constraint.

    ``Table.constraints`` and ``Table.indexes`` are sets, and most constraints
    are unnamed, so ordering them by name would leave ties whose order depends
    on object identity.  Signing by content keeps the fingerprint stable
    across processes, which repeat-invocation validation depends on.
    """
    column_names = ",".join(
        sorted(column.name for column in (getattr(constraint, "columns", ()) or ()))
    )
    elements = getattr(constraint, "elements", ()) or ()
    referred = ";".join(
        sorted(
            f"{element.column.table.name}.{element.column.name}"
            for element in elements
            if getattr(element, "column", None) is not None
        )
    )
    name = getattr(constraint, "name", "") or ""
    return (
        f"{type(constraint).__name__}:{table.name}:{name}:"
        f"{column_names}:{referred}"
    )


def compute_schema_fingerprint(metadata: MetaData) -> str:
    """Deterministic digest of the model-derived schema.

    Deliberately includes only model-owned objects (tables, columns, indexes,
    constraints, enums).  The marker table and ``alembic_version`` are excluded
    because they are not model-owned.
    """
    parts: List[str] = []
    for table in metadata.sorted_tables:
        parts.append(f"T:{table.name}")
        for column in sorted(table.columns, key=lambda c: c.name):
            parts.append(f"C:{table.name}.{column.name}:{_type_token(column.type)}")
            parts.append(f"N:{table.name}.{column.name}:{bool(column.nullable)}")
        for signature in sorted(
            _index_signature(table, index) for index in table.indexes
        ):
            parts.append(f"I:{signature}")
        for signature in sorted(
            _constraint_signature(table, constraint)
            for constraint in table.constraints
        ):
            parts.append(f"K:{signature}")
    for spec in collect_enum_specs(metadata):
        parts.append(f"E:{spec.name}:{','.join(spec.labels)}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Group A enum creation
# --------------------------------------------------------------------------


def _pg_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_enum_type_block(name: str, labels: Sequence[str]) -> str:
    """Build a schema-scoped, exact-label ``CREATE TYPE`` block.

    PostgreSQL has no ``IF NOT EXISTS`` for ``CREATE TYPE``, so the block
    creates the type only when it is absent, and refuses an existing type
    whose labels differ in membership, order or case.  It never rewrites an
    incompatible type.
    """
    if not _IDENTIFIER_RE.match(name):
        raise ModelBootstrapError(
            f"refusing to build an enum type for unsafe identifier {name!r}"
        )
    if not labels:
        raise ModelBootstrapError(f"enum type '{name}' declares no labels")
    label_list = ",".join(_pg_quote(label) for label in labels)
    expected_array = f"ARRAY[{label_list}]::text[]"
    return (
        "DO $afcon360_enum$\n"
        "BEGIN\n"
        "    IF EXISTS (\n"
        "        SELECT 1\n"
        "        FROM pg_catalog.pg_type AS t\n"
        "        JOIN pg_catalog.pg_namespace AS n\n"
        "          ON n.oid = t.typnamespace\n"
        f"        WHERE t.typname = {_pg_quote(name)}\n"
        "          AND n.nspname = current_schema()\n"
        "    ) THEN\n"
        "        IF (\n"
        "            SELECT array_agg(e.enumlabel::text ORDER BY e.enumsortorder)\n"
        "            FROM pg_catalog.pg_enum AS e\n"
        "            JOIN pg_catalog.pg_type AS t2\n"
        "              ON t2.oid = e.enumtypid\n"
        "            JOIN pg_catalog.pg_namespace AS n2\n"
        "              ON n2.oid = t2.typnamespace\n"
        f"            WHERE t2.typname = {_pg_quote(name)}\n"
        "              AND n2.nspname = current_schema()\n"
        f"        ) IS DISTINCT FROM {expected_array} THEN\n"
        "            RAISE EXCEPTION\n"
        "                'AFCON360 enum type % already exists in schema % with "
        "incompatible labels; refusing to reuse or rewrite it',\n"
        f"                {_pg_quote(name)}, current_schema();\n"
        "        END IF;\n"
        "    ELSE\n"
        f"        CREATE TYPE {name} AS ENUM ({label_list});\n"
        "    END IF;\n"
        "END\n"
        "$afcon360_enum$;"
    )


def read_persisted_enum_labels(connection) -> Dict[str, List[str]]:
    """Read enum labels from the current schema through the expression API."""
    query = (
        select(_PG_TYPE.c.typname, _PG_ENUM.c.enumlabel)
        .select_from(
            _PG_TYPE.join(
                _PG_ENUM, _PG_ENUM.c.enumtypid == _PG_TYPE.c.oid
            ).join(
                _PG_NAMESPACE, _PG_NAMESPACE.c.oid == _PG_TYPE.c.typnamespace
            )
        )
        .where(_PG_NAMESPACE.c.nspname == sa.func.current_schema())
        .order_by(_PG_TYPE.c.typname, _PG_ENUM.c.enumsortorder)
    )
    labels: Dict[str, List[str]] = {}
    for type_name, label in connection.execute(query).all():
        labels.setdefault(type_name, []).append(label)
    return labels


# --------------------------------------------------------------------------
# Read-only classification
# --------------------------------------------------------------------------


class SchemaProbe:
    """Minimal read-only view of a database used by the classifier."""

    def table_names(self) -> List[str]:  # pragma: no cover - interface
        raise NotImplementedError

    def marker_row(self) -> Optional[MarkerRow]:  # pragma: no cover - interface
        raise NotImplementedError

    def alembic_revisions(self) -> Tuple[str, ...]:  # pragma: no cover - interface
        raise NotImplementedError


class SqlAlchemySchemaProbe(SchemaProbe):
    """Schema probe backed by a SQLAlchemy connection."""

    def __init__(self, connection) -> None:
        self._connection = connection
        self._inspector = sa.inspect(connection)

    def table_names(self) -> List[str]:
        return list(self._inspector.get_table_names())

    def marker_row(self) -> Optional[MarkerRow]:
        if not self._inspector.has_table(MARKER_TABLE):
            return None
        row = self._connection.execute(select(MARKER_TABLE_OBJ)).mappings().first()
        if row is None:
            return None
        return MarkerRow(
            marker=row["marker"],
            status=row["status"],
            fingerprint=row["fingerprint"],
        )

    def alembic_revisions(self) -> Tuple[str, ...]:
        if not self._inspector.has_table("alembic_version"):
            return ()
        rows = self._connection.execute(
            select(ALEMBIC_VERSION_TABLE.c.version_num)
        ).scalars()
        return tuple(rows)


def classify_database_state(
    probe: SchemaProbe,
    heads: Sequence[str] = (),
) -> DatabaseState:
    """Classify a database without mutating it."""
    heads_tuple = tuple(heads)
    tables = set(probe.table_names())
    marker_present = MARKER_TABLE in tables
    alembic_present = "alembic_version" in tables
    app_tables = tables - {MARKER_TABLE, "alembic_version"}

    marker = probe.marker_row() if marker_present else None
    revisions = probe.alembic_revisions() if alembic_present else ()

    common = dict(app_table_count=len(app_tables), heads=heads_tuple)

    if marker_present and alembic_present:
        return DatabaseState(
            code=STATE_CONTRADICTORY,
            revision=", ".join(revisions) or None,
            marker_status=marker.status if marker else None,
            marker_fingerprint=marker.fingerprint if marker else None,
            **common,
        )

    if marker_present:
        status = marker.status if marker else None
        if status == STATUS_COMPLETE:
            code = STATE_MODEL_BOOTSTRAP_COMPLETE
        elif status == STATUS_BUILDING:
            code = STATE_MODEL_BOOTSTRAP_BUILDING
        else:
            code = STATE_CONTRADICTORY
        return DatabaseState(
            code=code,
            marker_status=status,
            marker_fingerprint=marker.fingerprint if marker else None,
            **common,
        )

    if alembic_present:
        revision = revisions[0] if len(revisions) == 1 else None
        at_head = (
            len(revisions) == 1
            and len(heads_tuple) == 1
            and revisions[0] == heads_tuple[0]
        )
        return DatabaseState(
            code=STATE_MIGRATION_BUILT_AT_HEAD if at_head
            else STATE_MIGRATION_BUILT_NOT_AT_HEAD,
            revision=", ".join(revisions) or None,
            **common,
        )

    if app_tables:
        return DatabaseState(code=STATE_UNMARKED_NONEMPTY, **common)

    return DatabaseState(code=STATE_EMPTY, **common)


def _classify_connection(connection, heads: Sequence[str]) -> DatabaseState:
    return classify_database_state(SqlAlchemySchemaProbe(connection), heads)


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def validate_model_schema_state(
    connection,
    metadata: MetaData,
    group_a: Mapping[str, Tuple[str, ...]],
    group_b: Mapping[str, Tuple[str, ...]],
) -> None:
    """Confirm the database matches the model-derived schema exactly."""
    inspector = sa.inspect(connection)
    problems: List[str] = []

    tables = set(inspector.get_table_names())
    if "alembic_version" in tables:
        problems.append(
            "alembic_version exists; a model-bootstrap database must never be "
            "stamped as an Alembic database"
        )

    expected_tables = {table.name for table in metadata.sorted_tables}
    missing_tables = sorted(expected_tables - tables)
    if missing_tables:
        problems.append(
            "missing model tables: " + ", ".join(missing_tables[:20])
            + (f" (+{len(missing_tables) - 20} more)" if len(missing_tables) > 20 else "")
        )

    persisted = read_persisted_enum_labels(connection)
    for name, labels in sorted(group_a.items()):
        actual = persisted.get(name)
        if actual is None:
            problems.append(f"group A enum type '{name}' was not created")
        elif not labels_identical(actual, labels):
            problems.append(
                f"group A enum type '{name}' has labels {actual} instead of "
                f"{list(labels)}"
            )
    for name, labels in sorted(group_b.items()):
        actual = persisted.get(name)
        if actual is None:
            problems.append(
                f"group B enum type '{name}' was not created by db.create_all()"
            )
        elif not labels_identical(actual, labels):
            problems.append(
                f"group B enum type '{name}' has labels {actual} instead of "
                f"{list(labels)}"
            )

    if problems:
        raise ModelBootstrapError(
            "model-bootstrap validation failed: " + "; ".join(problems)
        )


# --------------------------------------------------------------------------
# Bootstrap
# --------------------------------------------------------------------------


def _assert_registration_complete() -> None:
    from app.core.model_registry import registration_failures

    failures = registration_failures()
    if failures:
        detail = "; ".join(
            f"{domain}: {error}" for domain, error in sorted(failures.items())
        )
        raise ModelBootstrapError(
            "refusing to build a schema from an incomplete model set. "
            f"Registration failures: {detail}. Fix model imports before "
            "bootstrapping, because a silent failure would produce a "
            "silently incomplete schema."
        )


def _ensure_group_a_types(connection, group_a: Mapping[str, Tuple[str, ...]]) -> None:
    for name in sorted(group_a):
        connection.exec_driver_sql(
            build_enum_type_block(name, group_a[name]),
            execution_options={"no_parameters": True},
        )


def _write_marker(connection, status: str, fingerprint: str) -> None:
    _MARKER_METADATA.create_all(connection, checkfirst=True)
    existing = connection.execute(
        select(MARKER_TABLE_OBJ.c.marker)
    ).scalars().first()
    if existing is None:
        connection.execute(
            MARKER_TABLE_OBJ.insert().values(
                marker=MARKER_KEY,
                status=status,
                fingerprint=fingerprint,
            )
        )
    else:
        connection.execute(
            MARKER_TABLE_OBJ.update()
            .where(MARKER_TABLE_OBJ.c.marker == MARKER_KEY)
            .values(status=status, fingerprint=fingerprint,
                    updated_at=sa.func.now())
        )


def _prepare(metadata: MetaData):
    """Validate the model-derived schema plan before touching the database."""
    specs = collect_enum_specs(metadata)
    group_a, group_b = partition_enum_ownership(specs)
    assert_inventory_ownership(group_a, group_b)
    fingerprint = compute_schema_fingerprint(metadata)
    return group_a, group_b, fingerprint


def bootstrap_model_schema(db, heads: Sequence[str]) -> BootstrapResult:
    """Provision a PostgreSQL model-bootstrap schema, or validate an existing one.

    The database is never stamped Alembic ``head``.  Only an empty database
    is provisioned; every other state raises ``ModelBootstrapError`` with an
    actionable description.
    """
    # Registration completeness is the first gate: it needs no metadata and no
    # engine, so an incomplete model set is refused before any database access.
    _assert_registration_complete()

    metadata = db.metadata
    engine = db.engine
    group_a, group_b, fingerprint = _prepare(metadata)

    with engine.connect() as connection:
        state = _classify_connection(connection, heads)

    if state.code == STATE_MODEL_BOOTSTRAP_COMPLETE:
        if state.marker_fingerprint != fingerprint:
            raise ModelBootstrapError(
                "the existing model-bootstrap database no longer matches the "
                f"current models (marker fingerprint "
                f"{state.marker_fingerprint}, computed {fingerprint}). "
                "create_all() does not migrate an existing schema; drop and "
                "recreate this database, or upgrade it with Alembic."
            )
        validate_model_schema_state(
            engine.connect(), metadata, group_a, group_b
        )
        return BootstrapResult(
            state_code=STATE_MODEL_BOOTSTRAP_COMPLETE,
            fingerprint=fingerprint,
            tables=state.app_table_count,
            group_a_types=len(group_a),
            group_b_types=len(group_b),
        )

    if state.code != STATE_EMPTY:
        raise ModelBootstrapError(
            "refusing to model-bootstrap this database: " + state.describe()
        )

    # Step 1: record the in-progress marker in its own transaction so that a
    # later failure leaves an unambiguous 'building' state, never a
    # valid-looking success marker.
    with engine.begin() as connection:
        _write_marker(connection, STATUS_BUILDING, fingerprint)

    try:
        # Step 2: Group A types are owned by this path.
        with engine.begin() as connection:
            _ensure_group_a_types(connection, group_a)

        # Step 3: db.create_all() owns Group B types and every table.
        db.create_all()

        # Step 4: validate, then mark complete.
        with engine.begin() as connection:
            state = _classify_connection(connection, heads)
            if state.code != STATE_MODEL_BOOTSTRAP_BUILDING:
                raise ModelBootstrapError(
                    "the database changed while bootstrapping and now reads "
                    f"as '{state.code}'; refusing to mark it complete."
                )
            if state.marker_fingerprint != fingerprint:
                raise ModelBootstrapError(
                    "the recorded bootstrap fingerprint does not match the "
                    "current models; refusing to mark it complete."
                )
            validate_model_schema_state(connection, metadata, group_a, group_b)
            _write_marker(connection, STATUS_COMPLETE, fingerprint)
    except ModelBootstrapError:
        raise
    except Exception as exc:
        raise ModelBootstrapError(
            "model bootstrap did not complete. The database is left in the "
            f"'{STATUS_BUILDING}' state with the partial schema untouched; "
            "drop and recreate it before retrying. Original error: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    return BootstrapResult(
        state_code=STATE_EMPTY,
        fingerprint=fingerprint,
        tables=len(metadata.tables),
        group_a_types=len(group_a),
        group_b_types=len(group_b),
        stamped_alembic=False,
    )


def validate_model_bootstrap(db, heads: Sequence[str]) -> BootstrapResult:
    """Validate an already-provisioned model-bootstrap database (read-only)."""
    _assert_registration_complete()
    metadata = db.metadata
    group_a, group_b, fingerprint = _prepare(metadata)

    with db.engine.connect() as connection:
        state = _classify_connection(connection, heads)
        if state.code != STATE_MODEL_BOOTSTRAP_COMPLETE:
            raise ModelBootstrapError(
                "expected a completed model-bootstrap database but found: "
                + state.describe()
            )
        if state.marker_fingerprint != fingerprint:
            raise ModelBootstrapError(
                "the model-bootstrap database no longer matches the current "
                f"models (marker fingerprint {state.marker_fingerprint}, "
                f"computed {fingerprint})."
            )
        validate_model_schema_state(connection, metadata, group_a, group_b)

    return BootstrapResult(
        state_code=STATE_MODEL_BOOTSTRAP_COMPLETE,
        fingerprint=fingerprint,
        tables=state.app_table_count,
        group_a_types=len(group_a),
        group_b_types=len(group_b),
    )
