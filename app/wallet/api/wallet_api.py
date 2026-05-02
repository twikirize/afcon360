"""
app/wallet/api/wallet_api.py
REST API endpoints for wallet operations with security fixes.

Fixed vulnerabilities:
- CORS: Uses ALLOWED_ORIGINS from config instead of wildcard *
- Added @require_not_frozen decorator
- Commission recording moved inside transaction boundary
"""

from datetime import datetime
from decimal import Decimal
from functools import wraps
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user

# SECURITY: Rate limiting for financial endpoints
from app.extensions import limiter

from app.wallet.services.wallet_service import WalletService
from app.wallet.services.currency_service import CurrencyService
from app.wallet.validators import DepositRequest, WithdrawRequest, TransferRequest, extract_idempotency_key
# from app.wallet.middleware.kill_switch import require_wallet_enabled  # DELETED
from app.wallet.exceptions import (
    InsufficientBalanceError,
    UnsupportedCurrencyError,
    WalletNotFoundError,
    LimitExceededError,
    DuplicateTransactionError,
    WalletFrozenError,
    ConversionError
)

# Create blueprint
wallet_api_bp = Blueprint('wallet_api', __name__, url_prefix='/api/wallet')


# ============================================================================
# SECURITY DECORATORS
# ============================================================================

def require_not_frozen(f):
    """Decorator to check if user's wallet is not frozen."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        service = WalletService()
        # Check if wallet is frozen
        wallet = service.wallet_repo.get_by_user_id(current_user.id)
        if wallet and wallet.is_frozen:
            return jsonify({
                "status": "error",
                "code": "WALLET_FROZEN",
                "message": f"Wallet is frozen: {wallet.frozen_reason or 'No reason provided'}"
            }), 403
        return f(*args, **kwargs)
    return decorated_function


def require_role(*allowed_roles):
    """Decorator to check if user has required role."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Simple role check - enhance based on your auth system
            if not hasattr(current_user, 'role') or current_user.role not in allowed_roles:
                return jsonify({
                    "status": "error",
                    "code": "FORBIDDEN",
                    "message": "Insufficient permissions"
                }), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def validate_csrf_token(f):
    """
    Decorator to validate CSRF token for state-changing operations.
    
    SECURITY: This prevents cross-site request forgery attacks.
    Token must be provided in X-CSRF-Token header.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask_wtf.csrf import validate_csrf
        from flask import session
        
        # Get CSRF token from header
        csrf_token = request.headers.get('X-CSRF-Token') or request.headers.get('X-CSRFToken')
        
        if not csrf_token:
            return jsonify({
                "status": "error",
                "code": "CSRF_TOKEN_REQUIRED",
                "message": "X-CSRF-Token header is required for this operation"
            }), 403
        
        try:
            validate_csrf(csrf_token)
        except Exception as e:
            current_app.logger.warning(f"CSRF validation failed: {e}")
            return jsonify({
                "status": "error",
                "code": "INVALID_CSRF_TOKEN",
                "message": "Invalid or expired CSRF token"
            }), 403
        
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# WALLET BALANCE ENDPOINTS
# ============================================================================

@wallet_api_bp.route('/me', methods=['GET'])
@login_required

def get_my_wallet():
    """
    Get current user's wallet balance.

    GET /api/wallet/me

    Response:
    {
        "status": "success",
        "data": {
            "exists": true,
            "balance": "1000.00",
            "currency": "USD",
            "is_frozen": false
        }
    }
    """
    try:
        service = WalletService()
        balance = service.get_balance(current_user.id)

        return jsonify({
            "status": "success",
            "data": balance
        })
    except Exception as e:
        current_app.logger.error(f"Wallet balance error: {e}")
        return jsonify({
            "status": "error",
            "code": "INTERNAL_ERROR",
            "message": "Unable to retrieve wallet balance"
        }), 500


# ============================================================================
# DEPOSIT ENDPOINTS
# ============================================================================

@wallet_api_bp.route('/deposit', methods=['POST'])
@login_required
@validate_csrf_token
@require_not_frozen
@limiter.limit("10 per minute", key_func=lambda: current_user.id)
@limiter.limit("50 per hour", key_func=lambda: current_user.id)
def deposit():
    """
    Deposit funds into wallet.

    POST /api/wallet/deposit
    Headers:
        X-Idempotency-Key: unique_client_generated_key

    Body:
    {
        "amount": "100.00",
        "currency": "USD",
        "payment_method": "mobile_money",
        "payment_provider": "flutterwave",
        "external_reference": "ref_123"
    }

    Response:
    {
        "status": "success",
        "data": {
            "transaction_id": "tx_abc123",
            "amount": "100.00",
            "currency": "USD",
            "new_balance": "1100.00"
        }
    }
    """
    try:
        # Validate request
        data = request.get_json()
        if not data:
            return jsonify({
                "status": "error",
                "code": "INVALID_REQUEST",
                "message": "Request body is required"
            }), 400

        validated, error = DepositRequest.validate(data)
        if error:
            return jsonify({
                "status": "error",
                "code": "VALIDATION_ERROR",
                "message": error
            }), 400

        # Get idempotency key from header (priority) or body
        idempotency_key = extract_idempotency_key()
        if not idempotency_key:
            return jsonify({
                "status": "error",
                "code": "IDEMPOTENCY_KEY_REQUIRED",
                "message": "X-Idempotency-Key header is required"
            }), 400

        # Process deposit
        service = WalletService()
        result = service.deposit(
            user_id=current_user.id,
            amount=validated['amount'],
            currency=validated['currency'],
            client_request_id=idempotency_key,
            metadata=validated.get('metadata', {}),
            payment_method=data.get('payment_method'),
            payment_provider=data.get('payment_provider'),
            external_reference=data.get('external_reference')
        )

        return jsonify({
            "status": "success",
            "data": result
        }), 200

    except DuplicateTransactionError as e:
        return jsonify({
            "status": "error",
            "code": "DUPLICATE_REQUEST",
            "message": str(e),
            "existing_transaction_id": e.existing_transaction_id
        }), 409

    except UnsupportedCurrencyError as e:
        return jsonify({
            "status": "error",
            "code": "UNSUPPORTED_CURRENCY",
            "message": str(e),
            "supported_currencies": e.supported
        }), 400

    except LimitExceededError as e:
        return jsonify({
            "status": "error",
            "code": "LIMIT_EXCEEDED",
            "message": str(e),
            "limit_type": e.limit_type,
            "limit": float(e.limit),
            "current": float(e.current)
        }), 429

    except WalletFrozenError as e:
        return jsonify({
            "status": "error",
            "code": "WALLET_FROZEN",
            "message": str(e)
        }), 403

    except ValueError as e:
        return jsonify({
            "status": "error",
            "code": "VALIDATION_ERROR",
            "message": str(e)
        }), 400

    except Exception as e:
        current_app.logger.error(f"Deposit error for user {current_user.id}: {e}")
        return jsonify({
            "status": "error",
            "code": "INTERNAL_ERROR",
            "message": "Deposit processing failed. Please try again."
        }), 500


# ============================================================================
# WITHDRAWAL ENDPOINTS
# ============================================================================

@wallet_api_bp.route('/withdraw', methods=['POST'])
@login_required
@validate_csrf_token
@require_not_frozen
@limiter.limit("5 per minute", key_func=lambda: current_user.id)
@limiter.limit("20 per hour", key_func=lambda: current_user.id)
def withdraw():
    """
    Withdraw funds from wallet.

    POST /api/wallet/withdraw
    Headers:
        X-Idempotency-Key: unique_client_generated_key

    Body:
    {
        "amount": "50.00",
        "currency": "UGX",
        "destination_type": "mobile_money",
        "destination_details": {
            "phone": "256700000000",
            "provider": "mtn"
        }
    }

    Response:
    {
        "status": "success",
        "data": {
            "transaction_id": "tx_abc123",
            "amount": "50.00",
            "currency": "UGX",
            "new_balance": "950.00"
        }
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "status": "error",
                "code": "INVALID_REQUEST",
                "message": "Request body is required"
            }), 400

        validated, error = WithdrawRequest.validate(data)
        if error:
            return jsonify({
                "status": "error",
                "code": "VALIDATION_ERROR",
                "message": error
            }), 400

        idempotency_key = extract_idempotency_key()
        if not idempotency_key:
            return jsonify({
                "status": "error",
                "code": "IDEMPOTENCY_KEY_REQUIRED",
                "message": "X-Idempotency-Key header is required"
            }), 400

        service = WalletService()
        result = service.withdraw(
            user_id=current_user.id,
            amount=validated['amount'],
            currency=validated['currency'],
            client_request_id=idempotency_key,
            metadata=validated.get('metadata', {}),
            destination_type=data.get('destination_type'),
            destination_details=data.get('destination_details'),
            payment_method=data.get('payment_method'),
            payment_provider=data.get('payment_provider')
        )

        return jsonify({
            "status": "success",
            "data": result
        }), 200

    except InsufficientBalanceError as e:
        return jsonify({
            "status": "error",
            "code": "INSUFFICIENT_BALANCE",
            "message": str(e),
            "required": e.required,
            "available": e.available,
            "currency": e.currency
        }), 402

    except DuplicateTransactionError as e:
        return jsonify({
            "status": "error",
            "code": "DUPLICATE_REQUEST",
            "message": str(e)
        }), 409

    except WalletFrozenError as e:
        return jsonify({
            "status": "error",
            "code": "WALLET_FROZEN",
            "message": str(e)
        }), 403

    except Exception as e:
        current_app.logger.error(f"Withdrawal error for user {current_user.id}: {e}")
        return jsonify({
            "status": "error",
            "code": "INTERNAL_ERROR",
            "message": "Withdrawal processing failed. Please try again."
        }), 500


# ============================================================================
# TRANSFER ENDPOINTS
# ============================================================================

@wallet_api_bp.route('/transfer', methods=['POST'])
@login_required
@validate_csrf_token
@require_not_frozen
@limiter.limit("10 per minute", key_func=lambda: current_user.id)
@limiter.limit("50 per hour", key_func=lambda: current_user.id)
def transfer():
    """
    Transfer funds to another user.

    POST /api/wallet/transfer
    Headers:
        X-Idempotency-Key: unique_client_generated_key

    Body:
    {
        "to_user_id": 12345,
        "amount": "25.00",
        "currency": "USD",
        "note": "Payment for services",
        "platform_fee": "0.50"
    }

    Response:
    {
        "status": "success",
        "data": {
            "transaction_id": "tx_abc123",
            "amount": "25.00",
            "currency": "USD",
            "new_balance_from": "975.00",
            "new_balance_to": "1025.00"
        }
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "status": "error",
                "code": "INVALID_REQUEST",
                "message": "Request body is required"
            }), 400

        validated, error = TransferRequest.validate(data)
        if error:
            return jsonify({
                "status": "error",
                "code": "VALIDATION_ERROR",
                "message": error
            }), 400

        idempotency_key = extract_idempotency_key()
        if not idempotency_key:
            return jsonify({
                "status": "error",
                "code": "IDEMPOTENCY_KEY_REQUIRED",
                "message": "X-Idempotency-Key header is required"
            }), 400

        # Parse platform fee if provided
        platform_fee = None
        fee_currency = None
        if data.get('platform_fee'):
            try:
                platform_fee = Decimal(str(data.get('platform_fee')))
                fee_currency = data.get('fee_currency', validated['currency'])
            except:
                pass

        service = WalletService()
        result = service.transfer(
            from_user_id=current_user.id,
            to_user_id=validated['to_user_id'],
            amount=validated['amount'],
            currency=validated['currency'],
            client_request_id=idempotency_key,
            note=validated.get('note'),
            metadata=validated.get('metadata', {}),
            platform_fee=platform_fee,
            fee_currency=fee_currency
        )

        # Commission recording is now INSIDE the transfer transaction
        # This is handled by the service layer, not here
        # If platform_fee was provided, the service handles it atomically

        return jsonify({
            "status": "success",
            "data": result
        }), 200

    except InsufficientBalanceError as e:
        return jsonify({
            "status": "error",
            "code": "INSUFFICIENT_BALANCE",
            "message": str(e),
            "required": e.required,
            "available": e.available,
            "currency": e.currency
        }), 402

    except DuplicateTransactionError as e:
        return jsonify({
            "status": "error",
            "code": "DUPLICATE_REQUEST",
            "message": str(e)
        }), 409

    except ValueError as e:
        return jsonify({
            "status": "error",
            "code": "VALIDATION_ERROR",
            "message": str(e)
        }), 400

    except Exception as e:
        current_app.logger.error(f"Transfer error from user {current_user.id}: {e}")
        return jsonify({
            "status": "error",
            "code": "INTERNAL_ERROR",
            "message": "Transfer failed. Please try again."
        }), 500


# ============================================================================
# TRANSACTION HISTORY ENDPOINTS
# ============================================================================

@wallet_api_bp.route('/transactions', methods=['GET'])
@login_required

def get_transactions():
    """
    Get transaction history.

    GET /api/wallet/transactions?limit=50&offset=0&type=deposit

    Response:
    {
        "status": "success",
        "data": {
            "transactions": [...],
            "total": 150,
            "limit": 50,
            "offset": 0,
            "has_more": true
        }
    }
    """
    try:
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        transaction_type = request.args.get('type')

        # Cap limit
        limit = min(limit, 100)

        service = WalletService()
        result = service.get_transaction_history(
            user_id=current_user.id,
            limit=limit,
            offset=offset,
            transaction_type=transaction_type
        )

        return jsonify({
            "status": "success",
            "data": result
        })

    except Exception as e:
        current_app.logger.error(f"Transaction history error for user {current_user.id}: {e}")
        return jsonify({
            "status": "error",
            "code": "INTERNAL_ERROR",
            "message": "Unable to retrieve transaction history"
        }), 500


# ============================================================================
# COMMISSION ENDPOINTS
# ============================================================================

@wallet_api_bp.route('/commissions', methods=['GET'])
@login_required

def get_commissions():
    """
    Get agent commissions.

    GET /api/wallet/commissions?status=pending&limit=50
    """
    try:
        status = request.args.get('status')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)

        commission_service = CommissionService()

        # Get summary
        summary = commission_service.get_commission_summary(current_user.id)

        # Get list
        commissions = commission_service.get_agent_commissions(
            agent_id=current_user.id,
            status=status,
            limit=limit,
            offset=offset
        )

        return jsonify({
            "status": "success",
            "data": {
                "summary": summary,
                "commissions": commissions,
                "limit": limit,
                "offset": offset
            }
        })

    except Exception as e:
        current_app.logger.error(f"Commissions error for user {current_user.id}: {e}")
        return jsonify({
            "status": "error",
            "code": "INTERNAL_ERROR",
            "message": "Unable to retrieve commissions"
        }), 500


# ============================================================================
# PAYOUT ENDPOINTS
# ============================================================================

@wallet_api_bp.route('/payouts', methods=['POST'])
@login_required

@require_not_frozen
def create_payout():
    """
    Create a payout request.

    POST /api/wallet/payouts

    Body:
    {
        "amount": "100.00",
        "currency": "UGX",
        "payment_method": "bank",
        "payment_details": {
            "bank_name": "Stanbic",
            "account_number": "1234567890",
            "account_name": "John Doe"
        }
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "status": "error",
                "code": "INVALID_REQUEST",
                "message": "Request body is required"
            }), 400

        amount = data.get('amount')
        currency = data.get('currency', 'UGX')
        payment_method = data.get('payment_method', 'bank')
        payment_details = data.get('payment_details', {})

        if not amount:
            return jsonify({
                "status": "error",
                "code": "VALIDATION_ERROR",
                "message": "Amount is required"
            }), 400

        try:
            amount_dec = Decimal(str(amount))
        except:
            return jsonify({
                "status": "error",
                "code": "VALIDATION_ERROR",
                "message": "Invalid amount format"
            }), 400

        payout_service = PayoutService()
        result = payout_service.create_request(
            agent_id=current_user.id,
            amount=amount_dec,
            currency=currency,
            payment_method=payment_method,
            payment_details=payment_details,
            metadata=data.get('metadata')
        )

        return jsonify({
            "status": "success",
            "data": result
        }), 201

    except ValueError as e:
        return jsonify({
            "status": "error",
            "code": "VALIDATION_ERROR",
            "message": str(e)
        }), 400
    except Exception as e:
        current_app.logger.error(f"Payout creation error for user {current_user.id}: {e}")
        return jsonify({
            "status": "error",
            "code": "INTERNAL_ERROR",
            "message": "Unable to create payout request"
        }), 500


@wallet_api_bp.route('/payouts', methods=['GET'])
@login_required

def list_payouts():
    """
    List payout requests for the current user.

    GET /api/wallet/payouts?status=pending&limit=50
    """
    try:
        status = request.args.get('status')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)

        payout_service = PayoutService()
        payouts = payout_service.list_requests(
            agent_id=current_user.id,
            status=status,
            limit=limit,
            offset=offset
        )

        summary = payout_service.get_agent_payout_summary(current_user.id)

        return jsonify({
            "status": "success",
            "data": {
                "summary": summary,
                "payouts": payouts,
                "limit": limit,
                "offset": offset
            }
        })

    except Exception as e:
        current_app.logger.error(f"Payout list error for user {current_user.id}: {e}")
        return jsonify({
            "status": "error",
            "code": "INTERNAL_ERROR",
            "message": "Unable to retrieve payouts"
        }), 500


# ============================================================================
# CURRENCY ENDPOINTS
# ============================================================================

@wallet_api_bp.route('/currencies', methods=['GET'])
@login_required
def get_supported_currencies():
    """
    Get list of supported currencies and current rates.

    GET /api/wallet/currencies
    """
    try:
        currency_service = CurrencyService()

        rates = {}
        home = current_app.config.get("HOME_CURRENCY_DEFAULT", "USD")
        local = current_app.config.get("LOCAL_CURRENCY_DEFAULT", "UGX")

        # Get current rates
        rate_home_to_local = currency_service.get_rate(home, local)
        if rate_home_to_local:
            rates[f"{home}_TO_{local}"] = str(rate_home_to_local)

        rate_local_to_home = currency_service.get_rate(local, home)
        if rate_local_to_home:
            rates[f"{local}_TO_{home}"] = str(rate_local_to_home)

        return jsonify({
            "status": "success",
            "data": {
                "supported": currency_service.get_supported_currencies(),
                "home_currency": home,
                "local_currency": local,
                "rates": rates,
                "last_updated": datetime.utcnow().isoformat()
            }
        })

    except Exception as e:
        current_app.logger.error(f"Currency list error: {e}")
        return jsonify({
            "status": "error",
            "code": "INTERNAL_ERROR",
            "message": "Unable to retrieve currency information"
        }), 500


@wallet_api_bp.route('/convert', methods=['POST'])
@login_required

def convert_currency():
    """
    Convert an amount between currencies (estimate, not actual transaction).

    POST /api/wallet/convert

    Body:
    {
        "amount": "100.00",
        "from_currency": "USD",
        "to_currency": "UGX"
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "status": "error",
                "code": "INVALID_REQUEST",
                "message": "Request body is required"
            }), 400

        amount = data.get('amount')
        from_currency = data.get('from_currency', '').upper()
        to_currency = data.get('to_currency', '').upper()

        if not amount or not from_currency or not to_currency:
            return jsonify({
                "status": "error",
                "code": "VALIDATION_ERROR",
                "message": "amount, from_currency, and to_currency are required"
            }), 400

        try:
            amount_dec = Decimal(str(amount))
        except:
            return jsonify({
                "status": "error",
                "code": "VALIDATION_ERROR",
                "message": "Invalid amount format"
            }), 400

        if amount_dec <= 0:
            return jsonify({
                "status": "error",
                "code": "VALIDATION_ERROR",
                "message": "Amount must be greater than zero"
            }), 400

        currency_service = CurrencyService()

        if not currency_service.validate_currency(from_currency):
            return jsonify({
                "status": "error",
                "code": "UNSUPPORTED_CURRENCY",
                "message": f"Unsupported currency: {from_currency}"
            }), 400

        if not currency_service.validate_currency(to_currency):
            return jsonify({
                "status": "error",
                "code": "UNSUPPORTED_CURRENCY",
                "message": f"Unsupported currency: {to_currency}"
            }), 400

        converted, rate, fee = currency_service.convert(
            amount_dec, from_currency, to_currency, apply_fee=True
        )

        return jsonify({
            "status": "success",
            "data": {
                "original_amount": str(amount_dec),
                "original_currency": from_currency,
                "converted_amount": str(converted),
                "target_currency": to_currency,
                "rate": str(rate),
                "fee": str(fee),
                "net_amount": str(converted)
            }
        })

    except Exception as e:
        current_app.logger.error(f"Currency conversion error: {e}")
        return jsonify({
            "status": "error",
            "code": "CONVERSION_ERROR",
            "message": str(e)
        }), 400


# ============================================================================
# HEALTH CHECK ENDPOINT
# ============================================================================

@wallet_api_bp.route('/home', methods=['GET'])
def wallet_home():
    """
    Wallet home page endpoint.

    GET /api/wallet/home
    """
    return jsonify({
        "status": "success",
        "message": "Wallet home"
    }), 200


@wallet_api_bp.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint for wallet API.

    GET /api/wallet/health
    """
    from app.wallet.middleware.kill_switch import wallet_enabled

    return jsonify({
        "status": "healthy",
        "wallet_enabled": wallet_enabled(),
        "timestamp": datetime.utcnow().isoformat(),
        "version": "3.0.0"  # New version for ledger rebuild
    }), 200


# ============================================================================
# CORS HEADERS (SECURE CONFIGURATION)
# ============================================================================

@wallet_api_bp.after_request
def add_cors_headers(response):
    """
    Add CORS headers for external access.
    
    FIXED: Uses ALLOWED_ORIGINS from config instead of wildcard *
    """
    allowed_origins = current_app.config.get('ALLOWED_ORIGINS', ['http://localhost:5000'])
    origin = request.headers.get('Origin')
    
    # Only allow specific origins from config
    if origin in allowed_origins:
        response.headers['Access-Control-Allow-Origin'] = origin
    
    response.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type, X-Idempotency-Key, X-CSRF-Token'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    
    return response
