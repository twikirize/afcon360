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
APK_PATH = os.environ.get("AFCON360_USER_E2E_APK", "mobile-e2e-evidence/user-e2e.apk")

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


def run_adb(
    *args: str,
    check: bool = True,
    capture: bool = True,
    timeout: int = 120,
) -> str:
    try:
        result = subprocess.run(
            ["adb", *args], check=False, text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.STDOUT if capture else None,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        output = error.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        raise RuntimeError(
            f"adb {' '.join(args[:4])} timed out after {timeout}s: "
            f"{str(output)[-2000:]}"
        ) from error

    output = result.stdout or ""
    if check and result.returncode:
        raise RuntimeError(f"adb {' '.join(args[:4])} failed ({result.returncode}): {output[-2000:]}")
    return output


def dump_tree(retries: int = 4) -> ET.Element:
    """Read a fresh UI hierarchy, retrying transient Android UIAutomator bridge failures.

    Older emulator images can briefly return "null root node" even while the
    app's Activity is visible and rendering. Retry those snapshot failures, but
    still fail the test if no valid hierarchy can be obtained after the bounded
    retry window. Never reuse an old UI tree.
    """
    last_error = "Android did not return a UI hierarchy."
    for attempt in range(1, retries + 1):
        run_adb("shell", "rm", "-f", UI_XML, check=False)
        result = run_adb("shell", "uiautomator", "dump", UI_XML, check=False, timeout=15)
        if "dumped to:" not in result.lower():
            last_error = (
                "Android did not create a fresh UI hierarchy: "
                + result[-1000:]
            )
        else:
            raw = run_adb("shell", "cat", UI_XML, check=False, timeout=15)
            start = raw.find("<?xml")
            if start < 0:
                last_error = (
                    "Fresh Android UI hierarchy was not readable: "
                    + raw[-1000:]
                )
            else:
                try:
                    return ET.fromstring(raw[start:])
                except ET.ParseError as error:
                    last_error = f"Fresh Android UI hierarchy was not valid XML: {error}"

        if attempt < retries:
            print(
                "ANDROID_UI_TREE_RETRY: "
                f"snapshot attempt {attempt}/{retries} failed; retrying: "
                + last_error.replace("\\n", " ")[:500],
                flush=True,
            )
            time.sleep(min(0.5 * attempt, 1.5))

    raise RuntimeError(
        f"Android could not produce a fresh UI hierarchy after {retries} attempts: "
        + last_error[-1000:]
    )


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
    if right <= left or bottom <= top:
        return None
    return ((left + right) // 2, (top + bottom) // 2)


def tap_text(value: str, *, last: bool = False, timeout: int = 12) -> None:
    """Tap a visible text target through its real clickable ancestor when needed.

    Android versions differ in how UIAutomator reports bounds for nested
    React Native Text nodes. Some return [0,0][0,0] for a visible tab label;
    tapping that Text node would silently tap screen coordinate (0,0). Walk
    up the native hierarchy and prefer the nearest enabled clickable parent.
    """
    deadline = time.monotonic() + timeout
    last_diagnostics = []
    while time.monotonic() < deadline:
        try:
            root = dump_tree()
            parents = {
                child: parent
                for parent in root.iter("node")
                for child in parent
            }
            matches = []
            for node in root.iter("node"):
                text_value = node.attrib.get("text", "").strip()
                description = node.attrib.get("content-desc", "").strip()
                if text_value != value and description != value:
                    continue

                matched = {
                    "class": node.attrib.get("class", ""),
                    "clickable": node.attrib.get("clickable", ""),
                    "enabled": node.attrib.get("enabled", ""),
                    "bounds": node.attrib.get("bounds", ""),
                    "text": text_value,
                    "content_desc": description,
                }

                ancestor = node
                nearest_visible = None
                clickable_target = None
                depth = 0
                while ancestor is not None:
                    center = bounds_center(ancestor.attrib.get("bounds", ""))
                    if center is not None:
                        candidate = {
                            "center": center,
                            "bounds": ancestor.attrib.get("bounds", ""),
                            "class": ancestor.attrib.get("class", ""),
                            "clickable": ancestor.attrib.get("clickable", ""),
                            "enabled": ancestor.attrib.get("enabled", ""),
                            "depth": depth,
                        }
                        if nearest_visible is None:
                            nearest_visible = candidate
                        if (
                            candidate["clickable"] == "true"
                            and candidate["enabled"] != "false"
                        ):
                            clickable_target = candidate
                            break
                    ancestor = parents.get(ancestor)
                    depth += 1

                target = clickable_target or nearest_visible
                if target is not None:
                    matches.append({
                        "matched_node": matched,
                        "target_node": target,
                        "target_source": (
                            "nearest-clickable-ancestor"
                            if clickable_target is not None
                            else "nearest-visible-ancestor"
                        ),
                    })

            if matches:
                chosen = matches[-1] if last else matches[0]
                x, y = chosen["target_node"]["center"]
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
            last_diagnostics = [
                f"matching text {value!r} was found without any usable bounds"
            ]
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
            print(f"PASS: tapped after {attempt} scroll(s): {value}", flush=True)
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


def dismiss_aosp_keyboard_contacts_prompt(timeout: int = 5) -> bool:
    """Deny the optional AOSP keyboard contacts prompt used by older AVD images.

    Android 7.x default system images can surface this OS permission sheet the
    first time Android Keyboard (AOSP) receives text input. It overlays the
    app's sign-in button and makes the background button appear to UIAutomator
    without usable bounds. AFCON360's login flow does not require keyboard
    contacts access, so deny only this known prompt and verify it closes.
    """
    deadline = time.monotonic() + timeout
    prompt = "Allow Android Keyboard (AOSP) to access your contacts?"
    while time.monotonic() < deadline:
        root = dump_tree()
        visible = " ".join(
            value for value in (node_value(node) for node in root.iter("node")) if value
        )
        if prompt in visible:
            tap_text("DENY", timeout=8)
            verify_deadline = time.monotonic() + 8
            while time.monotonic() < verify_deadline:
                root = dump_tree()
                visible = " ".join(
                    value for value in (node_value(node) for node in root.iter("node")) if value
                )
                if prompt not in visible:
                    print(
                        "ANDROID_SYSTEM_PERMISSION_HANDLED: denied optional "
                        "AOSP keyboard contacts access.",
                        flush=True,
                    )
                    return True
                time.sleep(0.4)
            raise AssertionError(
                "The AOSP keyboard contacts permission dialog remained visible after DENY."
            )
        time.sleep(0.4)
    return False


def save_screen(name: str) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    data = subprocess.run(
        ["adb", "exec-out", "screencap", "-p"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout
    # Preserve the visual checkpoint even if Android's accessibility bridge
    # transiently fails to provide a hierarchy snapshot.
    (EVIDENCE / f"{name}.png").write_bytes(data)
    root = dump_tree()
    (EVIDENCE / f"{name}.xml").write_bytes(ET.tostring(root, encoding="utf-8"))
    (EVIDENCE / f"{name}.txt").write_text(
        "\n".join(filter(None, (node_value(node) for node in root.iter("node")))),
        encoding="utf-8",
    )


def return_to_explore() -> None:
    """Return to Explore and verify a stable action, even when scroll is preserved."""
    run_adb("shell", "input", "keyevent", "4")
    time.sleep(1)
    try:
        # Android can restore Explore at the previous scroll offset. The top
        # heading is therefore not a reliable screen identity check. The Stays
        # action is present on the Explore service list at both tested offsets.
        wait_for_text("Find and book a stay", timeout=8, label="Explore after Android Back")
    except AssertionError:
        # If Back leaves us on another tab, explicitly select Explore and then
        # verify its stable Stays action rather than assuming scroll-to-top.
        tap_text("Explore", last=True)
        wait_for_text("Find and book a stay", timeout=20, label="Explore tab")


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

    capture("failure-logcat-full.txt", "logcat", "-b", "all", "-d", "-t", "4000")
    capture(
        "failure-logcat-errors.txt", "logcat", "-d", "-t", "4000",
        "AndroidRuntime:E", "ReactNativeJS:E", "ReactNative:E", "Expo:E",
        "system_server:E", "PackageManager:E", "PackageManagerService:E",
        "ActivityManager:E", "installd:E", "*:S",
    )
    capture("failure-foreground-activity.txt", "shell", "dumpsys", "activity", "activities")
    capture("failure-focused-window.txt", "shell", "dumpsys", "window", "windows")
    capture("failure-package-path.txt", "shell", "pm", "path", PACKAGE)
    capture("failure-process.txt", "shell", "pidof", PACKAGE)
    capture("failure-ui-dump-command.txt", "shell", "uiautomator", "dump", UI_XML)
    capture("failure-ui-hierarchy.xml", "shell", "cat", UI_XML)



def wait_for_android_package_manager(timeout: int = 120, stable_checks: int = 3) -> None:
    """Wait for several consecutive successful Package Manager Binder checks.

    Some Android 17 CI emulator boots report sys.boot_completed before the
    package service is usable, or briefly expose the service before it drops.
    Requiring consecutive successful checks avoids treating one brief response
    as proof that Android is ready to install an APK.
    """
    deadline = time.monotonic() + timeout
    last_service = ""
    last_packages = ""
    consecutive_ready = 0
    while time.monotonic() < deadline:
        last_service = run_adb("shell", "service", "check", "package", check=False)
        last_packages = run_adb("shell", "pm", "list", "packages", check=False)
        package_service_ready = "found" in last_service.lower()
        package_list_ready = any(
            line.strip().startswith("package:")
            for line in last_packages.splitlines()
        )
        if package_service_ready and package_list_ready:
            consecutive_ready += 1
            if consecutive_ready >= stable_checks:
                print(
                    "ANDROID_PACKAGE_MANAGER_READY: system package service "
                    f"responded successfully {stable_checks} consecutive times.",
                    flush=True,
                )
                return
        else:
            consecutive_ready = 0
        time.sleep(2)

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "package-manager-readiness.txt").write_text(
        "service check output:\n"
        + last_service
        + "\npackage list output:\n"
        + last_packages
        + "\n",
        encoding="utf-8",
    )
    raise RuntimeError(
        "ANDROID_TEST_INFRA_FAILURE: Android reported boot completion but its "
        f"Package Manager service did not remain usable for {stable_checks} "
        f"consecutive checks within {timeout} seconds."
    )


def install_user_apk_with_retries(apk_path: str, attempts: int = 3) -> None:
    """Retry only when Android's Package Manager Binder service has broken."""
    for attempt in range(1, attempts + 1):
        try:
            run_adb("install", "--no-streaming", apk_path)
            return
        except RuntimeError as error:
            message = str(error).lower()
            transient_package_service_error = (
                "failure calling service package" in message
                or "broken pipe" in message
            )
            if not transient_package_service_error or attempt >= attempts:
                raise

            print(
                "ANDROID_TEST_INFRA_RETRY: Package Manager Binder failed during "
                f"APK install (attempt {attempt}/{attempts}); waiting for a "
                "stable service before retrying.",
                flush=True,
            )
            try:
                wait_for_android_package_manager(timeout=60, stable_checks=5)
            except RuntimeError as readiness_error:
                raise RuntimeError(
                    f"{error}; Package Manager did not recover: {readiness_error}"
                ) from error
            time.sleep(3)


def main() -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text(json.dumps({"completed_stages": []}, indent=2) + "\n", encoding="utf-8")
    run_adb("wait-for-device")
    wait_for_android_package_manager()
    run_adb("reverse", "tcp:5000", "tcp:5000")
    install_user_apk_with_retries(APK_PATH)
    run_adb("shell", "monkey", "-p", PACKAGE, "-c", "android.intent.category.LAUNCHER", "1")

    wait_for_text("AFCON360 User", "Sign in securely", label="native sign-in screen")
    save_screen("01-login")
    mark_stage("login_screen")

    tap_edit_field("Username or email")
    type_text(USERNAME)
    tap_edit_field("Password")
    type_text(PASSWORD)
    dismiss_aosp_keyboard_contacts_prompt()
    run_adb("shell", "input", "keyevent", "4")
    tap_text("Sign in securely")

    wait_for_text("Welcome to Pamoja", f"Good to see you, {USERNAME}.", timeout=45, label="authenticated User home")
    save_screen("02-home")
    mark_stage("authenticated_home")

    mark_stage("activity_navigation_started")
    tap_text("Activity", last=True)
    wait_for_text("Your rides and bookings.", "No rides yet", timeout=35, label="authenticated ride activity")
    save_screen("03-activity")
    mark_stage("activity_screen")

    mark_stage("wallet_navigation_started")
    tap_text("Wallet", last=True)
    wait_for_text(
        "Your money, clearly managed.", "Wallet accounts", "No Wallet account is active yet.",
        timeout=35, label="authenticated Wallet read views",
    )
    save_screen("04-wallet")
    mark_stage("wallet_screen")

    tap_text("Account", last=True)
    wait_for_text("Your AFCON360 identity.", timeout=25, label="authenticated account")
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

    # Verify that both native location inputs reach the shared GEO endpoint
    # and display its truthful empty state when a deliberately unique query
    # has no provider match. This does not create a booking or touch Wallet.
    tap_edit_field("Pickup location")
    type_text("AFCON360E2ENoSuchPickup92746215")
    wait_for_text(
        "No matching places were found.",
        timeout=30,
        label="native pickup GEO search empty state",
    )
    mark_stage("pickup_geo_search_empty_state")

    # Dismiss Android's soft keyboard before targeting the second field. On
    # compact emulators the keyboard can cover the destination input.
    run_adb("shell", "input", "keyevent", "4")
    tap_edit_field("Destination")
    type_text("AFCON360E2ENoSuchDestination92746215")
    deadline = time.monotonic() + 30
    last_visible = ""
    while time.monotonic() < deadline:
        last_visible = visible_text()
        if last_visible.count("No matching places were found.") >= 2:
            print(
                "PASS: native pickup and destination fields both show the GEO empty state.",
                flush=True,
            )
            break
        time.sleep(1)
    else:
        raise AssertionError(
            "Destination GEO search did not show its own empty state. "
            f"Visible screen text:\n{last_visible[:6000]}"
        )
    save_screen("07a-pickup-destination-geo-search")
    mark_stage("pickup_and_destination_geo_search")

    # The destination TextInput still owns Android's soft keyboard. Dismiss
    # it before return_to_explore sends the separate navigation Back action.
    run_adb("shell", "input", "keyevent", "4")
    time.sleep(0.5)
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
    wait_for_text("Welcome to Pamoja", f"Good to see you, {USERNAME}.", timeout=45, label="restored authenticated session")
    save_screen("10-session-restored")
    mark_stage("session_restored")

    tap_text("Account", last=True)
    wait_for_text("Your AFCON360 identity.", label="account before logout")
    tap_text_scrolling("Sign out")
    tap_text("Sign out")
    wait_for_text("Sign out of AFCON360 on this device?", timeout=12, label="logout confirmation")
    mark_stage("logout_started")
    # The Android confirmation action is rendered in uppercase; target that
    # actual dialog button, not its title or the underlying Account action.
    tap_text("SIGN OUT")
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
