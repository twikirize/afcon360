#!/usr/bin/env python3
"""Unit checks for the temporary root entry route used by Android qualification."""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("verify-user-dev-client-delivery.py")
SPEC = importlib.util.spec_from_file_location("afcon360_user_dev_delivery", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Could not load delivery verifier: {SCRIPT}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def reset_route_state() -> None:
    MODULE.ROUTE_CREATED = False
    MODULE.ROUTE_BACKUP = None
    MODULE.ROUTE_EXISTED = False


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="afcon360-fast-refresh-test-") as directory:
        route = Path(directory) / "app" / "index.tsx"
        route.parent.mkdir(parents=True)
        original = b"// developer-owned root route\nexport default function Index() { return null; }\n"
        route.write_bytes(original)

        MODULE.ROUTE = route
        reset_route_state()
        MODULE.write_qa_route("AFCON360_METRO_FAST_REFRESH_BEFORE")
        assert "AFCON360_METRO_FAST_REFRESH_BEFORE" in route.read_text(encoding="utf-8")
        print("PASS qualification temporarily replaces the app root route")

        MODULE.write_qa_route("AFCON360_METRO_FAST_REFRESH_AFTER")
        second = route.read_text(encoding="utf-8")
        assert "AFCON360_METRO_FAST_REFRESH_AFTER" in second
        assert "AFCON360_METRO_FAST_REFRESH_BEFORE" not in second
        print("PASS qualification edits its root route to exercise Fast Refresh")

        MODULE.restore_qa_route()
        assert route.read_bytes() == original
        assert not MODULE.ROUTE_CREATED
        print("PASS original root route is restored byte-for-byte")

        route.unlink()
        reset_route_state()
        MODULE.write_qa_route("TEMPORARY_ROOT_ROUTE")
        assert route.exists()
        MODULE.restore_qa_route()
        assert not route.exists()
        print("PASS generated root route is removed after qualification")


if __name__ == "__main__":
    main()
