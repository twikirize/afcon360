"""
Correlation / causation context propagation.

Enterprise requirement: "Show me everything that happened for transaction X."

A *correlation id* identifies one logical user journey (registration -> login ->
KYC -> payment -> booking -> confirmation email). Every event, notification and
delivery attempt produced anywhere in that journey carries the same
``correlation_id`` so the whole chain can be reconstructed from the ledger.

A *causation id* is narrower: it is the ``event_id`` of the event that directly
caused this one, giving a parent/child tree rather than a flat bag.

Implementation notes
--------------------
* Uses :class:`contextvars.ContextVar` so the value is correct under threads,
  greenlets and asyncio, and does not leak between concurrent requests the way
  a module-level global or ``flask.g`` alone would under a threaded worker.
* Falls back gracefully outside a request (Celery tasks, CLI scripts).
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional

# Header a client / upstream service may set to continue an existing trace.
CORRELATION_HEADER = 'X-AFCON360-Correlation-Id'
CAUSATION_HEADER = 'X-AFCON360-Causation-Id'

_correlation_id: ContextVar[Optional[str]] = ContextVar(
    'afcon360_correlation_id', default=None
)
_causation_id: ContextVar[Optional[str]] = ContextVar(
    'afcon360_causation_id', default=None
)


def new_correlation_id() -> str:
    """Generate a fresh correlation id."""
    return f"cor_{uuid.uuid4().hex}"


def new_event_id() -> str:
    """Generate a fresh event id."""
    return f"evt_{uuid.uuid4().hex}"


def get_correlation_id(create: bool = True) -> Optional[str]:
    """
    Return the current correlation id.

    When *create* is True (default) a new id is generated and stored if none is
    active, so callers can always attach one to an event.
    """
    cid = _correlation_id.get()
    if cid:
        return cid

    # Try to inherit from the active Flask request (set by the middleware).
    try:
        from flask import has_request_context, request

        if has_request_context():
            header = request.headers.get(CORRELATION_HEADER)
            if header:
                _correlation_id.set(header)
                return header
    except Exception:
        pass

    if not create:
        return None

    cid = new_correlation_id()
    _correlation_id.set(cid)
    return cid


def set_correlation_id(correlation_id: Optional[str]) -> None:
    """Bind *correlation_id* to the current execution context."""
    _correlation_id.set(correlation_id)


def get_causation_id() -> Optional[str]:
    """Return the id of the event currently being processed, if any."""
    return _causation_id.get()


def set_causation_id(causation_id: Optional[str]) -> None:
    """Bind the causing event id to the current execution context."""
    _causation_id.set(causation_id)


@contextmanager
def correlation_scope(
    correlation_id: Optional[str] = None,
    causation_id: Optional[str] = None,
):
    """
    Run a block under an explicit correlation/causation context.

    Used by the consumer runtime so that any event emitted while handling event
    ``E`` automatically inherits ``E.correlation_id`` and records
    ``causation_id = E.event_id``::

        with correlation_scope(evt.correlation_id, evt.event_id):
            handler(evt)   # anything emitted here is linked to evt
    """
    cid = correlation_id or new_correlation_id()
    corr_token = _correlation_id.set(cid)
    caus_token = _causation_id.set(causation_id)
    try:
        yield cid
    finally:
        _correlation_id.reset(corr_token)
        _causation_id.reset(caus_token)


def install_request_correlation(app) -> None:
    """
    Attach correlation-id propagation to a Flask app.

    * Inbound requests reuse ``X-AFCON360-Correlation-Id`` when supplied,
      otherwise a new id is minted.
    * The id is echoed back on the response so clients and load balancers can
      stitch traces together.
    """

    @app.before_request
    def _bind_correlation():  # pragma: no cover - trivial glue
        from flask import request

        incoming = request.headers.get(CORRELATION_HEADER)
        set_correlation_id(incoming or new_correlation_id())
        set_causation_id(request.headers.get(CAUSATION_HEADER))

    @app.after_request
    def _emit_correlation(response):  # pragma: no cover - trivial glue
        cid = get_correlation_id(create=False)
        if cid:
            response.headers[CORRELATION_HEADER] = cid
        return response
