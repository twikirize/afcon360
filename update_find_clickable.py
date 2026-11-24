with open(r"C:\Users\OBED\Desktop\afcon360-user-dev\mobile\scripts\verify-user-packageinstaller-ui.py", "r", encoding="utf-8") as f:
    content = f.read()

# Update perform_packageinstaller_install to call screen_size() and pass to find_clickable
old_intent_block = """    write_text(evidence / f"{label}-installer-launch.txt", intent)
    if re.search(r"(^|\n)Error:", intent, flags=re.IGNORECASE) or "exception" in intent.lower():
        capture_screenshot(evidence, f"{label}-launch-failure")
        capture_device_state(evidence, f"{label}-launch-failure")
        raise TestFailure(
            f"Android did not launch PackageInstaller for {content_uri}: {intent}"
        )

    tapped_install = False"""

new_intent_block = """    write_text(evidence / f"{label}-installer-launch.txt", intent)
    if re.search(r"(^|\n)Error:", intent, flags=re.IGNORECASE) or "exception" in intent.lower():
        capture_screenshot(evidence, f"{label}-launch-failure")
        capture_device_state(evidence, f"{label}-launch-failure")
        raise TestFailure(
            f"Android did not launch PackageInstaller for {content_uri}: {intent}"
        )

    display = screen_size()

    tapped_install = False"""

content = content.replace(old_intent_block, new_intent_block)

# Update find_clickable calls to pass display
old_done = "done = find_clickable(root, (r\"Done\",))"
new_done = "done = find_clickable(root, (r\"Done\",), display)"
content = content.replace(old_done, new_done)

old_confirm = "confirm = find_clickable(root, (r\"Install\", r\"Update\", r\"Install anyway\"))"
new_confirm = "confirm = find_clickable(root, (r\"Install\", r\"Update\", r\"Install anyway\"), display)"
content = content.replace(old_confirm, new_confirm)

old_next = "next_button = find_clickable(root, (r\"Next\", r\"Continue\"))"
new_next = "next_button = find_clickable(root, (r\"Next\", r\"Continue\"), display)"
content = content.replace(old_next, new_next)

with open(r"C:\Users\OBED\Desktop\afcon360-user-dev\mobile\scripts\verify-user-packageinstaller-ui.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Updated find_clickable calls with display parameter")