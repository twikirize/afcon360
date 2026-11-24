#!/usr/bin/env python3
"""Exercise Android's visible PackageInstaller UI for AFCON360 User APKs.

This intentionally does not use adb install. APKs are handed to the Android
system installer through ACTION_INSTALL_PACKAGE using a MediaStore content URI.
The confirmation UI is inspected with uiautomator, and resulting package/session
state is captured.
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
from urllib.parse import urlsplit

PACKAGE_OLD = "space.pamoja.afcon360.user"
PACKAGE_PREVIEW = "space.pamoja.afcon360.user.preview"
INSTALLER_MIME = "application/vnd.android.package-archive"


class TestFailure(RuntimeError):
    pass


class InfrastructureFailure(TestFailure):
    """ADB, emulator boot, PackageManager or MediaProvider infrastructure failure."""

    pass


def run(
    args: Sequence[str],
    *,
    timeout: int = 30,
    check: bool = True,
    binary: bool = False,
) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            list(args),
            capture_output=True,
            text=not binary,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout or ""
        stderr = error.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        if check:
            message = (
                f"Command timed out after {timeout}s: {' '.join(args)}\n"
                f"stdout: {stdout[-3000:]}\nstderr: {stderr[-3000:]}"
            )
            if args and Path(args[0]).name.lower() == "adb":
                raise InfrastructureFailure(message) from error
            raise TestFailure(message) from error
        return subprocess.CompletedProcess(list(args), 124, stdout, stderr)

    if check and result.returncode != 0:
        stdout = result.stdout if isinstance(result.stdout, str) else repr(result.stdout)
        stderr = result.stderr if isinstance(result.stderr, str) else repr(result.stderr)
        message = (
            f"Command failed ({result.returncode}): {' '.join(args)}\n"
            f"stdout: {stdout[-3000:]}\nstderr: {stderr[-3000:]}"
        )
        if args and Path(args[0]).name.lower() == "adb":
            raise InfrastructureFailure(message)
        raise TestFailure(message)
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
    # Keep UIAutomator evidence in shell-owned storage, not /sdcard shared storage.
    remote_xml = "/data/local/tmp/afcon360-packageinstaller-window.xml"
    dump = adb("shell", "uiautomator", "dump", remote_xml, timeout=40, check=False)
    raw = adb("exec-out", "cat", remote_xml, timeout=20, check=False)
    write_text(evidence / f"{label}-window.xml", raw)
    if "ERROR" in dump.upper() and not raw.strip().startswith("<?xml"):
        write_text(evidence / f"{label}-uiautomator-error.txt", dump + "\n" + raw)
        return raw, None
    try:
        return raw, ET.fromstring(raw)
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


def parse_bounds(value: str) -> tuple[int, int, int, int] | None:
    match = re.fullmatch(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", value.strip())
    if not match:
        return None
    left, top, right, bottom = map(int, match.groups())
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def find_clickable(
    root: ET.Element,
    patterns: Sequence[str],
    screen_size: tuple[int, int],
) -> tuple[int, int, str] | None:
    """Find a matching text/content-description node or its enabled clickable ancestor."""
    parents = {child: parent for parent in root.iter() for child in parent}
    width, height = screen_size
    for node in root.iter("node"):
        candidates = [
            node.attrib.get("text", "").strip(),
            node.attrib.get("content-desc", "").strip(),
        ]
        matched = next(
            (
                candidate for candidate in candidates if candidate
                and any(re.fullmatch(pattern, candidate, flags=re.IGNORECASE) for pattern in patterns)
            ),
            None,
        )
        if matched is None:
            continue
        current: ET.Element | None = node
        while current is not None:
            attrs = current.attrib
            if (
                attrs.get("clickable", "false").lower() == "true"
                and attrs.get("enabled", "false").lower() == "true"
                and attrs.get("visible-to-user", "true").lower() != "false"
            ):
                bounds = parse_bounds(attrs.get("bounds", ""))
                if bounds is not None:
                    left, top, right, bottom = bounds
                    x, y = (left + right) // 2, (top + bottom) // 2
                    if left >= 0 and top >= 0 and right <= width and bottom <= height:
                        return x, y, matched
            current = parents.get(current)
    return None

def package_version(package: str) -> tuple[int | None, str | None, str]:
    output = adb("shell", "dumpsys", "package", package, timeout=45, check=False)
    match = re.search(
        r"\bversionCode=(\d+).*?\bversionName=([^\s]+)",
        output,
        flags=re.DOTALL,
    )
    if not match:
        return None, None, output
    return int(match.group(1)), match.group(2).strip("\"'"), output

def package_path(package: str) -> str:
    return adb("shell", "pm", "path", package, timeout=20, check=False).strip()


def wait_android_ready(evidence: Path, timeout_seconds: int = 900) -> tuple[str, int]:
    """Wait for ADB, Android boot, PackageManager and MediaProvider."""
    deadline = time.monotonic() + timeout_seconds
    last_state = ""
    while time.monotonic() < deadline:
        devices = adb("devices", check=False)
        online = [
            line.split()[0]
            for line in devices.splitlines()[1:]
            if len(line.split()) >= 2 and line.split()[1] == "device"
        ]
        state = adb("get-state", check=False).strip()
        boot = adb("shell", "getprop", "sys.boot_completed", check=False).strip()
        service = adb("shell", "service", "check", "package", check=False)
        last_state = (
            f"adb_devices={devices.strip()}\nadb_state={state}\n"
            f"sys.boot_completed={boot}\npackage_service={service}"
        )
        if online and state == "device" and boot == "1" and "found" in service.lower():
            packages = adb("shell", "pm", "list", "packages", check=False)
            if "package:" in packages:
                provider = run(
                    [
                        "adb", "shell", "content", "query",
                        "--uri", "content://media/external/file",
                        "--projection", "_id",
                    ],
                    timeout=30,
                    check=False,
                )
                provider_output = (provider.stdout or "") + (provider.stderr or "")
                write_text(evidence / "mediaprovider-readiness.txt", provider_output)
                provider_error = any(
                    marker in provider_output.lower()
                    for marker in (
                        "no content provider", "unknown uri", "failed to find provider",
                        "securityexception", "does not exist",
                    )
                )
                if provider.returncode == 0 and not provider_error:
                    release = adb("shell", "getprop", "ro.build.version.release").strip()
                    api_text = adb("shell", "getprop", "ro.build.version.sdk").strip()
                    if not api_text.isdigit():
                        raise InfrastructureFailure(
                            f"Emulator returned an invalid Android API value: {api_text!r}"
                        )
                    write_text(
                        evidence / "device-info.txt",
                        f"state=device\nrelease={release}\napi={api_text}\n"
                        "package_manager=ready\nmediaprovider=ready\n",
                    )
                    print(f"ANDROID_READY: Android {release} / API {api_text}; MediaProvider ready")
                    return release, int(api_text)
        time.sleep(5)

    write_text(evidence / "android-readiness-failure.txt", last_state)
    raise InfrastructureFailure(
        f"Android emulator did not become ready within {timeout_seconds}s.\n{last_state}"
    )


def screen_size() -> tuple[int, int]:
    output = adb("shell", "wm", "size", timeout=20)
    matches = re.findall(r"(?:Physical|Override) size:\s*(\d+)x(\d+)", output)
    if not matches:
        raise InfrastructureFailure(f"Could not determine emulator display size: {output}")
    width, height = map(int, matches[-1])
    if width <= 0 or height <= 0:
        raise InfrastructureFailure(f"Invalid emulator display size: {width}x{height}")
    return width, height

def set_up_installer_source(evidence: Path) -> None:
    # The emulator's shell is the source opening the system installer intent.
    # Grant only the test shell the sideload app-op; this changes no APK.
    output = adb("shell", "appops", "set", "com.android.shell", "REQUEST_INSTALL_PACKAGES", "allow", check=False)
    write_text(evidence / "installer-source-appop.txt", output)
    verify = adb("shell", "appops", "get", "com.android.shell", "REQUEST_INSTALL_PACKAGES", check=False)
    write_text(evidence / "installer-source-appop-verify.txt", verify)
    if "allow" not in verify.lower():
        raise InfrastructureFailure(f"Emulator shell cannot be authorized to open PackageInstaller: {verify}")
    return verify.strip()




def parse_media_store_content_uri(output: str) -> str:
    """Extract a content URI from MediaProvider Bundle, JSON or plain output."""
    match = re.search(r"""content://[^\s,\]\}\)"']+""", output)
    if not match:
        raise InfrastructureFailure(
            "MediaProvider did not return a content:// URI. "
            f"Output: {output[-3000:]}"
        )
    uri = match.group(0).rstrip(".,;:)'\"}]")
    parsed = urlsplit(uri)
    if parsed.scheme != "content" or not parsed.netloc or any(ch.isspace() for ch in uri):
        raise InfrastructureFailure(f"MediaProvider returned an invalid content URI: {uri!r}")
    return uri


def media_store_content_uri(remote_path: str, evidence: Path, label: str) -> str:
    """Ask MediaProvider to expose the staged APK through a readable content URI."""
    result = run(
        [
            "adb", "shell", "content", "call",
            "--uri", "content://media",
            "--method", "scan_file",
            "--arg", remote_path,
        ],
        timeout=90,
        check=False,
    )
    output = (result.stdout or "") + (result.stderr or "")
    write_text(evidence / f"{label}-media-scan.txt", output)
    if result.returncode != 0:
        raise InfrastructureFailure(
            f"MediaProvider could not scan {remote_path} (exit {result.returncode}): "
            f"{output[-3000:]}"
        )
    uri = parse_media_store_content_uri(output)
    write_text(evidence / f"{label}-content-uri.txt", uri + "\n")
    return uri


def run_self_tests() -> None:
    """Offline parser and UI-hierarchy tests; no ADB or emulator required."""
    examples = (
        ("Result: Bundle[{uri=content://media/external/file/123}]", "content://media/external/file/123"),
        ('{"uri":"content://media/external/file/456"}', "content://media/external/file/456"),
        ("scan result: content://media/external/file/789, status=ok", "content://media/external/file/789"),
    )
    for raw, expected in examples:
        assert parse_media_store_content_uri(raw) == expected
    print("PASS MediaProvider URI parsing: Bundle, JSON and plain text")

    nested = ET.fromstring(
        '<hierarchy><node text="" clickable="true" enabled="true" bounds="[100,2100][980,2300]">'
        '<node text="Install" clickable="false" enabled="true" bounds="[0,0][0,0]" />'
        '</node></hierarchy>'
    )
    assert find_clickable(nested, (r"Install",), (1080, 2400)) == (540, 2200, "Install")
    print("PASS zero-sized label resolves only to a valid clickable ancestor")

    non_clickable = ET.fromstring(
        '<hierarchy><node text="Install" clickable="false" enabled="true" bounds="[0,0][1080,2400]" /></hierarchy>'
    )
    disabled = ET.fromstring(
        '<hierarchy><node text="Install" clickable="true" enabled="false" bounds="[100,2100][980,2300]" /></hierarchy>'
    )
    outside = ET.fromstring(
        '<hierarchy><node text="Install" clickable="true" enabled="true" bounds="[100,2300][1200,2500]" /></hierarchy>'
    )
    assert find_clickable(non_clickable, (r"Install",), (1080, 2400)) is None
    assert find_clickable(disabled, (r"Install",), (1080, 2400)) is None
    assert find_clickable(outside, (r"Install",), (1080, 2400)) is None
    print("PASS non-clickable, disabled and off-screen controls are rejected")

    bottom = ET.fromstring(
        '<hierarchy><node text="Install" clickable="true" enabled="true" bounds="[100,2200][980,2380]" /></hierarchy>'
    )
    assert find_clickable(bottom, (r"Install",), (1080, 2400)) == (540, 2290, "Install")
    print("PASS valid bottom-screen button is not blocked by a percentage rule")

def perform_packageinstaller_install(
    *,
    apk: Path,
    package: str,
    expected_version_code: int,
    expected_version_name: str,
    label: str,
    evidence: Path,
    display: tuple[int, int],
    expected_previous: tuple[int, str] | None = None,
) -> dict:
    if not apk.is_file() or apk.stat().st_size == 0:
        raise TestFailure(f"APK fixture is missing or empty: {apk}")

    actual_before, name_before, _ = package_version(package)
    if expected_previous is None:
        if package_path(package):
            raise TestFailure(
                f"Expected a clean install of {package}, but it is already installed "
                f"(versionCode={actual_before}, versionName={name_before})."
            )
    elif (actual_before, name_before) != expected_previous:
        raise TestFailure(
            f"Upgrade precondition failed for {package}: expected {expected_previous}, "
            f"found {(actual_before, name_before)}."
        )

    # Shell-owned storage avoids /sdcard mount problems. MediaProvider returns
    # the installer-readable content URI; this never uses adb install.
    remote = f"/data/local/tmp/{label}.apk"
    adb("push", str(apk), remote, timeout=120)
    write_text(evidence / f"{label}-remote-apk.txt", adb("shell", "ls", "-l", remote, timeout=30))
    content_uri = media_store_content_uri(remote, evidence, label)

    adb("logcat", "-c")
    launch = run(
        [
            "adb", "shell", "am", "start",
            "-a", "android.intent.action.INSTALL_PACKAGE",
            "-d", content_uri,
            "-t", INSTALLER_MIME,
            "-f", "0x10000001",
        ],
        timeout=45,
        check=False,
    )
    intent = (launch.stdout or "") + (launch.stderr or "")
    write_text(evidence / f"{label}-installer-launch.txt", intent)
    if launch.returncode != 0 or re.search(r"(^|\n)Error:", intent, flags=re.IGNORECASE) or "exception" in intent.lower():
        capture_screenshot(evidence, f"{label}-launch-failure")
        capture_device_state(evidence, f"{label}-launch-failure")
        raise TestFailure(f"Android did not launch PackageInstaller for {content_uri}: {intent}")

    tapped_install = False
    tapped_next = False
    last_texts: list[str] = []
    deadline = time.monotonic() + 150
    while time.monotonic() < deadline:
        _, root = dump_ui(evidence, f"{label}-ui")
        texts = visible_texts(root)
        last_texts = texts
        lowered = " | ".join(texts).lower()

        if any(token in lowered for token in ("app not installed", "can't install app", "cannot install app")):
            capture_screenshot(evidence, f"{label}-failure")
            raise TestFailure(f"PackageInstaller reported failure for {label}: " + " | ".join(texts))
        if "not allowed to install unknown apps" in lowered or "allow from this source" in lowered:
            capture_screenshot(evidence, f"{label}-unknown-source-block")
            raise TestFailure(f"PackageInstaller blocked the initiating source for {label}: " + " | ".join(texts))

        actual_code, actual_name, package_dump = package_version(package)
        if (
            package_path(package)
            and actual_code == expected_version_code
            and actual_name == expected_version_name
        ):
            if not tapped_install:
                capture_screenshot(evidence, f"{label}-unexpected-auto-install")
                raise TestFailure(
                    f"{label} reached the expected version without a verified visible Install/Update tap."
                )
            write_text(evidence / f"{label}-package-dump.txt", package_dump)
            capture_screenshot(evidence, f"{label}-result")
            sessions = adb("shell", "dumpsys", "packageinstaller", timeout=45, check=False)
            write_text(evidence / f"{label}-sessions-after.txt", sessions)
            logcat = adb("logcat", "-d", "-v", "threadtime", "-t", "8000", timeout=45, check=False)
            write_text(evidence / f"{label}-logcat-after.txt", logcat)
            result = {
                "label": label,
                "package": package,
                "expected_version_code": expected_version_code,
                "installed_version_code": actual_code,
                "expected_version_name": expected_version_name,
                "installed_version_name": actual_name,
                "package_path": package_path(package),
                "installer_action": "android.intent.action.INSTALL_PACKAGE",
                "installer_uri": content_uri,
                "installer_intent": intent.strip(),
                "install_button_tapped": tapped_install,
                "next_button_tapped": tapped_next,
                "status": "PASS",
            }
            write_text(evidence / f"{label}-result.json", json.dumps(result, indent=2))
            print(
                f"PACKAGEINSTALLER_UI_PASS: {label} => {package} "
                f"version={actual_name} code={actual_code}"
            )
            return result

        if root is not None:
            confirm = find_clickable(root, (r"Install", r"Update", r"Install anyway"), display)
            if confirm and not tapped_install:
                x, y, button_text = confirm
                capture_screenshot(evidence, f"{label}-confirmation")
                adb("shell", "input", "tap", str(x), str(y))
                tapped_install = True
                write_text(evidence / f"{label}-confirm-button.txt", f"Tapped enabled {button_text} at {x},{y}")
                time.sleep(2)
                continue

            next_button = find_clickable(root, (r"Next", r"Continue"), display)
            if next_button and tapped_install and not tapped_next:
                x, y, button_text = next_button
                adb("shell", "input", "tap", str(x), str(y))
                tapped_next = True
                write_text(evidence / f"{label}-next-button.txt", f"Tapped enabled {button_text} at {x},{y}")
                time.sleep(2)
                continue

        time.sleep(2)

    capture_screenshot(evidence, f"{label}-timeout")
    capture_device_state(evidence, f"{label}-timeout")
    raise TestFailure(
        f"PackageInstaller did not install {package} versionCode={expected_version_code} "
        f"versionName={expected_version_name}. Install button tapped={tapped_install}; "
        f"last visible UI: {' | '.join(last_texts)}"
    )

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true", help="run offline helper tests without ADB")
    parser.add_argument("--expected-api", type=int)
    parser.add_argument("--old-apk", type=Path)
    parser.add_argument("--current-apk", type=Path)
    parser.add_argument("--upgrade-apk", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args()

    if args.self_test:
        run_self_tests()
        return 0

    required = {
        "--expected-api": args.expected_api,
        "--old-apk": args.old_apk,
        "--current-apk": args.current_apk,
        "--upgrade-apk": args.upgrade_apk,
        "--evidence-dir": args.evidence_dir,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        parser.error("required unless --self-test: " + ", ".join(missing))

    evidence = args.evidence_dir
    evidence.mkdir(parents=True, exist_ok=True)
    release, api = wait_android_ready(evidence)
    if api != args.expected_api:
        raise InfrastructureFailure(
            f"Expected Android API {args.expected_api}, emulator reports {api} ({release})"
        )
    display = screen_size()
    write_text(evidence / "display-size.txt", f"{display[0]}x{display[1]}\n")
    print(f"Testing PackageInstaller UI on Android {release} / API {api}")

    installer_source = set_up_installer_source(evidence)
    results = []

    results.append(
        perform_packageinstaller_install(
            apk=args.old_apk,
            package=PACKAGE_OLD,
            expected_version_code=1,
            expected_version_name="1.0.0",
            label="fresh-legacy-1.0.0",
            evidence=evidence,
            display=display,
        )
    )
    results.append(
        perform_packageinstaller_install(
            apk=args.current_apk,
            package=PACKAGE_PREVIEW,
            expected_version_code=1,
            expected_version_name="1.0.2",
            label="fresh-preview-1.0.2",
            evidence=evidence,
            display=display,
        )
    )
    results.append(
        perform_packageinstaller_install(
            apk=args.upgrade_apk,
            package=PACKAGE_PREVIEW,
            expected_version_code=2,
            expected_version_name="1.0.3",
            label="upgrade-preview-1.0.2-to-1.0.3",
            evidence=evidence,
            display=display,
            expected_previous=(1, "1.0.2"),
        )
    )

    summary = {
        "android_release": release,
        "android_api": api,
        "display_size": {"width": display[0], "height": display[1]},
        "installer_source_appop": installer_source,
        "tests": results,
        "overall": "PASS",
        "note": (
            "Uses Android ACTION_INSTALL_PACKAGE with a MediaStore content URI "
            "and visible PackageInstaller UI. It does not use adb install."
        ),
    }
    write_text(evidence / "summary.json", json.dumps(summary, indent=2))
    print(f"USER_PACKAGEINSTALLER_UI_MATRIX_PASS: Android API {api}")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InfrastructureFailure as error:
        print(f"USER_PACKAGEINSTALLER_INFRA_FAILURE: {error}", file=sys.stderr)
        raise SystemExit(2)
    except TestFailure as error:
        print(f"USER_PACKAGEINSTALLER_TEST_FAILURE: {error}", file=sys.stderr)
        raise SystemExit(1)
