# AFCON360 – SYSTEM CONTEXT (MASTER)

## 🎯 PRODUCT VISION

A unified event operating system where:

* Events coordinate accommodation, transport, food, tourism
* Each module is independent but orchestrated together
* Supports both:

  * Self-managed users (like Airbnb/Uber)
  * Organizer-managed large events (Olympics, Crusades, CHOGM)

---

## 🏗️ CURRENT ARCHITECTURE

Modules:

* events
* accommodation
* transport
* wallet
* identity
* admin

Each module is independent and already functional.

---

## ✅ COMPLETED (PHASE 1)

Event moderation system implemented with:

* EventStatus enum:
  draft → pending_approval → approved → live → suspended → paused → cancelled → archived → deleted

* Backend-enforced state transitions via:
  change_event_status()

* Role-based permissions:
  require_event_permission()

* EventModerationLog table:
  tracks all actions (approve, reject, suspend, etc.)

* Protected routes:
  /approve
  /reject
  /suspend
  /reactivate
  /pause
  /resume
  /delete

* All new events default to:
  pending_approval

---

## ⚠️ KNOWN TECH DEBT (DO NOT FIX YET)

* ALLOWED_TRANSITIONS duplicated in:

  * permissions.py
  * services.py

(To be unified later)

---

## 🚀 NEXT PHASE (PHASE 2)

Introduce orchestration layer:

1. EventParticipation

   * user ↔ event relationship
   * role + control_mode

2. EventAssignment

   * links attendee → bookings (accommodation, transport, meals)

3. Add optional event_id to booking models

4. DO NOT break existing modules

---

## 🔧 DEVELOPMENT METHOD

* ChatGPT = Architect (design + decisions)
* Aider = Implementer (code changes)
* User = Tester (runs + validates)

---

## ❗ STRICT RULES

* Do NOT rewrite existing modules
* Do NOT tightly couple services
* Events must ONLY orchestrate, not own services
* Always implement in phases

---

## 📌 CURRENT STATUS

Phase 1: DONE (moderation system)
Phase 2: NEXT (orchestration layer)

---
