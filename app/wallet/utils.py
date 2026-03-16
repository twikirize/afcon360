from datetime import datetime
from typing import Any, Dict, Optional
from app.extensions import db

def get_or_create_wallet(user_id: int):
    """
    user_id: internal BIGINT PK from users.id.
    Return the WalletModel row for user_id, creating it if missing.
    """
    from app.wallet.models import WalletModel

    if isinstance(user_id, str):
        raise TypeError("WalletModel.user_id must be internal integer users.id, not a public string")

    wallet = WalletModel.query.filter_by(user_id=user_id).first()
    if wallet:
        return wallet

    wallet = WalletModel(
        user_id=user_id,
        home_currency="USD",
        local_currency="UGX",
        balance_home=0,
        balance_local=0,
    )
    db.session.add(wallet)
    db.session.commit()
    return wallet


def wallet_to_dict(wallet) -> Dict[str, Any]:
    """
    Serialize a WalletModel or wallet-like object to a dict.
    """
    if wallet is None:
        return {}

    try:
        if hasattr(wallet, "get_balances") and callable(wallet.get_balances):
            balances = wallet.get_balances()
            return {"user_id": getattr(wallet, "user_id", None), "balances": balances}
    except Exception:
        pass

    return {
        "user_id": getattr(wallet, "user_id", None),
        "home_currency": getattr(wallet, "home_currency", None),
        "local_currency": getattr(wallet, "local_currency", None),
        "balance_home": str(getattr(wallet, "balance_home", 0)),
        "balance_local": str(getattr(wallet, "balance_local", 0)),
        "disabled_features": getattr(wallet, "disabled_features", {}) or {},
        "verified": bool(getattr(wallet, "verified", False)),
        "updated_at": (
            getattr(wallet, "updated_at", None) and getattr(wallet, "updated_at").isoformat() or None
        ),
    }


def dict_to_wallet(data: Dict[str, Any], wallet_class: Optional[type] = None):
    """
    Create or update a WalletModel from a dict.
    user_id must be internal BIGINT (users.id).
    """
    if wallet_class is None:
        from app.wallet.models import WalletModel as _WalletModel
        wallet_class = _WalletModel

    user_id = data.get("user_id")
    if user_id is None:
        raise ValueError("user_id is required to create/update a wallet")
    if isinstance(user_id, str):
        raise TypeError("wallet.user_id must be internal integer users.id, not a public string")

    wallet = wallet_class.query.filter_by(user_id=user_id).first()
    if not wallet:
        wallet = wallet_class(user_id=user_id)

    if "home_currency" in data:
        wallet.home_currency = data["home_currency"]
    if "local_currency" in data:
        wallet.local_currency = data["local_currency"]
    if "balance_home" in data:
        wallet.balance_home = data["balance_home"]
    if "balance_local" in data:
        wallet.balance_local = data["balance_local"]
    if "disabled_features" in data:
        wallet.disabled_features = data["disabled_features"]

    db.session.add(wallet)
    db.session.commit()
    return wallet
