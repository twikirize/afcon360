# app/wallet/services/deposit_service.py

from datetime import datetime, UTC

def process_deposit(wallet, amount, source_currency):
    """
    Apply a deposit of `amount` in `source_currency`.
    Always updates both balance_home and balance_local.
    Returns the wallet summary dict.
    """

    # 1) Deposit in home currency
    if source_currency == wallet.home_currency:
        # add to home
        wallet.balance_home += amount
        wallet.transactions.append({
            "type": "deposit_home",
            "amount": amount,
            "currency": wallet.home_currency,
            "timestamp": datetime.now(UTC).isoformat()
        })

        # convert to local
        converted_local, err = wallet.convert_currency(
            wallet.home_currency, wallet.local_currency, amount
        )
        if not err:
            wallet.balance_local += converted_local

    # 2) Deposit in local currency
    elif source_currency == wallet.local_currency:
        # add to local
        wallet.balance_local += amount
        wallet.transactions.append({
            "type": "deposit_local",
            "amount": amount,
            "currency": wallet.local_currency,
            "timestamp": datetime.now(UTC).isoformat()
        })

        # convert to home
        converted_home, err = wallet.convert_currency(
            wallet.local_currency, wallet.home_currency, amount
        )
        if not err:
            wallet.balance_home += converted_home

    # 3) Deposit in other foreign currency
    else:
        # convert to home
        converted_home, err = wallet.convert_currency(
            source_currency, wallet.home_currency, amount
        )
        if err:
            return {"error": err}

        wallet.balance_home += converted_home
        wallet.transactions.append({
            "type": "deposit_foreign",
            "original_amount": amount,
            "currency": source_currency,
            "converted_home": converted_home,
            "timestamp": datetime.now(UTC).isoformat()
        })

        # convert that home amount to local
        converted_local, err2 = wallet.convert_currency(
            wallet.home_currency, wallet.local_currency, converted_home
        )
        if not err2:
            wallet.balance_local += converted_local

    return wallet.get_summary()