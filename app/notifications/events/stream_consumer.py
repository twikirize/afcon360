"""
app/notifications/events/stream_consumer.py

Standalone Redis Streams consumer process. Replaces the Celery-beat-driven
``events.consume`` task.

Why a process, not a task
-------------------------
Stream consumption is a long-poll pattern. Celery beat is a scheduler
(fire, return, done). Running a long-poll loop inside beat:

  * has no backpressure — beat enqueues on cadence regardless of backlog
  * shares a worker pool with critical dispatch tasks (transport.*)
  * wastes 93% of each cycle when block_ms=1000 and cadence=15s
  * hits the starvation class we saw when a single invocation runs long

Running it as its own process:

  * scales horizontally by adding processes (consumer group fan-out)
  * is isolated from critical tasks at the OS level
  * gets full throughput from Redis (one loop, not 1s slices every 15s)
  * is signal-safe on Windows AND Linux (Ctrl+C / SIGTERM both handled)

Usage
-----
    python -m app.notifications.events.stream_consumer \
        --group afcon360-consumers \
        --consumer dev-1

Operational guarantees
----------------------
* ``XREADGROUP`` with ``BLOCK`` bounded (default 5000 ms).
* ``XAUTOCLAIM`` every idle cycle — orphaned PEL entries from a dead
  consumer are reclaimed automatically.
* Heartbeat log emitted every ``HEARTBEAT_EVERY`` iterations AND every
  ``HEARTBEAT_IDLE_SECONDS`` of consecutive empty reads, whichever first.
* Graceful shutdown on SIGINT/SIGTERM: the current message completes,
  then the loop stops BEFORE processing the next unprocessed message.
  Remaining messages stay unacked and will be reclaimed on next start.
* Never ack a message whose consumers returned ``retry``; the message
  stays in the PEL and will be reclaimed.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import sys
import time
from threading import Event as ThreadEvent
from typing import Optional


logger = logging.getLogger("events.stream_consumer")

DEFAULT_BLOCK_MS = 5000
DEFAULT_COUNT = 128
DEFAULT_MIN_IDLE_MS = 300_000  # reclaim after 5 minutes of consumer silence
DEFAULT_HEARTBEAT_ITERATIONS = 100
DEFAULT_HEARTBEAT_IDLE_SECONDS = 60
RECONNECT_BACKOFF_SECONDS = (1, 2, 5, 10, 30)


def _log_heartbeat(group: str, consumer: str, iterations: int,
                   processed: int, retried: int, reclaimed: int) -> None:
    """Machine-readable line so log aggregation can alert on absence."""
    logger.info(
        "[heartbeat] stream_consumer group=%s consumer=%s iterations=%d "
        "processed=%d retried=%d reclaimed=%d",
        group, consumer, iterations, processed, retried, reclaimed,
    )


def _check_redis_version(client) -> None:
    """Gate on the deployment baseline, not a general API claim.

    XAUTOCLAIM itself is available since Redis 6.2. Redis 7 added PEL
    cleanup of deleted/trimmed entries in the XAUTOCLAIM reply. The
    deployment baseline for AFCON360 is Redis 7 (matches prod); this
    function refuses to start on anything older so dev does not
    silently diverge.
    """
    try:
        info = client.info("server")
        version = str(info.get("redis_version", "0.0.0"))
    except Exception as exc:
        raise SystemExit(f"stream_consumer: cannot read Redis version: {exc}")
    major = int(version.split(".", 1)[0])
    if major < 7:
        raise SystemExit(
            f"stream_consumer: deployment baseline is Redis >= 7 "
            f"(running {version}). Match prod or update the baseline."
        )


def _dispatch_batch(registry, bus, group, stream, messages, stop) -> tuple:
    """Run each message through every registered consumer. Ack only on
    success; leave retries unacked so XAUTOCLAIM redelivers them.

    On shutdown: stop before processing the next unprocessed message;
    remaining messages stay unacked and are reclaimed on next start.
    """
    processed = retried = 0
    for message_id, envelope in messages:
        if stop.is_set():
            break
        try:
            result = registry.dispatch(envelope)
            statuses = {r.get("status") for r in result.get("results", [])}
            if "retry" in statuses or "error" in statuses:
                retried += 1
                continue
            bus.ack(group, message_id, stream)
            processed += 1
        except Exception as exc:
            logger.error(
                "stream_consumer: dispatch failed for %s: %s",
                message_id, exc, exc_info=True,
            )
            try:
                from app.extensions import db
                db.session.rollback()
            except Exception:
                pass
    return processed, retried


def run(group: str, consumer: str, block_ms: int, count: int) -> int:
    from app import create_app
    from app.extensions import db
    from app.notifications.events.bus import FIREHOSE_STREAM, event_bus
    from app.notifications.events.consumers import consumer_registry

    app = create_app()
    with app.app_context():
        client = event_bus.client
        if client is None:
            logger.error("stream_consumer: Redis not reachable at startup")
            return 2
        _check_redis_version(client)

        stop = ThreadEvent()

        def _signal_handler(signum, _frame):
            logger.warning(
                "stream_consumer: received signal %s, stopping before next "
                "message", signum,
            )
            stop.set()

        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

        event_bus.ensure_group(FIREHOSE_STREAM, group)

        iterations = 0
        total_processed = 0
        total_retried = 0
        total_reclaimed = 0
        idle_since: Optional[float] = None
        backoff_idx = 0

        logger.info(
            "stream_consumer: started group=%s consumer=%s stream=%s "
            "block_ms=%d count=%d",
            group, consumer, FIREHOSE_STREAM, block_ms, count,
        )

        while not stop.is_set():
            iterations += 1
            try:
                reclaimed = event_bus.claim_stale(
                    group, consumer, FIREHOSE_STREAM,
                    min_idle_ms=DEFAULT_MIN_IDLE_MS, count=count,
                )
                if reclaimed:
                    total_reclaimed += len(reclaimed)
                    _dispatch_batch(
                        consumer_registry, event_bus, group,
                        FIREHOSE_STREAM, reclaimed, stop,
                    )
                    idle_since = None

                messages = event_bus.read(
                    group, consumer, FIREHOSE_STREAM,
                    count=count, block_ms=block_ms,
                )
                if messages:
                    idle_since = None
                    processed, retried = _dispatch_batch(
                        consumer_registry, event_bus, group,
                        FIREHOSE_STREAM, messages, stop,
                    )
                    total_processed += processed
                    total_retried += retried
                else:
                    idle_since = idle_since or time.monotonic()

                idle_for = (
                    time.monotonic() - idle_since if idle_since else 0.0
                )
                if (iterations % DEFAULT_HEARTBEAT_ITERATIONS == 0
                        or idle_for >= DEFAULT_HEARTBEAT_IDLE_SECONDS):
                    _log_heartbeat(
                        group, consumer, iterations,
                        total_processed, total_retried, total_reclaimed,
                    )

                backoff_idx = 0

            except Exception as exc:
                logger.error(
                    "stream_consumer: iteration failed: %s", exc, exc_info=True,
                )
                try:
                    db.session.rollback()
                except Exception:
                    pass
                wait = RECONNECT_BACKOFF_SECONDS[
                    min(backoff_idx, len(RECONNECT_BACKOFF_SECONDS) - 1)
                ]
                backoff_idx += 1
                logger.warning(
                    "stream_consumer: backing off %ds before retry", wait,
                )
                if stop.wait(timeout=wait):
                    break

        logger.info(
            "stream_consumer: stopped cleanly (signal) iterations=%d "
            "processed=%d retried=%d reclaimed=%d",
            iterations, total_processed, total_retried, total_reclaimed,
        )
        return 0


def _cli() -> int:
    p = argparse.ArgumentParser(
        prog="python -m app.notifications.events.stream_consumer"
    )
    p.add_argument("--group", default="afcon360-consumers")
    p.add_argument(
        "--consumer",
        default=f"{socket.gethostname()}-{os.getpid()}",
    )
    p.add_argument("--block-ms", type=int, default=DEFAULT_BLOCK_MS)
    p.add_argument("--count", type=int, default=DEFAULT_COUNT)
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    return run(args.group, args.consumer, args.block_ms, args.count)


if __name__ == "__main__":
    sys.exit(_cli())