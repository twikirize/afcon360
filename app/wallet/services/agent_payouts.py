# wallet/services/agent_payouts.py
from datetime import datetime
from collections import defaultdict

# Simple in-memory stores (swap to DB later)
payout_requests = []
agent_payout_balance = defaultdict(float)  # cached available payouts (optional)

def create_payout_request(agent_id, amount, method="bank", details=None):
    if amount <= 0:
        return None, "Amount must be greater than zero."
    req = {
        "id": len(payout_requests) + 1,
        "agent_id": agent_id,
        "amount": amount,
        "method": method,
        "details": details or {},
        "status": "pending",
        "requested_at": datetime.utcnow().isoformat(),
        "processed_at": None,
        "processor": None,
        "notes": None
    }
    payout_requests.append(req)
    return req, None

def list_payout_requests(filter_status=None):
    if not filter_status:
        return list(payout_requests)
    return [r for r in payout_requests if r["status"] == filter_status]

def get_payout_request(req_id):
    for r in payout_requests:
        if r["id"] == int(req_id):
            return r
    return None

def update_payout_status(req_id, status, processor=None, notes=None):
    r = get_payout_request(req_id)
    if not r:
        return None, "Request not found."
    if status not in ("approved","rejected","paid"):
        return None, "Invalid status."
    r["status"] = status
    r["processed_at"] = datetime.utcnow().isoformat()
    r["processor"] = processor
    r["notes"] = notes
    return r, None