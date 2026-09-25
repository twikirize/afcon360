"""
Fix 2.2 - directions circuit breaker tests.

Contract: docs/transport/fixes/Fix-2.2-contract.md
(all six decisions RESOLVED - 2026-09-23).

Obligations T1-T11 (contract section "Test obligations").
File-local fixtures only; tests/conftest.py is not modified.
"""

import math
import threading
import time

import pytest
import requests

from app.transport.services import external_platforms as ep
from app.transport.services.external_platforms import (
    CIRCUIT_RECOVERY_TIMEOUT,
    CircuitOpenError,
    ExternalPlatformsService,
)
from app.utils.exceptions import ValidationError

ORIGIN = {"latitude": -1.2921, "longitude": 36.8219}
DESTINATION = {"latitude": -1.3032, "longitude": 36.8606}

GOOGLE_FAILURES_KEY = "transport:circuit:google:directions:failures"
GOOGLE_STATE_KEY = "transport:circuit:google:directions:state"
MAPBOX_FAILURES_KEY = "transport:circuit:mapbox:directions:failures"
MAPBOX_STATE_KEY = "transport:circuit:mapbox:directions:state"

GOOGLE_OK_PAYLOAD = {
    "status": "OK",
    "routes": [
        {
            "overview_polyline": {"points": "abcDE"},
            "legs": [
                {
                    "distance": {"value": 1234, "text": "1.2 km"},
                    "duration": {"value": 300, "text": "5 mins"},
                    "steps": [
                        {
                            "html_instructions": "Head north",
                            "distance": {"text": "1.2 km"},
                            "duration": {"text": "5 mins"},
                        }
                    ],
                }
            ],
        }
    ],
}

MAPBOX_OK_PAYLOAD = {
    "code": "Ok",
    "routes": [
        {
            "distance": 1234.0,
            "duration": 300.0,
            "geometry": "abc~def",
        }
    ],
}


# ===================================================================
# Doubles
# ===================================================================

class Clock:
    """Injectable clock for TTL control."""

    def __init__(self):
        self.now = time.time()

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class FakePipeline:
    def __init__(self, client):
        self._client = client
        self._ops = []

    def get(self, key):
        self._ops.append(("get", (key,), {}))
        return self

    def incr(self, key):
        self._ops.append(("incr", (key,), {}))
        return self

    def expire(self, key, ttl):
        self._ops.append(("expire", (key, ttl), {}))
        return self

    def execute(self):
        results = []
        for name, args, kwargs in self._ops:
            results.append(getattr(self._client, name)(*args, **kwargs))
        self._ops = []
        return results


class FakeRedis:
    """Redis double with TTL semantics, mirroring decode_responses=False:

    - GET returns bytes
    - INCR returns int and keeps any existing TTL
    - SET stores encoded str
    """

    def __init__(self, clock):
        self.store = {}  # key -> [value_bytes, expires_at | None]
        self._clock = clock
        self._lock = threading.Lock()
        # Test-only rendezvous: when armed with a threading.Barrier, every
        # delete() waits there first. Lets a concurrency test force two
        # workers to reach the recovery claim together. None in all
        # sequential tests.
        self.delete_barrier = None

    def _alive(self, key):
        entry = self.store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at is not None and self._clock() >= expires_at:
            del self.store[key]
            return None
        return value

    def get(self, key):
        value = self._alive(key)
        if value is None:
            return None
        if isinstance(value, str):
            return value.encode("utf-8")
        return value

    def set(self, key, value, ex=None):
        if isinstance(value, str):
            value = value.encode("utf-8")
        self.store[key] = [value, (self._clock() + ex) if ex else None]
        return True

    def incr(self, key):
        value = self._alive(key)
        if value is None:
            current = 0
            expires_at = None
        else:
            if isinstance(value, (bytes, bytearray)):
                value = value.decode("utf-8")
            current = int(value)
            expires_at = self.store[key][1]
        current += 1
        self.store[key] = [str(current).encode("utf-8"), expires_at]
        return current

    def expire(self, key, ttl):
        entry = self.store.get(key)
        if entry is None:
            return False
        entry[1] = self._clock() + ttl
        return True

    def delete(self, key):
        barrier = self.delete_barrier
        if barrier is not None:
            barrier.wait()
        # dict.pop is atomic under the GIL, but the lock models Redis'
        # single-command DEL atomicity explicitly for threaded tests.
        with self._lock:
            return 1 if self.store.pop(key, None) is not None else 0

    def pipeline(self):
        return FakePipeline(self)


class BrokenRedis:
    """Redis double that raises on every command (unconfigured LazyRedis)."""

    def _boom(self, *args, **kwargs):
        raise RuntimeError("Redis URL not configured. Call configure() first.")

    pipeline = _boom
    get = _boom
    set = _boom
    incr = _boom
    delete = _boom
    expire = _boom


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} Server Error")

    def json(self):
        return self._payload


class ProviderHttp:
    """Spy/replacement for external_platforms.requests.get.

    respond(None) makes any HTTP attempt raise AssertionError loudly,
    which the circuit classifies as LOCAL_DEFECT and lets escape - so a
    test that expects zero HTTP fails hard if HTTP happens.
    """

    def __init__(self):
        self.calls = []
        self._default = None

    def respond(self, item):
        self._default = item

    def __call__(self, url, params=None, timeout=None, **kwargs):
        self.calls.append({"url": url, "timeout": timeout})
        item = self._default
        if item is None:
            raise AssertionError("Unexpected provider HTTP call")
        if isinstance(item, Exception):
            raise item
        if isinstance(item, FakeResponse):
            return item
        return FakeResponse(item)  # raw payload dict


# ===================================================================
# File-local fixtures
# ===================================================================

@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def fake_redis(clock):
    return FakeRedis(clock=clock)


@pytest.fixture
def circuit(monkeypatch, app, fake_redis, clock):
    """Wire FakeRedis into external_platforms; expose key inspection."""
    monkeypatch.setattr(ep, "redis_client", fake_redis)

    class Handle:
        def __init__(self, client, clock):
            self.client = client
            self.store = client.store
            self.clock = clock

        def failures(self, provider):
            raw = fake_redis.get(
                f"transport:circuit:{provider}:directions:failures"
            )
            if raw is None:
                return 0
            return int(raw.decode("utf-8"))

        def state(self, provider):
            return fake_redis.get(
                f"transport:circuit:{provider}:directions:state"
            )

    return Handle(fake_redis, clock)


@pytest.fixture
def google_key(monkeypatch, app):
    monkeypatch.setitem(app.config, "GOOGLE_MAPS_API_KEY", "test-google-key")


@pytest.fixture
def mapbox_token(monkeypatch, app):
    monkeypatch.setitem(app.config, "MAPBOX_ACCESS_TOKEN", "test-mapbox-token")


@pytest.fixture
def provider_http(monkeypatch):
    http = ProviderHttp()
    monkeypatch.setattr(ep.requests, "get", http)
    return http


@pytest.fixture
def log_spy(monkeypatch):
    """File-local spy on the module logger's emission methods.

    Observes exactly what production code passes to logger.info/
    logger.warning/logger.error. monkeypatch restores the original
    methods on teardown; no propagation or logger config is changed.
    """
    captured = {"info": [], "warning": [], "error": []}

    def _install(level):
        def spy(msg, *args, **kwargs):
            captured[level].append(msg % args if args else str(msg))

        monkeypatch.setattr(ep.logger, level, spy)

    for level in captured:
        _install(level)
    return captured


@pytest.fixture
def metric_spy(monkeypatch):
    """Direct spy on the module-level record_metric reference."""
    calls = []

    def spy(name, value, tags=None):
        calls.append((name, value))

    monkeypatch.setattr(ep, "record_metric", spy)
    return calls


def _directions(provider="google"):
    return ExternalPlatformsService.get_directions(
        ORIGIN, DESTINATION, provider=provider
    )


def _open_google_circuit(http, times=5):
    http.respond(requests.exceptions.Timeout("connect timeout"))
    for _ in range(times):
        _directions("google")


# ===================================================================
# T1 - failures actually increment; provider A opens alone
# ===================================================================

def test_five_provider_failures_open_circuit_for_that_provider_only(
        app, circuit, google_key, provider_http):
    provider_http.respond(requests.exceptions.Timeout("connect timeout"))

    for i in range(1, 5):
        result = _directions("google")
        assert result["provider"] == "mock"
        assert circuit.failures("google") == i
        assert circuit.state("google") is None

    result = _directions("google")
    assert result["provider"] == "mock"
    assert circuit.failures("google") == 5
    assert circuit.state("google") == b"open"
    assert len(provider_http.calls) == 5

    # D-RedisKeys: exactly the two contract keys, no third key.
    assert set(circuit.store.keys()) == {GOOGLE_FAILURES_KEY, GOOGLE_STATE_KEY}
    # Namespace isolation: provider B untouched.
    assert circuit.failures("mapbox") == 0
    assert circuit.state("mapbox") is None
    assert MAPBOX_FAILURES_KEY not in circuit.store
    assert MAPBOX_STATE_KEY not in circuit.store


def test_provider_declared_error_counts_toward_circuit(
        app, circuit, google_key, provider_http):
    """D-InvalidPayload, first half: provider-declared status = PROVIDER_FAILURE."""
    provider_http.respond(FakeResponse({"status": "REQUEST_DENIED"}))

    result = _directions("google")

    assert result["provider"] == "mock"
    assert circuit.failures("google") == 1
    assert circuit.state("google") is None
    assert len(provider_http.calls) == 1


# ===================================================================
# T2 - OPEN means zero HTTP; output == _mock_directions
# ===================================================================

def test_open_circuit_short_circuits_without_http_and_returns_mock_shape(
        app, circuit, google_key, provider_http):
    _open_google_circuit(provider_http)
    assert circuit.state("google") == b"open"

    provider_http.calls.clear()
    provider_http.respond(None)  # any HTTP attempt now fails the test loudly

    result = _directions("google")

    assert result == ExternalPlatformsService._mock_directions(
        ORIGIN, DESTINATION
    )
    assert provider_http.calls == []
    assert circuit.failures("google") == 5
    assert circuit.state("google") == b"open"


# ===================================================================
# T3 - state TTL expiry resumes CLOSED (unconditional)
# ===================================================================

def test_state_ttl_expiry_resumes_closed_unconditionally(
        app, circuit, google_key, provider_http):
    _open_google_circuit(provider_http)
    assert circuit.state("google") == b"open"

    # state TTL (30s) expires; failures TTL (60s) still alive.
    clock = circuit.clock
    clock.advance(CIRCUIT_RECOVERY_TIMEOUT + 1)

    provider_http.respond(FakeResponse(GOOGLE_OK_PAYLOAD))
    result = _directions("google")

    assert result["distance_meters"] == 1234  # real provider payload, not mock
    assert circuit.state("google") is None    # CLOSED again
    assert circuit.failures("google") == 0    # recovery cleared the window
    assert len(provider_http.calls) == 6      # HTTP resumed


# ===================================================================
# T4 - LOCAL_DEFECT escapes; uncounted; no mock
# ===================================================================

@pytest.mark.parametrize("payload,exc_type", [
    ({"status": "OK"}, KeyError),
    ({"status": "OK", "routes": []}, IndexError),
    ({"status": "OK", "routes": None}, TypeError),
])
def test_parse_local_defects_escape_uncounted(
        app, circuit, google_key, provider_http, payload, exc_type):
    provider_http.respond(FakeResponse(payload))

    with pytest.raises(exc_type):
        _directions("google")

    assert circuit.failures("google") == 0
    assert circuit.state("google") is None
    assert len(provider_http.calls) == 1


def test_unsupported_provider_validation_escapes_uncounted(
        app, circuit, google_key, provider_http):
    with pytest.raises(ValidationError):
        _directions("bing")

    assert circuit.failures("google") == 0
    assert circuit.state("google") is None
    assert provider_http.calls == []


# ===================================================================
# T5 - missing key: mock, no HTTP, not counted, no false reset
# ===================================================================

def test_missing_key_neither_counts_nor_resets_failure_sequence(
        app, circuit, google_key, provider_http, monkeypatch):
    provider_http.respond(requests.exceptions.Timeout("connect timeout"))
    for _ in range(4):
        _directions("google")
    assert circuit.failures("google") == 4
    calls_after_four = len(provider_http.calls)

    # CONFIGURATION_UNAVAILABLE: no key -> mock before any decorator/HTTP.
    monkeypatch.setitem(app.config, "GOOGLE_MAPS_API_KEY", None)
    result = _directions("google")

    assert result["provider"] == "mock"
    assert len(provider_http.calls) == calls_after_four  # no HTTP
    assert circuit.failures("google") == 4              # not counted, not reset

    # Restore key: the next genuine failure is the true 5th and must open.
    monkeypatch.setitem(app.config, "GOOGLE_MAPS_API_KEY", "test-google-key")
    result = _directions("google")

    assert result["provider"] == "mock"
    assert circuit.failures("google") == 5
    assert circuit.state("google") == b"open"


# ===================================================================
# T6 - genuine provider success resets the sequence
# ===================================================================

def test_provider_success_resets_failure_sequence(
        app, circuit, google_key, provider_http):
    provider_http.respond(requests.exceptions.Timeout("connect timeout"))
    for _ in range(4):
        _directions("google")
    assert circuit.failures("google") == 4

    provider_http.respond(FakeResponse(GOOGLE_OK_PAYLOAD))
    result = _directions("google")
    assert result["distance_meters"] == 1234  # provider payload, not mock
    assert circuit.failures("google") == 0    # DEL failures on success

    # Sequence restarts: four more failures stay CLOSED...
    provider_http.respond(requests.exceptions.Timeout("connect timeout"))
    for _ in range(4):
        _directions("google")
    assert circuit.failures("google") == 4
    assert circuit.state("google") is None

    # ...the fifth post-success failure opens.
    _directions("google")
    assert circuit.failures("google") == 5
    assert circuit.state("google") == b"open"


# ===================================================================
# T7 - Redis unavailable: warn, fail open, call proceeds,
#      Redis failure never increments the circuit
# ===================================================================

def test_redis_unavailable_fails_open_and_never_increments(
        app, monkeypatch, google_key, provider_http, log_spy):
    monkeypatch.setattr(ep, "redis_client", BrokenRedis())

    provider_http.respond(requests.exceptions.Timeout("connect timeout"))
    result = _directions("google")
    assert result["provider"] == "mock"
    assert len(provider_http.calls) == 1  # provider call proceeded (fail open)

    provider_http.respond(FakeResponse(GOOGLE_OK_PAYLOAD))
    result = _directions("google")
    assert result["distance_meters"] == 1234
    assert len(provider_http.calls) == 2

    assert any("failing open" in message for message in log_spy["warning"])
    # The broken client stays installed; no FakeRedis exists in this test,
    # so no circuit key could have been written by the Redis outage itself.
    assert isinstance(ep.redis_client, BrokenRedis)


# ===================================================================
# T8 - provider A circuit does not affect provider B
# ===================================================================

def test_provider_circuits_are_isolated(
        app, circuit, google_key, mapbox_token, provider_http):
    _open_google_circuit(provider_http)
    assert circuit.state("google") == b"open"
    google_calls = len(provider_http.calls)

    # Google stays OPEN: no new HTTP for google.
    provider_http.respond(None)
    result = _directions("google")
    assert result["provider"] == "mock"
    assert len(provider_http.calls) == google_calls

    # Mapbox is unaffected: HTTP still goes out and succeeds.
    provider_http.respond(FakeResponse(MAPBOX_OK_PAYLOAD))
    result = _directions("mapbox")
    assert result["provider"] == "mapbox"
    assert result["distance_meters"] == 1234.0
    assert len(provider_http.calls) == google_calls + 1

    # State untouched across the boundary.
    assert circuit.failures("google") == 5
    assert circuit.state("google") == b"open"
    assert circuit.failures("mapbox") == 0
    assert circuit.state("mapbox") is None


# ===================================================================
# T9 - _mock_directions output shape unchanged
# ===================================================================

def test_mock_directions_shape_unchanged(app):
    result = ExternalPlatformsService._mock_directions(ORIGIN, DESTINATION)

    assert set(result.keys()) == {
        "success",
        "distance_meters",
        "distance_text",
        "duration_seconds",
        "duration_text",
        "polyline",
        "provider",
        "note",
    }
    assert result["success"] is True
    assert result["provider"] == "mock"
    assert result["polyline"] is None
    assert result["note"] == "Using mock directions data"

    lat_diff = abs(ORIGIN["latitude"] - DESTINATION["latitude"])
    lon_diff = abs(ORIGIN["longitude"] - DESTINATION["longitude"])
    distance_km = math.sqrt(lat_diff ** 2 + lon_diff ** 2) * 111
    distance_meters = distance_km * 1000
    duration_seconds = distance_km * 120
    assert result["distance_meters"] == pytest.approx(distance_meters)
    assert result["distance_text"] == f"{distance_km:.1f} km"
    assert result["duration_seconds"] == pytest.approx(duration_seconds)
    assert result["duration_text"] == f"{int(duration_seconds / 60)} mins"


# ===================================================================
# T10 - transition logging only at CLOSED->OPEN and OPEN->CLOSED
# ===================================================================

def test_transition_logging_only_at_transitions(
        app, circuit, google_key, provider_http, log_spy, metric_spy):
    provider_http.respond(requests.exceptions.Timeout("connect timeout"))

    # Requests 1-4: failures accrue, state absent, still CLOSED.
    # No transition message (incl. recovery: 4 failures is NOT recovery
    # evidence) and zero transition metrics on normal requests.
    for _ in range(4):
        _directions("google")
    assert not any("reason=threshold_reached" in m for m in log_spy["error"])
    assert not any("reason=recovery_expired" in m for m in log_spy["info"])
    assert metric_spy == []

    # Request 5: exactly one CLOSED->OPEN transition log + its metric.
    _directions("google")
    opened = [
        m for m in log_spy["error"] if "reason=threshold_reached" in m
    ]
    assert len(opened) == 1
    assert "provider=google" in opened[0]
    assert "operation=directions" in opened[0]
    assert "failure_count=5" in opened[0]
    assert metric_spy == [("circuit.open.google.directions", 5)]

    # Request 6 (already OPEN): no new transition log, no new metric.
    _directions("google")
    assert sum(
        "reason=threshold_reached" in m for m in log_spy["error"]
    ) == 1
    assert metric_spy == [("circuit.open.google.directions", 5)]
    assert not any("reason=recovery_expired" in m for m in log_spy["info"])

    # TTL expiry: first observing request logs OPEN->CLOSED exactly once.
    # Detection: state key absent + surviving failures key >= threshold.
    circuit.clock.advance(CIRCUIT_RECOVERY_TIMEOUT + 1)
    provider_http.respond(FakeResponse(GOOGLE_OK_PAYLOAD))
    _directions("google")
    recovered = [
        m for m in log_spy["info"] if "reason=recovery_expired" in m
    ]
    assert len(recovered) == 1
    assert "provider=google" in recovered[0]
    assert "operation=directions" in recovered[0]
    assert "failure_count=5" in recovered[0]
    # Contract (Fix-2.2-contract.md:260): OPEN->CLOSED is log-only;
    # the sole transition metric is the CLOSED->OPEN one (line 259).
    assert metric_spy == [("circuit.open.google.directions", 5)]

    # Subsequent request: no repeated recovery log, no new metrics.
    _directions("google")
    assert sum(
        "reason=recovery_expired" in m for m in log_spy["info"]
    ) == 1
    assert sum(
        "reason=threshold_reached" in m for m in log_spy["error"]
    ) == 1
    assert metric_spy == [("circuit.open.google.directions", 5)]


# ===================================================================
# T11 - semantic proof: mock success=True is never the
#       provider-success signal
# ===================================================================

def test_mock_success_flag_never_resets_circuit(
        app, circuit, google_key, provider_http):
    _open_google_circuit(provider_http)
    assert circuit.state("google") == b"open"
    assert circuit.failures("google") == 5

    provider_http.calls.clear()
    provider_http.respond(None)  # zero-HTTP enforcement

    result = _directions("google")

    # The fallback carries the compatibility flag...
    assert result["success"] is True
    assert result["provider"] == "mock"

    # ...but the circuit did NOT treat it as PROVIDER_SUCCESS:
    # state and failures are untouched by any mock return path.
    assert circuit.state("google") == b"open"
    assert circuit.failures("google") == 5
    assert provider_http.calls == []


# ===================================================================
# T12 - concurrent first-after-expiry: exactly one recovery transition
# (T10's concurrency dimension; authorized by the recovery gate §6)
# ===================================================================

def test_concurrent_first_after_expiry_single_recovery_log(
        app, circuit, google_key, provider_http, log_spy):
    provider_http.respond(requests.exceptions.Timeout("connect timeout"))
    for _ in range(5):
        _directions("google")
    assert circuit.failures("google") == 5
    assert circuit.state("google") == b"open"

    # Expire state (30s); failures (60s TTL) survive as recovery evidence.
    circuit.clock.advance(CIRCUIT_RECOVERY_TIMEOUT + 1)

    provider_http.calls.clear()
    provider_http.respond(FakeResponse(GOOGLE_OK_PAYLOAD))

    # Rendezvous inside FakeRedis.delete: delete() is reached only after a
    # worker has completed its state+failures read, so arming this barrier
    # forces both workers to reach the recovery claim together before
    # either completes it. Deterministic: no timing luck. The barrier is
    # cyclic (each worker deletes twice: claim + post-success reset), and
    # its timeout fails loudly instead of hanging on any path deviation.
    circuit.client.delete_barrier = threading.Barrier(2, timeout=15)

    results = []
    errors = []

    def observe():
        try:
            # Request contexts are thread-local; each worker pushes its own.
            with app.test_request_context():
                results.append(_directions("google"))
        except Exception as exc:
            errors.append(exc)

    workers = [threading.Thread(target=observe) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=60)

    assert errors == []
    assert all(not worker.is_alive() for worker in workers)

    # Exactly one worker claimed the recovery transition...
    recovered = [
        message for message in log_spy["info"]
        if "reason=recovery_expired" in message
    ]
    assert len(recovered) == 1
    assert "provider=google" in recovered[0]
    assert "operation=directions" in recovered[0]

    # ...while BOTH workers resumed normally (unconditional resume) and
    # reached the provider with real payloads.
    assert len(results) == 2
    assert all(result["distance_meters"] == 1234 for result in results)
    assert len(provider_http.calls) == 2

    # The claim consumed the evidence; the circuit is CLOSED and clean.
    assert circuit.state("google") is None
    assert circuit.failures("google") == 0
