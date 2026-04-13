"""
KYC upgrade routes for Bank of Uganda compliant tier system.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_required, current_user

from app.auth.kyc_compliance import (
    calculate_kyc_tier, get_user_limits, TIER_REQUIREMENTS,
    TIER_0_UNREGISTERED, TIER_1_BASIC, TIER_2_STANDARD,
    TIER_3_ENHANCED, TIER_4_PREMIUM, TIER_5_CORPORATE,
    can_upgrade_to_tier, get_missing_requirements
)
from app.extensions import db
from app.identity.individuals.individual_verification import IndividualVerification
from app.audit.comprehensive_audit import AuditService

kyc_bp = Blueprint('kyc', __name__, url_prefix='/kyc')

@kyc_bp.route('/upgrade')
@login_required
def upgrade():
    """Show current KYC tier and upgrade path."""
    try:
        kyc_info = calculate_kyc_tier(current_user.id)
        user_limits = get_user_limits(current_user.id)

        # Update session data for use in templates
        session['kyc_tier'] = kyc_info["tier"]
        session['kyc_tier_name'] = kyc_info["tier_name"]
        session['kyc_limits'] = user_limits
        session['kyc_missing_reqs'] = kyc_info.get("missing_requirements", [])

        # Get all tiers for display
        all_tiers = [
            (TIER_1_BASIC, TIER_REQUIREMENTS[TIER_1_BASIC]),
            (TIER_2_STANDARD, TIER_REQUIREMENTS[TIER_2_STANDARD]),
            (TIER_3_ENHANCED, TIER_REQUIREMENTS[TIER_3_ENHANCED]),
            (TIER_4_PREMIUM, TIER_REQUIREMENTS[TIER_4_PREMIUM]),
            (TIER_5_CORPORATE, TIER_REQUIREMENTS[TIER_5_CORPORATE]),
        ]

        # Check upgrade possibilities
        upgrade_options = []
        current_tier = kyc_info["tier"]

        for tier_num, tier_info in all_tiers:
            if tier_num > current_tier:
                can_upgrade, missing = can_upgrade_to_tier(current_user.id, tier_num)
                upgrade_options.append({
                    "tier": tier_num,
                    "name": tier_info["name"],
                    "description": tier_info["description"],
                    "limits": {
                        "daily": tier_info.get("daily_limit"),
                        "monthly": tier_info.get("monthly_limit"),
                        "transaction": tier_info.get("transaction_limit"),
                    },
                    "can_upgrade": can_upgrade,
                    "missing_requirements": missing,
                    "required_documents": tier_info["required_documents"],
                })

        # Check if redirected from protected route
        redirect_url = session.pop('kyc_redirect_url', None)
        required_tier = session.pop('required_tier', None)

        try:
            return render_template('kyc/upgrade.html',
                              kyc_info=kyc_info,
                              user_limits=user_limits,
                              upgrade_options=upgrade_options,
                              redirect_url=redirect_url,
                              required_tier=required_tier)
        except:
            # Fallback to simple HTML if template not found
            html = f"""
            <!DOCTYPE html>
            <html>
            <head><title>KYC Upgrade</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            </head>
            <body>
            <div class="container mt-4">
                <h1>KYC Upgrade</h1>
                <div class="card">
                    <div class="card-header">
                        Current Tier: {kyc_info['tier_name']} (Tier {kyc_info['tier']})
                    </div>
                    <div class="card-body">
                        <h5>Your Limits</h5>
                        <p><strong>Daily:</strong> UGX {user_limits.get('daily_remaining', 0)} / {user_limits.get('daily', 'Unlimited')}</p>
                        <p><strong>Monthly:</strong> UGX {user_limits.get('monthly_remaining', 0)} / {user_limits.get('monthly', 'Unlimited')}</p>
                        <p><strong>Transaction:</strong> UGX {user_limits.get('transaction', 'Unlimited')}</p>
            """
            if upgrade_options:
                html += "<h5 class='mt-4'>Available Upgrades</h5><div class='row'>"
                for option in upgrade_options:
                    html += f"""
                    <div class="col-md-4 mb-3">
                        <div class="card">
                            <div class="card-body">
                                <h6>Tier {option['tier']}: {option['name']}</h6>
                                <p>{option['description']}</p>
                                <p><small>Daily Limit: UGX {option['limits']['daily'] if option['limits']['daily'] else 'Custom'}</small></p>
                    """
                    if option['can_upgrade']:
                        html += f"""<a href="/kyc/upgrade/{option['tier']}" class="btn btn-sm btn-primary">Upgrade</a>"""
                    else:
                        html += f"""<button class="btn btn-sm btn-secondary" disabled>Requirements Missing</button>
                                <small class="text-muted d-block mt-1">
                                    Missing: {', '.join(option['missing_requirements'])}
                                </small>"""
                    html += "</div></div></div>"
                html += "</div>"

            html += """
                        <div class="mt-3">
                            <a href="/kyc/verify/national-id" class="btn btn-info">Verify National ID</a>
                            <a href="/kyc/verify/address" class="btn btn-info">Verify Address</a>
                        </div>
                    </div>
                </div>
                <div class="mt-3">
                    <a href="/kyc/limits" class="btn btn-link">View Limits</a>
                    <a href="/kyc/status" class="btn btn-link">API Status</a>
                    <a href="/" class="btn btn-link">Home</a>
                </div>
            </div>
            </body>
            </html>
            """
            return html
    except Exception as e:
        return f"Error loading KYC upgrade: {str(e)}", 500

@kyc_bp.route('/upgrade/<int:tier>', methods=['GET', 'POST'])
@login_required
def upgrade_to_tier(tier):
    """Initiate verification for specific KYC tier."""
    if tier not in [TIER_1_BASIC, TIER_2_STANDARD, TIER_3_ENHANCED, TIER_4_PREMIUM, TIER_5_CORPORATE]:
        return "Invalid KYC tier", 400

    current_tier_info = calculate_kyc_tier(current_user.id)
    current_tier = current_tier_info["tier"]

    if tier <= current_tier:
        return f"You are already at KYC tier {current_tier} or higher", 400

    # Check if user can upgrade
    can_upgrade, missing = can_upgrade_to_tier(current_user.id, tier)

    if request.method == 'POST':
        if not can_upgrade:
            return f"Cannot upgrade to tier {tier}. Missing: {', '.join(missing)}", 400

        # Create verification request
        tier_info = TIER_REQUIREMENTS[tier]

        verification = IndividualVerification(
            user_id=current_user.id,
            status="pending",
            scope=tier_info["required_scope"],
            notes=f"KYC upgrade to {tier_info['name']} tier"
        )

        db.session.add(verification)
        db.session.commit()

        # Log the upgrade request
        AuditService.security(
            event_type="kyc_upgrade_requested",
            severity="low",
            description=f"User {current_user.id} requested KYC upgrade to tier {tier} ({tier_info['name']})",
            user_id=current_user.id,
            ip_address=request.remote_addr,
            extra_data={
                "target_tier": tier,
                "tier_name": tier_info["name"],
                "verification_id": verification.id
            }
        )

        return redirect(url_for('kyc.status'))

    # GET request - show upgrade requirements
    tier_info = TIER_REQUIREMENTS[tier]

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Upgrade to Tier {tier}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body>
    <div class="container mt-4">
        <h1>Upgrade to {tier_info['name']} (Tier {tier})</h1>
        <div class="card">
            <div class="card-body">
                <p><strong>Description:</strong> {tier_info['description']}</p>
                <p><strong>Current Tier:</strong> {current_tier_info['tier_name']} (Tier {current_tier})</p>
                """
    if can_upgrade:
        html += f"""
                <p class="text-success">You can upgrade to this tier!</p>
                <form method="POST">
                    <button type="submit" class="btn btn-primary">Request Upgrade</button>
                </form>
                """
    else:
        html += f"""
                <p class="text-danger">Cannot upgrade yet. Missing requirements:</p>
                <ul>
                """
        for req in missing:
            html += f"<li>{req}</li>"
        html += """
                </ul>
                """
    html += f"""
                <div class="mt-3">
                    <a href="/kyc/upgrade" class="btn btn-link">Back to KYC Upgrade</a>
                </div>
            </div>
        </div>
    </div>
    </body>
    </html>
    """
    return html

@kyc_bp.route('/status')
@login_required
def status():
    """API endpoint returning current KYC tier and limits."""
    kyc_info = calculate_kyc_tier(current_user.id)
    user_limits = get_user_limits(current_user.id)

    return jsonify({
        "success": True,
        "user_id": current_user.id,
        "kyc_tier": kyc_info["tier"],
        "kyc_tier_name": kyc_info["tier_name"],
        "limits": user_limits,
        "missing_requirements": kyc_info.get("missing_requirements", []),
        "verification_status": kyc_info.get("verification_status"),
        "verification_id": kyc_info.get("verification_id"),
    })

@kyc_bp.route('/limits')
@login_required
def limits():
    """Show remaining limits for the day/month."""
    try:
        user_limits = get_user_limits(current_user.id)

        # Update session data
        kyc_info = calculate_kyc_tier(current_user.id)
        session['kyc_tier'] = kyc_info["tier"]
        session['kyc_tier_name'] = kyc_info["tier_name"]
        session['kyc_limits'] = user_limits
        session['kyc_missing_reqs'] = kyc_info.get("missing_requirements", [])

        try:
            return render_template('kyc/limits.html',
                              limits=user_limits,
                              user_id=current_user.id)
        except:
            # Fallback HTML
            html = f"""
            <!DOCTYPE html>
            <html>
            <head><title>KYC Limits</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            </head>
            <body>
            <div class="container mt-4">
                <h1>Your KYC Limits</h1>
                <div class="card">
                    <div class="card-header">
                        User ID: {current_user.id}
                    </div>
                    <div class="card-body">
                        <h5>Current Limits</h5>
                        <table class="table">
                            <tr>
                                <th>Limit Type</th>
                                <th>Used</th>
                                <th>Total</th>
                                <th>Remaining</th>
                            </tr>
                            <tr>
                                <td>Daily</td>
                                <td>UGX {user_limits.get('daily_used', 0)}</td>
                                <td>UGX {user_limits.get('daily', 'Unlimited')}</td>
                                <td>UGX {user_limits.get('daily_remaining', 'Unlimited')}</td>
                            </tr>
                            <tr>
                                <td>Monthly</td>
                                <td>UGX {user_limits.get('monthly_used', 0)}</td>
                                <td>UGX {user_limits.get('monthly', 'Unlimited')}</td>
                                <td>UGX {user_limits.get('monthly_remaining', 'Unlimited')}</td>
                            </tr>
                            <tr>
                                <td>Transaction</td>
                                <td>N/A</td>
                                <td>UGX {user_limits.get('transaction', 'Unlimited')}</td>
                                <td>N/A</td>
                            </tr>
                        </table>
                        <div class="mt-3">
                            <a href="/kyc/upgrade" class="btn btn-primary">Upgrade KYC</a>
                            <a href="/" class="btn btn-link">Home</a>
                        </div>
                    </div>
                </div>
            </div>
            </body>
            </html>
            """
            return html
    except Exception as e:
        return f"Error loading limits: {str(e)}", 500

@kyc_bp.route('/verify/national-id', methods=['GET', 'POST'])
@login_required
def verify_national_id():
    """National ID verification page."""
    if request.method == 'POST':
        id_number = request.form.get('id_number', '').strip()
        surname = request.form.get('surname', '').strip()
        given_names = request.form.get('given_names', '').strip()

        if not all([id_number, surname, given_names]):
            return "Please fill all required fields", 400

        # TODO: Integrate with NIRA verification
        # For now, create pending verification

        verification = IndividualVerification.query.filter_by(
            user_id=current_user.id,
            status="pending"
        ).order_by(IndividualVerification.requested_at.desc()).first()

        if not verification:
            verification = IndividualVerification(
                user_id=current_user.id,
                status="pending"
            )
            db.session.add(verification)

        # Update scope with national ID info
        current_scope = verification.scope or {}
        current_scope.update({
            "national_id": True,
            "id_number": id_number[:4] + "****",  # Partial for privacy
            "surname": surname,
            "given_names": given_names,
            "verification_method": "manual_pending"
        })
        verification.scope = current_scope
        verification.notes = "National ID verification submitted"

        db.session.commit()

        AuditService.security(
            event_type="national_id_verification_submitted",
            severity="low",
            description=f"User {current_user.id} submitted National ID for verification",
            user_id=current_user.id,
            ip_address=request.remote_addr,
            extra_data={
                "id_number_partial": id_number[:4] + "****",
                "verification_id": verification.id
            }
        )

        return redirect(url_for('kyc.upgrade'))

    # GET request - return simple form
    html = """
    <!DOCTYPE html>
    <html>
    <head><title>Verify National ID</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body>
    <div class="container mt-4">
        <h1>Verify National ID</h1>
        <div class="card">
            <div class="card-body">
                <form method="POST">
                    <div class="mb-3">
                        <label for="id_number" class="form-label">National ID Number</label>
                        <input type="text" class="form-control" id="id_number" name="id_number" required>
                    </div>
                    <div class="mb-3">
                        <label for="surname" class="form-label">Surname</label>
                        <input type="text" class="form-control" id="surname" name="surname" required>
                    </div>
                    <div class="mb-3">
                        <label for="given_names" class="form-label">Given Names</label>
                        <input type="text" class="form-control" id="given_names" name="given_names" required>
                    </div>
                    <button type="submit" class="btn btn-primary">Submit Verification</button>
                    <a href="/kyc/upgrade" class="btn btn-link">Cancel</a>
                </form>
            </div>
        </div>
    </div>
    </body>
    </html>
    """
    return html

@kyc_bp.route('/verify/address', methods=['GET', 'POST'])
@login_required
def verify_address():
    """Proof of address verification page."""
    if request.method == 'POST':
        address_proof_type = request.form.get('address_proof_type')
        file_path = request.form.get('file_path')  # In production, handle file upload

        if not address_proof_type:
            return "Please select proof type", 400

        # Create or update verification
        verification = IndividualVerification.query.filter_by(
            user_id=current_user.id,
            status="pending"
        ).order_by(IndividualVerification.requested_at.desc()).first()

        if not verification:
            verification = IndividualVerification(
                user_id=current_user.id,
                status="pending"
            )
            db.session.add(verification)

        current_scope = verification.scope or {}
        current_scope.update({
            "address": True,
            "address_proof_type": address_proof_type,
            "address_verification_method": "manual_pending"
        })
        verification.scope = current_scope
        verification.notes = "Address verification submitted"

        db.session.commit()

        return redirect(url_for('kyc.upgrade'))

    # GET request - return simple form
    html = """
    <!DOCTYPE html>
    <html>
    <head><title>Verify Address</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body>
    <div class="container mt-4">
        <h1>Verify Address</h1>
        <div class="card">
            <div class="card-body">
                <form method="POST">
                    <div class="mb-3">
                        <label for="address_proof_type" class="form-label">Proof Type</label>
                        <select class="form-select" id="address_proof_type" name="address_proof_type" required>
                            <option value="">Select proof type</option>
                            <option value="utility_bill">Utility Bill</option>
                            <option value="bank_statement">Bank Statement</option>
                            <option value="rental_agreement">Rental Agreement</option>
                            <option value="government_letter">Government Letter</option>
                        </select>
                    </div>
                    <div class="mb-3">
                        <label for="file_path" class="form-label">File Path (for demo only)</label>
                        <input type="text" class="form-control" id="file_path" name="file_path" placeholder="/path/to/document.pdf">
                        <small class="text-muted">In production, this would be a file upload field</small>
                    </div>
                    <button type="submit" class="btn btn-primary">Submit Verification</button>
                    <a href="/kyc/upgrade" class="btn btn-link">Cancel</a>
                </form>
            </div>
        </div>
    </div>
    </body>
    </html>
    """
    return html
