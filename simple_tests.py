import os
import re

template_dir = r"C:\Users\ADMIN\Desktop\afcon360_app\templates"

# Matches the EXACT broken pattern found in files:
# safe_url('url_for\(['"]blueprint.endpoint', kwargs)')
# safe_url('url_for\(['"]blueprint.endpoint")')   <- double-quote variant
#
# Literal file content: url_for\(['"] then endpoint then ' or " then optional kwargs then )
BROKEN = re.compile(
    r"""safe_url\(['"]url_for\\\(\['"]\s*([a-zA-Z0-9_.]+)\s*['"]([^)]*)\)"""
)

def fix_match(m):
    endpoint = m.group(1).strip()
    after = m.group(2).strip()  # e.g. ", id=property.id" or ""
    if after.startswith(','):
        after = after[1:].strip()
    if after:
        return f"safe_url('{endpoint}', {after})"
    else:
        return f"safe_url('{endpoint}')"

fixed_count = 0
files_fixed = []

for root, dirs, files in os.walk(template_dir):
    for file in files:
        if not file.endswith('.html'):
            continue
        filepath = os.path.join(root, file)
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        original = content
        new_content = BROKEN.sub(fix_match, content)

        if new_content != original:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            fixed_count += 1
            files_fixed.append(filepath)
            print(f"✅ Fixed: {os.path.relpath(filepath, template_dir)}")

print(f"\n{'='*60}")
print(f"✅ Fixed {fixed_count} files")
if files_fixed:
    print("\nFiles changed:")
    for f in files_fixed:
        print(f"  - {os.path.relpath(f, template_dir)}")
print(f"{'='*60}")
print("\n🔄 Restart Flask and test!")


""" """
#Results
:\Users\ADMIN\Desktop\afcon360_app\.venv\Scripts\python.exe C:\Users\ADMIN\Desktop\afcon360_app\simple_tests.py
✅ Fixed: accommodation\moderate.html
✅ Fixed: accommodation\moderate_property.html
✅ Fixed: accommodation\moderate_review.html
✅ Fixed: accommodation\guest\detail.html
✅ Fixed: accommodation\guest\my_bookings.html
✅ Fixed: admin\settings.html
✅ Fixed: admin\moderator\events.html
✅ Fixed: admin\moderator\view_event.html
✅ Fixed: admin\settings\moderation.html
✅ Fixed: dashboard\user_dashboard.html
✅ Fixed: events\events_hub.html
✅ Fixed: events\moderate.html
✅ Fixed: events\moderate_detail.html
✅ Fixed: events\admin\dashboard.html
✅ Fixed: events\admin\events.html
✅ Fixed: events\admin\pending.html
✅ Fixed: events\admin\settings.html
✅ Fixed: events\admin\staff.html
✅ Fixed: events\admin\org\dashboard.html
✅ Fixed: events\attendee\attendee_dashboard.html
✅ Fixed: events\attendee\my_registrations.html
✅ Fixed: events\attendee\register.html
✅ Fixed: events\attendee\registration_confirmation.html
✅ Fixed: events\organizer\analytics.html
✅ Fixed: events\organizer\attendees.html
✅ Fixed: events\organizer\edit.html
✅ Fixed: events\organizer\my_events.html
✅ Fixed: events\organizer\organizer_dashboard.html
✅ Fixed: events\organizer\scanner.html
✅ Fixed: events\organizer\waitlist.html
✅ Fixed: events\public\landing.html
✅ Fixed: events\service_provider\service_provider_dashboard.html
✅ Fixed: tourism\moderate.html
✅ Fixed: tourism\moderate_listing.html
✅ Fixed: transport\become_driver.html
✅ Fixed: transport\book.html
✅ Fixed: transport\booking_detatails.html
✅ Fixed: transport\moderate.html
✅ Fixed: transport\moderate_booking.html
✅ Fixed: transport\moderate_driver.html
✅ Fixed: transport\moderate_vehicle.html
✅ Fixed: transport\analytics\index.html
✅ Fixed: transport\bookings\index.html
✅ Fixed: transport\bookings\show.html
✅ Fixed: transport\drivers\show.html
✅ Fixed: transport\drivers\_form.html
✅ Fixed: transport\incidents\index.html
✅ Fixed: transport\routes\index.html
✅ Fixed: wallet\agent_payout_request.html
✅ Fixed: wallet\original_file.html

============================================================
✅ Fixed 50 files

Files changed:
  - accommodation\moderate.html
  - accommodation\moderate_property.html
  - accommodation\moderate_review.html
  - accommodation\guest\detail.html
  - accommodation\guest\my_bookings.html
  - admin\settings.html
  - admin\moderator\events.html
  - admin\moderator\view_event.html
  - admin\settings\moderation.html
  - dashboard\user_dashboard.html
  - events\events_hub.html
  - events\moderate.html
  - events\moderate_detail.html
  - events\admin\dashboard.html
  - events\admin\events.html
  - events\admin\pending.html
  - events\admin\settings.html
  - events\admin\staff.html
  - events\admin\org\dashboard.html
  - events\attendee\attendee_dashboard.html
  - events\attendee\my_registrations.html
  - events\attendee\register.html
  - events\attendee\registration_confirmation.html
  - events\organizer\analytics.html
  - events\organizer\attendees.html
  - events\organizer\edit.html
  - events\organizer\my_events.html
  - events\organizer\organizer_dashboard.html
  - events\organizer\scanner.html
  - events\organizer\waitlist.html
  - events\public\landing.html
  - events\service_provider\service_provider_dashboard.html
  - tourism\moderate.html
  - tourism\moderate_listing.html
  - transport\become_driver.html
  - transport\book.html
  - transport\booking_detatails.html
  - transport\moderate.html
  - transport\moderate_booking.html
  - transport\moderate_driver.html
  - transport\moderate_vehicle.html
  - transport\analytics\index.html
  - transport\bookings\index.html
  - transport\bookings\show.html
  - transport\drivers\show.html
  - transport\drivers\_form.html
  - transport\incidents\index.html
  - transport\routes\index.html
  - wallet\agent_payout_request.html
  - wallet\original_file.html
============================================================

🔄 Restart Flask and test!

Process finished with exit code 0
