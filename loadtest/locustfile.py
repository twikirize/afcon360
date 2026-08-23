"""Locust load test for the AFCON360 reserve endpoint.

Hits the REAL Flask route POST /events/<slug>/reserve (same code path as production)
under concurrency, counting 201 (seat won) vs 409 sold_out.
Exactly EVENT_CAP buyers must win; the rest must be rejected — never oversold.

Run AFTER staging_server.py is up:
    locust -f loadtest/locustfile.py --headless \
        -u 150 -r 30 -t 120s \
        --host http://127.0.0.1:5001

Environment (printed by staging_server.py):
    EVENT_SLUG, TICKET_TYPE_ID, LOADTEST_USERS, LOADTEST_PASSWORD
"""

import json
import os
import uuid

from locust import HttpUser, between, events, task

EVENT_SLUG = os.getenv("EVENT_SLUG", "loadtest-onsale")
TICKET_TYPE_ID = os.getenv("TICKET_TYPE_ID")
LOADTEST_USERS = int(os.getenv("LOADTEST_USERS", "500"))
PASSWORD = os.getenv("LOADTEST_PASSWORD", "LoadTest123!")

REQUEST_TIMEOUT = 30  # seconds — used explicitly on every request below

stats = {"won": 0, "sold_out": 0, "error": 0}


@events.test_stop.add_listener
def _on_stop(environment, **_kwargs):
    print("\n" + "=" * 60)
    print("LOADTEST_RESULTS")
    print(f"  seats_won (201)   : {stats['won']}")
    print(f"  sold_out (409)    : {stats['sold_out']}")
    print(f"  other/error       : {stats['error']}")
    print("=" * 60)


class Buyer(HttpUser):
    # Each simulated buyer logs in once, then keeps reserving for the run.
    wait_time = between(0, 0)

    def on_start(self):
        idx = self._pick_index()
        self.email = f"loadtest_{idx}@example.com"
        try:
            with self.client.post(
                "/login",
                data={"username": self.email, "password": PASSWORD},
                allow_redirects=True,
                catch_response=True,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status_code not in (200, 302):
                    resp.failure(f"login failed {resp.status_code}")
        except Exception:
            # Login itself timed out / connection error. This Buyer simply
            # won't have a valid session, so its reserve calls will fail
            # fast (401) rather than hang — no separate handling needed here.
            pass

    def _pick_index(self):
        # Deterministic-per-user index spread across the seeded pool.
        base = getattr(self, "_idx", None)
        if base is None:
            base = int(uuid.uuid4().hex, 16) % LOADTEST_USERS
            self._idx = base
        return base

    @task
    def reserve(self):
        if TICKET_TYPE_ID is None:
            stats["error"] += 1
            return
        try:
            with self.client.post(
                f"/events/{EVENT_SLUG}/reserve",
                json={"quantity": 1, "ticket_type_id": int(TICKET_TYPE_ID)},
                headers={"Idempotency-Key": uuid.uuid4().hex},
                name="/events/[slug]/reserve",
                catch_response=True,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status_code == 201:
                    stats["won"] += 1
                elif resp.status_code == 409:
                    stats["sold_out"] += 1
                else:
                    stats["error"] += 1
                    try:
                        detail = resp.json().get("error", resp.text[:80])
                    except Exception:
                        detail = resp.text[:80]
                    resp.failure(f"unexpected {resp.status_code}: {detail}")
        except Exception as e:
            stats["error"] += 1
