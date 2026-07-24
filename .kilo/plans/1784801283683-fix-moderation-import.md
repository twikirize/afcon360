# Fix Accommodation Startup ImportError

## Root cause
`app/accommodation/services/moderation_service.py:4` imports `AccommodationProperty` from `app.accommodation.models.property`, but no class with that name exists in that module. The model class is `Property` (`property.py:70`). This causes an `ImportError` at application startup, preventing the entire accommodation module from loading.

## Fix
Edit `app/accommodation/services/moderation_service.py`:
- Replace `from app.accommodation.models.property import AccommodationProperty` with `from app.accommodation.models.property import Property`
- Replace all references to `AccommodationProperty` in that file with `Property`

## Files changed
- `app/accommodation/services/moderation_service.py`

## Validation
1. Run `python -c "from app import create_app"` — should succeed without `ImportError`.
2. Run `flask run` — app should start and register the accommodation blueprint.

## Risks / Notes
- Single-line rename, no schema or behavior changes.
- No migration required.
- Ensure no other modules reference `AccommodationProperty` (pre-checked: none exist).
