import os
import re

template_dir = "templates/admin/compliance"
old_prefix = "url_for('compliance."
new_prefix = "url_for('admin.compliance."

count = 0
for root, dirs, files in os.walk(template_dir):
    for fname in files:
        if fname.endswith('.html'):
            fpath = os.path.join(root, fname)
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()
            new_content = content.replace(old_prefix, new_prefix)
            if new_content != content:
                with open(fpath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                replacements = content.count(old_prefix)
                count += replacements
                print(f"Fixed {fpath}: {replacements} replacements")

print(f"\nTotal replacements: {count}")
