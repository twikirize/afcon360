import sys
import os
from flask import Flask
from app import create_app
from app.events.models import Event
from app.extensions import db

app = create_app()

with app.app_context():
    events = Event.query.all()
    report_lines = [
        "# Phase 4 Step 1: Pre-Removal Evidence",
        "",
        "## 1. Backfill Candidate Report",
        "| Event ID | Name | Organizer ID | Current Owner Type | Current Owner ID | Organization ID | Eligibility | Reason |",
        "|----------|------|--------------|--------------------|------------------|-----------------|-------------|--------|"
    ]
    
    for e in events:
        eligibility = "NO"
        reason = ""
        
        if getattr(e, 'current_owner_id', None) is not None:
            eligibility = "NO"
            reason = "current_owner_id already populated"
        elif getattr(e, 'organizer_id', None) is not None:
            eligibility = "YES"
            reason = "Null current_owner_id, has organizer_id (Legacy Ownership)"
        else:
            eligibility = "NO"
            reason = "No organizer_id and no current_owner_id"
            
        report_lines.append(f"| {e.id} | {getattr(e, 'name', 'N/A')} | {getattr(e, 'organizer_id', 'N/A')} | {getattr(e, 'current_owner_type', 'N/A')} | {getattr(e, 'current_owner_id', 'N/A')} | {getattr(e, 'organization_id', 'N/A')} | {eligibility} | {reason} |")
        
    report_lines.append("")
    report_lines.append("## 2. Legacy organizer_id Observability Strategy")
    report_lines.append("Since no code changes are authorized yet, we define the observability approach to be implemented in Step 2:")
    report_lines.append("- **Action**: Add logger.warning('LEGACY_API_USAGE: organizer_id present in request') to all Event creation/update routes in pp/events/routes.py.")
    report_lines.append("- **Metrics**: Track occurrences of this log entry over a 7-day compatibility window.")
    report_lines.append("")
    report_lines.append("## 3. Verified Consumer Inventory")
    report_lines.append("- **Permissions**: _is_event_owner (Fallback logic intact)")
    report_lines.append("- **Metrics**: get_organizer_metrics (To be refactored)")
    report_lines.append("- **Routes**: Event creation/update APIs (Requires payload mapping)")
    report_lines.append("- **Models**: Event.__init__ (Requires deprecation warning)")
    
    with open("app/events/Events_Phase4_Step1_Report.md", "w") as f:
        f.write("\n".join(report_lines))

print("Report generated successfully.")
