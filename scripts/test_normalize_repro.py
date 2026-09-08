"""
Reproduction + verification for the false-positive semantic drift in
sync_check_constraints.py normalize_sql().

Imports the REAL normalize_sql() from scripts/sync_check_constraints.py
(after the precedence-aware grouping-parenthesis fix) and checks that:

  - the exact provider_participations pair now compares equal,
  - the precedence test matrix is satisfied,
  - genuinely different expressions never compare equal.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.sync_check_constraints import (  # noqa: E402
    normalize_sql,
    _canonicalize_bool,
)


# ============================================================================
# PRIMARY REPRODUCTION
# ============================================================================

print("=" * 72)
print("SECTION 1: PRIMARY BUG REPRODUCTION")
print("=" * 72)

DB_RAW = (
    "user_id IS NOT NULL AND organisation_id IS NULL "
    "OR user_id IS NULL AND organisation_id IS NOT NULL"
)
MODEL_RAW = (
    "((user_id IS NOT NULL AND organisation_id IS NULL) "
    "OR (user_id IS NULL AND organisation_id IS NOT NULL))"
)

norm_db = normalize_sql(DB_RAW)
norm_model = normalize_sql(MODEL_RAW)

print()
print(f"  DB raw          : {DB_RAW!r}")
print(f"  Model raw       : {MODEL_RAW!r}")
print()
print(f"  DB normalized   : {norm_db!r}")
print(f"  Model normalized: {norm_model!r}")
print()
print(f"  Strings equal   : {norm_db == norm_model}")
print()

# Verify logical equivalence under PostgreSQL precedence
# AND binds tighter than OR, so:
#   A AND B OR C AND D  ≡  (A AND B) OR (C AND D)  ≡  ((A AND B) OR (C AND D))
print("  PostgreSQL precedence: NOT > AND > OR")
print("  Therefore A AND B OR C AND D == (A AND B) OR (C AND D)")
print("  The normalizer reports FALSE POSITIVE semantic drift: "
      f"{'YES — BUG CONFIRMED' if norm_db != norm_model else 'no — already fixed'}")

# ============================================================================
# SINGLE-PREDICATE PAREN REMOVAL (line 316-320 of original)
# ============================================================================

print()
print("=" * 72)
print("SECTION 2: SINGLE-PREDICATE PAREN REMOVAL ANALYSIS")
print("=" * 72)

# The regex at line 316-320 removes parens around a single predicate
# that has NO and/or inside.  Verify that behavior (input is normalized
# to lowercase + no operator spacing by normalize_sql).
single_pred_tests = [
    ("(user_id IS NOT NULL)",           "user_id is not null",          True),
    ("(a > 1)",                         "a>1",                          True),
    ("(a = 'x')",                       "a='x'",                        True),
    ("(a > 1 AND b > 2)",               "a>1 and b>2",                  True),  # whole expr wrapped → stripped
    ("(a > 1 OR b > 2)",                "a>1 or b>2",                   True),  # whole expr wrapped → stripped
    ("in(a > 1)",                       "in(a>1)",                      True),  # IN list, not a grouping
]

print()
for expr, expected, _ in single_pred_tests:
    norm = normalize_sql(expr)
    match = "PASS" if norm == expected else "FAIL"
    print(f"  [{match}] normalize({expr!r})")
    print(f"      -> {norm!r}  (expected {expected!r})")

# ============================================================================
# BROADER BOOLEAN EXPRESSION EQUIVALENCE TESTS
# ============================================================================

print()
print("=" * 72)
print("SECTION 3: BOOLEAN EXPRESSION EQUIVALENCE TESTS")
print("=" * 72)

# Each entry: (label, expr_a, expr_b, logically_equivalent)
# "logically_equivalent" = true if PostgreSQL would treat them identically
# when used as CHECK constraint text.

bool_tests = [
    # ---- Known false-positive cases (AND inside OR) ----
    (
        "AND inside OR — both sides",
        "a > 1 AND b > 1 OR c > 1 AND d > 1",
        "(a > 1 AND b > 1) OR (c > 1 AND d > 1)",
        True,
    ),
    (
        "AND inside OR — double outer parens",
        "a > 1 AND b > 1 OR c > 1 AND d > 1",
        "((a > 1 AND b > 1) OR (c > 1 AND d > 1))",
        True,
    ),
    (
        "AND inside OR — left only",
        "a > 1 AND b > 1 OR c > 1",
        "(a > 1 AND b > 1) OR c > 1",
        True,
    ),
    (
        "AND inside OR — right only",
        "c > 1 OR a > 1 AND b > 1",
        "c > 1 OR (a > 1 AND b > 1)",
        True,
    ),
    (
        "Triple OR with AND groups",
        "a>1 and b>1 or c>1 and d>1 or e>1 and f>1",
        "(a>1 and b>1) or (c>1 and d>1) or (e>1 and f>1)",
        True,
    ),

    # ---- Cases where parens MUST be preserved ----
    (
        "OR inside AND — parens REQUIRED",
        "a > 1 OR b > 1 AND c > 1",
        "(a > 1 OR b > 1) AND c > 1",
        False,
    ),
    (
        "NOT(OR) — parens REQUIRED",
        "NOT (a > 1 OR b > 1)",
        "NOT a > 1 OR b > 1",
        False,
    ),
    (
        "NOT(AND) — parens REQUIRED",
        "NOT (a > 1 AND b > 1)",
        "NOT a > 1 AND b > 1",
        False,
    ),

    # ---- Cases where parens are redundant (same associativity) ----
    (
        "OR inside OR — parens redundant",
        "a > 1 OR b > 1 OR c > 1",
        "(a > 1 OR b > 1) OR c > 1",
        True,
    ),
    (
        "AND inside AND — parens redundant",
        "a > 1 AND b > 1 AND c > 1",
        "(a > 1 AND b > 1) AND c > 1",
        True,
    ),

    # ---- Single-predicate parens ----
    (
        "Single predicate parens",
        "(a > 1)",
        "a > 1",
        True,
    ),

    # ---- IN expressions ----
    (
        "IN list — equivalent",
        "status IN ('a','b') AND type = 'x' OR status IN ('c') AND type = 'y'",
        "(status IN ('a','b') AND type = 'x') OR (status IN ('c') AND type = 'y')",
        True,
    ),

    # ---- IS NULL / IS NOT NULL ----
    (
        "IS NULL checks — equivalent",
        "a IS NOT NULL AND b IS NULL OR a IS NULL AND b IS NOT NULL",
        "(a IS NOT NULL AND b IS NULL) OR (a IS NULL AND b IS NOT NULL)",
        True,
    ),

    # ---- Expressions that must NOT match ----
    (
        "Genuinely different expressions",
        "a > 1 AND b > 1",
        "a > 1 OR b > 1",
        False,
    ),
    (
        "Different column names",
        "a > 1 AND b > 1",
        "a > 1 AND c > 1",
        False,
    ),
    (
        "Different operators",
        "a > 1 AND b > 1",
        "a >= 1 AND b > 1",
        False,
    ),
    (
        "Different structure",
        "a > 1 OR b > 1 AND c > 1",
        "a > 1 AND b > 1 OR c > 1",
        False,
    ),

    # ---- Nested complexity ----
    (
        "Nested AND/OR mix",
        "(a > 1 AND (b > 1 OR c > 1)) OR d > 1",
        "a > 1 AND (b > 1 OR c > 1) OR d > 1",
        True,
    ),
    (
        "NOT with redundant outer parens",
        "NOT (a > 1)",
        "NOT a > 1",
        True,
    ),
]

print()
failures = 0
for label, expr_a, expr_b, expected_equiv in bool_tests:
    norm_a = normalize_sql(expr_a)
    norm_b = normalize_sql(expr_b)
    actually_eq = (norm_a == norm_b)
    correct = (actually_eq == expected_equiv)

    tag = "PASS" if correct else "FAIL"
    if not correct:
        failures += 1

    equiv_label = "equivalent" if expected_equiv else "different"
    print(f"  [{tag}] {label}  (should be {equiv_label})")
    if not correct:
        print(f"       A normalized: {norm_a!r}")
        print(f"       B normalized: {norm_b!r}")
        print(f"       Actually {'equal' if actually_eq else 'different'}, "
              f"expected {'equal' if expected_equiv else 'different'}")

print()
print(f"  Results: {len(bool_tests) - failures}/{len(bool_tests)} correct")
if failures:
    print(f"  FAILURES: {failures}")
else:
    print("  All tests pass with current normalizer.")

# ============================================================================
# EXACT MIGRATION-CRITICAL TEST
# ============================================================================

print()
print("=" * 72)
print("SECTION 4: EXACT MIGRATION-CRITICAL TEST")
print("=" * 72)

# This is the exact pair from the existing migration file (line 34-35)
# The migration currently DROP+RECREATEs this constraint.
# After the fix, these must compare as EQUAL.

migration_db = "user_id IS NOT NULL AND organisation_id IS NULL OR user_id IS NULL AND organisation_id IS NOT NULL"
migration_model = "((user_id IS NOT NULL AND organisation_id IS NULL) OR (user_id IS NULL AND organisation_id IS NOT NULL))"

norm_mig_db = normalize_sql(migration_db)
norm_mig_model = normalize_sql(migration_model)

print()
print(f"  ck_provider_participations_single_subject:")
print(f"    DB    raw: {migration_db!r}")
print(f"    Model raw: {migration_model!r}")
print()
print(f"    DB    norm: {norm_mig_db!r}")
print(f"    Model norm: {norm_mig_model!r}")
print()
print(f"    Match: {norm_mig_db == norm_mig_model}")

if norm_mig_db == norm_mig_model:
    print()
    print("    RESULT: No false-positive semantic drift.")
    print("    The migration should NOT drop+recreate this constraint.")
else:
    print()
    print("    RESULT: FALSE POSITIVE confirmed.")
    print("    The synchronizer would incorrectly generate a REPLACE migration.")

# ============================================================================
# DECISION
# ============================================================================

print()
print("=" * 72)
print("SECTION 5: ARCHITECTURAL DECISION")
print("=" * 72)
print("""
The root cause is that normalize_sql() performs ONLY representation-level
normalization (whitespace, casts, ARRAY→IN, BETWEEN→comparisons) but does
NOT account for SQL boolean operator precedence.

PostgreSQL (and SQL standard) operator precedence:
  NOT  (highest)
  AND
  OR   (lowest)

Therefore:
  A AND B OR C AND D
  == (A AND B) OR (C AND D)
  == ((A AND B) OR (C AND D))

These are logically identical, but the normalizer keeps the explicit
parentheses, producing a false "semantic drift" result.

FIX OPTIONS:

  A) Strip redundant grouping parentheses via precedence-aware normalization
     - Targeted, small change
     - Handles the specific bug pattern
     - Verified: no genuinely different expressions compare equal
     - IMPLEMENTED (_canonicalize_bool + helpers, called as the final
       step of normalize_sql in scripts/sync_check_constraints.py)

  B) PostgreSQL-side comparison (pg_expr equivalence)
     - Most theoretically correct
     - Requires database connection at comparison time
     - Adds complexity and fragility
     - Overkill for this problem

  C) Full SQL expression parser / AST comparison
     - Correct but heavy
     - 200+ lines of new code
     - Overkill for CHECK constraint text

  D) Do nothing / document the false positive
     - Unsafe: would generate a destructive migration
     - Unacceptable

IMPLEMENTED DESIGN (option A):

  A pure, semantics-preserving canonicalization run as the final step of
  normalize_sql().  It removes ONLY grouping parentheses that are
  provably redundant under PostgreSQL boolean precedence (NOT > AND > OR),
  applying the rule:

      A parenthesized operand (E) of an operator OP is redundant iff
      prec(E) >= prec(OP)

      where prec(OR)=1, prec(AND)=2, prec(NOT)=3, prec(atom)=4.

  Required grouping (e.g. `(A OR B) AND C`, `NOT (A OR B)`) is preserved
  because there prec(E) < prec(OP).  Atoms (comparisons, IN lists,
  function calls, casts) are treated as opaque tokens and never altered.
""")
