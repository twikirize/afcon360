with open('app/__init__.py', 'rb') as f:
    content = f.read()

# Replace the transport models import
old = b'from app.event_accommodation import \\\r\n        models as event_accommodation_models  # Required for Alembic to detect event accommodation models\r\n    logger.info(\r\n        f"\xe2\x8f\xb1 lazy model imports (identity/profile/audit/roles/admin/event_accommodation) took {time.time() - _boot_t3:.2f}s")'

new = b'from app.event_accommodation import \\\r\n        models as event_accommodation_models  # Required for Alembic to detect event accommodation models\r\n    from app.transport import models as transport_models  # Required for Alembic to detect transport models\r\n    logger.info(\r\n        f"\xe2\x8f\xb1 lazy model imports (identity/profile/audit/roles/admin/event_accommodation/transport) took {time.time() - _boot_t3:.2f}s")'

if old in content:
    content = content.replace(old, new)
    with open('app/__init__.py', 'wb') as f:
        f.write(content)
    print('Fixed!')
else:
    print('Old text not found!')