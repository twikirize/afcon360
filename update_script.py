with open(r"C:\Users\OBED\Desktop\afcon360-user-dev\mobile\scripts\verify-user-packageinstaller-ui.py", "r", encoding="utf-8") as f:
    content = f.read()

# Add InfrastructureFailure class after TestFailure
old = """class TestFailure(RuntimeError):
    pass


def run("""
new = """class TestFailure(RuntimeError):
    pass


class InfrastructureFailure(TestFailure):
    \"\"\"ADB, emulator boot, PackageManager or MediaProvider infrastructure failure.\"\"\"
    pass


def run("""
content = content.replace(old, new)

# Add urlsplit import
old_import = "from typing import Sequence"
new_import = "from typing import Sequence\nfrom urllib.parse import urlsplit"
content = content.replace(old_import, new_import)

# Add parse_media_store_content_uri and run_self_tests before main
old_main = "def main() -> int:"
new_main = """def parse_media_store_content_uri(output: str) -> str:
    \"\"\"Extract a content URI from MediaProvider Bundle, JSON or plain output.\"\"\"
    match = re.search(r"(content://[^\\s,}\\]\\)]+)", output)
    if not match:
        raise InfrastructureFailure(
            f"MediaProvider did not return a content:// URI. Output: {output[-3000:]}"
        )
    uri = match.group(1).rstrip(").,]\'\"")
    if not uri.startswith("content://"):
        raise InfrastructureFailure(f"MediaProvider returned an invalid content URI: {uri!r}")
    parsed = urlsplit(uri)
    if parsed.scheme != "content" or not parsed.netloc or any(ch.isspace() for ch in uri):
        raise InfrastructureFailure(f"MediaProvider returned an invalid content URI: {uri!r}")
    return uri


def run_self_tests() -> None:
    \"\"\"Offline parser and UI-hierarchy tests; no ADB or emulator required.\"\"\"
    # MediaStore URI parsing tests
    examples = (
        ("Result: Bundle[{uri=content://media/external/file/123}]", "content://media/external/file/123"),
        ("{\\"uri\\":\\"content://media/external/file/456\\"}", "content://media/external/file/456"),
        ("scan result: content://media/external/file/789, status=ok", "content://media/external/file/789"),
    )
    for raw, expected in examples:
        assert parse_media_store_content_uri(raw) == expected
    print("PASS MediaProvider URI parsing: Bundle, JSON and plain text")

    # clickable ancestor resolution tests
    nested = ET.fromstring(
        "<hierarchy><node text=\"\" clickable=\"true\" enabled=\"true\" bounds=\"[100,2100][980,2300]\">"
        "<node text=\"Install\" clickable=\"false\" enabled=\"true\" bounds=\"[0,0][0,0]\" />"
        "</node></hierarchy>"
    )
    assert find_clickable(nested, (r"Install",)) == (540, 2200, "Install")
    print("PASS zero-sized label resolves only to a valid clickable ancestor")

    non_clickable = ET.fromstring(
        "<hierarchy><node text=\"Install\" clickable=\"false\" enabled=\"true\" bounds=\"[0,0][1080,2400]\"/></hierarchy>"
    )
    assert find_clickable(non_clickable, (r"Install",)) is None
    print("PASS non-clickable ancestor is rejected")

    disabled = ET.fromstring(
        "<hierarchy><node text=\"Install\" clickable=\"true\" enabled=\"false\" bounds=\"[100,2100][980,2300]\"/></hierarchy>"
    )
    assert find_clickable(disabled, (r"Install",)) is None
    print("PASS disabled ancestor is rejected")

    outside = ET.fromstring(
        "<hierarchy><node text=\"Install\" clickable=\"true\" enabled=\"true\" bounds=\"[100,2300][1200,2500]\"/></hierarchy>"
    )
    assert find_clickable(outside, (r"Install",)) is None
    print("PASS off-screen ancestor is rejected")

    bottom = ET.fromstring(
        "<hierarchy><node text=\"Install\" clickable=\"true\" enabled=\"true\" bounds=\"[100,2200][980,2380]\"/></hierarchy>"
    )
    assert find_clickable(bottom, (r"Install",)) == (540, 2290, "Install")
    print("PASS valid bottom-screen button is not blocked by a percentage rule")

    print("All self-tests passed.")


def main() -> int:"""
content = content.replace(old_main, new_main)

# Add urlsplit import
old_import = "from typing import Sequence"
new_import = "from typing import Sequence\nfrom urllib.parse import urlsplit"
content = content.replace(old_import, new_import)

# Add --self-test argument parsing in main
old_parser = """    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-api", type=int)"""
new_parser = """    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true", help="run offline helper tests without ADB")
    parser.add_argument("--expected-api", type=int)"""
content = content.replace(old_parser, new_parser)

# Add self-test handling
old_args_parse = """    args = parser.parse_args()

    evidence = args.evidence_dir"""
new_args_parse = """    args = parser.parse_args()

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

    evidence = args.evidence_dir"""
content = content.replace(old_args_parse, new_args_parse)

with open(r"C:\Users\OBED\Desktop\afcon360-user-dev\mobile\scripts\verify-user-packageinstaller-ui.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Script updated successfully")