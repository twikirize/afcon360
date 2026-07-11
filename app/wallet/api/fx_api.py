"""
app/wallet/api/fx_api.py
Foreign exchange API endpoints for multi-currency operations.

Features:
- Real-time exchange rates
- Currency conversion
- FX transaction history
- Supported currencies
"""

from decimal import Decimal
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user

from app.wallet.services.fx_service import FXService
from app.wallet.exceptions import UnsupportedCurrencyError, ConversionError
from app.wallet.validators import parse_amount, validate_amount

# Create blueprint
fx_api_bp = Blueprint('fx_api', __name__, url_prefix='/api/fx')


# ============================================================================
# RATE ENDPOINTS
# ============================================================================

@fx_api_bp.route('/rates/<base_currency>/<quote_currency>', methods=['GET'])
@login_required
def get_exchange_rate(base_currency, quote_currency):
    """
    Get current exchange rate for currency pair.
    
    Args:
        base_currency: Source currency (e.g., USD)
        quote_currency: Destination currency (e.g., UGX)
        
    Returns:
        JSON with rate information
    """
    try:
        fx_service = FXService()
        rate = fx_service.get_rate(base_currency, quote_currency)
        
        return jsonify({
            "status": "success",
            "data": rate.to_dict()
        }), 200
        
    except UnsupportedCurrencyError as e:
        return jsonify({
            "status": "error",
            "code": "UNSUPPORTED_CURRENCY",
            "message": str(e)
        }), 400
        
    except Exception as e:
        current_app.logger.error(f"Error fetching rate: {e}")
        return jsonify({
            "status": "error",
            "code": "RATE_FETCH_ERROR",
            "message": "Failed to fetch exchange rate"
        }), 500


@fx_api_bp.route('/rates', methods=['GET'])
@login_required
def get_all_rates():
    """
    Get all available exchange rates.
    
    Query params:
        base: Base currency (default: USD)
        
    Returns:
        JSON with all rates for base currency
    """
    try:
        base_currency = request.args.get('base', 'USD').upper()
        fx_service = FXService()
        
        # Get all supported currencies
        currencies = fx_service.get_supported_currencies()
        
        # Fetch rates for all currency pairs
        rates = []
        for quote_currency in currencies:
            if quote_currency != base_currency:
                try:
                    rate = fx_service.get_rate(base_currency, quote_currency)
                    rates.append(rate.to_dict())
                except Exception:
                    continue
        
        return jsonify({
            "status": "success",
            "data": {
                "base_currency": base_currency,
                "rates": rates
            }
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Error fetching rates: {e}")
        return jsonify({
            "status": "error",
            "code": "RATES_FETCH_ERROR",
            "message": "Failed to fetch exchange rates"
        }), 500


# ============================================================================
# CONVERSION ENDPOINTS
# ============================================================================

@fx_api_bp.route('/convert', methods=['POST'])
@login_required
def convert_currency():
    """
    Convert amount between currencies.
    
    Request body:
        {
            "amount": 1000,
            "from_currency": "USD",
            "to_currency": "UGX"
        }
        
    Returns:
        JSON with conversion details
    """
    try:
        data = request.get_json()
        
        # Validate input
        amount = parse_amount(data.get('amount'))
        if not validate_amount(amount):
            return jsonify({
                "status": "error",
                "code": "INVALID_AMOUNT",
                "message": "Invalid amount. Must be greater than zero."
            }), 400
        
        from_currency = data.get('from_currency', '').upper()
        to_currency = data.get('to_currency', '').upper()
        
        if not from_currency or not to_currency:
            return jsonify({
                "status": "error",
                "code": "MISSING_CURRENCY",
                "message": "Both from_currency and to_currency are required."
            }), 400
        
        # Perform conversion
        fx_service = FXService()
        conversion = fx_service.convert_amount(
            amount=amount,
            from_currency=from_currency,
            to_currency=to_currency,
            user_id=current_user.id,
            source_account_id=None,  # Will be set by wallet service
            dest_account_id=None
        )
        
        return jsonify({
            "status": "success",
            "data": {
                "source_amount": str(conversion['source_amount']),
                "dest_amount": str(conversion['dest_amount']),
                "fx_rate": str(conversion['fx_rate']),
                "spread": str(conversion['spread']),
                "platform_fee": str(conversion['platform_fee']),
                "from_currency": from_currency,
                "to_currency": to_currency,
            }
        }), 200
        
    except UnsupportedCurrencyError as e:
        return jsonify({
            "status": "error",
            "code": "UNSUPPORTED_CURRENCY",
            "message": str(e)
        }), 400
        
    except ConversionError as e:
        return jsonify({
            "status": "error",
            "code": "CONVERSION_ERROR",
            "message": str(e)
        }), 400
        
    except Exception as e:
        current_app.logger.error(f"Error converting currency: {e}")
        return jsonify({
            "status": "error",
            "code": "CONVERSION_FAILED",
            "message": "Failed to convert currency"
        }), 500


# ============================================================================
# HISTORY ENDPOINTS
# ============================================================================

@fx_api_bp.route('/history', methods=['GET'])
@login_required
def get_fx_history():
    """
    Get FX transaction history for current user.
    
    Query params:
        limit: Maximum number of records (default: 50)
        
    Returns:
        JSON with transaction history
    """
    try:
        limit = request.args.get('limit', 50, type=int)
        limit = min(limit, 100)  # Cap at 100
        
        fx_service = FXService()
        transactions = fx_service.get_user_fx_history(current_user.id, limit)
        
        return jsonify({
            "status": "success",
            "data": {
                "transactions": [tx.to_dict() for tx in transactions],
                "count": len(transactions)
            }
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Error fetching FX history: {e}")
        return jsonify({
            "status": "error",
            "code": "HISTORY_FETCH_ERROR",
            "message": "Failed to fetch transaction history"
        }), 500


# ============================================================================
# SUPPORTED CURRENCIES
# ============================================================================

@fx_api_bp.route('/currencies', methods=['GET'])
@login_required
def get_supported_currencies():
    """
    Get list of supported currencies.
    
    Returns:
        JSON with supported currencies
    """
    try:
        fx_service = FXService()
        currencies = fx_service.get_supported_currencies()
        
        return jsonify({
            "status": "success",
            "data": {
                "currencies": currencies,
                "count": len(currencies)
            }
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Error fetching currencies: {e}")
        return jsonify({
            "status": "error",
            "code": "CURRENCIES_FETCH_ERROR",
            "message": "Failed to fetch supported currencies"
        }), 500
