# seed_payment_configs.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.wallet import PaymentMethodConfig


BUILTIN_TIMINGS = {
    'wallet': ['pay_now', 'deposit'],
    'cash': ['pay_on_arrival'],
}

def seed_configs():
    app = create_app()
    with app.app_context():
        PaymentMethodConfig.initialize_defaults()
        repaired = []
        for method_id, timings in BUILTIN_TIMINGS.items():
            method = PaymentMethodConfig.query.filter_by(method_id=method_id).first()
            if method and not method.allowed_timings:
                method.allowed_timings = timings
                repaired.append(method_id)
        from app.extensions import db
        db.session.commit()
        print(f'SEEDED; repaired={repaired}')

if __name__ == '__main__':
    seed_configs()