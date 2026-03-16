from datetime import datetime, UTC

def log_agent_commission(agent_id, amount, user_id, txn_type):
    # Stubbed out for demo; replace with actual logic
    print(f"Commission logged: agent={agent_id}, amount={amount}, user={user_id}, type={txn_type}")

def process_withdrawal(wallet, amount, currency, method="ATM", agent_id=None):
    if amount <= 0:
        return None, "Amount must be greater than zero."

    # Check balance
    if currency == wallet.home_currency and wallet.balance_home < amount:
        return None, "Insufficient home balance."
    if currency == wallet.local_currency and wallet.balance_local < amount:
        return None, "Insufficient local balance."

    # Deduct
    if currency == wallet.home_currency:
        wallet.balance_home -= amount
    else:
        wallet.balance_local -= amount

    # Commission for Agent method
    if method == "Agent" and agent_id:
        log_agent_commission(agent_id, 500, wallet.user_id, "withdrawal")  # 500 UGX flat fee

    # Log transaction with timezone-aware UTC timestamp
    wallet.transactions.append({
        "type": "withdrawal",
        "method": method,
        "agent_id": agent_id,
        "amount": amount,
        "currency": currency,
        "timestamp": datetime.now(UTC)
    })

    return wallet, None
