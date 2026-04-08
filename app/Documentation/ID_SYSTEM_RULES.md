# Dual ID System Rules (READ THIS BEFORE CODING)

## The Golden Rule
INTERNAL OPERATIONS → use .id (BIGINT)
EXTERNAL OPERATIONS → use .user_id (UUID)

NEVER MIX THEM!

## Quick Reference

| What you're doing | Use this | Example |
|-----------------|----------|---------|
| Foreign key | `.id` | `log.owner_id = current_user.id` |
| Database query | `.id` | `User.query.get(user_id)` |
| Session storage | `.id` | `session['user_internal_id'] = user.id` |
| URL generation | `.user_id` | `url_for('profile', user_id=user.user_id)` |
| API response | `.user_id` | `{'id': user.user_id, ...}` |
| Flask-Login | `.user_id` | `User.get_id() returns user.user_id` |
| HTML data attribute | `.user_id` | `data-user-id="{{ user.user_id }}"` |
| JavaScript | `.user_id` | `fetch('/api/user/' + userId)` |

## Common Mistakes (NEVER DO THESE)

```python
# ❌ WRONG - Using UUID for foreign key
audit_log.owner_id = current_user.user_id

# ❌ WRONG - Using internal ID in URL
url_for('profile', user_id=user.id)

# ❌ WRONG - Direct session access
user_id = session['user_id']

# ❌ WRONG - Foreign key to user_id
owner_id = db.ForeignKey('users.user_id')

# ✅ CORRECT - Foreign key to id
owner_id = db.ForeignKey('users.id')
```

## Helpers to Use
```python
from app.utils.id_helpers import get_current_internal_id, get_current_public_id

# For database operations
internal_id = get_current_internal_id()

# For URLs/APIs
public_id = get_current_public_id()

# For routes
@route_uses_public_id
def profile(user_id):  # user_id here is UUID
    user = User.get_by_public_id(user_id)
```

## Pre-commit Hook
We have a pre-commit hook that blocks commits with ID violations.
Run `python scripts/check_id_usage.py` to check manually.

## If You See This Error
`ID System Violation: Foreign key assigned non-integer`
You're using `.user_id` (UUID) where `.id` (BIGINT) is required.

## Testing Your Changes
Always test both paths:
1. Login with a user
2. Create an audit log (checks FK)
3. Visit a user profile URL (checks UUID)
