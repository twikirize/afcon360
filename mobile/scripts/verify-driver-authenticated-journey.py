#!/usr/bin/env python3
"""Android UI proof for the AFCON360 Driver preview APK against disposable CI.

The journey signs in a synthetic driver, reads Driver-only screens, kills and
relaunches the Android process to test SecureStore session restoration, then
uses server-side logout. It deliberately performs no dispatch, status, GPS,
booking, payment or financial write.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

PACKAGE = "space.pamoja.afcon360.driver.preview"
USERNAME = os.environ.get("AFCON360_DRIVER_E2E_USERNAME", "native_e2e_driver")
PASSWORD = os.environ.get("AFCON360_DRIVER_E2E_PASSWORD", "DriverE2ePassword2026")
DRIVER_CODE = "E2E-DRV01"
EVIDENCE = Path(os.environ.get("AFCON360_DRIVER_E2E_EVIDENCE_DIR", "driver-e2e-evidence"))
UI_XML = "/sdcard/afcon360-driver-e2e-ui.xml"


def run_adb(*args: str, check: bool = True, timeout: int = 45) -> str:
    result = subprocess.run(
        ["adb", *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    output = result.stdout or ""
    if check and result.returncode:
        raise RuntimeError(
            f"adb {' '.join(args[:4])} failed ({result.returncode}): {output[-2000:]}"
        )
    return output


def dump_tree() -> ET.Element:
    # Do not accept a stale hierarchy when Android fails to produce a new one.
    run_adb("shell", "rm", "-f", UI_XML, check=False)
    result = run_adb("shell", "uiautomator", "dump", UI_XML, check=False, timeout=60)
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


def wait_for_text(*needles: str, timeout: int = 40, label: str = "screen") -> str:
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
        f"Timed out waiting for {label}: {needles}. Last visible hierarchy:\n{last[:7000]}"
    )


def bounds_center(value: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", value or "")
    if not match:
        return None
    left, top, right, bottom = map(int, match.groups())
    return ((left + right) // 2, (top + bottom) // 2)


def scroll_until_text(value: str, *, max_swipes: int = 10, label: str = "screen") -> str:
    """Scroll a long native screen until its requested control is actually visible."""
    last = ""
    for _ in range(max_swipes + 1):
        try:
            last = visible_text()
        except Exception:
            time.sleep(0.5)
            continue
        if value in last:
            print(f"PASS: {label}: {value}", flush=True)
            return last
        run_adb("shell", "input", "swipe", "540", "1900", "540", "700", "450")
        time.sleep(0.5)
    raise AssertionError(
        f"Could not scroll {label} to {value!r}. Last visible hierarchy:\\n{last[:7000]}"
    )


def scroll_to_top(*, max_swipes: int = 10, label: str = "screen") -> str:
    """Return a restored long screen to its top before asserting its page header."""
    last = ""
    for _ in range(max_swipes):
        try:
            last = visible_text()
        except Exception:
            last = ""
        if "Your AFCON360 identity." in last:
            print(f"PASS: {label}: Account page top is visible", flush=True)
            return last
        # Finger moves downward, revealing the upper part of the scroll view.
        run_adb("shell", "input", "swipe", "540", "700", "540", "1900", "450")
        time.sleep(0.45)
    last = visible_text()
    if "Your AFCON360 identity." not in last:
        raise AssertionError(
            f"Could not return {label} to the Account page header. "
            f"Last visible hierarchy:\\n{last[:7000]}"
        )
    print(f"PASS: {label}: Account page top is visible", flush=True)
    return last


def tap_text(value: str, *, last: bool = False, timeout: int = 15) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            root = dump_tree()
            matches = []
            for node in root.iter("node"):
                if (
                    node.attrib.get("text", "").strip() == value
                    or node.attrib.get("content-desc", "").strip() == value
                ):
                    center = bounds_center(node.attrib.get("bounds", ""))
                    if center:
                        matches.append(center)
            if matches:
                x, y = matches[-1] if last else matches[0]
                run_adb("shell", "input", "tap", str(x), str(y))
                time.sleep(0.8)
                return
        except Exception:
            pass
        time.sleep(0.6)
    raise AssertionError(f"Could not find tappable Android UI text: {value!r}")


def _edit_text_node(root: ET.Element, label: str) -> ET.Element | None:
    """Return only the actual labelled native EditText, never its wrapper or label."""
    for node in root.iter("node"):
        if (
            "EditText" in node.attrib.get("class", "")
            and node.attrib.get("content-desc", "").strip() == label
        ):
            if bounds_center(node.attrib.get("bounds", "")):
                return node
    return None


def tap_edit_field(label: str) -> None:
    root = dump_tree()
    node = _edit_text_node(root, label)
    if node is None:
        # Report only class names and node counts. Do not dump text, content
        # descriptions, typed identifiers, passwords or any user-entered value.
        edit_nodes = [
            item for item in root.iter("node")
            if "EditText" in item.attrib.get("class", "")
        ]
        classes = sorted({item.attrib.get("class", "unknown") for item in edit_nodes})
        raise AssertionError(
            f"Could not locate the actual labelled EditText for {label!r}; "
            f"visible_edit_text_count={len(edit_nodes)}, classes={classes!r}. "
            "Refusing to tap a generic wrapper or submit an unintended account."
        )
    center = bounds_center(node.attrib.get("bounds", ""))
    if center is None:
        raise AssertionError(f"The labelled EditText for {label!r} has no usable bounds.")
    x, y = center
    run_adb("shell", "input", "tap", str(x), str(y))
    time.sleep(0.4)


def assert_edit_text_value(label: str, expected: str, *, timeout: int = 8) -> None:
    """Prove that Android placed the intended text in the intended input field."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        root = dump_tree()
        node = _edit_text_node(root, label)
        if node is not None and node.attrib.get("text", "") == expected:
            print(f"PASS: intended value is present in the {label!r} input", flush=True)
            return
        time.sleep(0.4)
    # Do not echo actual or expected field contents into CI logs.
    raise AssertionError(
        f"The {label!r} input did not contain the expected CI value after typing. "
        "The test stopped before submitting a login request."
    )


def type_text(value: str) -> None:
    # CI-only credentials are intentionally shell-safe ASCII without spaces.
    if not re.fullmatch(r"[A-Za-z0-9._@+-]+", value):
        raise ValueError("The synthetic CI input contains unsupported characters.")
    run_adb("shell", "input", "text", value)
    time.sleep(0.3)


def save_screen(name: str) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    image = subprocess.run(
        ["adb", "exec-out", "screencap", "-p"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=45,
    ).stdout
    (EVIDENCE / f"{name}.png").write_bytes(image)
    (EVIDENCE / f"{name}.txt").write_text(visible_text(), encoding="utf-8")


def save_failure_diagnostics() -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    def capture(name: str, *args: str) -> None:
        try:
            result = subprocess.run(
                ["adb", *args],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=45,
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
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=45,
        ).stdout
        if image:
            (EVIDENCE / "failure-screen.png").write_bytes(image)
    except Exception as error:
        (EVIDENCE / "failure-screen-error.txt").write_text(
            f"{type(error).__name__}: {error}\n", encoding="utf-8"
        )

    capture(
        "failure-logcat-errors.txt",
        "logcat", "-d", "-t", "3000",
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
    run_adb("wait-for-device", timeout=180)
    run_adb("reverse", "tcp:5000", "tcp:5000")
    run_adb("install", "-r", "driver-e2e-evidence/driver-e2e.apk", timeout=120)
    run_adb(
        "shell", "monkey", "-p", PACKAGE, "-c", "android.intent.category.LAUNCHER", "1"
    )

    wait_for_text(
        "AFCON360 Driver", "Username or email", "Password", "Sign in to Driver",
        label="Driver native sign-in screen",
    )
    save_screen("01-login")

    tap_edit_field("Username or email")
    type_text(USERNAME)
    assert_edit_text_value("Username or email", USERNAME)
    tap_edit_field("Password")
    type_text(PASSWORD)
    run_adb("shell", "input", "keyevent", "4")
    tap_text("Sign in to Driver")

    wait_for_text(
        "Your driving workspace.", DRIVER_CODE,
        timeout=60, label="authenticated Driver home",
    )
    save_screen("02-driver-home")
    # The readiness action sits below the profile details on smaller screens.
    run_adb("shell", "input", "swipe", "540", "1900", "540", "700", "450")
    wait_for_text(
        "Complete checks to go online",
        timeout=20, label="go-online action gated by the server readiness checklist",
    )

    tap_text("Status", last=True)
    wait_for_text(
        "Your operating status.",
        timeout=60, label="Driver operating status",
    )
    scroll_until_text("Operating preferences", label="Driver operating preferences")
    wait_for_text("Operating preferences", label="Driver operating preferences section")
    scroll_until_text("Compliance status", label="Driver compliance section")
    wait_for_text("Compliance status", label="Driver compliance section visible")
    save_screen("03-status")

    tap_text("Trips", last=True)
    wait_for_text(
        "Your assigned work.", "No active trip",
        timeout=30, label="Driver active-trip empty state",
    )
    save_screen("03-trips")
    scroll_until_text("Trip history", label="Driver trip history filters")
    tap_text("All", last=True)
    wait_for_text(
        "Trip history", "No recent trips",
        timeout=60, label="All Driver trip history filter",
    )
    save_screen("04-all-trips")

    tap_text("Earnings", last=True)
    wait_for_text(
        "Know what you have earned.", "No captured earnings yet",
        timeout=30, label="Driver captured-earnings empty state",
    )
    save_screen("06-earnings")

    tap_text("Assignments", last=True)
    wait_for_text(
        "Your assigned transport.", "Current assigned vehicle",
        timeout=60, label="Driver current vehicle assignment",
    )
    scroll_until_text("Scheduled work", label="Driver scheduled routes section")
    wait_for_text("Scheduled work", label="Driver scheduled routes section visible")
    scroll_until_text("Vehicle history", label="Driver vehicle assignment history")
    wait_for_text("Vehicle history", label="Driver vehicle history section visible")
    save_screen("07-assignments")

    tap_text("Vehicles", last=True)
    wait_for_text(
        "Your vehicles and opportunities.", "Vehicles you own",
        timeout=60, label="Driver owned vehicles",
    )
    scroll_until_text("Vehicle marketplace", label="Driver public vehicle marketplace")
    wait_for_text("Vehicle marketplace", label="Driver vehicle marketplace section visible")
    save_screen("08-vehicles")

    tap_text("Account", last=True)
    wait_for_text(
        "Your AFCON360 identity.", "Signed in securely",
        timeout=30, label="authenticated Driver account",
    )
    scroll_until_text("Transport notifications", label="Driver account notification link")
    tap_text("Transport notifications")
    wait_for_text(
        "Your Driver inbox.", "Inbox", "No Transport notifications",
        timeout=60, label="Driver notification inbox (read-only)",
    )
    save_screen("09-notifications")
    tap_text("Back to Driver account")
    # router.back() restores the previous scroll offset; return to the top
    # before checking the Account heading and moving to the next section.
    scroll_to_top(label="Driver account after notification review")
    wait_for_text("Your AFCON360 identity.", label="Driver account after notification review")

    scroll_until_text("Report a safety or service incident", label="Driver account incident link")
    tap_text("Report a safety or service incident")
    wait_for_text(
        "Report an incident.",
        timeout=60, label="Driver incident report form",
    )
    scroll_until_text("Your incident reports", label="Driver incident history")
    wait_for_text("Your incident reports", label="Driver incident history section visible")
    save_screen("10-incidents")
    scroll_until_text(
        "Back to Driver account",
        label="Driver incident return control",
    )
    tap_text("Back to Driver account")
    scroll_to_top(label="Driver account after incident review")
    wait_for_text("Your AFCON360 identity.", label="Driver account before process restart")
    scroll_until_text("Sign out", label="authenticated Driver account sign-out control")
    save_screen("11-account")



    # Kill the real Android process, not just navigate away, then prove the
    # driver session restores from the app's SecureStore token pair.
    run_adb("shell", "am", "force-stop", PACKAGE)
    time.sleep(1)
    run_adb(
        "shell", "monkey", "-p", PACKAGE, "-c", "android.intent.category.LAUNCHER", "1"
    )
    wait_for_text(
        "Your driving workspace.", DRIVER_CODE,
        timeout=60, label="restored authenticated Driver session",
    )
    save_screen("12-session-restored")

    tap_text("Account", last=True)
    wait_for_text("Your AFCON360 identity.", label="Driver account before logout")
    scroll_until_text("Sign out", label="Driver account sign-out control after process restart")
    tap_text("Sign out", last=True)
    wait_for_text(
        "Sign out this driver device?",
        timeout=15, label="Driver logout confirmation",
    )
    # Android renders the Alert action in uppercase; the Account-page
    # button behind the modal remains title-cased and must not be tapped.
    tap_text("SIGN OUT", last=True)
    wait_for_text(
        "AFCON360 Driver", "Username or email", "Password", "Sign in to Driver",
        timeout=45, label="Driver signed-out login screen",
    )
    save_screen("13-logged-out")

    print(
        "DRIVER_ANDROID_E2E_UI_PASS: Driver login, status/readiness, map and demand, "
        "active trip and trip history, earnings, assignments, owned vehicles and marketplace, "
        "notifications, incident history, account, process-death session restore and logout. "
        "No dispatch, status/location, vehicle, booking, incident or payment write was performed.",
        flush=True,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        save_failure_diagnostics()
        raise
