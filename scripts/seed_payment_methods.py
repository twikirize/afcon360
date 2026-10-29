# seed_payment_configs.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.wallet import PaymentMethodConfig


BUILTIN_TIMINGS = {
    'wallet': ['pay_now', 'deposit', 'pay_on_completion'],
    'cash': ['pay_on_arrival', 'pay_on_completion'],
}

def seed_configs():
    app = create_app()
    with app.app_context():
        PaymentMethodConfig.initialize_defaults()
        repaired = []
        for method_id, timings in BUILTIN_TIMINGS.items():
            method = PaymentMethodConfig.query.filter_by(method_id=method_id).first()
            if method:
                current_timings = [
                    str(timing).strip().lower()
                    for timing in (method.allowed_timings or [])
                ]
                updated_timings = list(current_timings)
                for timing in timings:
                    if timing not in updated_timings:
                        updated_timings.append(timing)
                if updated_timings != current_timings:
                    method.allowed_timings = updated_timings
                    repaired.append(method_id)
        from app.extensions import db
        db.session.commit()
        print(f'SEEDED; repaired={repaired}')

if __name__ == '__main__':
    seed_configs()