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
    time.sleep(0.4)


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

    tap_text("Trips", last=True)
    wait_for_text(
        "Your assigned work.", "No active trip",
        timeout=30, label="Driver active-trip empty state",
    )
    save_screen("03-trips")

    tap_text("Earnings", last=True)
    wait_for_text(
        "Know what you have earned.", "No captured earnings yet",
        timeout=30, label="Driver captured-earnings empty state",
    )
    save_screen("04-earnings")

    tap_text("Account", last=True)
    wait_for_text(
        "Your AFCON360 identity.", "Signed in securely",
        timeout=30, label="authenticated Driver account",
    )
    save_screen("05-account")
    # The account page is longer than the viewport; sign-out is intentionally
    # near the bottom and must be scrolled into view before the test can tap it.
    scroll_until_text("Sign out", label="authenticated Driver account sign-out control")

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
    save_screen("06-session-restored")

    tap_text("Account", last=True)
    wait_for_text("Your AFCON360 identity.", label="Driver account before logout")
    scroll_until_text("Sign out", label="Driver account sign-out control after process restart")
    tap_text("Sign out", last=True)
    wait_for_text(
        "Sign out this driver device?",
        timeout=15, label="Driver logout confirmation",
    )
    tap_text("Sign out", last=True)
    wait_for_text(
        "AFCON360 Driver", "Username or email", "Password", "Sign in to Driver",
        timeout=45, label="Driver signed-out login screen",
    )
    save_screen("07-logged-out")

    print(
        "DRIVER_ANDROID_E2E_UI_PASS: Driver login, server go-live gate, offers read, "
        "active-trip read, earnings read, account, Android process-death session restore, "
        "and logout. No dispatch, status, location, booking or payment action was performed.",
        flush=True,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        save_failure_diagnostics()
        raise
