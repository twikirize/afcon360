from app import create_app
from app.extensions import db

app = create_app()
with app.app_context():
    from app.fan.models import FanProfile
    print("FanProfile has is_deleted:", hasattr(FanProfile, 'is_deleted'))
    print("FanProfile has deleted_at:", hasattr(FanProfile, 'deleted_at'))

    # Also check Wallet
    from app.wallet.models import Wallet
    print("\nWallet has is_deleted:", hasattr(Wallet, 'is_deleted'))
    print("Wallet has deleted_at:", hasattr(Wallet, 'deleted_at'))

    # Check if columns exist in database
    print("\nChecking database columns...")
    try:
        # Try to query to see if columns exist
        fan = FanProfile.query.first()
        if fan:
            print(f"FanProfile record exists, checking attributes...")
            print(f"  Can access is_deleted: {hasattr(fan, 'is_deleted')}")
            print(f"  Can access deleted_at: {hasattr(fan, 'deleted_at')}")
        else:
            print("No FanProfile records in database")
    except Exception as e:
        print(f"Error querying FanProfile: {e}")
