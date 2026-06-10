#!/usr/bin/env python
"""
Bug detection script for accommodation module.
Run from project root: python check_bugs.py
"""

issues = []

# =====================================================
# Read all relevant files
# =====================================================
with open('app/accommodation/routes.py', 'r', encoding='utf-8') as f:
    routes_content = f.read()
    routes_lines = routes_content.splitlines()

with open('app/accommodation/services/booking_service.py', 'r', encoding='utf-8') as f:
    svc_content = f.read()

with open('app/accommodation/models/booking.py', 'r', encoding='utf-8') as f:
    model_content = f.read()

with open('templates/accommodation/my_accommodation.html', 'r', encoding='utf-8') as f:
    tmpl_content = f.read()

with open('templates/accommodation/guest/checkout.html', 'r', encoding='utf-8') as f:
    checkout_content = f.read()


# =====================================================
# BUG 1: routes.py uses 'request.session' - Flask doesn't have this
# Flask session is imported from flask as `session`
# =====================================================
request_session_count = routes_content.count('request.session')
if request_session_count > 0:
    for i, line in enumerate(routes_lines, 1):
        if 'request.session' in line:
            issues.append(f'[BUG-1] routes.py line {i}: `request.session` used - should be Flask `session` (imported from flask). Line: {line.strip()}')

# =====================================================
# BUG 2: confirm_booking error message calls .value on a string
# booking.status is stored as string (e.g. "pending"), calling .value on it will crash
# =====================================================
if 'booking.status.value' in svc_content:
    for i, line in enumerate(svc_content.splitlines(), 1):
        if 'booking.status.value' in line:
            issues.append(f'[BUG-2] booking_service.py line {i}: `booking.status.value` - booking.status is already a string, calling .value will crash. Line: {line.strip()}')

# =====================================================
# BUG 3: Payment status assigned as Enum object (not .value string)
# =====================================================
bad_payment_assigns = [
    ('booking.payment_status = AccommodationPaymentStatus.PAID\n', 'confirm_booking sets payment_status as enum object, not string'),
    ('booking.payment_status = AccommodationPaymentStatus.REFUNDED\n', 'cancel_booking sets payment_status as enum object, not string'),
]
for pattern, msg in bad_payment_assigns:
    if pattern in svc_content:
        for i, line in enumerate(svc_content.splitlines(), 1):
            if pattern.strip() in line:
                issues.append(f'[BUG-3] booking_service.py line {i}: {msg}. Line: {line.strip()}')

# =====================================================
# BUG 4: context_type stored as enum object (not .value) in create_booking
# =====================================================
if "context_type=context_type or BookingContextType.NONE," in svc_content:
    issues.append('[BUG-4] booking_service.py: context_type stored as enum object not string (.value). DB stores strings.')

# =====================================================
# BUG 5: guest_cancel_booking only checks guest_user_id
# Third-party bookers (booked_by_user_id) cannot cancel
# =====================================================
cancel_start = None
for i, line in enumerate(routes_lines):
    if 'def guest_cancel_booking' in line:
        cancel_start = i
        break

if cancel_start is not None:
    cancel_snippet = '\n'.join(routes_lines[cancel_start:cancel_start+25])
    if 'booking.guest_user_id != current_user.id' in cancel_snippet and 'booked_by_user_id' not in cancel_snippet:
        issues.append(f'[BUG-5] routes.py ~line {cancel_start+1}: guest_cancel_booking only checks guest_user_id, ignores booked_by_user_id - third-party bookers cannot cancel their bookings')

# =====================================================
# BUG 6: my_accommodation.html conditional extends is invalid Jinja2
# `{% extends %}` must be the first statement, not inside an if block
# =====================================================
if '{% if request.args.get' in tmpl_content and '{% extends' in tmpl_content:
    issues.append('[BUG-6] my_accommodation.html: Jinja2 `{% extends %}` inside `{% if %}` block is INVALID - this will cause a TemplateError at runtime. Need separate templates or different approach.')

# =====================================================
# BUG 7: cancel route sends JSON request but expects form data
# The cancel endpoint returns flash+redirect, but my_accommodation.html
# calls it via fetch() expecting JSON response
# =====================================================
if 'fetch(' in tmpl_content and '/cancel' in tmpl_content:
    # Check if cancel route returns JSON
    cancel_route_content = ''
    in_cancel = False
    for line in routes_lines:
        if 'def guest_cancel_booking' in line:
            in_cancel = True
        if in_cancel:
            cancel_route_content += line + '\n'
            if 'return redirect' in line or 'return jsonify' in line:
                if 'return redirect' in line:
                    break

    if 'jsonify' not in cancel_route_content and 'return redirect' in cancel_route_content:
        issues.append('[BUG-7] my_accommodation.html: cancelBooking() calls cancel endpoint via fetch() expecting JSON, but endpoint returns redirect/flash - will fail silently')

# =====================================================
# BUG 8: group booking - 'group_booking_id' and 'room_number' variables
# only defined in elif booking_type == 'group' block but used outside it
# =====================================================
checkout_route_start = None
for i, line in enumerate(routes_lines):
    if 'def guest_checkout' in line:
        checkout_route_start = i
        break

if checkout_route_start is not None:
    checkout_snippet = '\n'.join(routes_lines[checkout_route_start:checkout_route_start+100])
    if 'room_number < total_rooms' in checkout_snippet:
        # Check if room_number can be undefined when booking_type != 'group'
        issues.append('[BUG-8] routes.py guest_checkout: variables `room_number`, `total_rooms`, `group_booking_id` used in notification block but only defined inside `elif booking_type == group` - will NameError for self/third_party bookings')

# =====================================================
# BUG 9: Event assigned hotel stay missing 'booked_by_name' key
# Template references stay.booked_by_name in event_assigned block
# =====================================================
if "'booked_by': f\"Event Organizer" in routes_content and "'booked_by_name'" not in routes_content.split("event_assigned_hotel")[1].split("event_assigned_community")[0]:
    issues.append("[BUG-9] routes.py: event_assigned_hotel stay dict has 'booked_by' key but template references 'booked_by_name' - KeyError or None display")

# =====================================================
# BUG 10: get_bookings_by_context uses enum value for filter_by
# filter_by(context_type=enum) won't match string values in DB
# =====================================================
if 'filter_by(\n            context_type=context_type\n        )' in svc_content or 'filter_by(\n                context_type=context_type' in svc_content:
    issues.append('[BUG-10] booking_service.py get_bookings_by_context: filters by enum object after conversion, but DB stores strings - should use context_type.value')


print("=" * 60)
print("ACCOMMODATION MODULE BUG REPORT")
print("=" * 60)
if issues:
    for issue in issues:
        print(issue)
else:
    print("No bugs found!")

bug_count = len([x for x in issues if x.startswith('[BUG')])
print(f"\nTotal bugs found: {bug_count}")
