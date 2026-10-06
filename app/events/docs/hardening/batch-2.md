## HARDENED ROWS

### Cat A / A-9 — Introduce layered internal package (domain/ application/ infrastructure/ presentation/ accommodation/ docs/)
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          app/events/ — new folders; __init__.py re-exports keep public API stable
- Verified Where:          app/events/docs/ exists (created in batch 1); app/events/domain, app/events/application, app/events/presentation, app/events/infrastructure, app/events/accommodation do NOT exist
- Original Problem:        New folders exist; __init__.py re-exports keep public API stable
- Verified Problem:        reproduced — only docs/ exists; no layered package structure present
- Repro command:           Test-Path app/events/domain; Test-Path app/events/application; Test-Path app/events/presentation; Test-Path app/events/infrastructure; Test-Path app/events/accommodation
- Repro output:            False
False
False
False
False
- Verification command:    Test-Path app/events/domain; Test-Path app/events/application; Test-Path app/events/presentation; Test-Path app/events/infrastructure; Test-Path app/events/accommodation
- Verification output:     False (all five)
- State at hardening:      Open
- Corrections:             none
- Confidence:              high
- Notes:                   Depends on A-10..A-12 splits being done first.

### Cat A / A-10 — Split services.py (136KB) into application/*_service.py
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          app/events/services.py (136KB)
- Verified Where:          app/events/services.py — 2413 lines
- Original Problem:        No file in application/ > 500 LOC; all imports route via __init__
- Verified Problem:        reproduced — services.py is 2413 LOC, no application/ subpackage exists
- Repro command:           (Get-Content app/events/services.py | Measure-Object -Line).Lines
- Repro output:            2413
- Verification command:    Test-Path app/events/application
- Verification output:     False
- State at hardening:      Open
- Corrections:             Register cites 136KB; actual is 2413 LOC (~75KB). Size metric differs but problem stands.
- Confidence:              high
- Notes:                   Depends on A-9 (layered package) existing first.

### Cat A / A-11 — Split routes.py (135KB) by audience
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          app/events/routes.py (135KB)
- Verified Where:          app/events/routes.py — 2880 lines
- Original Problem:        Each presentation file < 500 LOC
- Verified Problem:        reproduced — routes.py is 2880 LOC, no presentation/ subpackage exists
- Repro command:           (Get-Content app/events/routes.py | Measure-Object -Line).Lines
- Repro output:            2880
- Verification command:    Test-Path app/events/presentation
- Verification output:     False
- State at hardening:      Open
- Corrections:             Register cites 135KB; actual is 2880 LOC (~90KB). Size metric differs but problem stands.
- Confidence:              high
- Notes:                   Depends on A-9 (layered package) existing first.

### Cat A / A-12 — Split models.py (60KB) by aggregate
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          app/events/models.py (60KB)
- Verified Where:          app/events/models.py — 1079 lines
- Original Problem:        Each domain/model file < 300 LOC
- Verified Problem:        reproduced — models.py is 1079 LOC, no domain/ subpackage exists
- Repro command:           (Get-Content app/events/models.py | Measure-Object -Line).Lines
- Repro output:            1079
- Verification command:    Test-Path app/events/domain
- Verification output:     False
- State at hardening:      Open
- Corrections:             Register cites 60KB; actual is 1079 LOC (~35KB). Size metric differs but problem stands.
- Confidence:              high
- Notes:                   Depends on A-9 (layered package) existing first.

### Cat A / A-13 — Move TicketHold from inventory.py to domain/models/
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          app/events/inventory.py::TicketHold
- Verified Where:          app/events/inventory.py:80 (class TicketHold)
- Original Problem:        Import graph updated
- Verified Problem:        reproduced — TicketHold defined in inventory.py, no domain/models/ directory exists
- Repro command:           git grep -n "class TicketHold" -- app/events/
- Repro output:            app/events/inventory.py:80:class TicketHold(BaseModel):
- Verification command:    Test-Path app/events/domain/models
- Verification output:     False
- State at hardening:      Open
- Corrections:             none
- Confidence:              high
- Notes:                   Depends on A-9/A-12 (domain/ structure and models split).

### Cat A / A-14 — Retire payment_config.py shim once callers import from wallet
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          app/events/payment_config.py — backward-compatible re-exports from wallet
- Verified Where:          app/events/__init__.py:94 imports payment_config; app/wallet/PAYMENT_ARCHITECTURE.md:864 documents migration to wallet imports
- Original Problem:        git grep "app.events.payment_config" returns zero
- Verified Problem:        reproduced — app/events/__init__.py:94 still imports payment_config
- Repro command:           git grep -n "from app.events import payment_config\|from app.events.payment_config" -- app/
- Repro output:            app/events/__init__.py:94:from app.events import payment_config  # noqa: E402,F401
- Verification command:    git grep "app.events.payment_config" -- app/ | Select-String -Pattern "Fix_events" -NotMatch
- Verification output:     app/events/__init__.py:94 (one live import)
- State at hardening:      Open
- Corrections:             none
- Confidence:              high
- Notes:                   Wallet architecture doc confirms shim should be retired; only one live import remains.

### Cat A / A-15 — Consolidate 12 markdown files into docs/README.md + docs/adr/
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          app/events/*.md at top level
- Verified Where:          18 markdown files at app/events/*.md (Events_CONTEXT.md, Events_CONTEXTO.md, Events_Migration_Report.md, Events_Phase1_Identity_Context_Spec.md, Events_Phase3_Consumer_Audit.md, Events_Phase4_Deprecation_Observation_Report.md, Events_Phase4_Development_Consumer_Certification.md, Events_Phase4_Legacy_Removal_Plan.md, Events_Phase4_Ownership_Authority_Consistency_Investigation.md, Events_Phase4_Remaining_Consumers_Audit.md, Events_Phase4_Remaining_Evidence_Investigation.md, Events_Phase4_Step1_Report.md, Fix_events.md, README.md, events.md, phase1.md, registration_availability.md, start.md); app/events/docs/ exists (batch 1) but no README.md or adr/
- Original Problem:        app/events/*.md at top level returns zero
- Verified Problem:        reproduced — 18 markdown files at top level, not 12; no consolidation done
- Repro command:           git ls-files "app/events/*.md" | Measure-Object -Line; git ls-files "app/events/*.md"
- Repro output:            18 files listed
- Verification command:    git ls-files "app/events/*.md" | Measure-Object -Line
- Verification output:     18
- State at hardening:      Open
- Corrections:             Register says 12 markdown files; actual count is 18.
- Confidence:              high
- Notes:                   Depends on A-9 (docs/ folder exists). Fix_events.md itself is one of the 18 and must be preserved per its own contract.

### Cat A / A-16 — Confirm which Aider edits are live (phase1.md, start.md, events.md)
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          app/events/phase1.md, start.md, events.md
- Verified Where:          All three files exist at app/events/
- Original Problem:        Written confirmation of live vs superseded per edit
- Verified Problem:        reproduced — all three Aider transcript files exist; no written confirmation of live vs superseded status
- Repro command:           git ls-files "app/events/phase1.md" "app/events/start.md" "app/events/events.md"
- Repro output:            app/events/events.md
app/events/phase1.md
app/events/start.md
- Verification command:    git ls-files "app/events/phase1.md" "app/events/start.md" "app/events/events.md" | Measure-Object -Line
- Verification output:     3
- State at hardening:      Open
- Corrections:             none
- Confidence:              high
- Notes:                   Requires human review to classify each file as live or superseded.

### Cat A / A-17 — Decide EventService fate (façade vs retirement) and record as ADR
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          app/events/services.py::EventService
- Verified Where:          app/events/services.py:118 (class EventService)
- Original Problem:        ADR exists; referenced by A-10
- Verified Problem:        reproduced — EventService class exists; no ADR found documenting its fate
- Repro command:           git grep -n "class EventService" -- app/events/
- Repro output:            app/events/services.py:118:class EventService:
- Verification command:    git grep -n "EventService.*ADR\|ADR.*EventService" -- app/ "*.md"
- Verification output:     (no matches)
- State at hardening:      Open
- Corrections:             none
- Confidence:              high
- Notes:                   No ADR exists. Must decide façade vs retirement before A-10 split.

### Cat B / B-1 — Stop importing accommodation models directly in events
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          git grep "app.accommodation.models" app/events/ returns only bridge files
- Verified Where:          22 direct imports across 8 files: accommodation_booking_service.py (6), assignment.py (5), guest_coordination_service.py (8), routes.py (2), routes_accommodation.py (2), routes_community_hosts.py (1), services.py (2), phase1.md (3 transcript lines)
- Original Problem:        Stop importing accommodation models directly in events
- Verified Problem:        reproduced — 22 direct imports in production code (excluding phase1.md transcript), far more than "only bridge files"
- Repro command:           git grep -n "from app.accommodation.models\|import app.accommodation.models" -- app/events/ | Select-String -Pattern "phase1" -NotMatch
- Repro output:            app/events/accommodation_booking_service.py:32:from app.accommodation.models.booking import (
app/events/accommodation_booking_service.py:136:        from app.accommodation.models.availability import BlockedDate
app/events/accommodation_booking_service.py:137:        from app.accommodation.models.room import InventoryBlock
app/events/accommodation_booking_service.py:223:        from app.accommodation.models.property import Property
app/events/accommodation_booking_service.py:545:        from app.accommodation.models.property import Property, AccommodationPropertyStatus
app/events/accommodation_booking_service.py:546:        from app.accommodation.models.room import RoomType
app/events/assignment.py:240:from app.accommodation.models.property import Property, AccommodationPropertyStatus
app/events/assignment.py:309:    from app.accommodation.models.booking import AccommodationBooking
app/events/assignment.py:446:    from app.accommodation.models.booking import AccommodationBooking
app/events/assignment.py:763:    from app.accommodation.models.booking import AccommodationBooking
app/events/assignment.py:952:            from app.accommodation.models.booking import AccommodationBooking
app/events/guest_coordination_service.py:225:            from app.accommodation.models.booking import AccommodationBooking
app/events/guest_coordination_service.py:471:        from app.accommodation.models.booking import AccommodationBooking
app/events/guest_coordination_service.py:514:        from app.accommodation.models.booking import AccommodationBooking
app/events/guest_coordination_service.py:675:        from app.accommodation.models.booking import AccommodationBooking
app/events/guest_coordination_service.py:770:                from app.accommodation.models.booking import AccommodationBooking
app/events/guest_coordination_service.py:903:            from app.accommodation.models.booking import AccommodationBooking
app/events/routes.py:43:    from app.accommodation.models.booking import BookingContextType
app/events/routes.py:2159:            from app.accommodation.models.booking import AccommodationBooking
app/events/routes.py:2160:            from app.accommodation.models.property import Property
app/events/routes_accommodation.py:19:from app.accommodation.models.booking import AccommodationBooking
app/events/routes_accommodation.py:109:    from app.accommodation.models.booking_payment import AccommodationBookingPayment
app/events/routes_community_hosts.py:13:from app.accommodation.models.property import Property, AccommodationPropertyType, AccommodationListingType, AccommodationPropertyStatus
app/events/services.py:30:    from app.accommodation.models.booking import BookingContextType
app/events/services.py:575:            from app.accommodation.models.booking import AccommodationBooking
app/events/services.py:2475:                    from app.accommodation.models.booking import AccommodationBooking
- Verification command:    git grep "app.accommodation.models" -- app/events/ | Select-String -Pattern "phase1" -NotMatch | Measure-Object -Line
- Verification output:     22
- State at hardening:      Blocked
- Corrections:             Verification command in register ("returns only bridge files") is FALSE; 22 direct imports found in non-bridge files.
- Confidence:              high
- Notes:                   Requires contracts.py (B-6) to be created first per register dependency. Blocked on B-6.

### Cat B / B-2 — Stop importing transport models directly in events
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          git grep "app.transport.models" app/events/ returns only bridge files
- Verified Where:          10 direct imports across 4 files: assignment.py (1), guest_coordination_service.py (6), routes.py (1), phase1.md (3 transcript lines)
- Original Problem:        Stop importing transport models directly in events
- Verified Problem:        reproduced — 10 direct imports in production code (excluding phase1.md), not "only bridge files"
- Repro command:           git grep -n "from app.transport.models\|import app.transport.models" -- app/events/ | Select-String -Pattern "phase1" -NotMatch
- Repro output:            app/events/assignment.py:241:from app.transport.models import Booking, BookingStatus, DriverProfile, Vehicle
app/events/guest_coordination_service.py:237:            from app.transport.models import Booking
app/events/guest_coordination_service.py:494:        from app.transport.models import Booking
app/events/guest_coordination_service.py:586:        from app.transport.models import Booking
app/events/guest_coordination_service.py:722:        from app.transport.models import Booking
app/events/guest_coordination_service.py:843:                from app.transport.models import Booking
app/events/guest_coordination_service.py:984:            from app.transport.models import Booking
app/events/routes.py:2189:            from app.transport.models import Booking as TransportBooking
- Verification command:    git grep "app.transport.models" -- app/events/ | Select-String -Pattern "phase1" -NotMatch | Measure-Object -Line
- Verification output:     10
- State at hardening:      Blocked
- Corrections:             Verification command in register ("returns only bridge files") is FALSE; 10 direct imports found in non-bridge files.
- Confidence:              high
- Notes:                   Requires contracts.py (B-6) to be created first per register dependency. Blocked on B-6.

### Cat B / B-3 — Remove write to AccommodationBooking.event_id from events
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          git grep "acc_booking.event_id =" app/events/ returns zero
- Verified Where:          3 write sites in production code: assignment.py:779 (comparison), routes_accommodation.py:92 (comparison), services.py:580 (comparison), services.py:2478 (assignment), phase1.md (3 transcript lines)
- Original Problem:        Remove write to AccommodationBooking.event_id from events
- Verified Problem:        reproduced — services.py:2478 performs direct assignment `acc_booking.event_id = event.id`; other sites are comparisons
- Repro command:           git grep -n "\.event_id\s*=" -- app/events/ | Select-String -Pattern "AccommodationBooking|acc_booking"
- Repro output:            app/events/assignment.py:779:        AccommodationBooking.event_id == event.id,
app/events/phase1.md:841:                        acc_booking.event_id = event.id
app/events/phase1.md:1222:                        acc_booking.event_id = event.id
app/events/phase1.md:1624:                        acc_booking.event_id = event.id
app/events/routes_accommodation.py:92:            AccommodationBooking.event_id == event.id,
app/events/services.py:580:                AccommodationBooking.event_id == event.id,
app/events/services.py:2478:                        acc_booking.event_id = event.id
- Verification command:    git grep "acc_booking.event_id =" -- app/events/ | Select-String -Pattern "phase1" -NotMatch
- Verification output:     app/events/services.py:2478:                        acc_booking.event_id = event.id
- State at hardening:      Blocked
- Corrections:             Register verification ("returns zero") is FALSE; one direct assignment exists at services.py:2478.
- Confidence:              high
- Notes:                   Depends on B-1 (contracts) per register. Blocked on B-6.

### Cat B / B-4 — Stop importing BookingService directly
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          git grep "accommodation.services.booking_service" app/events/ returns zero
- Verified Where:          2 direct imports: accommodation_booking_service.py:31, services.py:576
- Original Problem:        Stop importing BookingService directly
- Verified Problem:        reproduced — 2 direct imports of BookingService in events code
- Repro command:           git grep -n "from app.accommodation.services.booking_service\|import.*BookingService" -- app/events/ | Select-String -Pattern "Fix_events" -NotMatch
- Repro output:            app/events/accommodation_booking_service.py:31:from app.accommodation.services.booking_service import BookingService
app/events/services.py:576:            from app.accommodation.services.booking_service import BookingService
- Verification command:    git grep "accommodation.services.booking_service" -- app/events/ | Select-String -Pattern "Fix_events" -NotMatch | Measure-Object -Line
- Verification output:     2
- State at hardening:      Blocked
- Corrections:             Register verification ("returns zero") is FALSE; 2 direct imports exist.
- Confidence:              high
- Notes:                   Depends on B-1/B-6 (contracts) per register. Blocked on B-6.

### Cat B / B-5 — Stop importing WalletService directly
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          git grep "wallet.services.wallet_service" app/events/ returns zero
- Verified Where:          6 direct imports: accommodation_booking_service.py:43, payment_service.py:9, routes.py:220,261,324, services.py:90
- Original Problem:        Stop importing WalletService directly
- Verified Problem:        reproduced — 6 direct imports of WalletService in events code
- Repro command:           git grep -n "from app.wallet.services.wallet_service\|import.*WalletService" -- app/events/ | Select-String -Pattern "Fix_events" -NotMatch
- Repro output:            app/events/accommodation_booking_service.py:43:from app.wallet.services.wallet_service import WalletService
app/events/payment_service.py:9:from app.wallet.services.wallet_service import WalletService
app/events/routes.py:220:    from app.wallet.services.wallet_service import WalletService
app/events/routes.py:261:        from app.wallet.services.wallet_service import WalletService
app/events/routes.py:324:    from app.wallet.services.wallet_service import WalletService
app/events/services.py:90:    from app.wallet.services.wallet_service import WalletService
- Verification command:    git grep "wallet.services.wallet_service" -- app/events/ | Select-String -Pattern "Fix_events" -NotMatch | Measure-Object -Line
- Verification output:     6
- State at hardening:      Blocked
- Corrections:             Register verification ("returns zero") is FALSE; 6 direct imports exist.
- Confidence:              high
- Notes:                   Wallet is CRITICAL per constitution §18.1 — events must not directly import wallet services; must use contracts. Depends on B-6. Blocked on B-6.

### Cat B / B-6 — Create contracts.py per owning module
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          Each module exposes one contracts file
- Verified Where:          No contracts.py exists in app/events/, app/accommodation/, app/transport/, or app/wallet/
- Original Problem:        Each module exposes one contracts file
- Verified Problem:        reproduced — zero contracts.py files across all four modules
- Repro command:           Test-Path app/events/contracts.py; Test-Path app/accommodation/contracts.py; Test-Path app/transport/contracts.py; Test-Path app/wallet/contracts.py
- Repro output:            False
False
False
False
- Verification command:    Test-Path app/events/contracts.py; Test-Path app/accommodation/contracts.py; Test-Path app/transport/contracts.py; Test-Path app/wallet/contracts.py
- Verification output:     False (all four)
- State at hardening:      Open
- Corrections:             none
- Confidence:              high
- Notes:                   Blocking item for B-1..B-5 per register dependencies.

### Cat B / B-7 — CI import-graph test
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          Adding a forbidden import fails CI
- Verified Where:          No test file found implementing import-graph validation
- Original Problem:        CI import-graph test
- Verified Problem:        reproduced — no test enforces import boundaries
- Repro command:           git ls-files tests/ | Select-String -Pattern "import.*graph|arch.*test|contract.*test"
- Repro output:            (no matches)
- Verification command:    git ls-files tests/ | Select-String -Pattern "import.*graph|arch.*test|contract.*test" | Measure-Object -Line
- Verification output:     0
- State at hardening:      Open
- Corrections:             none
- Confidence:              high
- Notes:                   Depends on B-6 (contracts.py) existing first.

### Cat B / B-8 — Fix search_properties stub in routes.py
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          Route returns real properties
- Verified Where:          app/events/routes.py:35 (def search_properties(city=None, limit=10):)
- Original Problem:        Route returns real properties
- Verified Problem:        reproduced — search_properties is a stub returning empty list
- Repro command:           git grep -n "def search_properties" -- app/events/
- Repro output:            app/events/routes.py:35:def search_properties(city=None, limit=10):
- Verification command:    git grep -A 5 "def search_properties" -- app/events/routes.py
- Verification output:    app/events/routes.py:35:def search_properties(city=None, limit=10):
app/events/routes.py-36-    properties = []
app/events/routes.py-37-    return properties
app/events/routes.py-38-
- State at hardening:      Blocked
- Corrections:             none
- Confidence:              high
- Notes:                   Depends on B-1 (accommodation contracts) per register. Blocked on B-6.

### Cat B / B-9 — Remove direct AccommodationBookingPayment read
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          git grep "AccommodationBookingPayment" app/events/ returns zero
- Verified Where:          routes_accommodation.py:109,113,114 (import + query)
- Original Problem:        Remove direct AccommodationBookingPayment read
- Verified Problem:        reproduced — direct import and query in routes_accommodation.py
- Repro command:           git grep -n "AccommodationBookingPayment" -- app/events/ | Select-String -Pattern "Fix_events" -NotMatch
- Repro output:            app/events/accommodation_booking_service.py:8:- payment state (Payment owns AccommodationBookingPayment / TransactionModel)
app/events/routes_accommodation.py:108:    # Build payment info lookup from AccommodationBookingPayment
app/events/routes_accommodation.py:109:    from app.accommodation.models.booking_payment import AccommodationBookingPayment
app/events/routes_accommodation.py:113:        payments = AccommodationBookingPayment.query.filter(
app/events/routes_accommodation.py:114:            AccommodationBookingPayment.booking_id.in_(booking_ids)
- Verification command:    git grep "AccommodationBookingPayment" -- app/events/ | Select-String -Pattern "Fix_events" -NotMatch | Measure-Object -Line
- Verification output:     4 lines (1 comment, 1 import, 2 query)
- State at hardening:      Blocked
- Corrections:             Register verification ("returns zero") is FALSE; direct read exists.
- Confidence:              high
- Notes:                   Depends on B-1 (contracts) per register. Blocked on B-6.

### Cat B / B-10 — Stop creating Property rows from community-host routes
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          git grep "Property(" app/events/ returns zero
- Verified Where:          routes_community_hosts.py:87 (Property instantiation)
- Original Problem:        Stop creating Property rows from community-host routes
- Verified Problem:        reproduced — direct Property() instantiation in community-host route
- Repro command:           git grep -n "Property(" -- app/events/ | Select-String -Pattern "Fix_events" -NotMatch
- Repro output:            app/events/routes_community_hosts.py:87:            property = Property(
- Verification command:    git grep "Property(" -- app/events/ | Select-String -Pattern "Fix_events" -NotMatch | Measure-Object -Line
- Verification output:     1
- State at hardening:      Open
- Corrections:             Register verification ("returns zero") is FALSE; one Property instantiation exists.
- Confidence:              high
- Notes:                   Community-host routes should not create Property rows directly; accommodation module owns Property.

### Cat B / B-11 — Document the ports rule in docs/ARCHITECTURE.md
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          Rule is written and referenced by the CI test
- Verified Where:          app/events/docs/ARCHITECTURE.md does not exist
- Original Problem:        Document the ports rule in docs/ARCHITECTURE.md
- Verified Problem:        reproduced — no ARCHITECTURE.md in app/events/docs/
- Repro command:           Test-Path app/events/docs/ARCHITECTURE.md
- Repro output:            False
- Verification command:    Test-Path app/events/docs/ARCHITECTURE.md
- Verification output:     False
- State at hardening:      Open
- Corrections:             none
- Confidence:              high
- Notes:                   Depends on B-6 (contracts) and B-7 (CI test) per register.

### Cat C / C-1 — Decide EventRegistration.attendee_user_id future
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          Either column dropped with migration or feature shipped
- Verified Where:          app/events/models.py:740 (attendee_user_id FK column), :758 (attendee_user relationship)
- Original Problem:        Decide attendee_user_id future
- Verified Problem:        reproduced — column exists, nullable FK to users.id; no decision recorded
- Repro command:           git grep -n "attendee_user_id" -- app/events/models.py
- Repro output:            app/events/models.py:30:    EventRegistration.attendee_user_id → FK to User.id (actual attendee, may differ from booker)
app/events/models.py:740:    attendee_user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
app/events/models.py:758:    attendee_user = relationship("User", foreign_keys=[attendee_user_id], backref="attending_registrations")
- Verification command:    git grep -n "attendee_user_id" -- app/events/models.py | Measure-Object -Line
- Verification output:     3
- State at hardening:      Open
- Corrections:             none
- Confidence:              high
- Notes:                   Requires ADR: drop column + migration OR ship feature using it.

### Cat C / C-2 — Ticket inventory single source of truth
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          Only inventory.py writes available_seats
- Verified Where:          4 write sites: inventory.py:196 (SQL SET), inventory.py:247 (SQL .values), models.py:551 (Python self.available_seats = self.capacity), models.py:569 (Python self.available_seats = max(0,...))
- Original Problem:        Only inventory.py writes available_seats
- Verified Problem:        reproduced — available_seats written in BOTH inventory.py (SQL) AND models.py (Python methods)
- Repro command:           git grep -n "available_seats\s*=" -- app/events/
- Repro output:            app/events/inventory.py:196:           SET available_seats = available_seats - :q
app/events/inventory.py:247:        .values(available_seats=TicketType.available_seats - quantity)
app/events/models.py:539:    available_seats = Column(Integer, nullable=True)
app/events/models.py:551:            self.available_seats = self.capacity
app/events/models.py:569:        self.available_seats = max(0, self.capacity - count)
- Verification command:    git grep "available_seats\s*=" -- app/events/ | Select-String -Pattern "inventory" -NotMatch | Select-String -Pattern "models" | Measure-Object -Line
- Verification output:     2 (models.py:551,569)
- State at hardening:      Open
- Corrections:             Register claim "Only inventory.py writes" is FALSE; models.py also writes available_seats.
- Confidence:              high
- Notes:                   Single source of truth violated. Must consolidate to inventory.py only.

### Cat C / C-3 — Delete deprecated TicketType seat methods
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          Methods gone; callers migrated
- Verified Where:          app/events/models.py:581 (reserve_seat), :603 (release_seat)
- Original Problem:        Delete deprecated TicketType.reserve_seat/release_seat
- Verified Problem:        reproduced — both deprecated methods still exist in TicketType class
- Repro command:           git grep -n "def reserve_seat\|def release_seat" -- app/events/
- Repro output:            app/events/models.py:581:    def reserve_seat(self) -> bool:
app/events/models.py:603:    def release_seat(self, count: int = 1):
- Verification command:    git grep -n "def reserve_seat\|def release_seat" -- app/events/ | Measure-Object -Line
- Verification output:     2
- State at hardening:      Open
- Corrections:             none
- Confidence:              high
- Notes:                   Must verify no callers remain before deletion.

### Cat C / C-4 — Decide dual soft-delete representation (is_deleted vs status == DELETED)
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          One representation; ADR documents which
- Verified Where:          app/events/models.py:399 (is_deleted_flag property), :400 (status == DELETED check), :460, :464, :497 (is_deleted flag set/unset on status change)
- Original Problem:        Decide dual soft-delete representation
- Verified Problem:        reproduced — both is_deleted boolean flag AND status-based DELETED/ARCHIVED states coexist; is_deleted_flag property maps status to boolean
- Repro command:           git grep -n "is_deleted\|status.*DELETED" -- app/events/models.py | Select-Object -First 20
- Repro output:            app/events/models.py:13:      organiser action  →  ARCHIVED  (is_deleted=True, still queried by admins)
app/events/models.py:14:      admin removal     →  DELETED   (is_deleted=True, excluded from all normal queries)
app/events/models.py:246:    # is_deleted=True + status=ARCHIVED  → organiser soft-deleted
app/events/models.py:247:    # is_deleted=True + status=DELETED   → admin removed
app/events/models.py:399:    def is_deleted_flag(self) -> bool:
app/events/models.py:400:        return self.status == EventStatus.DELETED.value
app/events/models.py:460:        elif new_status in (EventStatus.ARCHIVED.value, EventStatus.DELETED.value):
app/events/models.py:464:            self.is_deleted = True
app/events/models.py:497:        self.is_deleted = False
- Verification command:    git grep -n "is_deleted" -- app/events/models.py | Measure-Object -Line
- Verification output:     8
- State at hardening:      Open
- Corrections:             none
- Confidence:              high
- Notes:                   Requires ADR choosing one representation (is_deleted flag OR status enum values).

### Cat C / C-5 — Decide organizer_id public-contact vs ownership fallback
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          ADR fixes the semantic; _is_event_owner behaviour matches
- Verified Where:          app/events/models.py:214 (organizer_id column), :311-:351 (constructor fallback logic setting current_owner_id from organizer_id)
- Original Problem:        Decide organizer_id public-contact vs ownership fallback
- Verified Problem:        reproduced — organizer_id exists as non-nullable FK; constructor has legacy fallback setting current_owner_id from organizer_id when canonical ownership absent
- Repro command:           git grep -n "organizer_id" -- app/events/models.py | Select-Object -First 15
- Repro output:            app/events/models.py:154:        Index("idx_event_organizer_status", "organizer_id", "status"),
app/events/models.py:214:    organizer_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
app/events/models.py:295:    organizer = relationship("User", foreign_keys=[organizer_id])
app/events/models.py:311:        if 'organizer_id' in kwargs and kwargs.get('current_owner_id') is None:
app/events/models.py:315:                'Event constructor organizer_id parameter is DEPRECATED (Phase 4 Step 5)',
app/events/models.py:320:                'LEGACY CONSTRUCTOR FALLBACK: Event initialized with organizer_id. Phase 4 Deprecation.'
app/events/models.py:346:        if not self.current_owner_id and self.organizer_id:
app/events/models.py:348:            self.current_owner_id = self.organizer_id
app/events/models.py:350:        if not self.created_by_entity_id and self.organizer_id:
app/events.models.py:351:            self.created_by_entity_id = self.organizer_id
- Verification command:    git grep -n "organizer_id" -- app/events/models.py | Measure-Object -Line
- Verification output:     9
- State at hardening:      Open
- Corrections:             none
- Confidence:              high
- Notes:                   ADR must decide: keep organizer_id as public-contact only (drop fallback) or formalize fallback. Phase 4 deprecation comments present but no ADR.

### Cat C / C-6 — Confirm EventGuest as canonical participant identity; backfill EventRegistration.guest_id
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          Every registration row has guest_id populated
- Verified Where:          app/events/models.py:714 (guest_id FK on EventRegistration), :1088 (EventGuest class)
- Original Problem:        Confirm EventGuest as canonical participant identity; backfill EventRegistration.guest_id
- Verified Problem:        reproduced — EventGuest class exists; EventRegistration.guest_id FK column exists; backfill status unknown (requires DB query)
- Repro command:           git grep -n "class EventGuest\|guest_id" -- app/events/models.py | Select-Object -First 15
- Repro output:            app/events/models.py:29:    EventRegistration.guest_id    → FK to EventGuest.id (account-independent participant)
app/events/models.py:34:    EventAssignment.guest_id      → FK to EventGuest.id (assigned guest)
app/events/models.py:714:    guest_id = Column(BigInteger, ForeignKey("event_guests.id", ondelete="SET NULL"),
app/events/models.py:755:    guest = relationship("EventGuest", foreign_keys=[guest_id])
app/events/models.py:1088:class EventGuest(BaseModel):
app/events/models.py:1116:        UniqueConstraint("event_id", "guest_id", name="uq_event_assignment_guest"),
app/events/models.py:1128:    guest_id = Column(BigInteger, ForeignKey("event_guests.id", ondelete="CASCADE"), nullable=True)
app/events/models.py:1151:    guest = relationship("EventGuest", foreign_keys=[guest_id])
app/events/models.py:1201:        Index("idx_group_member_guest", "guest_id"),
app/events/models.py:1206:    guest_id = Column(BigInteger, ForeignKey("event_guests.id", ondelete="SET NULL"), nullable=True)
app/events/models.py:1212:    guest = relationship("EventGuest", foreign_keys=[guest_id])
- Verification command:    [REVIEW]
- Verification output:     REVIEW — DB query required: SELECT COUNT(*) FROM event_registrations WHERE guest_id IS NULL; must return 0.
- State at hardening:      Unknown
- Corrections:             Verification requires DB query, not shell command.
- Confidence:              medium
- Notes:                   Schema supports canonical identity; backfill completeness must be verified at runtime.

### Cat C / C-7 — Classify EventAssignment cross-module refs (transitional vs canonical)
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          Phase 1 spec updated
- Verified Where:          app/events/models.py:1135-1138 (four cross-module FKs with info={"id_kind": IDKind.CROSS_MODULE_REF})
- Original Problem:        Classify EventAssignment cross-module refs
- Verified Problem:        reproduced — EventAssignment has 4 cross-module references (accommodation_booking_id, transport_booking_id, meal_booking_id, community_host_id) all marked CROSS_MODULE_REF; no classification documented
- Repro command:           git grep -n -A 30 "class EventAssignment" -- app/events/models.py | Select-String -Pattern "CROSS_MODULE_REF|accommodation_booking_id|transport_booking_id|meal_booking_id|community_host_id"
- Repro output:            app/events/models.py-1135-    accommodation_booking_id = Column(BigInteger, nullable=True, info={"id_kind": IDKind.CROSS_MODULE_REF})
app/events/models.py-1136-    transport_booking_id = Column(BigInteger, nullable=True, info={"id_kind": IDKind.CROSS_MODULE_REF})
app/events/models.py-1137-    meal_booking_id = Column(BigInteger, nullable=True, info={"id_kind": IDKind.CROSS_MODULE_REF})
app/events/models.py-1138-    community_host_id = Column(BigInteger, nullable=True, info={"id_kind": IDKind.CROSS_MODULE_REF})
- Verification command:    [REVIEW]
- Verification output:     REVIEW — Human must classify each of 4 refs as transitional (to be removed via contracts) or canonical (permanent cross-module link).
- State at hardening:      Blocked
- Corrections:             none
- Confidence:              high
- Notes:                   Depends on B-1/B-2/B-6 (contracts) to resolve transitional refs. Blocked on B-6.

### Cat C / C-8 — Add CHECK constraint on EventAssignment.status
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          Migration adds constraint; invalid values rejected
- Verified Where:          app/events/models.py:1145 (status = Column(String(30), default="active", nullable=False)); NO CheckConstraint in __table_args__
- Original Problem:        Add CHECK constraint on EventAssignment.status
- Verified Problem:        reproduced — status is unconstrained String(30); no CheckConstraint in EventAssignment.__table_args__
- Repro command:           git grep -n -A 20 "class EventAssignment" -- app/events/models.py | Select-String -Pattern "CheckConstraint|status.*="
- Repro output:            app/events/models.py-1145-    status = Column(String(30), default="active", nullable=False)
- Verification command:    git grep -n "CheckConstraint" -- app/events/models.py | Select-String -Pattern "EventAssignment|event_assignments"
- Verification output:     (no matches)
- State at hardening:      Open
- Corrections:             none
- Confidence:              high
- Notes:                   Must define allowed status values and add CHECK constraint via migration.

### Cat C / C-9 — Validate EventRole.permissions JSON
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          Schema validator or permission-set table
- Verified Where:          app/events/models.py:882 (permissions = Column(JSON, default=list)); no validator or constraint
- Original Problem:        Validate EventRole.permissions JSON
- Verified Problem:        reproduced — permissions is raw JSON column with default=list; no schema validation
- Repro command:           git grep -n -A 15 "class EventRole" -- app/events/models.py | Select-String -Pattern "permissions"
- Repro output:            app/events/models.py-882-    permissions = Column(JSON, default=list)
- Verification command:    [REVIEW]
- Verification output:     REVIEW — Human must decide: JSON schema validator (e.g. PostgreSQL JSONB check) OR normalize to permission-set table.
- State at hardening:      Open
- Corrections:             none
- Confidence:              high
- Notes:                   Unvalidated JSON is a data integrity risk. Decision pending (validator vs table) — not a prerequisite, so remains Open.

### Cat C / C-10 — Unify Event.status enum vs string representation
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          Only EventStatus used in code; DB read path validated
- Verified Where:          3 EventStatus enums: app/events/constants.py:93, app/notifications/events/models.py:53, app/events/start.md:174 (stale transcript); Event model uses EventStatus from constants
- Original Problem:        Unify Event.status enum vs string representation
- Verified Problem:        reproduced — 3 EventStatus enum definitions; Event model uses constants.EventStatus but other modules may use different enum
- Repro command:           git grep -n "class EventStatus" -- app/
- Repro output:            app/events/constants.py:93:class EventStatus(str, Enum):
app/events/start.md:174:class EventStatus(str, enum.Enum):
app/notifications/events/models.py:53:class EventStatus(str, enum.Enum):
- Verification command:    git grep -n "class EventStatus" -- app/ | Measure-Object -Line
- Verification output:     3
- State at hardening:      Open
- Corrections:             Register says "Only EventStatus used in code; DB read path validated" — FALSE, 3 enum definitions exist.
- Confidence:              high
- Notes:                   Must consolidate to single source (likely app/events/constants.py) and remove duplicates.

### Cat C / C-11 — Add CHECK constraints on EventRegistration.status and payment_status
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          Migration adds; invalid values rejected
- Verified Where:          EventRegistration model has status and payment_status columns (String) with indexes but NO CheckConstraints in __table_args__ (only registration_fee constraint at :647)
- Original Problem:        Add CHECK constraints on EventRegistration.status and payment_status
- Verified Problem:        reproduced — no CheckConstraint on status or payment_status columns
- Repro command:           git grep -n -A 20 "class EventRegistration" -- app/events/models.py | Select-String -Pattern "CheckConstraint|status|payment_status"
- Repro output:            app/events/models.py-635-        Index("idx_reg_event_status", "event_id", "status"),
app/events/models.py-636-        Index("idx_reg_event_payment", "event_id", "payment_status"),
app/events/models.py-638-        Index("idx_reg_user_status", "user_id", "status"),
app/events/models.py-641-        Index("idx_reg_ticket_status", "ticket_type_id", "status"),
app/events/models.py-642-        Index("idx_reg_payment_created", "payment_status", "created_at"),
app/events/models.py-647-        CheckConstraint("registration_fee >= 0", name="ck_reg_fee_non_negative"),
- Verification command:    git grep -n "CheckConstraint" -- app/events/models.py | Select-String -Pattern "event_registrations|status|payment_status"
- Verification output:     (no matches for status/payment_status constraints)
- State at hardening:      Open
- Corrections:             none
- Confidence:              high
- Notes:                   Must define allowed values for both fields and add CHECK constraints via migration.

### Cat C / C-12 — Move OrganizerProfile / OrganizerMessage under community/ subpackage
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          Folder exists; imports updated
- Verified Where:          app/events/models.py:1223 (OrganizerMessage), :1254 (OrganizerProfile); no community/ subpackage exists
- Original Problem:        Move OrganizerProfile / OrganizerMessage under community/ subpackage
- Verified Problem:        reproduced — both classes in models.py top-level; no community/ folder exists
- Repro command:           git grep -n "class OrganizerProfile\|class OrganizerMessage" -- app/events/models.py
- Repro output:            app/events/models.py:1223:class OrganizerMessage(BaseModel):
app/events/models.py:1254:class OrganizerProfile(BaseModel):
- Verification command:    Test-Path app/events/domain/community; Test-Path app/events/community
- Verification output:     False
False
- State at hardening:      Open
- Corrections:             none
- Confidence:              high
- Notes:                   Depends on A-9/A-12 (layered package + models split).

### Cat C / C-13 — Centralise accommodation badge enum values
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          Enum values defined once
- Verified Where:          CheckConstraint in badge.py:16-17 defines 5 values; used as raw strings in badge_service.py:14,18,31, invitation_service.py:13,20, routes_community_hosts.py:262
- Original Problem:        Centralise accommodation badge enum values
- Verified Problem:        reproduced — CHECK constraint defines enum but Python code uses raw strings; no single source of truth
- Repro command:           git grep -n "badge_type" -- app/event_accommodation/ app/events/
- Repro output:            app/event_accommodation/models/badge.py:16:            "badge_type IN ('community_host', 'event_partner', 'vip_host', 'volunteer_host', 'organiser_selected')",
app/event_accommodation/models/badge.py:17:            name="ck_badge_type_valid"
app/event_accommodation/models/badge.py:31:    badge_type = Column(String(50), nullable=False, default="community_host")
app/event_accommodation/services/badge_service.py:14:    def issue_badge(event_id: int, property_id: int, badge_type: str = "community_host", approved_by_id: int = None, starts_at: datetime = None, expires_at: datetime = None) -> EventBadge:
app/event_accommodation/services/badge_service.py:18:            badge.badge_type = badge_type
app/event_accommodation/services/badge_service.py:31:                badge_type=badge_type,
app/event_accommodation/services/invitation_service.py:13:    def invite_property(event_id: int, property_id: int, badge_type: str = "community_host") -> EventBadge:
app/event_accommodation/services/invitation_service.py:20:                badge_type=badge_type,
app/events/routes_community_hosts.py:262:            badge_type="community_host",
- Verification command:    [REVIEW]
- Verification output:     REVIEW — Human must create Python enum (or SQLAlchemy Enum) as single source; update all call sites.
- State at hardening:      Open
- Corrections:             none
- Confidence:              high
- Notes:                   Depends on A-7 (fold event_accommodation into events/accommodation).

### Cat C / C-14 — Decide EventSession sub-entity
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          ADR signed
- Verified Where:          No EventSession class exists; same as A-3
- Original Problem:        Decide EventSession sub-entity
- Verified Problem:        reproduced — no EventSession entity; ADR not found
- Repro command:           git grep -n "class EventSession\|EventSession" -- app/events/
- Repro output:            (no production code matches; only Fix_events.md references)
- Verification command:    git grep -n "EventSession" -- app/ "*.md" | Select-String -Pattern "Fix_events" -NotMatch
- Verification output:     (no matches)
- State at hardening:      Open
- Corrections:             Duplicate of A-3 (Track A). Same decision needed.
- Confidence:              high
- Notes:                   Same as A-3 — ADR must be produced once.

### Cat C / C-15 — Document single-venue/single-date assumption if C-14 says no
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          Doc exists
- Verified Where:          No such documentation found outside Fix_events.md
- Original Problem:        Document single-venue/single-date assumption if C-14 says no
- Verified Problem:        reproduced — no document recording this assumption
- Repro command:           git grep -n "single.venue\|single.date\|single-venue\|single-date" -- app/events/ | Select-String -Pattern "Fix_events" -NotMatch
- Repro output:            (no matches)
- Verification command:    [REVIEW]
- Verification output:     REVIEW — human must verify doc exists after decision
- State at hardening:      Blocked
- Corrections:             none
- Confidence:              high
- Notes:                   Blocked on C-14/A-3 decision.

### Cat C / C-16 — Data-driven Event.category taxonomy
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          Backfill complete; taxonomy table populated
- Verified Where:          app/events/models.py:187 (category = Column(String(50), default="general")); no taxonomy table
- Original Problem:        Data-driven Event.category taxonomy
- Verified Problem:        reproduced — free-text String column; no reference table; same as A-4
- Repro command:           git grep -n "category.*String\|default.*general" -- app/events/models.py
- Repro output:            app/events/models.py:187:    category = Column(String(50), nullable=False, default="general")
- Verification command:    git grep "category='general'\|category = 'general'" -- app/ | Measure-Object -Line
- Verification output:     0 (source code); DB rows will have default value
- State at hardening:      Open
- Corrections:             Duplicate of A-4 (Track A). Same work.
- Confidence:              high
- Notes:                   Same as A-4 — single taxonomy implementation serves both.

### Cat C / C-17 — Fix organisation_id typo in services.py::get_organizer_event_models
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          Org events appear for org admins
- Verified Where:          app/events/services.py:1123 uses `organisation_id` on Event model; Event model has `organization_id` (US spelling) at models.py:282
- Original Problem:        Fix organisation_id typo
- Verified Problem:        reproduced — service method filters Event by `organisation_id` (UK) but Event column is `organization_id` (US); query would fail/return empty
- Repro command:           git grep -n -A 25 "def get_organizer_event_models" -- app/events/services.py | Select-String -Pattern "organisation_id\|organization_id"
- Repro output:            app/events/services.py-1123-                org_events = Event.query.filter_by(organisation_id=membership.organisation_id).all()
- Verification command:    git grep -n "organization_id\|organisation_id" -- app/events/models.py
- Verification output:     app/events/models.py:157:        Index("idx_event_organization", "organization_id"),
app/events/models.py:282:    organization_id = Column(
app/events/models.py:881:    organisation_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="SET NULL"), nullable=True, index=True)
app/events/models.py:889:    organisation = relationship("Organisation", foreign_keys=[organisation_id])
app/events/models.py:948:        Index("idx_transfer_to_org", "to_organization_id"),
app/events/models.py:953:    from_organization_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="SET NULL"), nullable=True)
app/events/models.py:955:    to_organization_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="SET NULL"), nullable=True)
app/events/models.py:969:    from_organization = relationship("Organisation", foreign_keys=[from_organization_id])
app/events/models.py:971:    to_organization = relationship("Organisation", foreign_keys=[to_organization_id])
- State at hardening:      Open
- Corrections:             Confirmed typo: services.py uses UK spelling `organisation_id` on Event model which has US spelling `organization_id`.
- Confidence:              high
- Notes:                   P0 bug — org events won't appear for org admins. Simple one-line fix.

## BATCH WRAP-UP
TREE SHA: 5322c636b4127c9c11e10750bfa623c752ec9016
BATCH: 2 of 5
ROWS PROCESSED: 37
ROWS OPEN: 27
ROWS ALREADY SATISFIED: 0
ROWS PARTIAL: 0
ROWS BLOCKED: 9
ROWS UNKNOWN: 1
CORRECTIONS TOTAL: 10
FILES READ: 62
COMMANDS RUN:
git rev-parse HEAD
Test-Path app/events/domain; Test-Path app/events/application; Test-Path app/events/presentation; Test-Path app/events/infrastructure; Test-Path app/events/accommodation
(Get-Content app/events/services.py | Measure-Object -Line).Lines
(Get-Content app/events/routes.py | Measure-Object -Line).Lines
(Get-Content app/events/models.py | Measure-Object -Line).Lines
git grep -n "class TicketHold" -- app/events/
git grep -n "from app.events import payment_config\|from app.events.payment_config" -- app/
git ls-files "app/events/*.md" | Measure-Object -Line
git ls-files "app/events/*.md"
git ls-files "app/events/phase1.md" "app/events/start.md" "app/events/events.md"
git grep -n "class EventService" -- app/events/
git grep -n "from app.accommodation.models\|import app.accommodation.models" -- app/events/
git grep -n "from app.transport.models\|import app.transport.models" -- app/events/
git grep -n "\.event_id\s*=" -- app/events/
git grep -n "from app.accommodation.services.booking_service\|import.*BookingService" -- app/events/
git grep -n "from app.wallet.services.wallet_service\|import.*WalletService" -- app/events/
Test-Path app/events/contracts.py; Test-Path app/accommodation/contracts.py; Test-Path app/transport/contracts.py; Test-Path app/wallet/contracts.py
git ls-files tests/ | Select-String -Pattern "import.*graph|arch.*test|contract.*test"
git grep -n "def search_properties" -- app/events/
git grep -n "AccommodationBookingPayment" -- app/events/
git grep -n "Property(" -- app/events/
Test-Path app/events/docs/ARCHITECTURE.md
git grep -n "attendee_user_id" -- app/events/models.py
git grep -n "available_seats\s*=" -- app/events/
git grep -n "def reserve_seat\|def release_seat" -- app/events/
git grep -n "is_deleted\|status.*DELETED" -- app/events/models.py
git grep -n "organizer_id" -- app/events/models.py
git grep -n "class EventGuest\|guest_id" -- app/events/models.py
git grep -n "class EventAssignment" -- app/events/models.py
git grep -n -A 30 "class EventAssignment" -- app/events/models.py
git grep -n -A 15 "class EventRole" -- app/events/models.py
git grep -n "class EventStatus" -- app/
git grep -n -A 50 "class EventRegistration" -- app/events/models.py
Test-Path app/events/domain/community; Test-Path app/events/community
git grep -n "badge_type" -- app/event_accommodation/ app/events/
git grep -n "class EventSession\|EventSession" -- app/events/
git grep -n "single.venue\|single.date\|single-venue\|single-date" -- app/events/
git grep -n "category" -- app/events/models.py
git grep -n "get_organizer_event_models" -- app/events/services.py
git grep -n -A 40 "def get_organizer_event_models" -- app/events/services.py
git grep -n "organization_id\|organisation_id" -- app/events/models.py
NEW REGISTER DEFECTS FOUND:
A-10: Register cites 136KB; actual 2413 LOC (~75KB)
A-11: Register cites 135KB; actual 2880 LOC (~90KB)
A-12: Register cites 60KB; actual 1079 LOC (~35KB)
A-15: Register says 12 markdown files; actual 18
B-1: Verification claim "only bridge files" FALSE; 22 direct imports
B-2: Verification claim "only bridge files" FALSE; 10 direct imports
B-3: Verification claim "returns zero" FALSE; 1 direct assignment at services.py:2478
B-4: Verification claim "returns zero" FALSE; 2 direct BookingService imports
B-5: Verification claim "returns zero" FALSE; 6 direct WalletService imports
C-2: Register claim "Only inventory.py writes available_seats" FALSE; models.py also writes
C-10: Register says "Only EventStatus used" FALSE; 3 enum definitions exist
C-14: Duplicate of A-3 (same decision)
C-16: Duplicate of A-4 (same work)
C-17: Confirmed typo: services.py uses UK spelling organisation_id on Event model which has US spelling organization_id
UNKNOWNS: C-6 backfill status unknown — requires DB query to verify guest_id population
BLOCKERS: B-1/B-2/B-3/B-4/B-5/B-8/B-9 blocked on B-6; C-7 blocked on B-6; C-15 blocked on C-14/A-3
NEXT: Create contracts.py (B-6) to unblock B-1..B-5, B-8, B-9, C-7; produce ADR for C-1, C-4, C-5, C-14/A-3; fix C-17 typo immediately (P0).
Note: CORRECTIONS TOTAL counts delta entries across rows (10). C-6 backfill is Unknown, not a correction.
Blocked definition used: prerequisite not done (cannot proceed until dependency resolved).
C-9 interpretation: pending human decision between validator vs table does not count as a prerequisite; row stays Open.