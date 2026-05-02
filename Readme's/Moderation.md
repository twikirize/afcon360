📋 Moderation System - Current Status & Developer Notes
┌─────────────────────────────────────────────────────────────┐
│                    Moderation Dashboard                      │
├─────────────────────────────────────────────────────────────┤
│  [All] [Transport] [Events] [Accommodation] [KYC] [Users]   │
├─────────────────────────────────────────────────────────────┤
│  Type          Item              Priority  Actions          │
│  🚌 Transport  Booking #123      HIGH      ✓ Approve ✗ Reject│
│  🎟️ Events     AFCON Final       CRITICAL  ✓ Approve ✗ Reject│
│  🏨 Hotel      Serena Kampala     NORMAL    ✓ Approve ✗ Reject│
│  👤 User       john_doe@email     MEDIUM    ✓ Approve ✗ Reject│
└─────────────────────────────────────────────────────────────┘
                          ↓
              /api/unified-queue endpoint
                          ↓
              ContentFlag table (all modules)
                          ↓
              Registry maps entity_type → display_name, icon, review_url


✅ WHAT'S IMPLEMENTED (FULLY FUNCTIONAL)
Core Infrastructure
✅ Universal Module Registry (app/admin/moderator/registry.py)

✅ Unified Queue API (/api/unified-queue)

✅ Unified Moderation Actions (/api/moderate/<type>/<id>/<action>)

✅ Module Auto-Discovery on startup

✅ Dynamic Dashboard with module filtering

✅ SLA tracking (claimed_at, resolved_at, processing_time)

✅ Performance metrics endpoint (/performance)

✅ Queue analytics endpoint (/queue_metrics)

✅ Audit insights endpoint (/audit_insights)

✅ Auto-priority engine (/api/auto-priority)

Working Features
text
✅ All flagged content from ANY module appears in one dashboard
✅ Filter by module (Transport, Events, Accommodation, KYC, Users)
✅ Sort by priority (Critical → High → Medium → Normal → Low)
✅ Approve/Reject actions work across all modules
✅ 30-second auto-refresh with manual trigger on actions
✅ Module icons display correctly (🚌, 🏨, 🎟️, etc.)
✅ Fallback to flag view if module review URL not implemented
✅ Rate limiting on API endpoints (2000/day, 500/hour)
✅ CSRF protection on all POST operations
⚠️ WHAT'S PARTIALLY IMPLEMENTED (NEEDS MODULE COOPERATION)
Module-Specific Features
Feature	Status	What Modules Need To Do
Human-readable titles	⚠️ Shows "User#42"	Implement get_title_fn(entity_id) in registry
Proper review URLs	⚠️ Falls back to flag view	Create admin view endpoints in each module
Module permissions	⚠️ Uses generic moderator role	Implement permission checks per entity type
Entity name resolution	⚠️ Shows raw IDs	Add get_entity_fn to fetch objects
Example: How A Module Should Register
python
# In app/transport/__init__.py
from app.admin.moderator.registry import register_module
from flask import url_for

def get_booking_title(booking_id):
    booking = Booking.query.get(booking_id)
    return f"#{booking.booking_reference} - {booking.passenger_name}"

register_module(
    entity_type='transport_booking',
    display_name='Transport Booking',
    review_url_fn=lambda id: url_for('transport.admin.view_booking', booking_id=id),
    get_title_fn=get_booking_title,  # ← Optional but recommended
    module_name='Transport',
    icon='fa-bus',
    required_permission='transport.moderate'  # ← Optional
)
❌ WHAT'S MISSING (FUTURE ENHANCEMENTS)
High Priority (Should Add Soon)
Entity Name Resolution

Currently shows "transport_booking#123" instead of meaningful names

Add get_entity_fn to registry

Modify /api/unified-queue to call it

Module-Specific Permissions

Currently only checks moderator role globally

Should check transport.moderate, events.moderate, etc.

Bulk Moderation Actions

No way to approve/reject multiple items at once

Add /api/moderate/bulk endpoint

Medium Priority (Nice to Have)
WebSocket Real-Time Updates

Currently uses 30-second polling

Implement with Flask-SocketIO for instant updates

Redis Caching for Registry

Registry rebuilds on every import

Cache in Redis with invalidation on module registration

Activity Logging per Module

Track which moderator moderated which module

Add module_name to ModerationLog

Low Priority (Future Polish)
Module Statistics Dashboard

Show moderation volume per module

Average response time per module

Automated Testing Suite

Unit tests for registry functions

Integration tests for API endpoints

Admin UI for Registry Management

Web interface to register/unregister modules

Configure icons, permissions without code changes

📝 NOTICE TO FUTURE DEVELOPERS
Important Files & Their Roles
text
app/admin/moderator/
├── registry.py          ← CENTRAL: Register new modules here
├── routes.py            ← API: /api/unified-queue, /api/moderate/*
├── __init__.py          ← Auto-discovery: Imports modules on startup
└── pipeline.py          ← Risk scoring: Priority calculation

templates/admin/moderator/
└── dashboard.html       ← UI: Unified moderation panel

static/js/modules/admin/
└── admin_moderation.js  ← Frontend: API calls, dynamic rendering
Adding a New Module to Moderation
Step 1: In your module's __init__.py, add registration:

python
try:
    from app.admin.moderator.registry import register_module
    from flask import url_for
    
    def get_my_entity_title(entity_id):
        # Return human-readable title
        entity = MyModel.query.get(entity_id)
        return entity.name if entity else f"#{entity_id}"
    
    register_module(
        entity_type='my_entity_type',      # Unique identifier
        display_name='My Entity',          # Shown in UI
        review_url_fn=lambda id: url_for('my_module.admin.view', id=id),
        get_title_fn=get_my_entity_title,  # Optional but recommended
        module_name='My Module',           # For filtering
        icon='fa-star',                    # FontAwesome icon
        required_permission='my_module.moderate'  # Optional
    )
except ImportError:
    pass  # Moderation system not available
Step 2: Create admin view endpoint:

python
@my_module_bp.route('/admin/view/<int:entity_id>')
@login_required
@require_permission('my_module.moderate')
def admin_view(entity_id):
    # Return JSON or HTML view for moderators
    pass
Step 3: Test by creating a flag:

python
from app.admin.services import create_flag
create_flag(moderator_user, 'my_entity_type', entity_id, 'Reason for flag')
Important Notes & Gotchas
⚠️ DO NOT create new files for module registration - use existing __init__.py files

⚠️ DO wrap imports in try/except - moderation system might be disabled

⚠️ DO implement review_url_fn - otherwise moderators can't see details

⚠️ DO test with FLASK_ENV=development first - production has stricter CSP

⚠️ DO NOT hardcode entity types - always use registry lookups

Common Issues & Solutions
Issue	Solution
"Entity not showing in dashboard"	Check registry._REGISTRY - is it registered?
Review URL returns 404	Implement the admin view endpoint
Icon not displaying	Use valid FontAwesome 5 icon name
Module filter not showing	Check module_name parameter in registration
Permissions denied	Add user to moderator role or implement permission
Debugging Commands
python
# In Flask shell
from app.admin.moderator.registry import get_registry, get_modules

# See all registered modules
print(get_modules())

# See all entity types
print(get_registry().keys())

# Check specific entity type
print(get_registry().get('transport_booking'))
Testing Checklist Before Deployment
All modules registered correctly

Review URLs work for each entity type

Approve/Reject actions update database

Priority sorting works (Critical → High → Medium → Normal → Low)

Module filters show correct counts

30-second auto-refresh doesn't cause duplicate actions

CSRF tokens present on all forms

Rate limiting doesn't block legitimate requests

Audit logs capture all moderation actions

📊 Current System Metrics
Component	Status	Coverage
Modules Registered	6	Users, Events, Transport, Accommodation, Tourism, KYC
API Endpoints	6	Health, My Queue, Unified Queue, Moderate, Performance, Metrics
Dashboard Panels	5	My Queue, Performance, Queue Analytics, Audit, Unified Queue
Database Tables	3	content_flags, moderation_logs, content_submissions
Auto-refresh Rate	30s	Moderate (can be reduced to 10s)
🚀 Quick Start for New Developers
bash
# 1. Clone and setup
git clone <repo>
cd afcon360_app
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Initialize database
flask db upgrade

# 3. Seed roles
flask seed-roles --force

# 4. Run development server
flask run --debug

# 5. Test moderation
# Login as moderator@example.com / password
# Visit /moderator/dashboard
# Create test flags via any module
📞 Support & Documentation
Registry API: See app/admin/moderator/registry.py docstrings

API Endpoints: Test with /moderator/api/unified-queue

Example Module: Reference app/transport/__init__.py

Dashboard UI: Modify templates/admin/moderator/dashboard.html

Last Updated: April 28, 2026
Version: 2.0 (Universal Moderation)
Maintainer: AFCON360 Development Team
Status: 🟢 Production Ready (with optional enhancements noted above)