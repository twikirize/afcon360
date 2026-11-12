"""
Payment Provider Enums - Shared definitions
"""

from enum import Enum


class PaymentProvider(Enum):
    FLUTTERWAVE = "flutterwave"
    PAYSTACK = "paystack"
    MTN_MOMO = "mtn_momo"
    AIRTEL_MONEY = "airtel_money"
    VISA = "visa"
    MASTERCARD = "mastercard"
    UNIONPAY = "unionpay"
    BANK_TRANSFER = "bank_transfer"


class PaymentMethod(Enum):
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    MOBILE_MONEY = "mobile_money"
    USSD = "ussd"
    QR_CODE = "qr_code"