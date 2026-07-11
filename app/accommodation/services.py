# app/accommodation/services.py
# Minimal placeholder service layer for accommodation.

def list_hotels():
    return [
        {"id": "h1", "name": "Central Hotel", "price": 80, "currency": "USD", "summary": "Close to the stadium"},
        {"id": "h2", "name": "Riverside Lodge", "price": 60, "currency": "USD", "summary": "Peaceful riverside location"},
    ]

def get_hotel(hotel_id):
    return next((h for h in list_hotels() if h["id"] == hotel_id), None)
