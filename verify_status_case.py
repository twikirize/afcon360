
from app import create_app
from app.extensions import db
from app.wallet.models.transaction import TransactionModel

app = create_app()
with app.app_context():
    # Attempt to insert with lowercase status
    try:
        txn = TransactionModel(
            status='completed', # Lowercase
            amount=100.0,
            currency='USD',
            tx_type='deposit',
            client_request_id='test_ref_123'
        )
        db.session.add(txn)
        db.session.commit()
        print("SUCCESS: Lowercase status inserted.")
    except Exception as e:
        db.session.rollback()
        print(f"FAILED: Status constraint rejected lowercase: {e}")
