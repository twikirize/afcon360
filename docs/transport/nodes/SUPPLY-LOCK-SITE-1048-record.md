# SUPPLY-LOCK-SITE-1048 — Record

Status:          PASS
Commit:          none (uncommitted working tree; commit is a human step)
Date:            2026-10-02
Owner:           Agent 1 (implementation) / control session (authorization + register)

Files changed:
  - app/transport/services/provider_service.py   (+17 -11)
  - tests/transport/test_org_registration_lock.py   (new)
  - docs/transport/nodes/SUPPLY-LOCK-SITE-1048-evidence.md   (new)
  - docs/transport/nodes/SUPPLY-LOCK-SITE-1048-record.md   (new, this file)

Evidence:
  See docs/transport/nodes/SUPPLY-LOCK-SITE-1048-evidence.md

Runtime verification:
  pytest tests/transport/test_org_registration_lock.py -v → 3 passed
  pytest tests/transport/test_supply00_override.py -q → 16 passed
  pytest tests/test_transport_concurrent_claim.py -q → 25 passed / 4 failed
    (pre-existing: 3 release-semantics + 1 threaded-deadlock flake, Agent 2's lane)

Residual risk:
  The org-registration path is non-functional in production until
  SUPPLY-ORG-REGISTRY-PACKAGE lands: get_organisation_identity fail-closes
  on app.organisation.services.registry_service, which does not exist, and no
  route currently wires the path. The passing tests prove the service logic
  (via a sys.modules registry fake), not the missing production wiring.

Follow-ups:
  - SUPPLY-DRIVER-CONFLICT-KWARGS (P1, OPEN): identical ConflictError kwargs
    bug in register_driver (~line 705). Separate node.
  - SUPPLY-ORG-REGISTRY-PACKAGE (P1, OPEN): build or retire the
    OrganisationRegistry dependency. Separate node.
  - SUPPLY-00-TEST-UPDATE (P1, existing, Agent 2's lane): concurrent_claim
    failures. No new filing.

Gate reference:
  SUPPLY-LOCK-SITE-1048 implementation authorization (APPROVED — EXPAND TO
  A + B + C) + control-session APPROVE of the duplicate-branch ConflictError
  kwargs correction with details={"organisation_id": ...} refinement.
  Scope interpretation recorded verbatim in evidence §6.
  Control-session final review: PASS accepted, node closes GREEN.
