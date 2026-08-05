import os
os.environ['FLASK_ENV'] = 'testing'
os.environ['APP_ENV'] = 'testing'
from app import create_app
from app.notifications.services import NotificationService as S
from app.notifications.models import NotificationChannel

print('EMAIL member:', repr(NotificationChannel.EMAIL))
print('str(EMAIL):', repr(str(NotificationChannel.EMAIL)))
print('HANDLERS keys:', list(S.HANDLERS.keys()))
print("get('email'):", S.HANDLERS.get('email'))
print("get(str(EMAIL)):", S.HANDLERS.get(str(NotificationChannel.EMAIL)))
print("get(EMAIL.value):", S.HANDLERS.get(NotificationChannel.EMAIL.value))
