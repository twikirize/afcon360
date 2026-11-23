content = """#!/usr/bin/env python3
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
            raise TestFailure(
                f"Command timed out after {timeout}s: {' '.join(args)}\\n"
                f"stdout: {stdout[-3000:]}\\nstderr: {stderr[-3000:]}"
            ) from error
        return subprocess.CompletedProcess(list(args), 124, stdout, stderr)
    if check and result.returncode != 0:
        stdout = result.stdout if isinstance(result.stdout, str) else repr(result.stdout)
        stderr = result.stderr if isinstance(result.stderr, str) else repr(result.stderr)
        message = (
            f"Command failed ({result.returncode}): {' '.join(args)}\\n"
            f"stdout: {stdout[-3000:]}\\nstderr: {stderr[-3000:]}"
        )
        if args and args[0].lower().endswith("adb"):
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
        match = re.fullmatch(r"\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]", bounds)
        if not match:
            continue
        left, top, right, bottom = map(int, match.groups())
        if right <= left or bottom <= top:
            continue
        return (left + right) // 2, (top + bottom) // 2, candidate
    return None


def package_version(package: str) -> tuple[int | None, str | None, str]:
    output = adb("shell", "dumpsys", "package", package, timeout=45, check=False)
    match = re.search(r"versionCode=(\\d+).*?versionName=([^\\s]+)", output, flags=re.DOTALL)
    if not match:
        return None, None, output
    return int(match.group(1)), match.group(2).strip('\'"'), output


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
    output = adb("shell", "appops", "set", "com.android.shell", "REQUEST_INSTALL_PACKAGES", "allow", check=False)
    write_text(evidence / "installer-source-appop.txt", output)
    verify = adb("shell", "appops", "get", "com.android.shell", "REQUEST_INSTALL_PACKAGES", check=False)
    write_text(evidence / "installer-source-appop-verify.txt", verify)
    if "allow" not in verify.lower():
        raise TestFailure(f"Emulator shell cannot be authorized to open PackageInstaller: {verify}")


def media_store_content_uri(remote_path: str, evidence: Path, label: str) -> str:
    """Ask Android MediaProvider for a readable content URI for the staged APK.

    PackageInstaller cannot consume a raw file:// URI. The shell MediaProvider
    scan call returns the content:// URI that can be granted to the installer.
    """
    result = run(
        [
            "adb",
            "shell",
            "content",
            "call",
            "--uri",
            "content://media",
            "--method",
            "scan_file",
            "--arg",
            remote_path,
        ],
        timeout=90,
        check=False,
    )
    output = (result.stdout or "") + (result.stderr or "")
    write_text(evidence / f"{label}-media-scan.txt", output)

    if result.returncode != 0:
        raise InfrastructureFailure(
            f"MediaProvider could not create an installer URI for {remote_path} "
            f"(exit {result.returncode}): {output[-3000:]}"
        )

    match = re.search(r"(content://[^\\s,}\\]\\)]+)", output)
    if not match:
        raise InfrastructureFailure(
            f"MediaProvider did not return a content:// URI for {remote_path}: "
            f"{output[-3000:]}"
        )

    uri = match.group(1).rstrip(").,]'\"")
    if not uri.startswith("content://"):
        raise InfrastructureFailure(f"MediaProvider returned an invalid installer URI: {uri}")

    parsed = urlsplit(uri)
    if parsed.scheme != "content" or not parsed.netloc or any(ch.isspace() for ch in uri):
        raise InfrastructureFailure(f"MediaProvider returned an invalid installer URI: {uri!r}")

    write_text(evidence / f"{label}-content-uri.txt", uri + "\n")
    return uri


def verify_content_uri_readable(uri: str, evidence: Path, label: str) -> None:
    """Confirm the content URI is actually readable by the installer."""
    result = run(
        ["adb", "shell", "cat", uri],
        timeout=30,
        check=False,
        binary=True,
    )
    write_text(evidence / f"{label}-content-uri-readability.txt",
               f"exit={result.returncode}\\nsize={len(result.stdout) if result.stdout else 0}\n")
    if result.returncode != 0 or not result.stdout:
        raise InfrastructureFailure(
            f"Content URI {uri} is not readable by adb shell cat: exit={result.returncode}"
        )
    if result.stdout and not (result.stdout[:2] == b"PK" or result.stdout[:4] == b"PK\x03\x04"):
        write_text(evidence / f"{label}-content-uri-warning.txt",
                   f"Content URI may not be an APK (magic bytes: {result.stdout[:8].hex()})")


def perform_packageinstaller_install(
    *,
    apk: Path,
    package: str,
    expected_version_code: int,
    expected_version_name: str | None,
    label: str,
    evidence: Path,
) -> dict:
    if not apk.is_file() or apk.stat().st_size == 0:
        raise TestFailure(f"APK fixture is missing or empty: {apk}")

    remote = f"/data/local/tmp/{label}.apk"
    write_text(
        evidence / f"{label}-storage-staging.txt",
        f"mode=data-local-tmp\nremote={remote}\n",
    )
    adb("push", str(apk), remote, timeout=120)
    remote_listing = adb("shell", "ls", "-l", remote, timeout=30)
    write_text(evidence / f"{label}-remote-apk.txt", remote_listing)

    content_uri = media_store_content_uri(remote, evidence, label)
    verify_content_uri_readable(content_uri, evidence, label)

    adb("logcat", "-c")
    intent = adb(
        "shell",
        "am",
        "start",
        "-a",
        "android.intent.action.INSTALL_PACKAGE",
        "-d",
        content_uri,
        "-t",
        INSTALLER_MIME,
        "-f",
        "0x10000001",
        timeout=45,
        check=False,
    )
    write_text(evidence / f"{label}-installer-launch.txt", intent)
    if re.search(r"(^|\n)Error:", intent, flags=re.IGNORECASE) or "exception" in intent.lower():
        capture_screenshot(evidence, f"{label}-launch-failure")
        capture_device_state(evidence, f"{label}-launch-failure")
        raise TestFailure(
            f"Android did not launch PackageInstaller for {content_uri}: {intent}"
        )

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

        if "not allowed to install unknown apps" in lowered or "allow from this source" in lowered:
            capture_screenshot(evidence, f"{label}-unknown-source-block")
            raise TestFailure(
                f"PackageInstaller blocked the initiating source for {label}: "
                + " | ".join(texts)
            )

        actual_code, actual_name, package_dump = package_version(package)

        if package_path(package) and actual_code == expected_version_code:
            write_text(evidence / f"{label}-package-dump.txt", package_dump)
            capture_screenshot(evidence, f"{label}-result")
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
                write_text(evidence / f"{label}-abandoned-session-note.txt",
                           "Historical dump includes an abandoned session; package path and expected version code are present.")
            result = {
                "label": label,
                "package": package,
                "expected_version_code": expected_version_code,
                "expected_version_name": expected_version_name,
                "installed_version_code": actual_code,
                "installed_version_name": actual_name,
                "package_path": package_path(package),
                "installer_action": "android.intent.action.INSTALL_PACKAGE",
                "installer_uri": content_uri,
                "installer_intent": intent.strip(),
                "install_button_tapped": tapped_install,
                "status": "PASS",
            }
            write_text(evidence / f"{label}-result.json", json.dumps(result, indent=2))
            print(f"PACKAGEINSTALLER_UI_PASS: {label} => {package} versionCode={actual_code}")
            return result

        if root is not None:
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


def run_self_tests() -> None:
    """Offline parser and UI-hierarchy tests; no ADB or emulator required."""
    # MediaStore URI parsing tests
    examples = (
        ("Result: Bundle[{uri=content://media/external/file/123}]", "content://media/external/file/123"),
        ('{"uri":"content://media/external/file/456"}', "content://media/external/file/456"),
        ("scan result: content://media/external/file/789, status=ok", "content://media/external/file/789"),
    )
    for raw, expected in examples:
        assert parse_media_store_content_uri(raw) == expected
    print("PASS MediaProvider URI parsing: Bundle, JSON and plain text")

    # clickable ancestor resolution tests
    nested = ET.fromstring(
        '<hierarchy><node text="" clickable="true" enabled="true" bounds="[100,2100][980,2300]">'
        '<node text="Install" clickable="false" enabled="true" bounds="[0,0][0,0]" />'
        '</node></hierarchy>'
    )
    assert find_clickable(nested, (r"Install",)) == (540, 2200, "Install")
    print("PASS zero-sized label resolves only to a valid clickable ancestor")

    non_clickable = ET.fromstring(
        '<hierarchy><node text="Install" clickable="false" enabled="true" bounds="[0,0][1080,2400]" /></hierarchy>'
    )
    assert find_clickable(non_clickable, (r"Install",)) is None
    print("PASS non-clickable ancestor is rejected")

    disabled = ET.fromstring(
        '<hierarchy><node text="Install" clickable="true" enabled="false" bounds="[100,2100][980,2300]" /></hierarchy>'
    )
    assert find_clickable(disabled, (r"Install",)) is None
    print("PASS disabled ancestor is rejected")

    outside = ET.fromstring(
        '<hierarchy><node text="Install" clickable="true" enabled="true" bounds="[100,2300][1200,2500]" /></hierarchy>'
    )
    assert find_clickable(outside, (r"Install",)) is None
    print("PASS off-screen ancestor is rejected")

    bottom = ET.fromstring(
        '<hierarchy><node text="Install" clickable="true" enabled="true" bounds="[100,2200][980,2380]" /></hierarchy>'
    )
    assert find_clickable(bottom, (r"Install",)) == (540, 2290, "Install")
    print("PASS valid bottom-screen button is not blocked by a percentage rule")

    print("All self-tests passed.")


def parse_media_store_content_uri(output: str) -> str:
    """Extract a content URI from MediaProvider Bundle, JSON or plain output."""
    match = re.search(r"(content://[^\s,}\]\)]+)", output)
    if not match:
        raise InfrastructureFailure(
            f"MediaProvider did not return a content:// URI. Output: {output[-3000:]}"
        )
    uri = match.group(1).rstrip(").,]'\"")
    if not uri.startswith("content://"):
        raise InfrastructureFailure(f"MediaProvider returned an invalid content URI: {uri!r}")
    parsed = urlsplit(uri)
    if parsed.scheme != "content" or not parsed.netloc or any(ch.isspace() for ch in uri):
        raise InfrastructureFailure(f"MediaProvider returned an invalid content URI: {uri!r}")
    return uri


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

    release = adb("shell", "getprop", "ro.build.version.release").strip()
    api = int(adb("shell", "getprop", "ro.build.version.sdk").strip())
    if api != args.expected_api:
        raise InfrastructureFailure(
            f"Expected Android API {args.expected_api}, emulator reports {api} ({release})"
        )

    device = adb("get-state").strip()
    write_text(evidence / "device-info.txt", f"state={device}\nrelease={release}\napi={api}\n")
    print(f"Testing PackageInstaller UI on Android {release} / API {api}")

    wait_package_manager()
    set_up_installer_source(evidence)

    fixtures = [
        (args.old_apk, PACKAGE_OLD, 1, None, "fresh-1.0.0"),
        (args.current_apk, PACKAGE_PREVIEW, 1, "1.0.1", "fresh-1.0.1"),
        (args.upgrade_apk, PACKAGE_PREVIEW, 2, "1.0.2", "upgrade-1.0.1-to-1.0.2"),
    ]

    results = []
    for apk, package, version_code, version_name, label in fixtures:
        results.append(
            perform_packageinstaller_install(
                apk=apk,
                package=package,
                expected_version_code=version_code,
                expected_version_name=version_name,
                label=label,
                evidence=evidence,
            )
        )

    summary = {
        "android_release": release,
        "android_api": api,
        "tests": results,
        "overall": "PASS",
        "note": "Uses Android ACTION_INSTALL_PACKAGE with a MediaStore content URI and visible PackageInstaller UI; it does not use adb install.",
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
"""

with open(r"C:\Users\OBED\Desktop\afcon360-user-dev\mobile\scripts\verify-user-packageinstaller-ui.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Script written successfully")