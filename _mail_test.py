import os
os.environ['APP_ENV'] = 'local'
os.environ['FLASK_ENV'] = 'development'
from app import create_app
from flask_mail import Message
from app.extensions import mail

app = create_app()
with app.app_context():
    msg = Message(
        subject="AFCON360 Email Test",
        recipients=["bsmgroup22015@gmail.com"],
        body="If you receive this, the AFCON360 notification email channel is live via Gmail SMTP.",
        html="<h1>AFCON360 Email Test</h1><p>Notification email channel is <b>live</b> via Gmail SMTP.</p>",
    )
    try:
        mail.send(msg)
        print("SMTP_SEND_OK")
    except Exception as e:
        print("SMTP_SEND_FAILED:", repr(e))
