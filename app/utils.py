# app/wallet/utils.py

"""
def wallet_to_dict(wallet):
    return {
        "user_id": wallet.user_id,
        "home_currency": wallet.home_currency,
        "nationality": wallet.nationality,
        "location": wallet.location,
        "verified": wallet.verified,
        "balance_home": wallet.balance_home,
        "balance_local": wallet.balance_local,
        "transactions": wallet.transactions,
        "local_currency": wallet.local_currency
    }

def dict_to_wallet(data, Wallet):
    wallet = Wallet(
        user_id=data["user_id"],
        home_currency=data["home_currency"],
        nationality=data["nationality"],
        location=data["location"],
        verified=data["verified"]
    )
    wallet.balance_home = data["balance_home"]
    wallet.balance_local = data["balance_local"]
    wallet.transactions = data["transactions"]
    wallet.local_currency = data["local_currency"]
    return wallet
"""
####
# app/wallet/utils.py
from flask import session
from .models import Wallet

def wallet_to_dict(wallet: Wallet):
    return {
        "user_id": wallet.user_id,
        "home_currency": wallet.home_currency,
        "nationality": wallet.nationality,
        "location": wallet.location,
        "local_currency": wallet.local_currency,
        "verified": wallet.verified,
        "balance_home": wallet.balance_home,
        "balance_local": wallet.balance_local,
        "transactions": wallet.transactions,
    }

def dict_to_wallet(data, wallet_class=Wallet):
    wallet = wallet_class(
        user_id=data["user_id"],
        home_currency=data["home_currency"],
        nationality=data["nationality"],
        location=data["location"],
        verified=data.get("verified", False),
        local_currency=data.get("local_currency") or "UGX",
    )
    wallet.balance_home = data.get("balance_home", 0.0)
    wallet.balance_local = data.get("balance_local", 0.0)
    wallet.transactions = data.get("transactions", [])
    return wallet

def get_or_create_wallet():
    if "wallet" in session:
        return dict_to_wallet(session["wallet"])
    # Seed a default wallet for demo
    wallet = Wallet(user_id="fan003", home_currency="USD", nationality="UG", location="UG", verified=True, local_currency="UGX")
    session["wallet"] = wallet_to_dict(wallet)
    return wallet
