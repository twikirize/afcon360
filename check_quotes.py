import re
with open('app/wallet/services/wallet_service.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i, line in enumerate(lines[:582], 1):
    stripped = line.strip()
    if stripped.startswith(('"""', "'''")) or '"""' in line or "'''" in line:
        print(f'{i}: {repr(line[:80])}')
