# wallet/services/agent_tracker.py

from collections import defaultdict
from datetime import datetime, UTC

# Registry of agent earnings
agent_earnings = defaultdict(list)

def log_agent_commission(agent_id, amount, source, tx_type):
    agent_earnings[agent_id].append({
        "amount": amount,
        "source": source,
        "type": tx_type,
        "timestamp": datetime.now(UTC).isoformat()
    })

def get_agent_total(agent_id):
    return sum(entry["amount"] for entry in agent_earnings.get(agent_id, []))

def get_agent_commissions(agent_id):
    return agent_earnings.get(agent_id, [])