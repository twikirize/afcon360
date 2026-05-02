import pytest
from types import SimpleNamespace
import contextlib


def test_process_webhook_events_dead_letter_triggers_alert(monkeypatch):
    """Simulate processing an event that fails enough times to become dead_letter and ensure alert is called."""
    # Import the task function
    from app.tasks.webhook_processor import process_webhook_events, MAX_ATTEMPTS

    # Create a dummy Flask app context manager
    class DummyApp:
        def app_context(self):
            @contextlib.contextmanager
            def _ctx():
                yield self
            return _ctx()

    # process_webhook_events imports create_app from the top-level `app` package
    monkeypatch.setattr('app.create_app', lambda: DummyApp())

    # Fake db with session commit/rollback
    fake_session = SimpleNamespace()
    fake_session.commit = lambda: None
    fake_session.rollback = lambda: None
    fake_db = SimpleNamespace()
    fake_db.session = fake_session
    # Provide simple placeholders for SQLAlchemy boolean/and/or helpers used by the code
    fake_db.or_ = lambda *args, **kwargs: None
    fake_db.and_ = lambda *args, **kwargs: None

    monkeypatch.setattr('app.extensions.db', fake_db)

    # Prepare a fake event that is already at retry_count = MAX_ATTEMPTS -1 and status 'failed'
    ev = SimpleNamespace()
    ev.id = 777
    ev.provider = 'flutterwave'
    ev.event_type = 'charge.completed'
    ev.status = 'failed'
    ev.retry_count = MAX_ATTEMPTS - 1
    ev.payload = {'data': {'txRef': 'abc123', 'status': 'successful', 'amount': 10, 'currency': 'USD'}}
    ev.signature = None
    ev.raw_body = None
    ev.next_retry_at = None
    ev.processed_at = None
    ev.last_error = ''

    # Fake WebhookEvent.query.filter(...).with_for_update(...).limit(...).all() to return [ev]
    class FakeFilter:
        def __init__(self, events):
            self._events = events
        def with_for_update(self, skip_locked=True):
            return self
        def limit(self, n):
            return self
        def all(self):
            return self._events

    class FakeQueryRoot:
        def __init__(self, events):
            self._events = events
        def filter(self, *args, **kwargs):
            return FakeFilter(self._events)

    fake_events = [ev]
    # Provide dummy column-like descriptors so expressions like
    # WebhookEvent.status == 'queued' do not raise during evaluation
    class DummyCol:
        def __eq__(self, other):
            return self
        def __lt__(self, other):
            return self
        def __le__(self, other):
            return self
        def __ge__(self, other):
            return self

    fake_WebhookEvent = SimpleNamespace()
    fake_WebhookEvent.status = DummyCol()
    fake_WebhookEvent.retry_count = DummyCol()
    fake_WebhookEvent.next_retry_at = DummyCol()
    fake_WebhookEvent.query = FakeQueryRoot(fake_events)

    # The task imports WebhookEvent from app.wallet.models.webhook_event at runtime
    monkeypatch.setattr('app.wallet.models.webhook_event.WebhookEvent', fake_WebhookEvent)

    # Ensure _process_single_event raises to trigger retry logic
    def fake_process_single(event, db):
        raise RuntimeError("simulated handler failure")

    monkeypatch.setattr('app.tasks.webhook_processor._process_single_event', fake_process_single)

    # Replace alert helper to capture call
    called = {'alerted': False}
    def fake_alert(event):
        called['alerted'] = True

    monkeypatch.setattr('app.tasks.webhook_processor._alert_owner_dead_letter', fake_alert)

    # Patch redis incr to avoid requiring real Redis
    import app.extensions as ext
    monkeypatch.setattr(ext.redis_client, 'incr', lambda k: None)

    # Run the task
    result = process_webhook_events()

    assert result['dead_lettered'] == 1
    assert called['alerted'] is True

