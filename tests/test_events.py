import pytest
from app import create_app


@pytest.fixture(scope='module')
def app():
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture(scope='module')
def app_ctx(app):
    with app.app_context():
        yield


def test_get_event_not_found(app_ctx):
    from app.events.services import EventService
    result = EventService.get_event('this-slug-does-not-exist-xyz')
    assert result is None, f"Expected None for unknown slug, got: {result}"


def test_get_event_returns_expected_fields(app_ctx):
    from app.events.services import EventService
    result = EventService.get_event('nothing')  # real event in DB
    assert result is not None, "Expected event with slug 'nothing' to exist"

    # Fields that MUST be present
    assert 'id' in result,          "Missing 'id' (public_id)"
    assert 'slug' in result,        "Missing 'slug'"
    assert 'name' in result,        "Missing 'name'"

    # Fields that MUST NOT be present
    assert 'internal_id' not in result,    "internal_id must not be exposed"
    assert 'approved_by_id' not in result, "approved_by_id must not be exposed"

    # id must be a UUID string, not an integer
    assert isinstance(result['id'], str), "id must be a UUID string, not an int"
    assert len(result['id']) == 36,       "id must be a valid UUID (36 chars)"

    # website must never be empty string
    assert result.get('website') != '', "website should be None not empty string"

    print('\nAPI response fields:')
    for k, v in result.items():
        if k != 'ticket_types':
            print(f'  {k:<25}: {v}')
    print(f'  ticket_types: {len(result["ticket_types"])} type(s)')
