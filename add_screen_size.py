with open(r"C:\Users\OBED\Desktop\afcon360-user-dev\mobile\scripts\verify-user-packageinstaller-ui.py", "r", encoding="utf-8") as f:
    content = f.read()

# Add screen_size() function after wait_package_manager()
old_wait = "def wait_package_manager() -> None:\n    for attempt in range(60):\n        service = adb(\"shell\", \"service\", \"check\", \"package\", check=False)\n        package_list = adb(\"shell\", \"pm\", \"list\", \"packages\", check=False)\n        if \"found\" in service.lower() and \"package:\" in package_list:\n            print(f\"ANDROID_PACKAGE_MANAGER_READY after {attempt + 1} checks\")\n            return\n        time.sleep(2)\n    raise TestFailure(\"Android Package Manager did not become ready\")"

new_wait = "def wait_package_manager() -> None:\n    for attempt in range(60):\n        service = adb(\"shell\", \"service\", \"check\", \"package\", check=False)\n        package_list = adb(\"shell\", \"pm\", \"list\", \"packages\", check=False)\n        if \"found\" in service.lower() and \"package:\" in package_list:\n            print(f\"ANDROID_PACKAGE_MANAGER_READY after {attempt + 1} checks\")\n            return\n        time.sleep(2)\n    raise TestFailure(\"Android Package Manager did not become ready\")\n\ndef screen_size() -> tuple[int, int]:\n    \"\"\"Get the emulator display size via adb.\"\"\"\n    output = adb(\"shell\", \"wm\", \"size\", timeout=20)\n    matches = re.findall(r\"(?:Physical|Override) size:\s*(\d+)x(\d+)\", output)\n    if not matches:\n        raise InfrastructureFailure(f\"Could not determine emulator display size: {output}\")\n    width, height = map(int, matches[-1])\n    if width <= 0 or height <= 0:\n        raise InfrastructureFailure(f\"Invalid emulator display size: {width}x{height}\")\n    return width, height"

content = content.replace(old_wait, new_wait)

with open(r"C:\Users\OBED\Desktop\afcon360-user-dev\mobile\scripts\verify-user-packageinstaller-ui.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Added screen_size() function")