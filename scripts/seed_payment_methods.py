# seed_payment_configs.py
from app import create_app
from app.wallet import PaymentMethodConfig

def seed_configs():
    app = create_app()
    with app.app_context():
        PaymentMethodConfig.initialize_defaults()
        print('SEEDED')

if __name__ == '__main__':
    seed_configs()