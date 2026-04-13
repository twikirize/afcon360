# app/kyc/routes.py
"""
KYC blueprint — Bank of Uganda compliance routes.

Endpoints:
  GET  /kyc/upgrade              — show available tier upgrades
  GET  /kyc/limits               — show per-tier transaction limits
  GET  /kyc/verify/national-id   — National ID (NIRA) verification form
  POST /kyc/verify/national-id   — submit National ID verification
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime

from app.extensions import db
from app.kyc.nira_verification import verify_national_id, check_id_against_watchlist, generate_nira_report
from app.kyc.models import KycRecord
from app.kyc.services import KycService
from app.auth.kyc_compliance import (
    TIER_0_UNREGISTERED, TIER_1_BASIC, TIER_2_STANDARD,
    calculate_kyc_tier
)

kyc_bp = Blueprint("kyc", __name__, url_prefix="/kyc")


# ── Tier metadata (used by upgrade + limits pages) ────────────────────────────
TIER_INFO = {
    TIER_0_UNREGISTERED: {
        "name": "Tier 0 — Unregistered",
        "daily_limit":    0,
        "monthly_limit":  0,
        "description":    "No transactions permitted. Complete identity verification to proceed.",
        "requirements":   [],
    },
    TIER_1_BASIC: {
        "name": "Tier 1 — Basic",
        "daily_limit":    1_000_000,   # UGX
        "monthly_limit":  5_000_000,
        "description":    "Phone-verified account. Limited transactions permitted.",
        "requirements":   ["Phone number verified"],
    },
    TIER_2_STANDARD: {
        "name": "Tier 2 — Standard",
        "daily_limit":    10_000_000,
        "monthly_limit":  50_000_000,
        "description":    "National ID verified. Standard transaction limits apply.",
        "requirements":   ["Phone number verified", "National ID (NIRA) verified"],
    },
}


# ── /kyc/ ───────────────────────────────────────────────────────────────────
@kyc_bp.route("/", methods=["GET"])
@login_required
def index():
    """Main KYC dashboard."""
    user_id = current_user.id
    kyc_info = calculate_kyc_tier(user_id)
    records = KycService.get_user_kyc(user_id)

    return render_template('kyc/index.html',
                           kyc_info=kyc_info,
                           records=records,
                           tier_requirements=TIER_INFO)

# ── /kyc/upgrade ─────────────────────────────────────────────────────────────
@kyc_bp.route("/upgrade", methods=["GET"])
@login_required
def upgrade():
    current_tier = getattr(current_user, "kyc_level", TIER_0_UNREGISTERED)
    available_upgrades = {
        k: v for k, v in TIER_INFO.items() if k > current_tier
    }
    return render_template(
        "kyc/upgrade.html",
        current_tier=current_tier,
        current_tier_info=TIER_INFO.get(current_tier, {}),
        available_upgrades=available_upgrades,
        TIER_INFO=TIER_INFO,
    )


# ── /kyc/limits ──────────────────────────────────────────────────────────────
@kyc_bp.route("/limits", methods=["GET"])
@login_required
def limits():
    current_tier = getattr(current_user, "kyc_level", TIER_0_UNREGISTERED)
    return render_template(
        "kyc/limits.html",
        current_tier=current_tier,
        tier_info=TIER_INFO,
    )

# ── /kyc/verify/address ──────────────────────────────────────────────────────
@kyc_bp.route("/verify/address", methods=["GET", "POST"])
@login_required
def verify_address():
    """Address verification page."""
    if request.method == 'POST':
        document_url = request.form.get('document_url')
        address_line1 = request.form.get('address_line1')
        address_line2 = request.form.get('address_line2')
        city = request.form.get('city')
        state = request.form.get('state')
        postal_code = request.form.get('postal_code')
        country = request.form.get('country')

        if not all([document_url, address_line1, city, country]):
            flash('Document URL and address details are required', 'error')
            return redirect(url_for('kyc.verify_address'))

        try:
            record = KycService.submit_kyc(
                user_id=current_user.id,
                id_type='address_proof',
                id_number=f'ADDR_{current_user.id}_{datetime.utcnow().timestamp()}',
                document_url=document_url,
                address_line1=address_line1,
                address_line2=address_line2,
                city=city,
                state=state,
                postal_code=postal_code,
                country=country,
                record_type='address_verification'
            )
            flash('Address verification submitted successfully!', 'success')
            return redirect(url_for('kyc.index'))
        except Exception as e:
            flash(f'Error submitting address verification: {str(e)}', 'error')
            return redirect(url_for('kyc.verify_address'))

    return render_template('kyc/verify_address.html')


# ── /kyc/verify/national-id ──────────────────────────────────────────────────
@kyc_bp.route("/verify/national-id", methods=["GET"])
@login_required
def verify_national_id_page():
    """Render the NIRA National ID verification form."""
    # Check if user already has a pending or approved verification
    existing = KycRecord.query.filter_by(
        user_id=current_user.id,
        record_type="nira_national_id"
    ).order_by(KycRecord.created_at.desc()).first()

    already_verified  = existing and existing.status == "verified"
    pending_review    = existing and existing.status in ("pending", "manual_review")

    return render_template(
        "kyc/verify_national_id.html",
        already_verified=already_verified,
        pending_review=pending_review,
        existing=existing,
    )


@kyc_bp.route("/verify/national-id", methods=["POST"])
@login_required
def submit_national_id():
    """
    Process NIRA National ID verification submission.

    Flow:
      1. Validate NIN format
      2. Check watchlist
      3. Submit to NIRA (currently: manual review queue)
      4. Create KycRecord
      5. Generate compliance report
    """
    id_number   = request.form.get("id_number",   "").strip().upper()
    surname     = request.form.get("surname",     "").strip()
    given_names = request.form.get("given_names", "").strip()
    date_of_birth = request.form.get("date_of_birth", None)

    # Basic presence check
    if not id_number or not surname or not given_names:
        flash("All fields are required.", "error")
        return redirect(url_for("kyc.verify_national_id_page"))

    # ── 1. Run NIRA verification (format + manual review queue) ──────────────
    result = verify_national_id(
        id_number=id_number,
        surname=surname,
        given_names=given_names,
        date_of_birth=date_of_birth,
    )

    if not result.get("is_valid_format"):
        flash(f"Invalid National ID format: {result.get('format_error', 'Unknown error')}", "error")
        return redirect(url_for("kyc.verify_national_id_page"))

    # ── 2. Watchlist check ────────────────────────────────────────────────────
    watchlist = check_id_against_watchlist(id_number)
    if watchlist.get("recommended_action") == "block_and_investigate":
        flash("Your ID could not be processed at this time. Please contact support.", "error")
        return redirect(url_for("kyc.verify_national_id_page"))

    # ── 3. Persist KycRecord ─────────────────────────────────────────────────
    try:
        record = KycRecord(
            user_id=current_user.id,           # BIGINT FK — internal id
            record_type="nira_national_id",    # Business Process ID
            id_type="national_id",             # Required field
            document_type="national_id",       # Required field
            id_number=id_number,               # Actual ID (unmasked for DB)
            status="manual_review" if result.get("manual_review_required") else "pending",
            id_number_masked=result.get("id_number"), # Masked version from result
            # verification_id is a BIGINT foreign key, not a string
            # Store the NIRA reference in reference_code field
            verification_id=None,
            reference_code=result.get("verification_id"),  # Store NIRA string here
            risk_score=watchlist.get("risk_score", 0),
            raw_response=result,
        )
        db.session.add(record)
        db.session.flush()  # get record.id before commit

        # ── 4. Generate compliance report ─────────────────────────────────────
        generate_nira_report(
            user_id=current_user.id,
            verification_data={**result, "watchlist": watchlist},
        )

        db.session.commit()

        flash(
            "Your National ID has been submitted for verification. "
            "A compliance officer will review it shortly.",
            "success",
        )
        return redirect(url_for("kyc.upgrade"))

    except Exception as exc:
        db.session.rollback()
        current_app.logger.error(f"KYC record creation failed for user {current_user.id}: {exc}")
        flash("An error occurred while saving your verification. Please try again.", "error")
        return redirect(url_for("kyc.verify_national_id_page"))

# ── Additional KYC Routes ──────────────────────────────────────────────────

@kyc_bp.route('/pending', methods=['GET'])
@login_required
def pending_review():
    """Admin view of pending KYC records (requires admin privileges)."""
    # Check if user has admin or owner role
    if not (current_user.has_global_role('admin') or current_user.has_global_role('owner')):
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('kyc.index'))

    pending_records = KycService.get_pending_kyc(limit=100)
    stats = KycService.get_kyc_stats()

    return render_template('kyc/pending_review.html',
                           records=pending_records,
                           stats=stats)

@kyc_bp.route('/admin/dashboard')
@login_required
def admin_dashboard():
    """Admin KYC dashboard with statistics and management tools."""
    if not (current_user.has_global_role('admin') or current_user.has_global_role('owner')):
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('kyc.index'))

    stats = KycService.get_kyc_stats()
    recent_pending = KycService.get_pending_kyc(limit=10)
    recent_approved = KycService.get_approved_kyc(limit=10)

    return render_template('kyc/admin_dashboard.html',
                           stats=stats,
                           recent_pending=recent_pending,
                           recent_approved=recent_approved)

@kyc_bp.route('/admin/search', methods=['GET', 'POST'])
@login_required
def admin_search():
    """Admin search interface for KYC records."""
    if not (current_user.has_global_role('admin') or current_user.has_global_role('owner')):
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('kyc.index'))

    records = []
    search_params = {}

    if request.method == 'POST':
        search_term = request.form.get('search_term', '').strip()
        status = request.form.get('status', '').strip()
        id_type = request.form.get('id_type', '').strip()
        start_date_str = request.form.get('start_date', '').strip()
        end_date_str = request.form.get('end_date', '').strip()

        # Parse dates
        start_date = None
        end_date = None
        try:
            if start_date_str:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            if end_date_str:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format. Use YYYY-MM-DD.', 'error')

        records = KycService.search_kyc_records(
            search_term=search_term if search_term else None,
            status=status if status else None,
            id_type=id_type if id_type else None,
            start_date=start_date,
            end_date=end_date,
            limit=200
        )

        search_params = {
            'search_term': search_term,
            'status': status,
            'id_type': id_type,
            'start_date': start_date_str,
            'end_date': end_date_str
        }

    return render_template('kyc/admin_search.html',
                           records=records,
                           search_params=search_params)

@kyc_bp.route('/admin/bulk-action', methods=['POST'])
@login_required
def admin_bulk_action():
    """Handle bulk actions on KYC records."""
    if not (current_user.has_global_role('admin') or current_user.has_global_role('owner')):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    data = request.get_json()
    record_ids = data.get('record_ids', [])
    action = data.get('action', '')
    rejection_reason = data.get('rejection_reason', '')

    if not record_ids:
        return jsonify({'success': False, 'error': 'No records selected'}), 400

    if action not in ['approve', 'reject']:
        return jsonify({'success': False, 'error': 'Invalid action'}), 400

    status = 'approved' if action == 'approve' else 'rejected'
    updated_count, errors = KycService.bulk_update_status(
        record_ids, status, current_user.id, rejection_reason
    )

    if errors:
        return jsonify({
            'success': True,
            'updated': updated_count,
            'errors': errors,
            'message': f'Updated {updated_count} records with some errors'
        }), 207

    return jsonify({
        'success': True,
        'updated': updated_count,
        'message': f'Successfully updated {updated_count} records'
    })

@kyc_bp.route('/provider/dashboard')
@login_required
def provider_dashboard():
    """KYC provider dashboard (for hotels, drivers, etc.)."""
    # Check if user has provider role or is a hotel/driver
    # For now, allow any authenticated user to see their verification status
    user_id = current_user.id
    verification_status = KycService.get_user_verification_status(user_id)
    kyc_info = calculate_kyc_tier(user_id)

    # Get user's role to determine what to show
    is_hotel = current_user.has_global_role('hotel_owner') or current_user.has_global_role('hotel_manager')
    is_driver = current_user.has_global_role('driver') or current_user.has_global_role('transport_operator')
    is_tour_operator = current_user.has_global_role('tour_operator')

    return render_template('kyc/provider_dashboard.html',
                           verification_status=verification_status,
                           kyc_info=kyc_info,
                           is_hotel=is_hotel,
                           is_driver=is_driver,
                           is_tour_operator=is_tour_operator)

@kyc_bp.route('/hotel/guest-kyc')
@login_required
def hotel_guest_kyc():
    """Hotel view to check guest KYC status."""
    if not (current_user.has_global_role('hotel_owner') or
            current_user.has_global_role('hotel_manager') or
            current_user.has_global_role('admin')):
        flash('Access denied. Hotel privileges required.', 'error')
        return redirect(url_for('kyc.index'))

    # In a real implementation, this would fetch guests from hotel bookings
    # For now, show a search interface
    return render_template('kyc/hotel_guest_kyc.html')

@kyc_bp.route('/driver/kyc-status')
@login_required
def driver_kyc_status():
    """Driver's own KYC status page."""
    if not (current_user.has_global_role('driver') or
            current_user.has_global_role('transport_operator')):
        flash('Access denied. Driver privileges required.', 'error')
        return redirect(url_for('kyc.index'))

    user_id = current_user.id
    verification_status = KycService.get_user_verification_status(user_id)
    kyc_info = calculate_kyc_tier(user_id)
    records = KycService.get_user_kyc(user_id)

    return render_template('kyc/driver_kyc_status.html',
                           verification_status=verification_status,
                           kyc_info=kyc_info,
                           records=records)

@kyc_bp.route('/status', methods=['GET'])
@login_required
def status():
    """Check KYC verification status."""
    user_id = current_user.id
    records = KycRecord.query.filter_by(user_id=user_id).order_by(KycRecord.id.desc()).all()
    kyc_info = calculate_kyc_tier(user_id)

    return render_template('kyc/status.html',
                           records=records,
                           kyc_info=kyc_info)

@kyc_bp.route('/verify/upload', methods=['GET', 'POST'])
@login_required
def verify_upload():
    """Upload KYC documents with multiple file support."""
    if request.method == 'POST':
        # Handle file uploads
        # This is a simplified version - in production, use proper file handling
        id_type = request.form.get('id_type')
        id_number = request.form.get('id_number')

        # Get file URLs (in production, these would be uploaded to cloud storage)
        document_url = request.form.get('document_url')
        selfie_url = request.form.get('selfie_url')

        if not all([id_type, id_number, document_url]):
            flash('ID type, ID number, and document are required', 'error')
            return redirect(url_for('kyc.verify_upload'))

        try:
            record = KycService.submit_kyc(
                user_id=current_user.id,
                id_type=id_type,
                id_number=id_number,
                document_url=document_url,
                selfie_url=selfie_url,
                record_type=f"{id_type}_verification"
            )
            flash('Documents uploaded successfully! They will be reviewed shortly.', 'success')
            return redirect(url_for('kyc.status'))
        except Exception as e:
            flash(f'Error uploading documents: {str(e)}', 'error')
            return redirect(url_for('kyc.verify_upload'))

    return render_template('kyc/verify_upload.html')
