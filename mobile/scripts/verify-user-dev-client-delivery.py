#!/usr/bin/env python3
"""Qualify one exact AFCON360 User development APK on an Android emulator.

The test exercises the signed candidate, Metro Fast Refresh, the laptop API
selection, EAS Update loading, and cold starts when Metro/network are absent.
It records failures without stopping early, so one run exposes all blockers.
All API requests use an in-memory test HTTP server; no real accounts or backend
records are touched.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
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
ROUTE = Path("apps/user/app/index.tsx")

RESULTS: dict[str, Any] = {"package": PACKAGE, "checks": [], "backend_requests": []}
SERVER: ThreadingHTTPServer | None = None
METRO: subprocess.Popen[str] | None = None
METRO_LOG = None
ROUTE_CREATED = False
ROUTE_BACKUP: bytes | None = None
ROUTE_EXISTED = False


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
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *_args: object) -> None:
        return


def record(label: str, passed: bool, detail: str = "") -> bool:
    RESULTS["checks"].append({"name": label, "passed": bool(passed), "detail": detail})
    print(("PASS " if passed else "FAIL ") + label + (": " + detail if detail else ""), flush=True)
    return bool(passed)


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


def visible_text() -> str:
    raw = ui_dump()
    start = raw.find("<?xml")
    if start < 0:
        return raw
    try:
        root = ET.fromstring(raw[start:])
    except ET.ParseError:
        return raw
    return "\n".join(
        " ".join(filter(None, (
            node.attrib.get("text", "").strip(),
            node.attrib.get("content-desc", "").strip(),
        )))
        for node in root.iter("node")
    )


def wait_for_text(*needles: str, timeout: int = 60) -> tuple[bool, str]:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        last = visible_text()
        if all(needle in last for needle in needles):
            return True, last
        time.sleep(1)
    return False, last


def tap_text(label: str, *, timeout: int = 20) -> bool:
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
                    value = " ".join(filter(None, (
                        node.attrib.get("text", "").strip(),
                        node.attrib.get("content-desc", "").strip(),
                    )))
                    if label not in value:
                        continue
                    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.attrib.get("bounds", ""))
                    if match:
                        x1, y1, x2, y2 = map(int, match.groups())
                        if x2 > x1 and y2 > y1:
                            adb("shell", "input", "tap", str((x1 + x2) // 2), str((y1 + y2) // 2))
                            time.sleep(1)
                            return True
        adb("shell", "input", "swipe", "520", "1500", "520", "650", "350", check=False)
        time.sleep(0.5)
    return False


def wait_http(url: str, timeout: int = 90) -> str:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                return response.read().decode("utf-8", errors="replace")
        except Exception as error:
            last_error = str(error)
            time.sleep(1)
    raise RuntimeError(f"HTTP endpoint did not become ready: {url}: {last_error}")


def start_backend_stub() -> None:
    global SERVER
    SERVER = ThreadingHTTPServer(("127.0.0.1", API_PORT), ReadyHandler)
    threading.Thread(target=SERVER.serve_forever, daemon=True).start()
    wait_http(f"http://127.0.0.1:{API_PORT}/api/health/ready", timeout=10)
    adb("reverse", f"tcp:{API_PORT}", f"tcp:{API_PORT}")
    record("disposable laptop API responds through ADB reverse", True, "tcp:5000")


def write_qa_route(marker: str) -> None:
    global ROUTE_CREATED, ROUTE_BACKUP, ROUTE_EXISTED
    # The qualification job runs in an isolated checkout. Back up the committed
    # app root route before replacing it with a marker screen for Metro/Fast Refresh.
    if not ROUTE_CREATED:
        ROUTE_EXISTED = ROUTE.exists()
        ROUTE_BACKUP = ROUTE.read_bytes() if ROUTE_EXISTED else None
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
    ROUTE_CREATED = True


def restore_qa_route() -> None:
    global ROUTE_CREATED, ROUTE_BACKUP, ROUTE_EXISTED
    if not ROUTE_CREATED:
        return
    if ROUTE_EXISTED:
        if ROUTE_BACKUP is None:
            raise RuntimeError("AFCON360 qualification lost the saved app root route.")
        ROUTE.write_bytes(ROUTE_BACKUP)
    else:
        ROUTE.unlink(missing_ok=True)
    ROUTE_CREATED = False
    ROUTE_BACKUP = None
    ROUTE_EXISTED = False


def start_metro() -> None:
    global METRO, METRO_LOG
    env = os.environ.copy()
    env.update({
        "AFCON360_PREVIEW_BUILD": "true",
        "AFCON360_RELEASE_BUILD": "false",
        "AFCON360_DEVELOPMENT_CLIENT": "true",
        "AFCON360_UPDATE_CHANNEL": "user-development-client",
        "EXPO_PUBLIC_API_BASE_URL": "http://127.0.0.1:5000",
        "EXPO_NO_TELEMETRY": "1",
    })
    # GitHub Actions exports CI=true, which makes Metro disable reloads and HMR.
    env.pop("CI", None)
    if not env.get("AFCON360_USER_EAS_PROJECT_ID"):
        raise RuntimeError("AFCON360_USER_EAS_PROJECT_ID is required for delivery qualification.")
    METRO_LOG = (EVIDENCE / "metro-server.log").open("w", encoding="utf-8")
    METRO = subprocess.Popen(
        [
            "pnpm", "--filter", "@afcon360/user-app", "exec", "expo", "start",
            "--dev-client", "--host", "localhost", "--port", str(METRO_PORT),
        ],
        cwd=Path.cwd(),
        env=env,
        stdout=METRO_LOG,
        stderr=subprocess.STDOUT,
        text=True,
    )
    wait_http(f"http://127.0.0.1:{METRO_PORT}/status", timeout=120)
    adb("reverse", f"tcp:{METRO_PORT}", f"tcp:{METRO_PORT}")
    record("Metro dev server is healthy and forwarded to Android", True, "tcp:8081")


def open_dev_url(target_url: str, filename: str) -> None:
    encoded = urllib.parse.quote(target_url, safe="")
    # SDK 58 launch URL contract; legacy expo-development-client/?url= is no
    # longer the preferred format but remains supported for older SDK clients.
    launch = (
        f"{SCHEME}://?__expo_url={encoded}"
        "&__expo_disable_onboarding=1"
        "&__expo_disable_fab=1"
        "&__expo_disable_auto_launch=1"
    )
    output = adb(
        "shell", "am", "start", "-W", "-a", "android.intent.action.VIEW",
        "-d", launch, timeout=60,
    )
    save_text(filename, output)
    if "Error" in output or "unable to resolve Intent" in output.lower():
        raise RuntimeError(f"Android could not resolve the app launch URL: {output}")
    time.sleep(5)


def open_app_route(route: str, filename: str) -> None:
    launch = f"{SCHEME}://{route.lstrip('/')}"
    output = adb(
        "shell", "am", "start", "-W", "-a", "android.intent.action.VIEW",
        "-d", launch, timeout=45,
    )
    save_text(filename, output)
    time.sleep(2)


def cold_launch(filename: str) -> str:
    adb("shell", "am", "force-stop", PACKAGE, check=False)
    time.sleep(2)
    output = adb("shell", "monkey", "-p", PACKAGE, "1", timeout=45)
    save_text(filename, output)
    time.sleep(3)
    return visible_text()


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


def set_network_offline() -> None:
    adb("shell", "svc", "wifi", "disable", check=False)
    adb("shell", "svc", "data", "disable", check=False)
    adb("shell", "cmd", "connectivity", "airplane-mode", "enable", check=False)
    adb("shell", "settings", "put", "global", "airplane_mode_on", "1", check=False)
    adb("shell", "am", "broadcast", "-a", "android.intent.action.AIRPLANE_MODE", "--ez", "state", "true", check=False)
    time.sleep(3)


def set_network_online() -> None:
    adb("shell", "cmd", "connectivity", "airplane-mode", "disable", check=False)
    adb("shell", "settings", "put", "global", "airplane_mode_on", "0", check=False)
    adb("shell", "am", "broadcast", "-a", "android.intent.action.AIRPLANE_MODE", "--ez", "state", "false", check=False)
    adb("shell", "svc", "wifi", "enable", check=False)
    adb("shell", "svc", "data", "enable", check=False)
    time.sleep(5)


def capture_failure() -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    save_text("failure-logcat.txt", adb("logcat", "-d", "-v", "time", timeout=60, check=False))
    save_text("failure-activities.txt", adb("shell", "dumpsys", "activity", "activities", check=False))
    save_text("failure-ui.xml", ui_dump())


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: verify-user-dev-client-delivery.py <candidate.apk>")
    apk = Path(sys.argv[1]).resolve()
    if not apk.is_file():
        raise FileNotFoundError(apk)
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    project_id = os.environ.get("AFCON360_USER_EAS_PROJECT_ID", "").strip()
    update_group = os.environ.get("AFCON360_USER_DEV_UPDATE_GROUP", "").strip()
    update_runtime = os.environ.get("AFCON360_USER_DEV_UPDATE_RUNTIME", "").strip()
    update_marker = os.environ.get("AFCON360_USER_DEV_UPDATE_MARKER", "").strip()
    if not project_id or not update_group or not update_runtime or not update_marker:
        raise RuntimeError("Workflow must supply EAS project ID, update group, runtime and marker.")

    RESULTS["apk_sha256"] = hashlib.sha256(apk.read_bytes()).hexdigest()
    RESULTS["eas_update_group"] = update_group
    RESULTS["eas_update_runtime"] = update_runtime
    RESULTS["eas_update_marker"] = update_marker

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
        ", ".join(bundle_entries) if bundle_entries else "No embedded Android bundle entry found",
    )
    RESULTS["embedded_bundle_entries"] = bundle_entries

    devices = [
        line.split()[0] for line in adb("devices").splitlines()[1:]
        if line.strip() and line.split()[1] == "device"
    ]
    if len(devices) != 1:
        raise RuntimeError(f"Expected one Android emulator, found: {devices}")
    RESULTS["android_device"] = devices[0]

    install_output = adb("install", "-r", str(apk), timeout=180)
    save_text("apk-install.txt", install_output)
    record("exact candidate APK installs on Android", "Success" in install_output, install_output.strip())

    package_output = adb("shell", "dumpsys", "package", PACKAGE)
    save_text("installed-package.txt", package_output)
    record("installed package identity matches the candidate", PACKAGE in package_output, PACKAGE)

    # First-launch offline proof: with no Metro history, no cached EAS update
    # and no internet, the startup fallback must enter the embedded AFCON360
    # bundle rather than leave the user on the development launcher.
    set_network_offline()
    cold_launch("fresh-install-offline-startup.txt")
    fresh_offline_ok, fresh_offline_ui = wait_for_text("THE WORLD, OPEN TO YOU", "Make every journey matter.", timeout=90)
    record(
        "fresh first launch opens embedded AFCON360 with Metro and internet unavailable",
        fresh_offline_ok,
        fresh_offline_ui[-2000:],
    )
    set_network_online()

    start_backend_stub()
    write_qa_route("AFCON360_METRO_FAST_REFRESH_BEFORE")
    start_metro()
    try:
        open_dev_url(f"http://127.0.0.1:{METRO_PORT}", "metro-launch.txt")
        before_ok, before_ui = wait_for_text("AFCON360_METRO_FAST_REFRESH_BEFORE", timeout=150)
        record("Metro serves the AFCON360 development app", before_ok, before_ui[-1500:])

        write_qa_route("AFCON360_METRO_FAST_REFRESH_AFTER")
        after_ok, after_ui = wait_for_text("AFCON360_METRO_FAST_REFRESH_AFTER", timeout=90)
        record("Fast Refresh applies a React source edit without rebuilding", after_ok, after_ui[-1500:])

        # Server configuration and readiness probe are checked while Metro is
        # deliberately serving the app, and use only an in-memory HTTP stub.
        open_app_route("login", "metro-login-launch.txt")
        selector_ok, selector_ui = wait_for_text("Connection settings (preview)", timeout=60)
        record("preview backend selector is reachable from login", selector_ok, selector_ui[-1200:])
        if selector_ok:
            selector_tap = tap_text("Connection settings (preview)")
            record("preview server settings can be opened", selector_tap)
            settings_ok, settings_ui = wait_for_text("Laptop development server", timeout=60)
            record("laptop server option is visible", settings_ok, settings_ui[-1500:])
            if settings_ok:
                button_tap = tap_text("Use server for this development session")
                record("laptop server option can be selected", button_tap)
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline and "/api/health/ready" not in RESULTS["backend_requests"]:
                    time.sleep(0.25)
                record(
                    "laptop backend selection checks API readiness",
                    "/api/health/ready" in RESULTS["backend_requests"],
                    ", ".join(RESULTS["backend_requests"]),
                )
    finally:
        # Keep the diagnostic route only during the Metro test. A route shipped
        # in the EAS qualification update is injected separately by the build job.
        stop_metro()
        restore_qa_route()

    # Test the exact behaviour requested: Metro has been used most recently,
    # but is now stopped. The icon launch must enter AFCON360, not the launcher.
    cold_launch("metro-off-after-metro-launch.txt")
    metro_off_deadline = time.monotonic() + 120
    metro_off_ui = ""
    automatic_fallback = False
    while time.monotonic() < metro_off_deadline:
        metro_off_ui = visible_text()
        if ("THE WORLD, OPEN TO YOU" in metro_off_ui or "Make every journey matter." in metro_off_ui) or "AFCON360_EAS_UPDATE_" in metro_off_ui:
            automatic_fallback = True
            break
        time.sleep(1)
    save_text("metro-off-after-metro-launch-ui.xml", ui_dump())
    record(
        "cold launch opens AFCON360 after the most-recent Metro server is stopped",
        automatic_fallback,
        metro_off_ui[-2500:],
    )

    # Independently prove the same APK can load a published, runtime-compatible
    # EAS Update using the documented SDK 58 dev-client update launch URL.
    update_url = f"https://u.expo.dev/{project_id}?channel-name=user-development-client"
    RESULTS["eas_update_channel"] = "user-development-client"
    open_dev_url(update_url, "eas-update-launch.txt")
    update_ok, update_ui = wait_for_text("AFCON360_EAS_UPDATE_" + update_marker, timeout=150)
    record("same APK loads the compatible EAS Update group", update_ok, update_ui[-2000:])

    # Having loaded the EAS bundle once, the last project should now be the
    # EAS update rather than Metro. Verify cold-start and then cached offline.
    cold_launch("eas-update-cold-launch.txt")
    update_cold_ok, update_cold_ui = wait_for_text("AFCON360_EAS_UPDATE_" + update_marker, timeout=120)
    record("EAS update becomes the app's cold-start project with Metro stopped", update_cold_ok, update_cold_ui[-2000:])

    set_network_offline()
    cold_launch("eas-update-offline-cold-launch.txt")
    offline_ui = visible_text()
    offline_cached_marker = "AFCON360_EAS_UPDATE_" + update_marker in offline_ui
    offline_embedded_fallback = ("THE WORLD, OPEN TO YOU" in offline_ui or "Make every journey matter." in offline_ui)
    offline_ok = offline_cached_marker or offline_embedded_fallback
    RESULTS["offline_startup_source"] = (
        "eas_update_marker" if offline_cached_marker
        else "embedded_bundle" if offline_embedded_fallback
        else "no_afcon360_screen"
    )
    RESULTS["persistent_eas_cache_qualification"] = (
        "observed" if offline_cached_marker
        else "not_proven_by_development_client; embedded fallback verified"
        if offline_embedded_fallback
        else "failed"
    )
    record(
        "offline cold launch keeps AFCON360 available with Metro and internet unavailable",
        offline_ok,
        "source=" + RESULTS["offline_startup_source"] + "; " + offline_ui[-2000:],
    )

    # Validate that the actual User login screen is present in the EAS-updated
    # application bundle, still without contacting production services.
    open_app_route("login", "eas-login-launch.txt")
    login_ok, login_ui = wait_for_text("Your journey starts here.", timeout=60)
    record("EAS-updated bundle opens the real AFCON360 login screen", login_ok, login_ui[-2000:])

    save_text("dev-client-logcat.txt", adb("logcat", "-d", "-v", "time", timeout=60, check=False))
    save_text("emulator-activities.txt", adb("shell", "dumpsys", "activity", "activities", check=False))
    (EVIDENCE / "dev-client-delivery-results.json").write_text(
        json.dumps(RESULTS, indent=2) + "\n", encoding="utf-8"
    )

    failed = [item for item in RESULTS["checks"] if not item["passed"]]
    RESULTS["status"] = "passed" if not failed else "failed"
    (EVIDENCE / "dev-client-delivery-results.json").write_text(
        json.dumps(RESULTS, indent=2) + "\n", encoding="utf-8"
    )
    if failed:
        raise AssertionError(
            "AFCON360 development delivery qualification failed "
            f"{len(failed)} of {len(RESULTS['checks'])} checks: "
            + "; ".join(item["name"] for item in failed)
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
        restore_qa_route()
        if SERVER:
            SERVER.shutdown()
