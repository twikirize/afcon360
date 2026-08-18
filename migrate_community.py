filepath = 'app/events/routes_community_hosts.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

import re

# Add import if missing
if 'from app.events.permissions import _is_event_owner' not in content:
    content = content.replace('from flask_login import login_required, current_user', 'from flask_login import login_required, current_user\nfrom app.events.permissions import _is_event_owner')

# Replace event.organizer_id != current_user.id checks
# e.g., if not event or (event.organizer_id != current_user.id and not current_user.has_global_role('admin')):
# e.g., if event.organizer_id != current_user.id and not current_user.has_global_role('admin'):

pattern1 = r"if not event or \(event\.organizer_id != current_user\.id and not current_user\.has_global_role\('admin'\)\):"
replacement1 = r"if not event or not (_is_event_owner(current_user, event) or current_user.has_global_role('admin')):"
content = re.sub(pattern1, replacement1, content)

pattern2 = r"if event\.organizer_id != current_user\.id and not current_user\.has_global_role\('admin'\):"
replacement2 = r"if not (_is_event_owner(current_user, event) or current_user.has_global_role('admin')):"
content = re.sub(pattern2, replacement2, content)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated routes_community_hosts.py")
