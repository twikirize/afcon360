"""Source contract for the Socket.IO Redis message-queue gate.

``socketio.redis_manager.RedisManager.initialize()`` refuses to start unless
``socket.socket`` is monkey-patched when the async mode is gevent/eventlet.
AFCON360 never monkey-patches, so handing it a queue under the gevent dev
server rejects every ``/socket.io/`` connect (HTTP 401) and kills the
production console stream.

These tests pin the gate in ``app/__init__.py`` without booting the app.
"""

import importlib

from app import _redis_queue_allowed, _socketio_async_mode

GREEN_MODES = ("eventlet", "gevent_uwsgi", "gevent")


def _engineio_detected_mode():
    """The mode engineio.base_server would resolve, computed independently."""
    for mode in ("eventlet", "gevent_uwsgi", "gevent", "threading"):
        try:
            importlib.import_module("engineio.async_drivers." + mode)
        except ImportError:
            continue
        return mode
    raise AssertionError("no engineio async driver importable")  # pragma: no cover


def test_async_mode_detection_mirrors_engineio():
    assert _socketio_async_mode() == _engineio_detected_mode()


def test_unpatched_green_mode_blocks_the_queue(monkeypatch):
    monkeypatch.setattr("gevent.monkey.is_module_patched", lambda name: False)
    for mode in GREEN_MODES:
        assert _redis_queue_allowed(mode) is False


def test_patched_green_mode_allows_the_queue(monkeypatch):
    monkeypatch.setattr("gevent.monkey.is_module_patched", lambda name: True)
    assert _redis_queue_allowed("gevent") is True
    assert _redis_queue_allowed("gevent_uwsgi") is True


def test_eventlet_without_eventlet_installed_blocks_the_queue():
    try:
        import eventlet.patcher  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        assert _redis_queue_allowed("eventlet") is False
    else:  # pragma: no cover - eventlet is not a project dependency
        assert isinstance(_redis_queue_allowed("eventlet"), bool)


def test_threading_mode_allows_the_queue():
    assert _redis_queue_allowed("threading") is True


def test_default_call_uses_detected_mode(monkeypatch):
    monkeypatch.setattr("gevent.monkey.is_module_patched", lambda name: False)
    mode = _socketio_async_mode()
    assert _redis_queue_allowed() is (mode not in GREEN_MODES)
