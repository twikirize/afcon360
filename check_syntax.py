import textwrap
with open('app/wallet/services/wallet_service.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

code = ''.join(lines[567:605])
code = textwrap.dedent(code)
for i, line in enumerate(code.split('\n'), 1):
    if i >= 35:
        print(f'{i}: {repr(line)}')
