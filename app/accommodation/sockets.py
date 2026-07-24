
from flask_socketio import Namespace, emit
from flask_login import login_required, current_user
import logging

class HostDashboardNamespace(Namespace):
    @login_required
    def on_connect(self):
        logging.info(f"Client connected: {current_user.public_id}")

    @login_required
    def on_subscribe(self, data):
        channel = data.get('channel')
        logging.info(f"User {current_user.public_id} subscribed to {channel}")
        # Logic to handle subscriptions goes here
