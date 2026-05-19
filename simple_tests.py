# fix_missing_quotes.py
import os
import re

template_dir = "C:/Users/ADMIN/Desktop/afcon360_app/templates"


def fix_missing_quotes(filepath):
    """Fix safe_url calls with missing closing quotes"""
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    original = content

    # Fix pattern: safe_url('something)  -> safe_url('something')
    content = re.sub(
        r"safe_url\(['\"](\w+\.\w+)\(?['\"]?\)",
        r"safe_url('\1')",
        content
    )

    # Fix pattern: safe_url('something.something)  (no closing quote before paren)
    content = re.sub(
        r"safe_url\(['\"](\w+\.\w+)['\"]?\)",
        r"safe_url('\1')",
        content
    )

    # Fix specifically wallet.wallet_settings
    content = content.replace(
        "safe_url('wallet.wallet_settings)",
        "safe_url('wallet.wallet_settings')"
    )

    # Fix any other obvious issues
    content = re.sub(
        r"safe_url\(['\"](\w+\.\w+)['\"]?\)",
        r"safe_url('\1')",
        content
    )

    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False


# Fix all template files
fixed = []
for root, dirs, files in os.walk(template_dir):
    for file in files:
        if file.endswith('.html'):
            filepath = os.path.join(root, file)
            if fix_missing_quotes(filepath):
                fixed.append(os.path.relpath(filepath, template_dir))
                print(f"✅ Fixed: {os.path.relpath(filepath, template_dir)}")

print(f"\n" + "=" * 60)
print(f"Fixed {len(fixed)} files")
print("=" * 60)

# Specifically check base_wallet.html
base_wallet = os.path.join(template_dir, "wallet", "base_wallet.html")
if os.path.exists(base_wallet):
    with open(base_wallet, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    if "safe_url('wallet.wallet_settings')" in content:
        print("✅ wallet/base_wallet.html fixed")
    else:
        print("⚠️ wallet/base_wallet.html may still need manual fix")