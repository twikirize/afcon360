with open(r'C:\Users\OBED\Desktop\afcon360_app\tests\wallet\test_ledger_concurrency.py', 'r') as f:
    content = f.read()

# Fix the escaped quotes
content = content.replace("\\'USD\\'", "'USD'")
content = content.replace("\\'UGX\\'", "'UGX'")

with open(r'C:\Users\OBED\Desktop\afcon360_app\tests\wallet\test_ledger_concurrency.py', 'w') as f:
    f.write(content)

print('Fixed quotes')