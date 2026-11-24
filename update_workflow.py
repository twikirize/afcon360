with open(r"C:\Users\OBED\Desktop\afcon360-user-dev\.github\workflows\user-packageinstaller-ui-matrix.yml", "r", encoding="utf-8") as f:
    content = f.read()

# Add self-test step after "Check User Expo dependency compatibility"
old_check = """      - name: Check User Expo dependency compatibility
        working-directory: mobile
        run: pnpm --filter "@afcon360/user-app" exec expo install --check

      - name: Generate OTA-enabled User preview Android project"""

new_check = """      - name: Check User Expo dependency compatibility
        working-directory: mobile
        run: pnpm --filter "@afcon360/user-app" exec expo install --check

      - name: Validate PackageInstaller test script
        run: |
          python -m py_compile mobile/scripts/verify-user-packageinstaller-ui.py
          python mobile/scripts/verify-user-packageinstaller-ui.py --self-test

      - name: Generate OTA-enabled User preview Android project"""

content = content.replace(old_check, new_check)

with open(r"C:\Users\OBED\Desktop\afcon360-user-dev\.github\workflows\user-packageinstaller-ui-matrix.yml", "w", encoding="utf-8") as f:
    f.write(content)
print("Added self-test step to workflow")