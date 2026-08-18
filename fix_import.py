filepath = 'app/events/services.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Add from app.identity.models.user import User if not present
if 'from app.identity.models.user import User' not in content:
    content = content.replace('from app.events.trust_service import EventTrustService, TrustLevel', 
                              'from app.events.trust_service import EventTrustService, TrustLevel\nfrom app.identity.models.user import User')

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
