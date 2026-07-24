import re, os

path = r"C:\Users\OBED\Desktop\afcon360_app\templates\owner\super_admins.html"
with open(path, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()
matches = re.findall(r"url_for\('owner\.[^']+'\)", content)
for m in matches:
    print(m)
print("Total:", len(matches))