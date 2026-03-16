# app/wallet/routes.py
from decimal import Decimal, InvalidOperation
from flask import Blueprint, request, jsonify, render_template, session, flash, redirect, url_for
from flask_login import login_required, current_user
from datetime import datetime, timezone as UTC
from app.wallet.wallet import Wallet
from app.wallet.utils import get_or_create_wallet, wallet_to_dict
from app.wallet.services.receiver import get_or_create_receiver, log_receiver_transaction
from app.wallet.services.withdraw_service import process_withdrawal
from app.wallet.services.agent_tracker import get_agent_total, get_agent_commissions, log_agent_commission
from app.wallet.services.agent_payouts import create_payout_request, list_payout_requests, update_payout_status

# --------------------------
# JSON API Blueprint
# --------------------------
wallet_bp = Blueprint("wallet_bp", __name__, url_prefix="/wallet")

def parse_amount(value):
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        return None

@wallet_bp.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    svc = Wallet(current_user.id)
    return jsonify({"status": "success", "balances": svc.get_balances()})

@wallet_bp.route("/deposit", methods=["POST"])
@login_required
def deposit():
    svc = Wallet(current_user.id)
    amount = parse_amount(request.json.get("amount"))
    if amount is None or amount <= 0:
        return jsonify({"status": "error", "message": "Invalid amount"}), 400
    currency = request.json.get("currency", "USD")
    client_request_id = request.json.get("client_request_id")
    res = svc.deposit(amount=amount, currency=currency, client_request_id=client_request_id)
    return jsonify(res), 200 if res.get("status") in ("success", "ok") else 400

@wallet_bp.route("/withdraw", methods=["POST"])
@login_required
def withdraw():
    svc = Wallet(current_user.id)
    amount = parse_amount(request.json.get("amount"))
    if amount is None or amount <= 0:
        return jsonify({"status": "error", "message": "Invalid amount"}), 400
    currency = request.json.get("currency")
    client_request_id = request.json.get("client_request_id")
    res = svc.withdraw(amount=amount, currency=currency, client_request_id=client_request_id)
    return jsonify(res), 200 if res.get("status") == "success" else 400

@wallet_bp.route("/send", methods=["POST"])
@login_required
def send():
    svc = Wallet(current_user.id)
    amount = parse_amount(request.json.get("amount"))
    if amount is None or amount <= 0:
        return jsonify({"status": "error", "message": "Invalid amount"}), 400
    receiver_id = request.json.get("receiver_user_id")
    currency = request.json.get("currency")
    platform_fee = request.json.get("platform_fee")
    client_request_id = request.json.get("client_request_id")
    res = svc.send_to_peer(
        receiver_user_id=receiver_id,
        amount=amount,
        currency=currency,
        platform_fee=platform_fee,
        client_request_id=client_request_id
    )
    return jsonify(res), 200 if res.get("status") == "success" else 400

# --------------------------
# HTML Template Blueprint
# --------------------------
wallet_routes = Blueprint("wallet_routes", __name__)

@wallet_routes.route("/wallet", endpoint="wallet_home")
def wallet_home():
    return render_template("wallet_home.html")

@wallet_routes.route("/wallet/dashboard")
def wallet_dashboard():
    wallet = get_or_create_wallet()
    commission = get_agent_total(wallet.user_id)
    recent_transactions = wallet.transactions[-5:][::-1]  # latest first
    return render_template(
        "wallet_dashboard.html",
        wallet=wallet,
        commission=commission,
        recent_transactions=recent_transactions,
        title="My Wallet Dashboard"
    )

# Deposit form (HTML)
@wallet_routes.route("/wallet/deposit-form", methods=["POST"])
def deposit_form():
    wallet = get_or_create_wallet()
    try:
        amount = Decimal(request.form.get("amount", "0"))
    except (InvalidOperation, TypeError):
        flash("Invalid amount.", "danger")
        return redirect(url_for("wallet_routes.wallet_dashboard"))

    currency = request.form.get("currency") or wallet.home_currency
    if amount <= 0:
        flash("Amount must be greater than zero.", "danger")
        return redirect(url_for("wallet_routes.wallet_dashboard"))

    wallet.balance_home += amount
    wallet.transactions.append({
        "type": "deposit_home",
        "amount": float(amount),
        "currency": currency,
        "timestamp": datetime.now(UTC).isoformat()
    })
    session["wallet"] = wallet_to_dict(wallet)
    flash("Deposit successful.", "success")
    return redirect(url_for("wallet_routes.wallet_dashboard"))

# Send funds
@wallet_routes.route("/wallet/send", methods=["POST"])
def send_funds():
    sender_wallet = get_or_create_wallet()
    receiver_id = (request.form.get("receiver_id") or "").strip()
    currency = (request.form.get("currency") or sender_wallet.home_currency).strip()
    amount = parse_amount(request.form.get("amount"))
    if amount is None or amount <= 0:
        flash("Invalid amount.", "danger")
        return redirect(url_for("wallet_routes.wallet_dashboard"))

    fee = parse_amount(request.form.get("agent_fee")) or Decimal(0)
    if fee < 0 or fee > amount * Decimal("0.5"):
        flash("Agent fee invalid (max 50% of amount).", "danger")
        return redirect(url_for("wallet_routes.wallet_dashboard"))
    if not receiver_id:
        flash("Receiver ID is required.", "danger")
        return redirect(url_for("wallet_routes.wallet_dashboard"))
    if fee > 0:
        log_agent_commission(sender_wallet.user_id, fee, receiver_id, "peer_transfer")

    receiver_wallet = get_or_create_receiver(receiver_id)

    # Deduct balances
    if currency == sender_wallet.home_currency:
        if sender_wallet.balance_home < (amount + fee):
            flash("Insufficient home balance.", "danger")
            return redirect(url_for("wallet_routes.wallet_dashboard"))
        sender_wallet.balance_home -= (amount + fee)
    elif currency == sender_wallet.local_currency:
        if sender_wallet.balance_local < (amount + fee):
            flash("Insufficient local balance.", "danger")
            return redirect(url_for("wallet_routes.wallet_dashboard"))
        sender_wallet.balance_local -= (amount + fee)
    else:
        flash("Unsupported currency.", "danger")
        return redirect(url_for("wallet_routes.wallet_dashboard"))

    # Conversion
    if currency == receiver_wallet.local_currency:
        converted = amount
    else:
        converted, err = sender_wallet.convert_currency(currency, receiver_wallet.local_currency, amount)
        if err:
            flash(f"Conversion failed: {err}", "danger")
            return redirect(url_for("wallet_routes.wallet_dashboard"))

    receiver_wallet.balance_local += converted

    timestamp = datetime.now(UTC).isoformat()
    sender_wallet.transactions.append({
        "type": "send",
        "to": receiver_id,
        "amount": float(amount),
        "currency": currency,
        "agent_fee": float(fee),
        "timestamp": timestamp
    })
    receiver_wallet.transactions.append({
        "type": "receive",
        "from": sender_wallet.user_id,
        "amount": float(converted),
        "currency": receiver_wallet.local_currency,
        "agent": sender_wallet.user_id if fee > 0 else None,
        "timestamp": timestamp
    })

    session["wallet"] = wallet_to_dict(sender_wallet)
    flash("Transfer sent successfully.", "success")
    return redirect(url_for("wallet_routes.wallet_dashboard"))

# Withdraw
@wallet_routes.route("/wallet/withdraw", methods=["POST"])
def withdraw_funds():
    wallet = get_or_create_wallet()
    amount = parse_amount(request.form.get("amount"))
    if amount is None or amount <= 0:
        flash("Invalid amount.", "danger")
        return redirect(url_for("wallet_routes.wallet_dashboard"))

    currency = request.form.get("currency") or wallet.local_currency
    method = request.form.get("method") or "ATM"
    agent_id = request.form.get("agent_id")
    updated_wallet, err = process_withdrawal(wallet, amount, currency, method, agent_id)
    if err:
        flash(err, "danger")
        return redirect(url_for("wallet_routes.wallet_dashboard"))

    session["wallet"] = wallet_to_dict(updated_wallet)
    flash("Withdrawal successful.", "success")
    return redirect(url_for("wallet_routes.wallet_dashboard"))
