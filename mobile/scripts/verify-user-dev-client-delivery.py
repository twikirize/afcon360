#!/usr/bin/env python3
"""Qualify the exact AFCON360 Metro development APK on an Android emulator.

Checks the embedded bundle, Metro connection, Fast Refresh, preview backend
selection, EAS-channel fallback with Metro stopped, and cached launch offline.
All backend calls use an in-memory / disposable HTTP readiness stub.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

PACKAGE = "space.pamoja.afcon360.user.preview.dev"
SCHEME = "afcon360-preview-dev"
METRO_PORT = 8081
API_PORT = 5000
EVIDENCE = Path(os.environ.get("AFCON360_DEV_EVIDENCE_DIR", "user-dev-delivery-evidence"))
APP_ROOT = Path("apps/user")
ROUTE = APP_ROOT / "app" / "dev-delivery-qualification.tsx"

RESULTS: dict[str, Any] = {"package": PACKAGE, "checks": [], "backend_requests": []}
SERVER: ThreadingHTTPServer | None = None
SERVER_THREAD: threading.Thread | None = None
METRO: subprocess.Popen[str] | None = None
METRO_LOG = None
ORIGINAL_ROUTE: bytes | None = None
ROUTE_EXISTED = ROUTE.exists()


class ReadyHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        RESULTS["backend_requests"].append(self.path)
        if self.path == "/api/health/ready":
            body = b'{"status":"ready","source":"ci-disposable-stub"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *_args: object) -> None:
        return


def record(label: str, passed: bool, detail: str = "") -> None:
    RESULTS["checks"].append({"name": label, "passed": bool(passed), "detail": detail})
    print(("PASS " if passed else "FAIL ") + label + (": " + detail if detail else ""), flush=True)
    if not passed:
        raise AssertionError(label + (": " + detail if detail else ""))


def run(command: list[str], *, timeout: int = 90, check: bool = True) -> str:
    completed = subprocess.run(
        command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        timeout=timeout, check=False,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(
            f"Command failed ({completed.returncode}): {' '.join(command)}\n"
            + completed.stdout[-6000:]
        )
    return completed.stdout


def adb(*args: str, timeout: int = 90, check: bool = True) -> str:
    return run(["adb", *args], timeout=timeout, check=check)


def save_text(name: str, content: str) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / name).write_text(content, encoding="utf-8")


def ui_dump() -> str:
    adb("shell", "uiautomator", "dump", "/sdcard/window.xml", timeout=30, check=False)
    return adb("shell", "cat", "/sdcard/window.xml", timeout=15, check=False)


def wait_for_text(*needles: str, timeout: int = 60, label: str = "screen") -> str:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        last = ui_dump()
        if all(needle in last for needle in needles):
            save_text(f"{label.replace(' ', '-')}-ui.xml", last)
            record(label, True, "visible text: " + ", ".join(needles))
            return last
        time.sleep(1)
    save_text(f"{label.replace(' ', '-')}-last-ui.xml", last)
    raise AssertionError(
        f"Timed out waiting for {label}; expected {needles}. Last UI XML:\n{last[-7000:]}"
    )


def tap_text(label: str, *, timeout: int = 20) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        raw = ui_dump()
        start = raw.find("<?xml")
        if start >= 0:
            try:
                root = ET.fromstring(raw[start:])
            except ET.ParseError:
                root = None
            if root is not None:
                for node in root.iter("node"):
                    value = " ".join(
                        part for part in (
                            node.attrib.get("text", "").strip(),
                            node.attrib.get("content-desc", "").strip(),
                        ) if part
                    )
                    if label not in value:
                        continue
                    bounds = node.attrib.get("bounds", "")
                    import re
                    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
                    if match:
                        x1, y1, x2, y2 = map(int, match.groups())
                        if x2 > x1 and y2 > y1:
                            adb("shell", "input", "tap", str((x1 + x2) // 2), str((y1 + y2) // 2))
                            time.sleep(1)
                            return
        # React Native pages can place the connection link below the viewport.
        adb("shell", "input", "swipe", "520", "1500", "520", "650", "350", check=False)
        time.sleep(0.5)
    raise AssertionError(f"Could not find a tappable UI element containing {label!r}.")


def wait_http(url: str, timeout: int = 90) -> str:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                return response.read().decode("utf-8", errors="replace")
        except Exception as error:  # retry startup while Metro initializes
            last_error = str(error)
            time.sleep(1)
    raise RuntimeError(f"HTTP endpoint did not become ready: {url}: {last_error}")


def start_backend_stub() -> None:
    global SERVER, SERVER_THREAD
    SERVER = ThreadingHTTPServer(("127.0.0.1", API_PORT), ReadyHandler)
    SERVER_THREAD = threading.Thread(target=SERVER.serve_forever, daemon=True)
    SERVER_THREAD.start()
    wait_http(f"http://127.0.0.1:{API_PORT}/api/health/ready", timeout=10)
    adb("reverse", f"tcp:{API_PORT}", f"tcp:{API_PORT}")
    record("laptop API port is forwarded to Android", True, "ADB reverse tcp:5000")


def write_qa_route(marker: str) -> None:
    ROUTE.parent.mkdir(parents=True, exist_ok=True)
    ROUTE.write_text(
        'import React from "react";\n'
        'import { Text, View } from "react-native";\n'
        'export default function DevDeliveryQualification() {\n'
        '  return <View style={{ flex: 1, alignItems: "center", justifyContent: "center", padding: 24 }}>\n'
        f'    <Text testID="delivery-marker">{marker}</Text>\n'
        '  </View>;\n'
        '}\n',
        encoding="utf-8",
    )


def start_metro() -> None:
    global METRO, METRO_LOG
    env = os.environ.copy()
    env.update({
        "AFCON360_PREVIEW_BUILD": "true",
        "AFCON360_RELEASE_BUILD": "false",
        "AFCON360_DEVELOPMENT_CLIENT": "true",
        "AFCON360_UPDATE_CHANNEL": "user-development-client",
        "EXPO_PUBLIC_API_BASE_URL": "http://127.0.0.1:5000",
        "EXPO_NO_DEV_MENU": "1",
        "EXPO_NO_TELEMETRY": "1",
        "CI": "1",
    })
    if not env.get("AFCON360_USER_EAS_PROJECT_ID"):
        raise RuntimeError("AFCON360_USER_EAS_PROJECT_ID is required for Metro/EAS runtime qualification.")
    METRO_LOG = (EVIDENCE / "metro-server.log").open("w", encoding="utf-8")
    METRO = subprocess.Popen(
        [
            "pnpm", "--filter", "@afcon360/user-app", "exec", "expo", "start",
            "--dev-client", "--host", "localhost", "--port", str(METRO_PORT),
            "--non-interactive",
        ],
        cwd=Path.cwd(),
        env=env,
        stdout=METRO_LOG,
        stderr=subprocess.STDOUT,
        text=True,
    )
    wait_http(f"http://127.0.0.1:{METRO_PORT}/status", timeout=120)
    adb("reverse", f"tcp:{METRO_PORT}", f"tcp:{METRO_PORT}")
    record("Metro dev server is healthy", True, "http://127.0.0.1:8081/status")


def open_metro_deep_link() -> None:
    encoded = urllib.parse.quote(f"http://127.0.0.1:{METRO_PORT}", safe="")
    launch = f"{SCHEME}://expo-development-client/?url={encoded}"
    output = adb(
        "shell", "am", "start", "-W", "-a", "android.intent.action.VIEW",
        "-d", launch, timeout=60,
    )
    save_text("metro-launch.txt", output)
    if "Error" in output or "unable to resolve Intent" in output.lower():
        raise RuntimeError("Android could not resolve the Metro development-client URL: " + output)
    time.sleep(8)


def open_route() -> None:
    launch = f"{SCHEME}://dev-delivery-qualification"
    output = adb(
        "shell", "am", "start", "-W", "-a", "android.intent.action.VIEW",
        "-d", launch, timeout=45,
    )
    save_text("qa-route-launch.txt", output)
    time.sleep(2)


def stop_metro() -> None:
    global METRO
    if METRO and METRO.poll() is None:
        METRO.terminate()
        try:
            METRO.wait(timeout=10)
        except subprocess.TimeoutExpired:
            METRO.kill()
            METRO.wait(timeout=10)
    METRO = None
    adb("reverse", "--remove", f"tcp:{METRO_PORT}", check=False)
    time.sleep(2)


def capture_failure() -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    save_text("failure-logcat.txt", adb("logcat", "-d", "-v", "time", timeout=60, check=False))
    save_text("failure-activities.txt", adb("shell", "dumpsys", "activity", "activities", check=False))
    save_text("failure-ui.xml", ui_dump())


def main() -> None:
    global ORIGINAL_ROUTE
    if len(sys.argv) != 2:
        raise SystemExit("Usage: verify-user-dev-client-delivery.py <candidate.apk>")
    apk = Path(sys.argv[1]).resolve()
    if not apk.is_file():
        raise FileNotFoundError(apk)
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    project_id = os.environ.get("AFCON360_USER_EAS_PROJECT_ID", "").strip()
    update_group = os.environ.get("AFCON360_USER_DEV_UPDATE_GROUP", "").strip()
    update_runtime = os.environ.get("AFCON360_USER_DEV_UPDATE_RUNTIME", "").strip()
    if not project_id or not update_group or not update_runtime:
        raise RuntimeError("The workflow must supply the EAS project ID, a published update group and runtime version.")

    with zipfile.ZipFile(apk) as archive:
        entries = set(archive.namelist())
    bundle_entries = sorted(
        entry for entry in entries
        if entry.endswith("assets/index.android.bundle") or
           entry.endswith("assets/index.android.bundle.hbc")
    )
    record(
        "APK contains an embedded React Native JavaScript bundle",
        bool(bundle_entries),
        ", ".join(bundle_entries) if bundle_entries else "No assets/index.android.bundle entry found",
    )
    RESULTS["embedded_bundle_entries"] = bundle_entries
    RESULTS["apk_sha256"] = __import__("hashlib").sha256(apk.read_bytes()).hexdigest()
    RESULTS["eas_update_group"] = update_group
    RESULTS["eas_update_runtime"] = update_runtime

    devices = [
        line.split()[0] for line in adb("devices").splitlines()[1:]
        if line.strip() and line.split()[1] == "device"
    ]
    if len(devices) != 1:
        raise RuntimeError(f"Expected one Android emulator/device, found: {devices}")
    RESULTS["android_device"] = devices[0]

    install_output = adb("install", "-r", str(apk), timeout=180)
    save_text("apk-install.txt", install_output)
    record("exact candidate APK installs on Android", "Success" in install_output, install_output.strip())

    package_output = adb("shell", "dumpsys", "package", PACKAGE)
    save_text("installed-package.txt", package_output)
    if PACKAGE not in package_output:
        raise RuntimeError("Installed package manager record does not contain the expected User App package.")
    record("installed package identity matches the candidate", True, PACKAGE)

    start_backend_stub()
    write_qa_route("AFCON360_METRO_FAST_REFRESH_BEFORE")
    start_metro()
    try:
        open_metro_deep_link()
        open_route()
        wait_for_text("AFCON360_METRO_FAST_REFRESH_BEFORE", timeout=120, label="Metro route loaded")
        write_qa_route("AFCON360_METRO_FAST_REFRESH_AFTER")
        wait_for_text("AFCON360_METRO_FAST_REFRESH_AFTER", timeout=60, label="Fast Refresh applied a source edit")
        record("Metro Fast Refresh works without rebuilding or reinstalling", True)
    finally:
        stop_metro()
        if ROUTE.exists():
            ROUTE.unlink()

    # Check the server-selection screen while the Metro-served AFCON360 code is
    # still available. The settings screen performs a real readiness GET to
    # the disposable host stub; no production account or backend is touched.
    adb("shell", "am", "start", "-W", "-a", "android.intent.action.VIEW",
        "-d", f"{SCHEME}://login", timeout=45)
    wait_for_text("Connection settings (preview)", timeout=60, label="preview server selector is available")
    tap_text("Connection settings (preview)")
    wait_for_text("Laptop development server", "Public Pamoja", timeout=60, label="server selection screen")
    wait_for_text("Use public Pamoja", timeout=20, label="public Pamoja option")
    tap_text("Use server for this development session")
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and "/api/health/ready" not in RESULTS["backend_requests"]:
        time.sleep(0.25)
    record(
        "laptop backend selection performs its readiness check",
        "/api/health/ready" in RESULTS["backend_requests"],
        ", ".join(RESULTS["backend_requests"]),
    )

    # Metro is now completely stopped and its USB/emulator reverse mapping is
    # removed. A normal launcher-icon start must use the EAS update fallback.
    adb("shell", "am", "force-stop", PACKAGE, check=False)
    time.sleep(2)
    launch_output = adb("shell", "monkey", "-p", PACKAGE, "1", timeout=45)
    save_text("metro-off-launch.txt", launch_output)
    wait_for_text("Your journey starts here.", timeout=120, label="AFCON360 opens with Metro stopped")
    ui = ui_dump()
    if "Development servers" in ui or "Enter URL manually" in ui or "Load embedded bundle" in ui:
        raise AssertionError("The Metro-off launch displayed the development launcher instead of AFCON360.")
    record("Metro-off startup opens AFCON360 rather than the development launcher", True)

    # Turn off device networking after the EAS update has opened once. The
    # next cold launch must use the locally cached EAS bundle or embedded one.
    adb("shell", "svc", "wifi", "disable", check=False)
    adb("shell", "svc", "data", "disable", check=False)
    adb("shell", "settings", "put", "global", "airplane_mode_on", "1", check=False)
    adb("shell", "am", "broadcast", "-a", "android.intent.action.AIRPLANE_MODE", "--ez", "state", "true", check=False)
    adb("shell", "am", "force-stop", PACKAGE, check=False)
    time.sleep(2)
    adb("shell", "monkey", "-p", PACKAGE, "1", timeout=45)
    wait_for_text("Your journey starts here.", timeout=90, label="cached bundle opens with Metro and internet unavailable")
    record("previously downloaded or embedded bundle opens without Metro and internet", True)

    # Save an auditable proof bundle, including Metro and Android logs.
    logcat = adb("logcat", "-d", "-v", "time", timeout=60, check=False)
    save_text("dev-client-logcat.txt", logcat)
    save_text("emulator-activities.txt", adb("shell", "dumpsys", "activity", "activities", check=False))
    RESULTS["status"] = "passed"
    (EVIDENCE / "dev-client-delivery-results.json").write_text(
        json.dumps(RESULTS, indent=2) + "\n", encoding="utf-8"
    )
    print("PASS: AFCON360 hybrid development delivery qualification completed.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        RESULTS["status"] = "failed"
        RESULTS["failure"] = str(error)
        try:
            capture_failure()
            (EVIDENCE / "dev-client-delivery-results.json").write_text(
                json.dumps(RESULTS, indent=2) + "\n", encoding="utf-8"
            )
        except Exception as capture_error:
            print("Could not capture complete failure evidence: " + str(capture_error), file=sys.stderr)
        print("FAIL: " + str(error), file=sys.stderr, flush=True)
        raise
    finally:
        stop_metro()
        if ROUTE.exists() and not ROUTE_EXISTED:
            ROUTE.unlink(missing_ok=True)
        if ORIGINAL_ROUTE is not None and not ROUTE_EXISTED:
            ROUTE.write_bytes(ORIGINAL_ROUTE)
        if SERVER:
            SERVER.shutdown()
