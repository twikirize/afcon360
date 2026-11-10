#!/usr/bin/env python3
"""Disposable-CI Android UI journey for the AFCON360 User APK.

The test account and backend exist only in the workflow's fresh PostgreSQL/Redis
services. No production account, payment, booking, or financial write is used.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

PACKAGE = "space.pamoja.afcon360.user.preview"
USERNAME = os.environ.get("AFCON360_E2E_USERNAME", "native_e2e_user")
PASSWORD = os.environ.get("AFCON360_E2E_PASSWORD", "NativeE2ePassword2026")
EVIDENCE = Path(os.environ.get("AFCON360_E2E_EVIDENCE_DIR", "mobile-e2e-evidence"))
UI_XML = "/sdcard/afcon360-user-e2e-ui.xml"

PROGRESS = EVIDENCE / "journey-progress.json"


def mark_stage(stage: str) -> None:
    """Persist the last completed stage of the Android journey."""
    completed = []
    if PROGRESS.is_file():
        try:
            completed = list(json.loads(PROGRESS.read_text(encoding="utf-8")).get("completed_stages", []))
        except (OSError, ValueError, TypeError):
            completed = []
    if stage not in completed:
        completed.append(stage)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text(
        json.dumps({"completed_stages": completed, "last_completed_stage": stage}, indent=2) + "\n",
        encoding="utf-8",
    )


def run_adb(*args: str, check: bool = True, capture: bool = True) -> str:
    result = subprocess.run(
        ["adb", *args], check=False, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    output = result.stdout or ""
    if check and result.returncode:
        raise RuntimeError(f"adb {' '.join(args[:4])} failed ({result.returncode}): {output[-2000:]}")
    return output


def dump_tree() -> ET.Element:
    # Never reuse an old UI tree when Android fails to produce a fresh snapshot.
    run_adb("shell", "rm", "-f", UI_XML, check=False)
    result = run_adb("shell", "uiautomator", "dump", UI_XML, check=False)
    if "dumped to:" not in result.lower():
        raise RuntimeError(f"Android did not create a fresh UI hierarchy: {result[-1000:]}")
    raw = run_adb("shell", "cat", UI_XML, check=False)
    start = raw.find("<?xml")
    if start < 0:
        raise RuntimeError(f"Fresh Android UI hierarchy was not readable: {raw[-1000:]}")
    return ET.fromstring(raw[start:])


def node_value(node: ET.Element) -> str:
    return " ".join(
        value for value in (node.attrib.get("text", ""), node.attrib.get("content-desc", ""))
        if value
    )


def visible_text() -> str:
    root = dump_tree()
    return "\n".join(filter(None, (node_value(node) for node in root.iter("node"))))


def wait_for_text(*needles: str, timeout: int = 35, label: str = "screen") -> str:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        try:
            last = visible_text()
        except Exception:
            time.sleep(1)
            continue
        if all(needle in last for needle in needles):
            print(f"PASS: {label}: " + " | ".join(needles), flush=True)
            return last
        time.sleep(1)
    raise AssertionError(
        f"Timed out waiting for {label}: {needles}. Last visible hierarchy:\n{last[:6000]}"
    )


def bounds_center(value: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", value or "")
    if not match:
        return None
    left, top, right, bottom = map(int, match.groups())
    return ((left + right) // 2, (top + bottom) // 2)


def tap_text(value: str, *, last: bool = False, timeout: int = 12) -> None:
    deadline = time.monotonic() + timeout
    last_diagnostics = []
    while time.monotonic() < deadline:
        try:
            root = dump_tree()
            matches = []
            for node in root.iter("node"):
                text_value = node.attrib.get("text", "").strip()
                description = node.attrib.get("content-desc", "").strip()
                if text_value == value or description == value:
                    bounds = node.attrib.get("bounds", "")
                    center = bounds_center(bounds)
                    if center:
                        matches.append({
                            "center": center,
                            "bounds": bounds,
                            "class": node.attrib.get("class", ""),
                            "clickable": node.attrib.get("clickable", ""),
                            "enabled": node.attrib.get("enabled", ""),
                            "text": text_value,
                            "content_desc": description,
                        })
            if matches:
                chosen = matches[-1] if last else matches[0]
                x, y = chosen["center"]
                print(
                    "ANDROID_TAP_TARGET: "
                    + json.dumps({
                        "label": value,
                        "match_count": len(matches),
                        "chosen": chosen,
                        "all_matches": matches,
                    }, sort_keys=True),
                    flush=True,
                )
                run_adb("shell", "input", "tap", str(x), str(y))
                time.sleep(0.7)
                return
            last_diagnostics = []
        except Exception as error:
            last_diagnostics = [f"{type(error).__name__}: {error}"]
        time.sleep(0.5)
    raise AssertionError(
        f"Could not find tappable Android UI text: {value!r}. "
        + "; ".join(last_diagnostics)
    )


def tap_text_scrolling(value: str, *, max_swipes: int = 6) -> None:
    """Scroll a long native screen until an exact action is visible, then tap it."""
    size_output = run_adb("shell", "wm", "size")
    sizes = re.findall(r"(\d+)x(\d+)", size_output)
    if not sizes:
        raise RuntimeError(f"Could not determine Android display size: {size_output.strip()}")
    width, height = map(int, sizes[-1])
    last_error: AssertionError | None = None
    for attempt in range(max_swipes + 1):
        try:
            tap_text(value, timeout=2)
            print(f"PASS: tapped after {attempt} Explore scroll(s): {value}", flush=True)
            return
        except AssertionError as error:
            last_error = error
        if attempt < max_swipes:
            x = width // 2
            start_y = int(height * 0.82)
            end_y = int(height * 0.38)
            run_adb("shell", "input", "swipe", str(x), str(start_y), str(x), str(end_y), "450")
            time.sleep(0.5)
    raise AssertionError(
        f"Could not reveal and tap {value!r} after {max_swipes} vertical swipes."
    ) from last_error


def tap_edit_field(label: str) -> None:
    root = dump_tree()
    candidates = []
    for node in root.iter("node"):
        description = node.attrib.get("content-desc", "").strip()
        text_value = node.attrib.get("text", "").strip()
        klass = node.attrib.get("class", "")
        if (description == label or text_value == label) and "EditText" in klass:
            center = bounds_center(node.attrib.get("bounds", ""))
            if center:
                candidates.append(center)
    if not candidates:
        for node in root.iter("node"):
            if node.attrib.get("content-desc", "").strip() == label:
                center = bounds_center(node.attrib.get("bounds", ""))
                if center:
                    candidates.append(center)
    if not candidates:
        raise AssertionError(f"Could not locate native input field {label!r}")
    x, y = candidates[0]
    run_adb("shell", "input", "tap", str(x), str(y))
    time.sleep(0.3)


def type_text(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9._@+-]+", value):
        raise ValueError("The synthetic CI test value contains unsupported input characters.")
    run_adb("shell", "input", "text", value)
    time.sleep(0.25)


def save_screen(name: str) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    data = subprocess.run(
        ["adb", "exec-out", "screencap", "-p"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout
    root = dump_tree()
    (EVIDENCE / f"{name}.png").write_bytes(data)
    (EVIDENCE / f"{name}.xml").write_bytes(ET.tostring(root, encoding="utf-8"))
    (EVIDENCE / f"{name}.txt").write_text(
        "\n".join(filter(None, (node_value(node) for node in root.iter("node")))),
        encoding="utf-8",
    )


def return_to_explore() -> None:
    """Return to Explore after a service route; handle Back landing on Home."""
    run_adb("shell", "input", "keyevent", "4")
    time.sleep(1)
    try:
        wait_for_text("Make more of the journey.", timeout=8, label="Explore after Android Back")
    except AssertionError:
        # The Ride route may return to the Home tab. Select Explore explicitly.
        tap_text("Explore", last=True)
        wait_for_text("Make more of the journey.", timeout=20, label="Explore tab")
    wait_for_text("Find and book a stay", label="Explore accommodation action")


def save_failure_diagnostics() -> None:
    """Capture safe device diagnostics before the emulator action shuts down."""
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    def capture(name: str, *args: str) -> None:
        try:
            result = subprocess.run(
                ["adb", *args], check=False, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=45,
            )
            (EVIDENCE / name).write_text(result.stdout or "", encoding="utf-8")
        except Exception as error:
            (EVIDENCE / name).write_text(
                f"Diagnostic command failed: {type(error).__name__}: {error}\n",
                encoding="utf-8",
            )

    try:
        image = subprocess.run(
            ["adb", "exec-out", "screencap", "-p"],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45,
        ).stdout
        if image:
            (EVIDENCE / "failure-screen.png").write_bytes(image)
    except Exception as error:
        (EVIDENCE / "failure-screen-error.txt").write_text(
            f"{type(error).__name__}: {error}\n", encoding="utf-8",
        )

    capture(
        "failure-logcat-errors.txt", "logcat", "-d", "-t", "2500",
        "AndroidRuntime:E", "ReactNativeJS:E", "ReactNative:E", "Expo:E", "*:S",
    )
    capture("failure-foreground-activity.txt", "shell", "dumpsys", "activity", "activities")
    capture("failure-focused-window.txt", "shell", "dumpsys", "window", "windows")
    capture("failure-package-path.txt", "shell", "pm", "path", PACKAGE)
    capture("failure-process.txt", "shell", "pidof", PACKAGE)
    capture("failure-ui-dump-command.txt", "shell", "uiautomator", "dump", UI_XML)
    capture("failure-ui-hierarchy.xml", "shell", "cat", UI_XML)


def main() -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text(json.dumps({"completed_stages": []}, indent=2) + "\n", encoding="utf-8")
    run_adb("wait-for-device")
    run_adb("reverse", "tcp:5000", "tcp:5000")
    run_adb("install", "-r", "mobile-e2e-evidence/user-e2e.apk")
    run_adb("shell", "monkey", "-p", PACKAGE, "-c", "android.intent.category.LAUNCHER", "1")

    wait_for_text("AFCON360 User", "Sign in securely", label="native sign-in screen")
    save_screen("01-login")
    mark_stage("login_screen")

    tap_edit_field("Username or email")
    type_text(USERNAME)
    tap_edit_field("Password")
    type_text(PASSWORD)
    run_adb("shell", "input", "keyevent", "4")
    tap_text("Sign in securely")

    wait_for_text("Your journey, together.", "Signed in securely", timeout=45, label="authenticated User home")
    save_screen("02-home")
    mark_stage("authenticated_home")

    tap_text("Activity", last=True)
    wait_for_text("Your rides and bookings.", "No rides yet", timeout=35, label="authenticated ride activity")
    save_screen("03-activity")
    mark_stage("activity_screen")

    tap_text("Wallet", last=True)
    wait_for_text(
        "Your money, clearly managed.", "Wallet accounts", "No Wallet account is active yet.",
        timeout=35, label="authenticated Wallet read views",
    )
    save_screen("04-wallet")
    mark_stage("wallet_screen")

    tap_text("Account", last=True)
    wait_for_text("Your AFCON360 identity.", "Sign out", timeout=25, label="authenticated account")
    account_text = visible_text()
    if USERNAME not in account_text and os.environ.get("AFCON360_E2E_EMAIL", "native-e2e@afcon360.test") not in account_text:
        raise AssertionError("The authenticated account screen did not display the synthetic user's identity.")
    save_screen("05-account")
    mark_stage("account_screen")

    tap_text("Explore", last=True)
    wait_for_text("Make more of the journey.", "Rides", label="Explore services")
    save_screen("06-explore")
    mark_stage("explore_screen")

    tap_text("Book a ride")
    wait_for_text("Where are you going?", "Pickup", timeout=25, label="native ride request screen")
    save_screen("07-ride")
    mark_stage("ride_screen")
    return_to_explore()
    save_screen("07b-explore-before-stays")
    mark_stage("explore_after_ride")

    tap_text("Find and book a stay")
    time.sleep(2)
    save_screen("08-stays-navigation-attempt")
    wait_for_text("Find your place to stay.", timeout=30, label="native accommodation screen")
    save_screen("08-stays")
    mark_stage("stays_screen")
    return_to_explore()
    mark_stage("explore_after_stays")

    mark_stage("events_navigation_started")
    tap_text_scrolling("Discover events and tickets")
    wait_for_text("Be there for the moments.", timeout=30, label="native events screen")
    save_screen("09-events")
    mark_stage("events_screen")
    return_to_explore()
    mark_stage("explore_after_events")

    # Force-stop the Android process and prove that SecureStore credentials
    # restore the authenticated session after an actual app restart.
    mark_stage("session_restore_started")
    run_adb("shell", "am", "force-stop", PACKAGE)
    time.sleep(1)
    run_adb("shell", "monkey", "-p", PACKAGE, "-c", "android.intent.category.LAUNCHER", "1")
    wait_for_text("Your journey, together.", "Signed in securely", timeout=45, label="restored authenticated session")
    save_screen("10-session-restored")
    mark_stage("session_restored")

    tap_text("Account", last=True)
    wait_for_text("Your AFCON360 identity.", "Sign out", label="account before logout")
    tap_text("Sign out")
    wait_for_text("Sign out of AFCON360 on this device?", timeout=12, label="logout confirmation")
    mark_stage("logout_started")
    tap_text("Sign out", last=True)
    wait_for_text("Sign in securely", "Username or email", "Password", timeout=35, label="signed-out login screen")
    save_screen("11-logged-out")
    mark_stage("logout_completed")

    print(
        "USER_ANDROID_E2E_UI_PASS: login, authenticated home, Activity, Wallet reads, "
        "Account, Explore, Ride, Stays, Events, process-death session restore, and logout.",
        flush=True,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        try:
            save_failure_diagnostics()
            print("ANDROID_E2E_FAILURE_DIAGNOSTICS_CAPTURED", flush=True)
        except Exception as diagnostic_error:
            print(f"ANDROID_E2E_DIAGNOSTICS_ERROR: {diagnostic_error}", flush=True)
        raise
