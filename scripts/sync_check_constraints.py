"""
AFCON360 CHECK Constraint Synchronizer

Purpose
-------
Detect CHECK-constraint drift between:

    SQLAlchemy models  -> desired state
    PostgreSQL DB      -> current state

and generate a normal Alembic migration that brings the DB toward the
model-defined desired state.

This exists because Alembic autogenerate does not reliably render
CreateCheckConstraintOp operations.

IMPORTANT
---------
The SQLAlchemy models are the source of truth.

The live database is inspected only to determine its current state.

Safe defaults:
    - missing model constraints are added
    - semantically different managed constraints are replaced
    - DB-only constraints are NOT dropped unless --prune-db is supplied
    - no migration is executed automatically

Discovery versus reconciliation (prefix policy)
-----------------------------------------------
DISCOVERY IS PREFIX-AGNOSTIC. Every PostgreSQL CHECK constraint is read
from the database and every model CheckConstraint is read from the
SQLAlchemy metadata, whatever it is called. Prefix filtering is NOT an
inventory eligibility filter: filtering the inventory is what produced
the historical false "0 orphaned constraints" result, because the
legacy ``chk_pickup_time_future`` row could never be seen.

RECONCILIATION IS PREFIX-SCOPED:

    ck_      managed     canonical prefix for application-managed
                         constraints. Eligible for ADD / REPLACE /
                         opt-in DROP (--prune-db).
    chk_     legacy      legacy transport-era naming. Discoverable and
                         REPORTED (DB-only, missing, semantic drift,
                         conflicts) but never dropped and never emitted
                         into a migration by this tool.
    other    unknown     reported as legacy-class inventory.

Destructive reconciliation stays conservative: an improved inventory
must never widen what gets pruned. ``--prune-db`` prunes managed
``ck_`` rows only; ``build_migration()`` re-checks that contract.

Examples
--------
Detect only:

    python scripts/sync_check_constraints.py --dry-run

Generate migration:

    python scripts/sync_check_constraints.py --accept-model-truth

Generate migration and explicitly prune DB-only managed constraints:

    python scripts/sync_check_constraints.py \
        --accept-model-truth \
        --prune-db

Add environment/message metadata:

    python scripts/sync_check_constraints.py \
        --environment development \
        --message "sync check constraints"

Debug:

    python scripts/sync_check_constraints.py --debug
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from typing import Dict, Tuple, List, Optional

from dataclasses import dataclass

from sqlalchemy import CheckConstraint, inspect


# ---------------------------------------------------------------------------
# Project bootstrap
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.extensions import db


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Canonical prefix for NEW / application-managed CHECK constraints.
# Used as a NAMING rule and as the reconciliation scope -- never as an
# inventory filter (see module docstring, "Discovery versus reconciliation").
MANAGED_PREFIX = "ck_"

# Recognised legacy prefixes. Constraints named this way are discovered,
# classified and reported, but are never pruned or migrated by this tool.
LEGACY_PREFIXES = ("chk_",)

ConstraintKey = Tuple[str, str]


def classify_constraint(name: str) -> str:
    """Classify a CHECK constraint name as managed / legacy / other."""

    if name.startswith(MANAGED_PREFIX):
        return "managed"

    if any(name.startswith(prefix) for prefix in LEGACY_PREFIXES):
        return "legacy"

    return "other"


def partition_checks(
    checks: Dict[ConstraintKey, str],
) -> Tuple[Dict[ConstraintKey, str], Dict[ConstraintKey, str]]:
    """Split an inventory into (managed, legacy_or_unknown)."""

    managed: Dict[ConstraintKey, str] = {}
    legacy: Dict[ConstraintKey, str] = {}

    for key, sql in checks.items():
        if classify_constraint(key[1]) == "managed":
            managed[key] = sql
        else:
            legacy[key] = sql

    return managed, legacy


def count_by_prefix(
    checks: Dict[ConstraintKey, str],
) -> Dict[str, int]:
    """Return {'ck_': n, 'chk_': n, 'other': n} for an inventory."""

    counts = {"ck_": 0, "chk_": 0, "other": 0}

    for key in checks:
        name = key[1]
        if name.startswith(MANAGED_PREFIX):
            counts["ck_"] += 1
        elif name.startswith(LEGACY_PREFIXES):
            counts["chk_"] += 1
        else:
            counts["other"] += 1

    return counts
# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Synchronize managed CHECK constraints from SQLAlchemy "
                    "models into the live PostgreSQL database."
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect and report drift without creating a migration."
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show raw SQL and normalized SQL for differences."
    )

    parser.add_argument(
        "--prune-db",
        action="store_true",
        help=(
            "Allow dropping DB-only managed CHECK constraints that are not "
            "present in the SQLAlchemy models. Legacy (chk_*) rows are "
            "never included; name them with --drop-legacy instead."
        ),
    )

    parser.add_argument(
        "--drop-legacy",
        action="append",
        default=[],
        metavar="NAME",
        help=(
            "Explicitly authorise dropping the named legacy CHECK "
            "constraint (e.g. chk_pickup_time_future). Repeatable. "
            "Legacy rows are never dropped implicitly."
        ),
    )

    parser.add_argument(
        "--accept-model-truth",
        action="store_true",
        help=(
            "Explicitly confirm that SQLAlchemy models are authoritative "
            "and that reviewed model constraints may replace DB constraints. "
            "Required when generating a migration."
        ),
    )

    parser.add_argument(
        "--environment",
        default="development",
        help="Environment label recorded in the generated migration."
    )

    parser.add_argument(
        "--message",
        default="sync managed check constraints",
        help="Migration message."
    )

    return parser.parse_args()


# ---------------------------------------------------------------------------
# SQL normalization
# ---------------------------------------------------------------------------

def normalize_sql(sql: Optional[str]) -> str:
    """
    Normalize PostgreSQL-reflected CHECK SQL for comparison.

    This function intentionally performs ONLY representation-level
    normalization.

    It must NOT remove information that could change the meaning of
    the constraint.
    """

    if not sql:
        return ""

    s = str(sql).strip().lower()

    # PostgreSQL/pg_get_constraintdef returns the whole
    # ``CHECK (<expr>)`` form, while SQLAlchemy's model sqltext is just
    # ``<expr>``. Strip the keyword and its wrapper so both sides are
    # compared as bare expressions.
    s = re.sub(r"^check\s*\(", "(", s)

    while _outer_parens_wrap(s):
        s = s[1:-1].strip()

    # PostgreSQL frequently reflects:
    #
    #   column::text = ANY (
    #       ARRAY[
    #           'pending'::character varying,
    #           'sent'::character varying
    #       ]::text[]
    #   )
    #
    # as opposed to the model:
    #
    #   column IN ('pending', 'sent')
    #
    # First normalize ARRAY/ANY to IN. PostgreSQL commonly includes the
    # array suffix in the cast (`::text[]`), so handle that form explicitly.

    any_array_cast_pattern = re.compile(
        r"=\s*any\s*\(\s*array\s*\[(?P<values>.*?)\]\s*"
        r"::\s*[a-z_][a-z0-9_ ]*\[\]\s*\)",
        re.IGNORECASE | re.DOTALL,
    )

    s = any_array_cast_pattern.sub(
        lambda match: f" IN ({match.group('values')}) ",
        s,
    )

    any_array_pattern = re.compile(
        r"""
        =
        \s*
        any
        \s*
        \(
            \s*
            array
            \s*
            \[
                (?P<values>.*?)
            \]
            \s*
            (?:
                ::
                \s*
                [a-z_][a-z0-9_ ]*
                (?:\(\s*\d+(?:\s*,\s*\d+)?\s*\))?
            )?
            \s*
        \)
        """,
        re.IGNORECASE | re.VERBOSE | re.DOTALL,
    )

    def replace_any_array(match):
        values = match.group("values")
        return f" IN ({values}) "

    s = any_array_pattern.sub(replace_any_array, s)

    # Fallback for dialects that place additional cast text between the
    # closing ARRAY bracket and the ANY parenthesis.
    s = re.sub(
        r"(?P<column>[a-z_][a-z0-9_.]*)\s*=\s*any\s*\(\s*array\s*\["
        r"(?P<values>.*?)\]\s*(?:::[^)]*)?\)",
        lambda match: (
            f"{match.group('column')} IN ({match.group('values')})"
        ),
        s,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Canonicalise interval literals BEFORE cast stripping, otherwise the
    # ``::interval`` cast disappears and the two spellings can never be
    # compared:
    #
    #   database : pickup_time > (created_at - '00:05:00'::interval)
    #   model    : pickup_time > created_at - INTERVAL '5 minutes'
    #
    # Both denote the same 300-second window, but the raw texts differ, so
    # the tool used to classify this as SEMANTIC DRIFT and propose a
    # destructive DROP+RECREATE of an unchanged constraint. Fixed-duration
    # units collapse to seconds; calendar units (mon/yr) keep a distinct
    # canonical suffix so ``1 month`` never equals ``30 days``.
    s = re.sub(
        r"'(?P<val>[^']*)'\s*::\s*interval\b",
        lambda match: _interval_token(match.group("val")),
        s,
        flags=re.IGNORECASE,
    )

    s = re.sub(
        r"\binterval\s+'(?P<val>[^']*)'",
        lambda match: _interval_token(match.group("val")),
        s,
        flags=re.IGNORECASE,
    )

    # Remove PostgreSQL type casts.
    #
    # Examples:
    #   ::text
    #   ::character varying
    #   ::numeric
    #   ::numeric(10,2)
    #
    # IMPORTANT: the type-name body must NOT include spaces in its general
    # (single-word) form.  An earlier version used [a-z0-9_ ]* which greedily
    # consumed spaces, so a cast like ``0::numeric AND deposit_percentage``
    # matched ``numeric AND deposit_percentage`` (all letters/spaces) and was
    # stripped entirely — collapsing two distinct predicates into one and
    # producing false "semantic drift" on constraints that were actually
    # identical.  Multi-word type names (``character varying``,
    # ``double precision``, ``timestamp without time zone`` ...) are handled
    # by explicit alternatives so they still match without letting the
    # single-word branch eat across SQL keywords/identifiers.

    s = re.sub(
        r"""
        ::
        \s*
        (?:
            ".*?"
            |
            character[ ]varying
            |
            double[ ]precision
            |
            (?:timestamp|time)[ ](?:without|with)[ ]time[ ]zone
            |
            [a-z_][a-z0-9_]*
        )
        (?:\([ ]*\d+(?:[ ]*,[ ]*\d+)?[ ]*\))?
        """,
        "",
        s,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    # PostgreSQL may quote identifiers.
    s = s.replace('"', "")

    # Normalize whitespace.
    s = re.sub(r"\s+", " ", s).strip()

    # Normalize whitespace around punctuation/operators.
    s = re.sub(r"\s*,\s*", ",", s)
    s = re.sub(r"\s*<>\s*", "!=", s)
    s = re.sub(r"\s*>=\s*", ">=", s)
    s = re.sub(r"\s*<=\s*", "<=", s)
    s = re.sub(r"\s*!=\s*", "!=", s)
    s = re.sub(r"(?<![<>!=])\s*=\s*(?![=])", "=", s)
    s = re.sub(r"(?<![<>=!])\s*>\s*", ">", s)
    s = re.sub(r"(?<![<>=!])\s*<\s*", "<", s)

    # SQLAlchemy commonly renders ranges as BETWEEN while PostgreSQL
    # reflection returns the equivalent pair of comparisons.
    s = re.sub(
        r"\b([a-z_][a-z0-9_.]*)\s+between\s+([^\s]+)\s+and\s+([^\s)]+)",
        r"\1>=\2 and \1<=\3",
        s,
    )

    # Normalize IN syntax.  Case-insensitive because the ANY/ARRAY
    # rewrites above emit an upper-case " IN " token, while the model's
    # sqltext (already lower-cased at the top of this function) uses
    # lower-case "in".  Without IGNORECASE the DB side keeps "IN ("
    # and the model side becomes "in(", causing false semantic drift
    # on every constraint that PostgreSQL reflects via ANY(ARRAY[...]).
    s = re.sub(r"\bin\s*\(", "in(", s, flags=re.IGNORECASE)

    # Remove harmless outer whitespace around parentheses.
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+\)", ")", s)

    # Reflection may add parentheses around a single predicate.  Do not
    # remove parentheses belonging to IN lists or compound expressions.
    s = re.sub(
        r"(?<!in)\((?![^()]*\b(?:and|or)\b)([^(),]+(?:is not null|is null|!=|>=|<=|=|~|>|<)[^(),]*)\)",
        r"\1",
        s,
    )

    # Normalize boolean operators.
    s = re.sub(r"\band\b", " and ", s)
    s = re.sub(r"\bor\b", " or ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\bnot\s*\(", "not(", s)

    # Keep PostgreSQL-reflected and model-rendered quoted value lists in the
    # same shape.  Restrict this to quoted lists so SQL functions are not
    # mistaken for membership predicates.
    s = re.sub(
        r"\b([a-z_][a-z0-9_.]*)\s*(?:in\s*)?\((?P<values>'[^']*'(?:\s*,\s*'[^']*')+)\)",
        r"\1 in(\g<values>)",
        s,
    )

    # Remove grouping parentheses that are redundant under SQL ARITHMETIC
    # operator precedence.
    #
    # PostgreSQL reflects
    #
    #   year <= (extract(year from current_date) + 1)
    #
    # while the model writes
    #
    #   year <= extract(year from current_date) + 1
    #
    # which are the same predicate. ``_canonicalize_bool`` only understands
    # AND/OR/NOT grouping, so without this step the pair was reported as
    # SEMANTIC DRIFT and a destructive DROP+RECREATE was proposed for an
    # unchanged constraint. Meaning-changing grouping (``a * (b + c)`` vs
    # ``a * b + c``, ``a - (b - c)`` vs ``a - b - c``) is preserved -- see
    # the precedence rule in ``_canonicalize_arith``.
    s = _canonicalize_arith(s)

    # Remove grouping parentheses that are redundant under SQL boolean
    # operator precedence (NOT > AND > OR).
    #
    # PostgreSQL reflects CHECK expressions with only the parentheses that
    # are semantically required, while SQLAlchemy model authors commonly
    # declare explicit grouping such as:
    #
    #   ((A AND B) OR (C AND D))
    #
    # which is logically identical to:
    #
    #   A AND B OR C AND D
    #
    # Without this step the synchronizer reports a false-positive
    # "semantic drift" and generates a destructive DROP+RECREATE for a
    # constraint whose meaning never changed.
    return _canonicalize_bool(s.strip())


# ---------------------------------------------------------------------------
# Redundant-grouping-parenthesis canonicalization
#
# Removes ONLY parentheses that are provably redundant under PostgreSQL
# boolean precedence (NOT > AND > OR).  Grouping that actually changes the
# parse tree -- such as `(A OR B) AND C` or `NOT (A OR B)` -- is preserved.
# ---------------------------------------------------------------------------

_BOOL_OR_PREC = 1
_BOOL_AND_PREC = 2
_BOOL_NOT_PREC = 3
_BOOL_ATOM_PREC = 4


def _is_ident_char(c: str) -> bool:
    return c.isalnum() or c == "_"


def _outer_parens_wrap(s: str) -> bool:
    """True when `s` is exactly one matched outer ( ... ) pair."""
    if not (s.startswith("(") and s.endswith(")")):
        return False
    depth = 0
    for i, c in enumerate(s):
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0 and i != len(s) - 1:
                return False
    return depth == 0


def _unwrap(s: str) -> str:
    """Strip matched outer parentheses from `s`."""
    t = s.strip()
    while _outer_parens_wrap(t):
        t = t[1:-1].strip()
    return t


def _matching_paren(s: str, open_idx: int) -> int:
    """Return the index of the `)` matching the `(` at ``open_idx``."""
    depth = 0
    for i in range(open_idx, len(s)):
        if s[i] == "(":
            depth += 1
        elif s[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _split_top_level(s: str, op: str) -> List[str]:
    """
    Split `s` on the boolean operator `op` ('and'/'or') occurring at
    parenthesis depth 0 and outside single-quoted string literals.
    """
    parts: List[str] = []
    depth = 0
    in_str = False
    start = 0
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if in_str:
            if c == "'":
                in_str = False
            i += 1
            continue
        if c == "'":
            in_str = True
            i += 1
            continue
        if c == "(":
            depth += 1
            i += 1
            continue
        if c == ")":
            depth -= 1
            i += 1
            continue
        if depth == 0 and s.startswith(op, i):
            before_ok = i == 0 or not _is_ident_char(s[i - 1])
            after = i + len(op)
            after_ok = after >= n or not _is_ident_char(s[after])
            if before_ok and after_ok:
                part = s[start:i].strip()
                if part:
                    parts.append(part)
                start = after
                i = after
                continue
        i += 1
    tail = s[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _top_level_prec(s: str) -> int:
    """Precedence of the top-level boolean operator of `s`."""
    t = _unwrap(s)
    if len(_split_top_level(t, "or")) > 1:
        return _BOOL_OR_PREC
    if len(_split_top_level(t, "and")) > 1:
        return _BOOL_AND_PREC
    if t.startswith("not ") or t.startswith("not("):
        return _BOOL_NOT_PREC
    return _BOOL_ATOM_PREC


def _canonicalize_operand(text: str, parent_prec: int) -> str:
    """
    Canonicalize `text` used as an operand of an operator with precedence
    ``parent_prec``.  Parentheses are kept only when required by precedence.
    """
    t = text.strip()
    if t.startswith("(") and _outer_parens_wrap(t):
        inner = t[1:-1].strip()
        if _top_level_prec(inner) >= parent_prec:
            return _canonicalize_bool(inner)
        return "(" + _canonicalize_bool(inner) + ")"
    return _canonicalize_bool(t)


def _canonicalize_bool(s: str) -> str:
    """
    Remove grouping parentheses that are redundant under SQL boolean
    operator precedence (NOT > AND > OR).

    Examples:
      ((A AND B) OR (C AND D))  ->  A AND B OR C AND D
      (A AND B) OR C            ->  A AND B OR C
      NOT (A AND B)             ->  NOT (A AND B)   (kept)
      (A OR B) AND C            ->  (A OR B) AND C  (kept)
    """
    s = s.strip()
    if not s:
        return s

    # Outer parentheses around the entire expression are always redundant.
    while _outer_parens_wrap(s):
        s = s[1:-1].strip()

    # Lowest-precedence operator first (OR, then AND).
    parts = _split_top_level(s, "or")
    if len(parts) > 1:
        return " or ".join(
            _canonicalize_operand(p, _BOOL_OR_PREC) for p in parts
        )

    parts = _split_top_level(s, "and")
    if len(parts) > 1:
        return " and ".join(
            _canonicalize_operand(p, _BOOL_AND_PREC) for p in parts
        )

    # Top-level NOT.
    if s.startswith("not "):
        operand = s[4:]
    elif s.startswith("not("):
        close = _matching_paren(s, 3)
        operand = s[4:close] if close != -1 else s[4:]
    else:
        return s

    operand = _canonicalize_bool(operand)
    if _top_level_prec(operand) < _BOOL_NOT_PREC:
        return "not (" + operand + ")"
    return "not " + operand


# ---------------------------------------------------------------------------
# Interval-literal canonicalization
# ---------------------------------------------------------------------------

_INTERVAL_UNIT_SECONDS = {
    "second": 1, "seconds": 1, "sec": 1, "secs": 1,
    "minute": 60, "minutes": 60, "min": 60, "mins": 60,
    "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600,
    "day": 86400, "days": 86400,
    "week": 604800, "weeks": 604800,
}

_INTERVAL_UNIT_SUFFIX = {
    "mon": "mon", "mons": "mon", "month": "mon", "months": "mon",
    "year": "yr", "years": "yr",
}


def _interval_seconds_text(total: float) -> str:
    if total == int(total):
        return str(int(total))
    return str(total)


def _interval_token(literal: str) -> str:
    """
    Canonicalize an interval literal body to ``interval(<seconds>)``.

    Fixed-duration spellings collapse to one token so that equivalent
    representations never look like semantic drift::

        '00:05:00'          -> interval(300)
        '5 minutes'         -> interval(300)
        '300 seconds'       -> interval(300)

    Calendar units are NOT fixed durations (a month is not 30 days), so
    they keep a distinct suffix: ``1 month`` -> ``interval(1mon)``.

    Anything unparseable keeps its literal text. Never collapse unknown
    values into a shared token: that would hide real drift, which is the
    unsafe direction for a reconciliation tool.
    """

    text = str(literal).strip().lower()

    # HH:MM:SS / MM:SS / HH:MM:SS.ffffff
    m = re.fullmatch(
        r"(?P<h>\d+):(?P<m>\d{1,2})(?::(?P<s>\d{1,2}(?:\.\d+)?))?",
        text,
    )
    if m:
        total = (
            int(m.group("h")) * 3600
            + int(m.group("m")) * 60
            + float(m.group("s") or 0)
        )
        return "interval(" + _interval_seconds_text(total) + ")"

    # ISO 8601 duration, e.g. P1DT2H, PT5M
    m = re.fullmatch(
        r"p(?P<d>\d+)d?"
        r"(?:t(?:(?P<h>\d+)h)?(?:(?P<mn>\d+)m)?(?:(?P<s>\d+(?:\.\d+)?)s)?)?"
        r"|pt(?:(?P<h2>\d+)h)?(?:(?P<mn2>\d+)m)?(?:(?P<s2>\d+(?:\.\d+)?)s)?",
        text,
    )
    if m and any(
        m.group(g) for g in ("d", "h", "mn", "s", "h2", "mn2", "s2")
    ):
        total = (
            int(m.group("d") or 0) * 86400
            + int(m.group("h") or m.group("h2") or 0) * 3600
            + int(m.group("mn") or m.group("mn2") or 0) * 60
            + float(m.group("s") or m.group("s2") or 0)
        )
        return "interval(" + _interval_seconds_text(total) + ")"

    # Plain number with a unit: '300 seconds', '5 minutes'
    m = re.fullmatch(
        r"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>[a-z]+)", text
    )
    if m:
        num = float(m.group("num"))
        unit = m.group("unit")

        if unit in _INTERVAL_UNIT_SECONDS:
            total = num * _INTERVAL_UNIT_SECONDS[unit]
            return "interval(" + _interval_seconds_text(total) + ")"

        if unit in _INTERVAL_UNIT_SUFFIX:
            if num == int(num):
                return "interval(" + str(int(num)) + _INTERVAL_UNIT_SUFFIX[unit] + ")"
            return "interval(" + _interval_seconds_text(num) + unit + ")"

        # Unknown unit: keep it distinct, never fold it into seconds.
        return "interval(" + _interval_seconds_text(num) + unit + ")"

    # Bare number: PostgreSQL reads it as seconds; keep the value distinct.
    m = re.fullmatch(r"\d+(?:\.\d+)?", text)
    if m:
        return "interval(" + _interval_seconds_text(float(text)) + ")"

    # Unknown form: preserve the literal so distinct values stay distinct.
    return "interval('" + text + "')"


# ---------------------------------------------------------------------------
# Arithmetic-paren canonicalization
# ---------------------------------------------------------------------------

# Precedence scale (low number = binds loosely):
#   1 or, 2 and, 3 comparison/concat, 4 + -, 5 * / %, 7 atom
_ARITH_OP_PREC = {
    "||": 3, "=": 3, "<>": 3, "!=": 3, "<": 3, ">": 3, "<=": 3, ">=": 3,
    "+": 4, "-": 4, "*": 5, "/": 5, "%": 5,
}

_ARITH_PREC_MIN = 4


def _skip_string_literal(s: str, i: int) -> int:
    """Return index just past the string literal starting at ``s[i] == "'"``."""

    j = i + 1
    n = len(s)
    while j < n:
        if s[j] == "'":
            if j + 1 < n and s[j + 1] == "'":
                j += 2
                continue
            return j + 1
        j += 1
    return n


def _matching_paren_str(s: str, i: int) -> int:
    """Index of the ``)`` matching ``s[i] == "("``, or -1.

    Unlike the boolean-canonicalization ``_matching_paren`` this variant
    skips single-quoted string literals, so a ``)`` or ``(`` inside a
    literal (e.g. ``'a)b'::text``) never confuses paren matching.
    """

    depth = 0
    n = len(s)
    j = i
    while j < n:
        c = s[j]
        if c == "'":
            j = _skip_string_literal(s, j)
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return -1


def _arith_top_op(s: str) -> int:
    """
    Weakest-binding depth-0 operator precedence of ``s``.

    Returns 7 (atom) when no operator is present, or -1 when the content
    contains a boolean keyword or a comma -- those belong to other
    canonicalizers (IN lists, boolean grouping) and must not be touched
    here.
    """

    depth = 0
    i = 0
    n = len(s)
    weakest = 7

    while i < n:
        c = s[i]

        if c == "'":
            i = _skip_string_literal(s, i)
            continue

        if c == "(":
            depth += 1
            i += 1
            continue

        if c == ")":
            depth -= 1
            i += 1
            continue

        if depth == 0:
            if c == ",":
                return -1

            two = s[i:i + 2]
            if two in ("||", "<>", "!=", "<=", ">="):
                if c in "!=" or two[0] in "=<>|":
                    weakest = min(weakest, _ARITH_OP_PREC[two])
                    i += 2
                    continue

            if c in "=<>+-*/%":
                weakest = min(weakest, _ARITH_OP_PREC[c])
                i += 1
                continue

            if c.isalpha() or c == "_":
                m = re.match(r"(and|or|not)\b", s[i:])
                if m:
                    return -1
                m = re.match(r"[a-z_][a-z0-9_]*", s[i:])
                i += m.end() if m else 1
                continue

        i += 1

    return weakest


def _prev_op(s: str, i: int) -> Optional[str]:
    """Operator immediately before ``s[i] == "("`` (spaces skipped), if any."""

    k = i - 1
    while k >= 0 and s[k] == " ":
        k -= 1

    if k < 0:
        return None

    if s[k].isalnum() or s[k] == "_":
        # Identifier or keyword (`and (`, `in (`, `extract(`): not an
        # operator, and grouping-guard rules already exclude keywords.
        return None

    two = s[k - 1:k + 1] if k >= 1 else ""
    if two in ("||", "<>", "!=", "<=", ">="):
        return two

    if s[k] in "=<>+-*/%":
        return s[k]

    return None


def _next_op(s: str, i: int) -> Optional[str]:
    """Operator immediately after ``s[i] == ")"`` (spaces skipped), if any."""

    k = i + 1
    while k < len(s) and s[k] == " ":
        k += 1

    if k >= len(s):
        return None

    two = s[k:k + 2]
    if two in ("||", "<>", "!=", "<=", ">="):
        return two

    if s[k] in "=<>+-*/%":
        return s[k]

    return None


def _arith_paren_redundant(s: str, open_i: int, close_i: int) -> bool:
    """
    Decide whether the grouping parentheses at ``open_i..close_i`` are
    redundant under SQL arithmetic precedence.

    Right-operand rule (``x OP (content)``): removable when
    ``prec(content) > prec(OP)`` -- same-precedence stays grouped, so
    ``a - (b - c)`` is preserved.

    Left-operand rule (``(content) OP x``): removable when
    ``prec(content) >= prec(OP)`` -- left associativity makes
    ``(a - b) - c`` identical to ``a - b - c``.
    """

    inner = s[open_i + 1:close_i].strip()

    if not inner:
        return False

    child_prec = _arith_top_op(inner)

    # Boolean / comma content belongs to other passes.
    if child_prec < _ARITH_PREC_MIN:
        return False

    left_op = _prev_op(s, open_i)
    if left_op is not None:
        return child_prec > _ARITH_OP_PREC[left_op]

    right_op = _next_op(s, close_i)
    if right_op is not None:
        return child_prec >= _ARITH_OP_PREC[right_op]

    # Standalone arithmetic expression: grouping carries no information.
    return True


def _canonicalize_arith(s: str) -> str:
    """Remove redundant arithmetic grouping parentheses (fixpoint pass)."""

    s = s.strip()
    if not s:
        return s

    for _ in range(64):
        changed = False
        i = 0
        n = len(s)

        while i < n:
            c = s[i]

            if c == "'":
                i = _skip_string_literal(s, i)
                continue

            if c != "(":
                i += 1
                continue

            # Function-call / keyword parens (`extract(`, `interval(`,
            # `in (`, `not(`) are not grouping parens.
            if i > 0 and (
                s[i - 1].isalnum() or s[i - 1] in "_"
            ):
                i += 1
                continue

            close_i = _matching_paren_str(s, i)
            if close_i == -1:
                i += 1
                continue

            if not _arith_paren_redundant(s, i, close_i):
                # Enter the group: a non-redundant OUTER paren can still
                # contain redundant INNER parens (e.g. the outer boolean
                # group wrapping ``((year) <= (extract(..) + 1))``).
                # Skipping past it would hide exactly the drift this
                # pass exists to remove.
                i += 1
                continue

            s = s[:i] + s[i + 1:close_i] + s[close_i + 1:]
            changed = True
            break

        if not changed:
            break

    return s


# ---------------------------------------------------------------------------
# Model inspection
# ---------------------------------------------------------------------------

def get_model_checks() -> Dict[ConstraintKey, str]:
    """
    Return EVERY CheckConstraint declared by SQLAlchemy models.

    The model is the desired state.

    Discovery is prefix-agnostic on purpose: legacy ``chk_*`` model
    declarations must be visible so their drift is reported instead of
    being invisible in both directions.
    """

    result: Dict[ConstraintKey, str] = {}

    for table in db.metadata.tables.values():

        for constraint in table.constraints:

            if not isinstance(constraint, CheckConstraint):
                continue

            name = getattr(constraint, "name", None)
            if not name:
                continue

            result[(table.name, str(name))] = str(
                constraint.sqltext
            )

    return result


# ---------------------------------------------------------------------------
# Database inspection
# ---------------------------------------------------------------------------

def get_db_checks(engine) -> Dict[ConstraintKey, str]:
    """
    Return EVERY CHECK constraint currently present in PostgreSQL.

    Discovery is prefix-agnostic on purpose: ``chk_*`` (and any other
    name) must be inventoried, otherwise DB-only legacy rows such as
    ``transport_bookings.chk_pickup_time_future`` are reported as
    "0 orphaned constraints".
    """

    inspector = inspect(engine)

    result: Dict[ConstraintKey, str] = {}

    for table_name in inspector.get_table_names():

        for constraint in inspector.get_check_constraints(table_name):

            name = constraint.get("name")

            if not name:
                continue

            result[(table_name, name)] = constraint.get("sqltext", "")

    return result


# ---------------------------------------------------------------------------
# Drift classification
# ---------------------------------------------------------------------------

# SQL keywords that are never column names.
_SQL_KEYWORDS = frozenset(
    """
    and or not null is in any array between like ilike similar
    true false current_date current_timestamp now extract cast
    interval case when then else end exists all some
    """.split()
)


def _constraint_columns(sql: str) -> frozenset:
    """
    Best-effort column identifier set for a CHECK expression.

    Only used for conflict *reporting*, never for migration decisions.
    """

    s = normalize_sql(sql)

    columns = set()

    for token in re.findall(r"[a-z_][a-z0-9_]*", s):

        if token in _SQL_KEYWORDS:
            continue

        # Function name followed by '(' is not a column reference.
        if re.search(re.escape(token) + r"\s*\(", s):
            continue

        columns.add(token)

    return frozenset(columns)


@dataclass(frozen=True)
class DiffResult:
    """Prefix-aware comparison of model state versus database state."""

    # Managed (ck_*) reconciliation sets -- the ONLY sets eligible to
    # become migration operations.
    to_add: List[Tuple[ConstraintKey, str]]
    to_drop_managed: List[Tuple[ConstraintKey, str]]
    to_replace: List[Tuple[ConstraintKey, str, str]]

    # Legacy / unknown inventory -- reported, never reconciled.
    to_drop_legacy: List[Tuple[ConstraintKey, str]]
    to_replace_legacy: List[Tuple[ConstraintKey, str, str]]

    # Representation-only differences (equivalent semantics).
    representation_matches: List[Tuple[ConstraintKey, str, str]]

    # Legacy constraints whose columns overlap a managed model
    # constraint on the same table -- human-review required.
    conflicts: List[Tuple[ConstraintKey, str, List[ConstraintKey]]]

    @property
    def has_managed_drift(self) -> bool:
        return bool(self.to_add or self.to_replace)

    @property
    def has_any_drift(self) -> bool:
        return bool(
            self.to_add
            or self.to_replace
            or self.to_replace_legacy
        )


def diff(
    model_checks: Dict[ConstraintKey, str],
    db_checks: Dict[ConstraintKey, str],
) -> DiffResult:
    """
    Compare desired model state with current DB state.

    Discovery is prefix-agnostic; reconciliation is prefix-scoped.
    Managed ``ck_`` constraints drive ADD / REPLACE / prune. Legacy
    ``chk_`` (and any other) constraints are inventoried and reported,
    but a legacy row is never emitted into a migration unless the human
    explicitly names it on the command line (``--drop-legacy``).
    """

    model_managed, model_legacy = partition_checks(model_checks)
    db_managed, db_legacy = partition_checks(db_checks)

    to_add: List[Tuple[ConstraintKey, str]] = []
    to_replace: List[Tuple[ConstraintKey, str, str]] = []
    representation_matches: List[Tuple[ConstraintKey, str, str]] = []

    for key, model_sql in model_managed.items():

        if key not in db_managed:
            to_add.append((key, model_sql))
            continue

        db_sql = db_managed[key]

        if normalize_sql(db_sql) == normalize_sql(model_sql):
            if db_sql.strip() != model_sql.strip():
                representation_matches.append(
                    (key, db_sql, model_sql)
                )
        else:
            to_replace.append((key, db_sql, model_sql))

    to_drop_managed = [
        (key, db_sql)
        for key, db_sql in db_managed.items()
        if key not in model_managed
    ]

    to_replace_legacy: List[Tuple[ConstraintKey, str, str]] = []

    for key, model_sql in model_legacy.items():

        if key not in db_legacy:
            continue

        db_sql = db_legacy[key]

        if normalize_sql(db_sql) != normalize_sql(model_sql):
            to_replace_legacy.append((key, db_sql, model_sql))

    to_drop_legacy = [
        (key, db_sql)
        for key, db_sql in db_legacy.items()
        if key not in model_legacy
    ]

    # Legacy rows whose columns overlap a MANAGED model constraint on
    # the same table are almost always leftovers from a managed
    # replacement (e.g. chk_pickup_time_future superseded by
    # ck_pickup_time_sane). They are reported as conflicts; dropping
    # them stays an explicitly authorised, separately gated decision.
    conflicts: List[Tuple[ConstraintKey, str, List[ConstraintKey]]] = []

    managed_columns_by_table: Dict[str, Dict[ConstraintKey, frozenset]] = {}

    for key, model_sql in model_managed.items():
        table = key[0]
        managed_columns_by_table.setdefault(table, {})[key] = (
            _constraint_columns(model_sql)
        )

    for key, db_sql in to_drop_legacy:

        table = key[0]
        db_columns = _constraint_columns(db_sql)

        overlapping = [
            managed_key
            for managed_key, columns in
            managed_columns_by_table.get(table, {}).items()
            if db_columns and db_columns & columns
        ]

        if overlapping:
            conflicts.append((key, db_sql, overlapping))

    return DiffResult(
        to_add=to_add,
        to_drop_managed=to_drop_managed,
        to_replace=to_replace,
        to_drop_legacy=to_drop_legacy,
        to_replace_legacy=to_replace_legacy,
        representation_matches=representation_matches,
        conflicts=conflicts,
    )


# ---------------------------------------------------------------------------
# Alembic head
# ---------------------------------------------------------------------------

def get_current_head() -> str:
    """
    Resolve the current Alembic migration head from migrations/.
    """

    from alembic.script import ScriptDirectory

    migrations_dir = PROJECT_ROOT / "migrations"

    script = ScriptDirectory(str(migrations_dir))

    heads = script.get_heads()

    if not heads:
        raise RuntimeError(
            "No Alembic migration head found."
        )

    if len(heads) > 1:
        raise RuntimeError(
            "Multiple Alembic heads detected: "
            + ", ".join(heads)
            + ". Resolve the migration branches before syncing "
              "CHECK constraints."
        )

    return heads[0]


# ---------------------------------------------------------------------------
# Migration generation
# ---------------------------------------------------------------------------

def build_migration(
    to_add,
    to_drop,
    to_replace,
    down_revision: str,
    environment: str,
    message: str,
):
    """
    Build an executable Alembic migration.

    Contract guard: ADD and REPLACE may only ever contain managed
    (``ck_``) constraints. DROP is supplied by the caller as an already
    authorised list (``--prune-db`` for managed rows, plus explicitly
    named ``--drop-legacy`` rows); this function still refuses any drop
    it was not handed as an explicit tuple, and refuses a legacy name in
    ADD/REPLACE outright.
    """

    for (table, name), _sql in to_add:
        if classify_constraint(name) != "managed":
            raise ValueError(
                "Refusing to ADD non-managed CHECK constraint "
                f"{table}.{name!r}. New constraints must use the "
                f"{MANAGED_PREFIX!r} prefix."
            )

    for (table, name), _old, _new in to_replace:
        if classify_constraint(name) != "managed":
            raise ValueError(
                "Refusing to REPLACE non-managed CHECK constraint "
                f"{table}.{name!r}. Legacy constraints are reported, "
                "not reconciled."
            )

    upgrade_lines: List[str] = []
    downgrade_operations: List[List[str]] = []

    # ---------------------------------------------------------------
    # ADD
    # ---------------------------------------------------------------

    for (table, name), sql in to_add:

        upgrade_lines.append(
            f"    op.create_check_constraint("
            f"{name!r}, {table!r}, {sql!r}"
            f")"
        )

        downgrade_operations.append([
            f"    op.drop_constraint({name!r}, {table!r}, type_='check')"
        ])

    # ---------------------------------------------------------------
    # DROP
    # ---------------------------------------------------------------

    for (table, name), sql in to_drop:

        upgrade_lines.append(
            f"    op.drop_constraint("
            f"{name!r}, {table!r}, type_='check'"
            f")"
        )

        downgrade_operations.append([
            f"    op.create_check_constraint({name!r}, {table!r}, {sql!r})"
        ])

    # ---------------------------------------------------------------
    # REPLACE
    # ---------------------------------------------------------------

    for (table, name), old_sql, new_sql in to_replace:

        upgrade_lines.append(
            f"    op.drop_constraint("
            f"{name!r}, {table!r}, type_='check'"
            f")"
        )

        upgrade_lines.append(
            f"    op.create_check_constraint("
            f"{name!r}, {table!r}, {new_sql!r}"
            f")"
        )

        downgrade_operations.append([
            f"    op.drop_constraint({name!r}, {table!r}, type_='check')",
            f"    op.create_check_constraint({name!r}, {table!r}, {old_sql!r})",
        ])

    # Downgrade must undo changes in reverse order, preserving each
    # replacement's drop-then-create ordering.
    downgrade_lines = [
        line
        for operation in reversed(downgrade_operations)
        for line in operation
    ]

    if not upgrade_lines:
        return None

    revision_id = str(int(time.time()))

    timestamp = time.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    upgrade_body = "\n".join(upgrade_lines)

    downgrade_body = "\n".join(downgrade_lines)

    return f'''"""
{message}

Generated by:
scripts/sync_check_constraints.py

Environment: {environment}

Revision ID: {revision_id}
Revises: {down_revision}
Create Date: {timestamp}

Source of truth:
    SQLAlchemy model metadata

Target:
    Live PostgreSQL database
"""

from alembic import op


revision = {revision_id!r}
down_revision = {down_revision!r}
branch_labels = None
depends_on = None


def upgrade():
{upgrade_body}


def downgrade():
{downgrade_body}
'''


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_report(
    result: "DiffResult",
    model_checks: Dict[ConstraintKey, str],
    db_checks: Dict[ConstraintKey, str],
):
    print()
    print("=" * 72)
    print("AFCON360 CHECK CONSTRAINT DRIFT REPORT")
    print("=" * 72)

    model_counts = count_by_prefix(model_checks)
    db_counts = count_by_prefix(db_checks)

    print()
    print(
        "Inventory (discovery is prefix-agnostic):"
    )
    print(
        f"  model  ck_={model_counts['ck_']}  "
        f"chk_={model_counts['chk_']}  "
        f"other={model_counts['other']}  "
        f"total={len(model_checks)}"
    )
    print(
        f"  db     ck_={db_counts['ck_']}  "
        f"chk_={db_counts['chk_']}  "
        f"other={db_counts['other']}  "
        f"total={len(db_checks)}"
    )

    print()
    print(
        "MANAGED (ck_) reconciliation:"
    )
    print(
        f"  Missing in DB / ADD       : {len(result.to_add)}"
    )
    print(
        f"  Semantic drift / REPLACE  : {len(result.to_replace)}"
    )
    print(
        f"  DB-only / prune candidate : {len(result.to_drop_managed)}"
    )
    print(
        f"  Representation-only       : "
        f"{len(result.representation_matches)}"
    )

    print()
    print(
        "LEGACY (chk_ and other) inventory -- reported only:"
    )
    print(
        f"  DB-only / orphaned        : {len(result.to_drop_legacy)}"
    )
    print(
        f"  Semantic drift            : {len(result.to_replace_legacy)}"
    )
    print(
        f"  Conflicts with managed    : {len(result.conflicts)}"
    )

    if result.to_add:
        print()
        print("--- ADD (managed) ---")

        for key, _ in result.to_add:
            print(f"  + {key}")

    if result.to_replace:
        print()
        print("--- SEMANTIC DRIFT (managed) ---")

        for key, _, _ in result.to_replace:
            print(f"  ~ {key}")

    if result.to_drop_managed:
        print()
        print("--- DB-ONLY MANAGED / PRUNE CANDIDATES ---")

        for key, _ in result.to_drop_managed:
            print(f"  - {key}")

    if result.to_drop_legacy:
        print()
        print("--- DB-ONLY LEGACY (never pruned implicitly) ---")

        for key, _ in result.to_drop_legacy:
            print(f"  - {key}")

    if result.to_replace_legacy:
        print()
        print("--- LEGACY SEMANTIC DRIFT ---")

        for key, _, _ in result.to_replace_legacy:
            print(f"  ~ {key}")

    if result.conflicts:
        print()
        print("--- CONFLICTS (legacy row vs managed model) ---")

        for key, _sql, overlapping in result.conflicts:
            print(f"  ! {key}")
            print(f"      overlaps: {overlapping}")
            print(
                "      drop requires explicit --drop-legacy "
                f"{key[1]}"
            )

    if result.representation_matches:
        print()
        print("--- REPRESENTATION DIFFERENCES ONLY ---")

        for key, _, _ in result.representation_matches:
            print(f"  = {key}")

    print()
    print("=" * 72)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():

    args = parse_args()

    print()
    print("AFCON360 CHECK CONSTRAINT SYNCHRONIZER")
    print("-" * 72)
    print(f"Project root : {PROJECT_ROOT}")
    print(f"Environment  : {args.environment}")
    print(f"Source       : SQLAlchemy models")
    print(f"Target       : Live PostgreSQL database")
    print()

    app = create_app()

    with app.app_context():

        engine = db.engine

        model_checks = get_model_checks()
        db_checks = get_db_checks(engine)

        result = diff(
            model_checks,
            db_checks,
        )

        print_report(
            result,
            model_checks,
            db_checks,
        )

        # -----------------------------------------------------------
        # Debug
        # -----------------------------------------------------------

        if args.debug:

            if result.to_replace:

                print()
                print("--- SEMANTIC DRIFT DETAILS ---")

                for key, db_sql, model_sql in result.to_replace:

                    print()
                    print(key)

                    print(
                        f"  DB raw         : {db_sql!r}"
                    )

                    print(
                        f"  Model raw      : {model_sql!r}"
                    )

                    print(
                        f"  DB normalized  : "
                        f"{normalize_sql(db_sql)!r}"
                    )

                    print(
                        f"  Model normalized: "
                        f"{normalize_sql(model_sql)!r}"
                    )

            if result.representation_matches:

                print()
                print("--- REPRESENTATION-ONLY DETAILS ---")

                for key, db_sql, model_sql in result.representation_matches:

                    print()
                    print(key)

                    print(
                        f"  DB raw         : {db_sql!r}"
                    )

                    print(
                        f"  Model raw      : {model_sql!r}"
                    )

                    print(
                        f"  DB normalized  : "
                        f"{normalize_sql(db_sql)!r}"
                    )

                    print(
                        f"  Model normalized: "
                        f"{normalize_sql(model_sql)!r}"
                    )

            if result.to_replace_legacy:

                print()
                print("--- LEGACY DRIFT DETAILS ---")

                for key, db_sql, model_sql in result.to_replace_legacy:

                    print()
                    print(key)

                    print(
                        f"  DB raw         : {db_sql!r}"
                    )

                    print(
                        f"  Model raw      : {model_sql!r}"
                    )

                    print(
                        f"  DB normalized  : "
                        f"{normalize_sql(db_sql)!r}"
                    )

                    print(
                        f"  Model normalized: "
                        f"{normalize_sql(model_sql)!r}"
                    )

        # -----------------------------------------------------------
        # Drop authorisation (legacy rows need explicit naming)
        # -----------------------------------------------------------

        # Managed drops are opt-in via --prune-db. Legacy drops require
        # BOTH --prune-db and an explicit --drop-legacy <name>, so a
        # legacy row can never disappear as a side effect of a routine
        # sync.
        requested_legacy = set(args.drop_legacy or [])

        known_legacy_names = {
            key[1] for key, _ in result.to_drop_legacy
        }

        unknown_legacy = requested_legacy - known_legacy_names

        if unknown_legacy:
            print()
            print(
                "SAFE STOP: --drop-legacy named constraints that are "
                "not DB-only legacy rows:"
            )
            for name in sorted(unknown_legacy):
                print(f"    {name}")
            return

        migration_drops = []

        if args.prune_db:
            migration_drops.extend(result.to_drop_managed)

            migration_drops.extend(
                item
                for item in result.to_drop_legacy
                if item[0][1] in requested_legacy
            )

        if result.to_drop_managed and not args.prune_db:

            print()
            print(
                f"WARNING: {len(result.to_drop_managed)} DB-only managed "
                "constraints will remain untouched."
            )

        pending_legacy = [
            item
            for item in result.to_drop_legacy
            if item[0][1] not in requested_legacy
        ]

        if pending_legacy:

            print()
            print(
                f"WARNING: {len(pending_legacy)} DB-only legacy "
                "constraints will remain untouched."
            )

            for (table, name), _ in pending_legacy:
                print(f"    {table}.{name}")

            print()
            print(
                "Drop one explicitly with:"
            )
            print()
            print(
                f"    --prune-db --drop-legacy {pending_legacy[0][0][1]}"
            )

        if result.to_replace_legacy:

            print()
            print(
                f"WARNING: {len(result.to_replace_legacy)} legacy "
                "constraints drift from their model declaration. "
                "They are reported, never auto-replaced."
            )

        # -----------------------------------------------------------
        # Nothing to change
        # -----------------------------------------------------------

        if not result.to_add and not result.to_replace:

            if not migration_drops:

                print()
                print(
                    "No CHECK constraint migration required."
                )

                return

            print()
            print(
                "No model-to-DB drift; only explicitly authorised "
                "drops remain."
            )

        # -----------------------------------------------------------
        # Dry run
        # -----------------------------------------------------------

        if args.dry_run:

            print()
            print(
                "DRY RUN: no migration file created."
            )

            return

        if not args.accept_model_truth:
            print()
            print(
                "SAFE STOP: migration generation is disabled unless you "
                "explicitly accept the SQLAlchemy models as the source of truth."
            )
            print()
            print(
                "Review the drift and database values first, then rerun with:"
            )
            print()
            print(
                "    python scripts/sync_check_constraints.py "
                "--accept-model-truth"
            )
            print()
            print(
                "This script never applies migrations; run flask db upgrade "
                "only after reviewing the generated file."
            )
            return

        # -----------------------------------------------------------
        # Resolve Alembic head
        # -----------------------------------------------------------

        down_revision = get_current_head()

        print()
        print(
            f"Alembic parent revision: {down_revision}"
        )

        # -----------------------------------------------------------
        # Build migration
        # -----------------------------------------------------------

        content = build_migration(
            to_add=result.to_add,
            to_drop=migration_drops,
            to_replace=result.to_replace,
            down_revision=down_revision,
            environment=args.environment,
            message=args.message,
        )

        if not content:
            print()
            print(
                "Nothing to migrate."
            )
            return

        # -----------------------------------------------------------
        # Write migration
        # -----------------------------------------------------------

        out_dir = (
            PROJECT_ROOT
            / "migrations"
            / "versions"
        )

        out_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        revision_id = str(int(time.time()))

        out_path = (
            out_dir
            / f"{revision_id}_sync_check_constraints.py"
        )

        out_path.write_text(
            content,
            encoding="utf-8",
        )

        print()
        print("=" * 72)
        print("MIGRATION CREATED")
        print("=" * 72)
        print()
        print(out_path)
        print()
        print(
            "Review the migration before upgrading."
        )
        print()
        print(
            "Then run:"
        )
        print()
        print(
            "    flask db upgrade"
        )
        print()
        print("=" * 72)


if __name__ == "__main__":
    main()