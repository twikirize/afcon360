# app/wallet/services/receiver.py
from app.identity.models.user import User
from app.wallet.wallet import Wallet
from typing import Dict

# In-memory registry keyed by public identifier (username or user_id string)
receiver_registry: Dict[str, Wallet] = {}

def resolve_identifier_to_internal_id(identifier: str) -> int:
    """
    Resolve a public identifier (user.user_id or username) to internal users.id (BIGINT).
    Raises ValueError if not found.
    """
    user = (
        User.query.filter_by(user_id=identifier).first()
        or User.query.filter_by(username=identifier).first()
    )
    if not user:
        raise ValueError(f"No user found for identifier: {identifier}")
    return user.id

def get_or_create_receiver(receiver_identifier: str) -> Wallet:
    """
    Return a Wallet bound to the internal users.id for the given identifier.
    Keeps an in-memory registry keyed by the public identifier for convenience.
    """
    if receiver_identifier in receiver_registry:
        return receiver_registry[receiver_identifier]

    internal_id = resolve_identifier_to_internal_id(receiver_identifier)
    wallet = Wallet(user_id=internal_id)
    receiver_registry[receiver_identifier] = wallet
    return wallet

def log_receiver_transaction(receiver_identifier: str, tx_data: dict) -> Wallet:
    """
    Append a transaction dict to the receiver wallet's transactions list.
    """
    wallet = get_or_create_receiver(receiver_identifier)
    wallet.transactions.append(tx_data)
    return wallet

def get_receiver_balance(receiver_identifier: str):
    wallet = receiver_registry.get(receiver_identifier)
    return wallet.balance_local if wallet else None

def get_receiver_transactions(receiver_identifier: str):
    wallet = receiver_registry.get(receiver_identifier)
    return wallet.transactions if wallet else []
