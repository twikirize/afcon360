# app/kyc_config_schema.py
"""
Single source of truth for Owner/Super-Admin configurable KYC settings.

Every tunable KYC value used by the codebase (tier requirements, transaction
limits, screening flags, per-activity minimum tiers, document-requirement
toggles and reporting thresholds) is described here as a schema item. The
values are persisted in ``system_configs`` (category ``kyc``) so changes made
on the Wallet Capabilities -> KYC Requirement Toggles page are reflected
*everywhere* KYC is evaluated (``app/auth/kyc_compliance.py`` and anything
that calls ``calculate_kyc_tier``).

Adding a new configurable item is just one entry in ``KYC_CONFIG_SCHEMA``;
no route or template changes are required because the admin page and the
runtime getters are both generated from this schema.
"""

import json
import time
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Canonical DEFAULTS (mirror the BoU-compliant constants previously hard-coded
# in app/auth/kyc_compliance.py). These are used as fallbacks whenever a value
# has not been overridden in system_configs.
# ---------------------------------------------------------------------------

DEFAULT_TIER_REQUIREMENTS = {
    0: {
        "name": "Unregistered",
        "description": "Email verification only",
        "required_documents": [],
        "aml_required": False,
        "pep_screening": False,
        "sanctions_check": False,
        "ubo_screening": False,
        "daily_limit": 0,
        "monthly_limit": 0,
        "transaction_limit": 0,
    },
    1: {
        "name": "Basic",
        "description": "Phone number and full name verification",
        "required_documents": ["phone_verified"],
        "aml_required": False,
        "pep_screening": False,
        "sanctions_check": False,
        "ubo_screening": False,
        "daily_limit": 400000,
        "monthly_limit": 2000000,
        "transaction_limit": 100000,
    },
    2: {
        "name": "Standard",
        "description": "National ID and selfie verification",
        "required_documents": ["national_id", "selfie"],
        "aml_required": True,
        "pep_screening": False,
        "sanctions_check": False,
        "ubo_screening": False,
        "daily_limit": 2000000,
        "monthly_limit": 10000000,
        "transaction_limit": 500000,
    },
    3: {
        "name": "Enhanced",
        "description": "Proof of address verification; TIN is optional for individuals",
        # 'tin' is included so it can be toggled on via kyc_require_tin; it
        # defaults to OFF (individual TIN optional) which preserves behaviour.
        "required_documents": ["proof_of_address", "tin"],
        "aml_required": True,
        "pep_screening": True,
        "sanctions_check": False,
        "ubo_screening": False,
        "daily_limit": 7000000,
        "monthly_limit": 35000000,
        "transaction_limit": 2000000,
    },
    4: {
        "name": "Premium",
        "description": "Income source and bank reference",
        "required_documents": ["income_source", "bank_reference"],
        "aml_required": True,
        "pep_screening": True,
        "sanctions_check": True,
        "ubo_screening": False,
        "daily_limit": 20000000,
        "monthly_limit": 100000000,
        "transaction_limit": 5000000,
    },
    5: {
        "name": "Corporate",
        "description": "KYB and business license verification",
        "required_documents": [
            "organisation_registration",
            "tin_certificate",
            "trading_license",
            "directors_list",
            "beneficial_owners",
        ],
        "aml_required": True,
        "pep_screening": True,
        "sanctions_check": True,
        "ubo_screening": True,
        "daily_limit": None,
        "monthly_limit": None,
        "transaction_limit": None,
    },
}

DEFAULT_ACTIVITY_TIER_REQUIREMENTS = {
    "wallet_send": 1,
    "wallet_receive": 1,
    "event_registration": 1,
    "event_payment": 2,
    "accommodation_booking": 2,
    "transport_booking": 2,
    "high_value_transaction": 3,
    "ticket_purchase": 2,
    "organiser_payouts": 3,
    "kyb_operations": 5,
}

# Display order of groups on the admin page.
KYC_CONFIG_GROUPS = [
    "Document Requirements",
    "Tier Requirements",
    "Tier Limits",
    "Tier Screening",
    "Activity Tiers",
    "Verification",
    "Policy",
]

# ---------------------------------------------------------------------------
# Schema generation
# ---------------------------------------------------------------------------

_DOC_TOGGLES = [
    ("kyc_require_phone_verified", "Phone Verification",
     "Require a verified phone number to reach Tier 1 (Basic).", True),
    ("kyc_require_national_id", "National ID",
     "Require National ID (NIN) verification to reach Tier 2 (Standard).", True),
    ("kyc_require_selfie", "Selfie / Biometric",
     "Require selfie/biometric verification to reach Tier 2 (Standard).", True),
    ("kyc_require_proof_of_address", "Proof of Address",
     "Require proof of address to reach Tier 3 (Enhanced).", True),
    ("kyc_require_tin", "Individual TIN",
     "Require a TIN certificate for individuals (default OFF).", False),
    ("kyc_require_income_source", "Source of Income",
     "Require a source of income to reach Tier 4 (Premium).", True),
    ("kyc_require_bank_reference", "Bank Reference",
     "Require a bank reference to reach Tier 4 (Premium).", True),
    ("kyc_require_organisation_registration", "Organisation Registration",
     "Require organisation registration to reach Tier 5 (Corporate).", True),
    ("kyc_require_tin_certificate", "TIN Certificate",
     "Require a TIN certificate to reach Tier 5 (Corporate).", True),
    ("kyc_require_trading_license", "Trading License",
     "Require a trading license to reach Tier 5 (Corporate).", True),
    ("kyc_require_directors_list", "Directors List",
     "Require a directors list to reach Tier 5 (Corporate).", True),
    ("kyc_require_beneficial_owners", "Beneficial Owners",
     "Require beneficial owners to reach Tier 5 (Corporate).", True),
]

_SCHEMA: List[Dict[str, Any]] = []

for _key, _label, _desc, _default in _DOC_TOGGLES:
    _SCHEMA.append({
        "key": _key, "label": _label, "description": _desc,
        "type": "bool", "group": "Document Requirements", "default": _default,
    })

for _t in range(6):
    _d = DEFAULT_TIER_REQUIREMENTS[_t]
    _name = _d["name"]
    _SCHEMA.append({
        "key": f"kyc_tier_{_t}_required_documents",
        "label": f"Tier {_t} ({_name}) — Required Documents",
        "description": "Document types required to reach this tier.",
        "type": "json", "group": "Tier Requirements",
        "default": _d["required_documents"],
    })
    _SCHEMA.append({
        "key": f"kyc_tier_{_t}_daily_limit",
        "label": f"Tier {_t} ({_name}) — Daily Limit (UGX)",
        "description": "Maximum daily transaction volume for this tier.",
        "type": "int", "group": "Tier Limits", "default": _d["daily_limit"],
    })
    _SCHEMA.append({
        "key": f"kyc_tier_{_t}_monthly_limit",
        "label": f"Tier {_t} ({_name}) — Monthly Limit (UGX)",
        "description": "Maximum monthly transaction volume for this tier.",
        "type": "int", "group": "Tier Limits", "default": _d["monthly_limit"],
    })
    _SCHEMA.append({
        "key": f"kyc_tier_{_t}_transaction_limit",
        "label": f"Tier {_t} ({_name}) — Per-Transaction Limit (UGX)",
        "description": "Maximum single transaction amount for this tier.",
        "type": "int", "group": "Tier Limits", "default": _d["transaction_limit"],
    })
    _SCHEMA.append({
        "key": f"kyc_tier_{_t}_aml_required",
        "label": f"Tier {_t} ({_name}) — AML Required",
        "description": "Require AML screening for this tier.",
        "type": "bool", "group": "Tier Screening",
        "default": _d.get("aml_required", False),
    })
    _SCHEMA.append({
        "key": f"kyc_tier_{_t}_pep_screening",
        "label": f"Tier {_t} ({_name}) — PEP Screening",
        "description": "Require Politically Exposed Person screening for this tier.",
        "type": "bool", "group": "Tier Screening",
        "default": _d.get("pep_screening", False),
    })
    _SCHEMA.append({
        "key": f"kyc_tier_{_t}_sanctions_check",
        "label": f"Tier {_t} ({_name}) — Sanctions Check",
        "description": "Require sanctions list screening for this tier.",
        "type": "bool", "group": "Tier Screening",
        "default": _d.get("sanctions_check", False),
    })
    _SCHEMA.append({
        "key": f"kyc_tier_{_t}_ubo_screening",
        "label": f"Tier {_t} ({_name}) — UBO Screening",
        "description": "Require ultimate beneficial owner screening for this tier.",
        "type": "bool", "group": "Tier Screening",
        "default": _d.get("ubo_screening", False),
    })

_SCHEMA.append({
    "key": "kyc_activity_tier_requirements",
    "label": "Activity Minimum Tiers",
    "description": "Minimum KYC tier required per activity (JSON object).",
    "type": "json", "group": "Activity Tiers",
    "default": DEFAULT_ACTIVITY_TIER_REQUIREMENTS,
})

_SCHEMA.append({
    "key": "kyc_aml_review_threshold",
    "label": "AML Review Threshold (UGX)",
    "description": "Transactions at/above this amount are flagged for AML review.",
    "type": "int", "group": "Policy", "default": 5000000,
})
_SCHEMA.append({
    "key": "kyc_fia_report_threshold",
    "label": "FIA Report Threshold (UGX)",
    "description": "Transactions at/above this amount are reported to the Financial Intelligence Authority.",
    "type": "int", "group": "Policy", "default": 20000000,
})

# Verification controls
_SCHEMA.append({
    "key": "kyc_accepted_id_types",
    "label": "Accepted ID Types",
    "description": "Individual identity document types users may submit (JSON list).",
    "type": "json", "group": "Verification",
    "default": ["national_id", "passport", "driver_license", "voter_card"],
})
_SCHEMA.append({
    "key": "kyc_document_expiry_warning_days",
    "label": "Document Expiry Warning (days)",
    "description": "Flag a KYC document as expiring when this many days remain.",
    "type": "int", "group": "Verification", "default": 30,
})
_SCHEMA.append({
    "key": "kyc_nira_auto_verify",
    "label": "NIRA Auto-Verify",
    "description": "When ON, a valid-format National ID is auto-approved instead of queued for manual review.",
    "type": "bool", "group": "Verification", "default": False,
})

KYC_CONFIG_SCHEMA: List[Dict[str, Any]] = _SCHEMA


# ---------------------------------------------------------------------------
# Runtime accessors (read live values, fall back to schema defaults)
# ---------------------------------------------------------------------------

_CACHE: Dict[str, Any] = {"data": None, "ts": 0}
_CACHE_TTL = 300  # seconds


def clear_kyc_config_cache() -> None:
    _CACHE["data"] = None
    _CACHE["ts"] = 0


def _load_rows() -> Dict[str, Any]:
    try:
        from app.models.system_config import SystemConfig
        return {r.key: r for r in SystemConfig.query.filter_by(category="kyc").all()}
    except Exception:
        # No app/DB context (e.g. offline script) -> fall back to defaults.
        return {}


def get_kyc_settings() -> Dict[str, Any]:
    """Return a dict of every KYC config key -> current (typed) value."""
    now = time.time()
    if _CACHE["data"] is not None and (now - _CACHE["ts"]) < _CACHE_TTL:
        return _CACHE["data"]

    rows = _load_rows()
    out: Dict[str, Any] = {}
    for item in KYC_CONFIG_SCHEMA:
        key = item["key"]
        typ = item["type"]
        default = item["default"]
        row = rows.get(key)
        if row is None or row.value is None:
            out[key] = default
            continue
        val = row.value
        if typ == "bool":
            out[key] = str(val).lower() in ("true", "1", "yes", "on")
        elif typ == "int":
            try:
                out[key] = int(val)
            except (ValueError, TypeError):
                out[key] = default
        elif typ == "json":
            try:
                out[key] = json.loads(val)
            except (ValueError, TypeError):
                out[key] = default
        else:
            out[key] = val

    _CACHE["data"] = out
    _CACHE["ts"] = now
    return out


def is_requirement_enabled(requirement: str) -> bool:
    """Whether a KYC document requirement is currently enforced.

    A requirement is enforced unless its ``kyc_require_<requirement>`` toggle
    has been turned OFF by the Owner/Super Admin.
    """
    return get_kyc_settings().get(f"kyc_require_{requirement}", True)


def get_tier_requirements() -> Dict[int, Dict[str, Any]]:
    """Return the live per-tier requirement structure."""
    s = get_kyc_settings()
    out: Dict[int, Dict[str, Any]] = {}
    for t in range(6):
        d = dict(DEFAULT_TIER_REQUIREMENTS[t])
        d["required_documents"] = s.get(
            f"kyc_tier_{t}_required_documents", d["required_documents"])
        d["daily_limit"] = s.get(f"kyc_tier_{t}_daily_limit", d["daily_limit"])
        d["monthly_limit"] = s.get(f"kyc_tier_{t}_monthly_limit", d["monthly_limit"])
        d["transaction_limit"] = s.get(
            f"kyc_tier_{t}_transaction_limit", d["transaction_limit"])
        d["aml_required"] = s.get(
            f"kyc_tier_{t}_aml_required", d.get("aml_required", False))
        d["pep_screening"] = s.get(
            f"kyc_tier_{t}_pep_screening", d.get("pep_screening", False))
        d["sanctions_check"] = s.get(
            f"kyc_tier_{t}_sanctions_check", d.get("sanctions_check", False))
        d["ubo_screening"] = s.get(
            f"kyc_tier_{t}_ubo_screening", d.get("ubo_screening", False))
        out[t] = d
    return out


def get_activity_tier_requirements() -> Dict[str, int]:
    return get_kyc_settings().get(
        "kyc_activity_tier_requirements", DEFAULT_ACTIVITY_TIER_REQUIREMENTS)


def get_thresholds() -> Dict[str, int]:
    s = get_kyc_settings()
    return {
        "aml_review": s.get("kyc_aml_review_threshold", 5000000),
        "fia_report": s.get("kyc_fia_report_threshold", 20000000),
    }
