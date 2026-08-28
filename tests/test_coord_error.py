from app.events.guest_coordination_service import CoordinationError
import traceback

try:
    raise CoordinationError('TEST', 'test message')
except CoordinationError as e:
    traceback.print_exc()
    print('args:', e.args)
    print('code:', e.code)
    print('message:', e.message)