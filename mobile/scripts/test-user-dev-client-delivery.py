#!/usr/bin/env python3
"""Unit checks for the temporary Fast Refresh route used by Android qualification."""

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


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="afcon360-fast-refresh-test-") as directory:
        route = Path(directory) / "dev-delivery-qualification.tsx"
        MODULE.ROUTE = route
        MODULE.ROUTE_CREATED = False

        MODULE.write_qa_route("AFCON360_METRO_FAST_REFRESH_BEFORE")
        first = route.read_text(encoding="utf-8")
        assert "AFCON360_METRO_FAST_REFRESH_BEFORE" in first
        print("PASS qualification creates its temporary React route")

        MODULE.write_qa_route("AFCON360_METRO_FAST_REFRESH_AFTER")
        second = route.read_text(encoding="utf-8")
        assert "AFCON360_METRO_FAST_REFRESH_AFTER" in second
        assert "AFCON360_METRO_FAST_REFRESH_BEFORE" not in second
        print("PASS qualification can edit its own route to exercise Fast Refresh")

        MODULE.ROUTE_CREATED = False
        route.write_text("developer-owned source", encoding="utf-8")
        try:
            MODULE.write_qa_route("MUST_NOT_OVERWRITE")
        except RuntimeError as error:
            assert "Refusing to overwrite an existing source file" in str(error)
        else:
            raise AssertionError("Qualification overwrote a developer-owned source file")
        assert route.read_text(encoding="utf-8") == "developer-owned source"
        print("PASS qualification refuses to overwrite developer-owned source")


if __name__ == "__main__":
    main()
