#!/usr/bin/env python3
"""Exercise Android's visible PackageInstaller UI for AFCON360 User APKs.

This intentionally does not use adb install. APKs are handed to the Android
system installer through ACTION_VIEW, the confirmation UI is inspected with
uiautomator, and the resulting package/session state is captured.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Sequence

PACKAGE_OLD = "space.pamoja.afcon360.user"
PACKAGE_PREVIEW = "space.pamoja.afcon360.user.preview"
INSTALLER_MIME = "application/vnd.android.package-archive"


class TestFailure(RuntimeError):
    pass


def run(
    args: Sequence[str],
    *,
    timeout: int = 30,
    check: bool = True,
    binary: bool = False,
) -> subprocess.CompletedProcess:
    result = subprocess.run(
        list(args),
        capture_output=True,
        text=not binary,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode != 0:
        stdout = result.stdout if isinstance(result.stdout, str) else repr(result.stdout)
        stderr = result.stderr if isinstance(result.stderr, str) else repr(result.stderr)
        raise TestFailure(
            f"Command failed ({result.returncode}): {' '.join(args)}\n"
            f"stdout: {stdout[-3000:]}\nstderr: {stderr[-3000:]}"
        )
    return result


def adb(*args: str, timeout: int = 30, check: bool = True) -> str:
    result = run(["adb", *args], timeout=timeout, check=check)
    return (result.stdout or "") + (result.stderr or "")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", errors="replace")


def capture_device_state(evidence: Path, label: str) -> None:
    write_text(evidence / f"{label}-packages.txt", adb("shell", "pm", "list", "packages"))
    write_text(evidence / f"{label}-packageinstaller.txt", adb("shell", "dumpsys", "packageinstaller", timeout=60))
    write_text(evidence / f"{label}-activity.txt", adb("shell", "dumpsys", "activity", "activities", timeout=45))
    write_text(evidence / f"{label}-logcat.txt", adb("logcat", "-d", "-v", "threadtime", "-t", "6000", timeout=45))


def capture_screenshot(evidence: Path, label: str) -> None:
    result = run(["adb", "exec-out", "screencap", "-p"], timeout=20, check=False, binary=True)
    if result.returncode == 0 and result.stdout:
        (evidence / f"{label}.png").write_bytes(result.stdout)


def dump_ui(evidence: Path, label: str) -> tuple[str, ET.Element | None]:
    adb("shell", "uiautomator", "dump", "/sdcard/afcon360-packageinstaller-window.xml", timeout=25, check=False)
    raw = adb("exec-out", "cat", "/sdcard/afcon360-packageinstaller-window.xml", timeout=15, check=False)
    write_text(evidence / f"{label}-window.xml", raw)
    try:
        root = ET.fromstring(raw)
        return raw, root
    except ET.ParseError:
        return raw, None


def visible_texts(root: ET.Element | None) -> list[str]:
    if root is None:
        return []
    return [
        value.strip()
        for node in root.iter("node")
        if (value := node.attrib.get("text", "").strip())
    ]


def find_clickable(root: ET.Element, patterns: Sequence[str]) -> tuple[int, int, str] | None:
    for node in root.iter("node"):
        text_value = node.attrib.get("text", "").strip()
        description = node.attrib.get("content-desc", "").strip()
        candidate = text_value or description
        if not candidate:
            continue
        if not any(re.fullmatch(pattern, candidate, flags=re.IGNORECASE) for pattern in patterns):
            continue
        bounds = node.attrib.get("bounds", "")
        match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
        if not match:
            continue
        left, top, right, bottom = map(int, match.groups())
        return (left + right) // 2, (top + bottom) // 2, candidate
    return None


def package_version(package: str) -> tuple[int | None, str]:
    output = adb("shell", "dumpsys", "package", package, timeout=45, check=False)
    match = re.search(r"versionCode=(\d+).*?versionName=([^\s]+)", output, flags=re.DOTALL)
    if not match:
        return None, output
    return int(match.group(1)), output


def package_path(package: str) -> str:
    return adb("shell", "pm", "path", package, timeout=20, check=False).strip()


def wait_package_manager() -> None:
    for attempt in range(60):
        service = adb("shell", "service", "check", "package", check=False)
        package_list = adb("shell", "pm", "list", "packages", check=False)
        if "found" in service.lower() and "package:" in package_list:
            print(f"ANDROID_PACKAGE_MANAGER_READY after {attempt + 1} checks")
            return
        time.sleep(2)
    raise TestFailure("Android Package Manager did not become ready")


def set_up_installer_source(evidence: Path) -> None:
    # The emulator's shell is the source opening the system installer intent.
    # Grant only the test shell the sideload app-op; this changes no APK.
    output = adb("shell", "appops", "set", "com.android.shell", "REQUEST_INSTALL_PACKAGES", "allow", check=False)
    write_text(evidence / "installer-source-appop.txt", output)
    verify = adb("shell", "appops", "get", "com.android.shell", "REQUEST_INSTALL_PACKAGES", check=False)
    write_text(evidence / "installer-source-appop-verify.txt", verify)
    if "allow" not in verify.lower():
        raise TestFailure(f"Emulator shell cannot be authorized to open PackageInstaller: {verify}")


def perform_packageinstaller_install(
    *,
    apk: Path,
    package: str,
    expected_version_code: int,
    label: str,
    evidence: Path,
) -> dict:
    if not apk.is_file() or apk.stat().st_size == 0:
        raise TestFailure(f"APK fixture is missing or empty: {apk}")

    # Prefer shared Download storage, but fall back to shell-owned staging if
    # an emulator image has not mounted emulated external storage yet.
    mkdir_result = run(
        ["adb", "shell", "mkdir", "-p", "/sdcard/Download"],
        timeout=20,
        check=False,
    )
    if mkdir_result.returncode == 0:
        remote = f"/sdcard/Download/{label}.apk"
        staging_mode = "shared-download"
    else:
        remote = f"/data/local/tmp/{label}.apk"
        staging_mode = "data-local-tmp-fallback"
    write_text(
        evidence / f"{label}-storage-staging.txt",
        f"mode={staging_mode}\\nmkdir_exit={mkdir_result.returncode}\\n"
        f"stdout={mkdir_result.stdout}\\nstderr={mkdir_result.stderr}\\n",
    )
    adb("push", str(apk), remote, timeout=90)
    remote_listing = adb("shell", "ls", "-l", remote)
    write_text(evidence / f"{label}-remote-apk.txt", remote_listing)

    # Start the Android system's own package installer activity, without adb install.
    adb("logcat", "-c")
    intent = adb(
        "shell",
        "am",
        "start",
        "-a",
        "android.intent.action.VIEW",
        "-d",
        f"file://{remote}",
        "-t",
        INSTALLER_MIME,
        "-f",
        "0x10000001",
        timeout=30,
        check=False,
    )
    write_text(evidence / f"{label}-installer-launch.txt", intent)
    if "error" in intent.lower() or "exception" in intent.lower():
        raise TestFailure(f"Android did not launch PackageInstaller: {intent}")

    tapped_install = False
    tapped_done = False
    last_texts: list[str] = []
    deadline = time.time() + 120
    while time.time() < deadline:
        raw, root = dump_ui(evidence, f"{label}-ui")
        texts = visible_texts(root)
        last_texts = texts
        lowered = " | ".join(texts).lower()

        if any(token in lowered for token in ("app not installed", "can't install app", "cannot install app")):
            capture_screenshot(evidence, f"{label}-failure")
            raise TestFailure(
                f"PackageInstaller UI reported failure for {label}: "
                + " | ".join(texts)
            )

        # Unknown-source warning must not be silently bypassed. The source app-op
        # is expected to have been granted above; record and fail if the UI still
        # requires an interactive settings detour.
        if "not allowed to install unknown apps" in lowered or "allow from this source" in lowered:
            capture_screenshot(evidence, f"{label}-unknown-source-block")
            raise TestFailure(
                f"PackageInstaller blocked the initiating source for {label}: "
                + " | ".join(texts)
            )

        actual_code, package_dump = package_version(package)
        if package_path(package) and actual_code == expected_version_code:
            write_text(evidence / f"{label}-package-dump.txt", package_dump)
            capture_screenshot(evidence, f"{label}-result")
            # Dismiss the success sheet if Done is present; do not tap Open.
            if root is not None:
                done = find_clickable(root, (r"Done",))
                if done and not tapped_done:
                    x, y, text_value = done
                    adb("shell", "input", "tap", str(x), str(y))
                    tapped_done = True
                    write_text(evidence / f"{label}-done-button.txt", f"Tapped {text_value} at {x},{y}")
            sessions = adb("shell", "dumpsys", "packageinstaller", timeout=45)
            write_text(evidence / f"{label}-sessions-after.txt", sessions)
            logcat = adb("logcat", "-d", "-v", "threadtime", "-t", "8000", timeout=45)
            write_text(evidence / f"{label}-logcat-after.txt", logcat)
            if "Session was abandoned" in sessions:
                # Old unrelated sessions can remain in history. Record only;
                # package path + expected version code is the install proof.
                write_text(evidence / f"{label}-abandoned-session-note.txt",
                           "Historical dump includes an abandoned session; package path and expected version code are present.")
            result = {
                "label": label,
                "package": package,
                "expected_version_code": expected_version_code,
                "installed_version_code": actual_code,
                "package_path": package_path(package),
                "installer_intent": intent.strip(),
                "install_button_tapped": tapped_install,
                "status": "PASS",
            }
            write_text(evidence / f"{label}-result.json", json.dumps(result, indent=2))
            print(f"PACKAGEINSTALLER_UI_PASS: {label} => {package} versionCode={actual_code}")
            return result

        if root is not None:
            # Android releases may label the confirmation button Install or Update.
            confirm = find_clickable(root, (r"Install", r"Update", r"Install anyway"))
            if confirm and not tapped_install:
                x, y, button_text = confirm
                capture_screenshot(evidence, f"{label}-confirmation")
                adb("shell", "input", "tap", str(x), str(y))
                tapped_install = True
                write_text(
                    evidence / f"{label}-confirm-button.txt",
                    f"Tapped {button_text} at {x},{y}",
                )
                time.sleep(2)
                continue

            # Some system images show a second "Next" confirmation page for apps
            # that have additional install disclosure screens.
            next_button = find_clickable(root, (r"Next", r"Continue"))
            if next_button and tapped_install:
                x, y, button_text = next_button
                adb("shell", "input", "tap", str(x), str(y))
                write_text(evidence / f"{label}-next-button.txt", f"Tapped {button_text} at {x},{y}")
                time.sleep(2)
                continue

        time.sleep(2)

    capture_screenshot(evidence, f"{label}-timeout")
    capture_device_state(evidence, f"{label}-timeout")
    raise TestFailure(
        f"PackageInstaller UI did not install {package} versionCode={expected_version_code}. "
        f"Install button tapped={tapped_install}; last visible UI: {' | '.join(last_texts)}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-api", required=True, type=int)
    parser.add_argument("--old-apk", required=True, type=Path)
    parser.add_argument("--current-apk", required=True, type=Path)
    parser.add_argument("--upgrade-apk", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    args = parser.parse_args()

    evidence = args.evidence_dir
    evidence.mkdir(parents=True, exist_ok=True)

    release = adb("shell", "getprop", "ro.build.version.release").strip()
    api = int(adb("shell", "getprop", "ro.build.version.sdk").strip())
    if api != args.expected_api:
        raise TestFailure(f"Expected Android API {args.expected_api}, emulator reports {api} ({release})")

    device = adb("get-state").strip()
    write_text(evidence / "device-info.txt", f"state={device}\nrelease={release}\napi={api}\n")
    print(f"Testing PackageInstaller UI on Android {release} / API {api}")

    wait_package_manager()
    set_up_installer_source(evidence)

    fixtures = [
        (args.old_apk, PACKAGE_OLD, 1, "fresh-1.0.0"),
        (args.current_apk, PACKAGE_PREVIEW, 1, "fresh-1.0.1"),
        (args.upgrade_apk, PACKAGE_PREVIEW, 2, "upgrade-1.0.1-to-1.0.2"),
    ]

    results = []
    for apk, package, version_code, label in fixtures:
        results.append(
            perform_packageinstaller_install(
                apk=apk,
                package=package,
                expected_version_code=version_code,
                label=label,
                evidence=evidence,
            )
        )

    summary = {
        "android_release": release,
        "android_api": api,
        "tests": results,
        "overall": "PASS",
        "note": "Uses Android ACTION_VIEW and visible PackageInstaller UI; it does not use adb install.",
    }
    write_text(evidence / "summary.json", json.dumps(summary, indent=2))
    print(f"USER_PACKAGEINSTALLER_UI_MATRIX_PASS: Android API {api}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TestFailure as error:
        print(f"USER_PACKAGEINSTALLER_UI_TEST_FAILURE: {error}", file=sys.stderr)
        raise SystemExit(1)
