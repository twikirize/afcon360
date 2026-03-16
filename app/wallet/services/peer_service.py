from app.wallet.services.receiver import get_or_create_receiver, log_receiver_transaction
from app.wallet.services.agent_tracker import log_agent_commission

if fee > 0:
    log_agent_commission(sender_wallet.user_id, fee, receiver_id, "peer_transfer")