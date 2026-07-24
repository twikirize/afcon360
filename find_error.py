with open('app/wallet/services/wallet_service.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

low, high = 1, len(lines)
first_bad = None
while low < high:
    mid = (low + high) // 2
    code = ''.join(lines[:mid])
    try:
        compile(code, 'test', 'exec')
        low = mid + 1
    except SyntaxError as e:
        first_bad = mid
        high = mid

if first_bad:
    print(f"First error at line {first_bad}")
    # Show context
    start = max(0, first_bad - 10)
    for i in range(start, min(len(lines), first_bad + 5)):
        print(f'{i+1}: {repr(lines[i])}')
