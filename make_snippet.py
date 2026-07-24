with open('app/wallet/services/wallet_service.py', 'rb') as f:
    lines = f.readlines()
with open('test_snippet.py', 'wb') as f:
    f.write(b'def x():\n')
    f.write(b'    """\n')
    f.write(lines[582])  # Transfer funds...
    f.write(lines[583])  # blank
    f.write(lines[584])  # Single transaction...
    f.write(lines[585])  # idempotency...
    f.write(lines[586])  # blank
    f.write(lines[587])  # NO COMPENSATION...
    f.write(lines[588])  # blank
    f.write(lines[589])  # Args:
    f.write(lines[590])  # from_user_id
    f.write(lines[591])  # to_user_id
    f.write(b'    """\n')
    f.write(b'    pass\n')
