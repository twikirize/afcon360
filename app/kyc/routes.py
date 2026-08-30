# app/kyc/routes.py
"""
KYC blueprint - Bank of Uganda compliance routes.

Endpoints:
  GET  /kyc/upgrade              - show available tier upgrades
  GET  /kyc/limits               - show per-tier transaction limits
  GET  /kyc/verify/national-id   - National ID (NIRA) verification form
  POST /kyc/verify/national-id   - submit National ID verification
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from app.core.context import RequestContext
from datetime import datetime, timezone

from app.extensions import db
from app.kyc.nira_verification import verify_national_id, check_id_against_watchlist, generate_nira_report
from app.kyc.models import KycRecord
from app.kyc.services import KycService
from app.media.service import MediaService
from app.identity.models.kyb import OrganisationKYBDocument
import hashlib
from app.auth.kyc_compliance import (
    TIER_0_UNREGISTERED, TIER_1_BASIC, TIER_2_STANDARD,
    calculate_kyc_tier
)
from app.auth.decorators import require_moderator, require_fresh_user
from app.auth.helpers import is_acting_as_organization, get_current_org_id
from app.kyc.reupload import (
    clear_individual_reupload_request,
    clear_organisation_reupload_request,
    get_individual_reupload_request,
    get_organisation_reupload_requests,
    load_reupload_token,
    make_reupload_token,
)


def flash_form_error(message):
    """Flash an error message (normalized category) for form submissions."""
    flash(message, 'error')
from app.utils.flash_helpers import flash_form_error, flash_notice

kyc_bp = Blueprint("kyc", __name__, url_prefix="/kyc")


# ── Tier metadata (used by upgrade + limits pages) ────────────────────────────
TIER_INFO = {
    TIER_0_UNREGISTERED: {
        "name": "Tier 0 - Unregistered",
        "daily_limit":    0,
        "monthly_limit":  0,
        "description":    "No transactions permitted. Complete identity verification to proceed.",
        "requirements":   [],
    },
    TIER_1_BASIC: {
        "name": "Tier 1 - Basic",
        "daily_limit":    1_000_000,   # UGX
        "monthly_limit":  5_000_000,
        "description":    "Phone-verified account. Limited transactions permitted.",
        "requirements":   ["Phone number verified"],
    },
    TIER_2_STANDARD: {
        "name": "Tier 2 - Standard",
        "daily_limit":    10_000_000,
        "monthly_limit":  50_000_000,
        "description":    "National ID verified. Standard transaction limits apply.",
        "requirements":   ["Phone number verified", "National ID (NIRA) verified"],
    },
}


# ── Shared verification-state helper ───────────────────────────────────────
def _compute_verification_state(user_id):
    """
    Derive the current KYC verification stage for a user.

    Returns a dict the progress tracker UI can consume directly:
      stage          : 1 = Submitted, 2 = Processing, 3 = Verified
      status         : not_started | processing | verified | rejected
      progress       : 33 | 66 | 100  (fill % for the CSS connector line)
      steps          : ordered list of step descriptors for the UI
      message        : human-readable caption

    Stage mapping:
      1 = Submitted (pending)
      2 = Processing (under review / manual_review)
      3 = Verified (approved / verified)
    Rejections hold at stage 2 and are flagged via status='rejected'.
    """
    records = KycService.get_user_kyc(user_id) if user_id else []
    statuses = [r.status for r in records]

    stage = 1
    status = "not_started"
    if "approved" in statuses or "verified" in statuses:
        stage, status = 3, "verified"
    elif "manual_review" in statuses or "pending" in statuses:
        stage, status = 2, "processing"
    elif "rejected" in statuses:
        stage, status = 2, "rejected"
    elif statuses:
        stage, status = 2, "processing"

    progress = {1: 33, 2: 66, 3: 100}.get(stage, 33)

    # Step descriptors the UI maps onto the CSS tracker.
    step_states = {
        1: "completed" if status != "not_started" else "active",
        2: ("rejected" if status == "rejected"
            else ("active" if stage >= 2 else "upcoming")),
        3: "completed" if stage >= 3 else "upcoming",
    }
    steps = [
        {"key": "submitted", "label": "Submitted",
         "state": step_states[1],
         "sub": "Start" if status == "not_started" else "Pending"},
        {"key": "processing", "label": "Processing",
         "state": step_states[2],
         "sub": ("Rejected" if status == "rejected"
                 else ("In Review" if stage >= 2 else "Awaiting"))},
        {"key": "verified", "label": "Verified",
         "state": step_states[3],
         "sub": "Approved" if stage >= 3 else "Pending"},
    ]

    messages = {
        "not_started": "You have not submitted any verification documents yet.",
        "verified": "Your identity has been successfully verified.",
        "rejected": "Your submission was rejected. Please review the feedback and resubmit.",
        "processing": "Your documents are being reviewed by our compliance team.",
    }

    return {
        "stage": stage,
        "status": status,
        "progress": progress,
        "steps": steps,
        "message": messages.get(status, ""),
        "record_count": len(records),
    }


# ── Requirement display metadata (static lookup maps) ──────────────────
REQUIREMENT_ICONS = {
    'income_source': 'bi-cash-stack',
    'bank_reference': 'bi-bank',
    'proof_of_address': 'bi-house',
    'tin': 'bi-hash',
    'national_id': 'bi-card-text',
    'passport': 'bi-passport',
    'driver_license': 'bi-license',
    'selfie': 'bi-camera',
}
REQUIREMENT_HELPS = {
    'income_source': 'Upload proof of income source',
    'bank_reference': 'Provide a bank reference letter',
    'proof_of_address': 'Upload proof of address',
    'tin': 'Submit Tax Identification Number',
    'national_id': 'Upload your national ID',
    'passport': 'Upload your passport',
    'driver_license': 'Upload your driver license',
    'selfie': 'Submit a selfie verification',
}

# ── /kyc/ ───────────────────────────────────────────────────────────────────
@kyc_bp.route("/", methods=["GET"])
@login_required
def index():
    """Main KYC dashboard."""
    effective = RequestContext.get_effective_user()
    user_id = effective.id if effective else None
    kyc_info = calculate_kyc_tier(user_id)
    records = KycService.get_user_kyc(user_id)

    state = _compute_verification_state(user_id)

    in_org_context = is_acting_as_organization()
    show_individual = not in_org_context
    show_organization = in_org_context

    return render_template('kyc/index.html',
                           kyc_info=kyc_info,
                           records=records,
                           tier_requirements=TIER_INFO,
                           next_tier_requirements=kyc_info.get("next_tier_requirements_labels", []),
                           next_tier_name=kyc_info.get("next_tier_name"),
                           missing_requirements=kyc_info.get("missing_requirements_labels", []),
                           fulfillment_percentage=kyc_info.get("fulfillment_percentage", 0),
                           kyc_stage=state["stage"],
                           overall_status=state["status"],
                           verification_message=state["message"],
                           in_org_context=in_org_context,
                           show_individual=show_individual,
                           show_organization=show_organization,
                           requirement_icons=REQUIREMENT_ICONS,
                           requirement_helps=REQUIREMENT_HELPS)


# ── /kyc/api/state ──────────────────────────────────────────────────────────
@kyc_bp.route("/api/state", methods=["GET"])
@login_required
def api_verification_state():
    """
    JSON endpoint the progress tracker UI polls to stay in sync with the
    user's current verification state.
    """
    effective = RequestContext.get_effective_user()
    user_id = effective.id if effective else None
    state = _compute_verification_state(user_id)
    return jsonify({
        "user_id": current_user.public_id,   # External UUID only, never internal id
        "verification": state,
    })

# ── /kyc/upgrade ─────────────────────────────────────────────────────────────
@kyc_bp.route("/upgrade", methods=["GET"])
@login_required
def upgrade():
    effective = RequestContext.get_effective_user()
    from app.auth.kyc_compliance import calculate_kyc_tier
    current_tier = calculate_kyc_tier(effective.id)["tier"] if effective else TIER_0_UNREGISTERED
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
    from app.auth.kyc_compliance import calculate_kyc_tier
    current_tier = calculate_kyc_tier(current_user.id)["tier"]
    return render_template(
        "kyc/limits.html",
        current_tier=current_tier,
        tier_info=TIER_INFO,
    )

# ── /kyc/verify/address ──────────────────────────────────────────────────────
@kyc_bp.route("/verify/address", methods=["GET", "POST"])
@login_required
@require_fresh_user
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
            flash_form_error('Document URL and address details are required')
            return redirect(url_for('kyc.verify_address'))

        try:
            record = KycService.submit_kyc(
                user_id=current_user.id,
                id_type='address_proof',
                id_number=f'ADDR_{current_user.id}_{datetime.now(timezone.utc).timestamp()}',
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
            flash_form_error(f'Error submitting address verification: {str(e)}')
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
@require_fresh_user
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
        flash_form_error("All fields are required.")
        return redirect(url_for("kyc.verify_national_id_page"))

    # ── 1. Run NIRA verification (format + manual review queue) ──────────────
    result = verify_national_id(
        id_number=id_number,
        surname=surname,
        given_names=given_names,
        date_of_birth=date_of_birth,
    )

    if not result.get("is_valid_format"):
        flash_form_error(f"Invalid National ID format: {result.get('format_error', 'Unknown error')}")
        return redirect(url_for("kyc.verify_national_id_page"))

    # ── 2. Watchlist check ────────────────────────────────────────────────────
    watchlist = check_id_against_watchlist(id_number)
    if watchlist.get("recommended_action") == "block_and_investigate":
        flash_form_error("Your ID could not be processed at this time. Please contact support.")
        return redirect(url_for("kyc.verify_national_id_page"))

    # ── 3. Persist KycRecord ─────────────────────────────────────────────────
    try:
        record = KycRecord(
            user_id=current_user.id,           # BIGINT FK - internal id
            record_type="nira_national_id",    # Business Process ID
            id_type="national_id",             # Required field
            document_type="national_id",       # Required field
            id_number=id_number,               # Actual ID (unmasked for DB)
            status=(
                "verified" if result.get("auto_verified")
                else "manual_review" if result.get("manual_review_required")
                else "pending"
            ),
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

        if result.get("auto_verified"):
            flash("Your National ID has been verified successfully.", "success")
        else:
            flash(
                "Your National ID has been submitted for verification. "
                "A compliance officer will review it shortly.",
                "success",
            )
        return redirect(url_for("kyc.upgrade"))

    except Exception as exc:
        db.session.rollback()
        current_app.logger.error(f"KYC record creation failed for user {current_user.id}: {exc}")
        flash_form_error("An error occurred while saving your verification. Please try again.")
        return redirect(url_for("kyc.verify_national_id_page"))

# ── Additional KYC Routes ──────────────────────────────────────────────────

@kyc_bp.route('/pending', methods=['GET'])
@login_required
def pending_review():
    """Admin view of pending KYC records (requires admin privileges)."""
    # Check if user has admin or owner role
    if not (current_user.has_global_role('admin') or current_user.has_global_role('owner')):
        flash_form_error('Access denied. Admin privileges required.')
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
        flash_form_error('Access denied. Admin privileges required.')
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
        flash_form_error('Access denied. Admin privileges required.')
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
            flash_form_error('Invalid date format. Use YYYY-MM-DD.')

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
        flash_form_error('Access denied. Hotel privileges required.')
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
        flash_form_error('Access denied. Driver privileges required.')
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
    verification_status = KycService.get_user_verification_status(user_id)
    user_orgs = _get_user_organisations()

    return render_template('kyc/status.html',
                           records=records,
                           kyc_info=kyc_info,
                           verification_status=verification_status,
                           reupload_requests=_get_individual_reupload_requests(records),
                           organisation_reupload_requests=(
                               _get_organisation_reupload_requests(user_orgs)
                           ))


def _get_verified_id_types(user_id):
    """
    Return the set of ``id_type`` values the user has already verified.

    Used to gate the individual upload form so a document type that compliance
    has already approved is not re-prompted / re-submitted. Compliance-requested
    replacements bypass this gate via the dedicated reupload token flow.
    """
    from app.kyc.models import KycRecord

    VERIFIED = {"verified", "approved"}
    verified = set()
    for record in KycRecord.query.filter_by(user_id=user_id).all():
        if (record.status or "pending").lower() in VERIFIED and record.id_type:
            verified.add(record.id_type.lower())
    return verified


def _get_user_organisations():
    """Return active organisations for the current user without detached objects."""
    from app.identity.models.organisation_member import OrganisationMember

    return [
        membership.organisation
        for membership in OrganisationMember.query.filter_by(
            user_id=current_user.id, is_active=True
        ).options(
            db.joinedload(OrganisationMember.organisation)
        ).all()
        if membership.organisation and membership.organisation.is_active
    ]


def _request_label(document_key):
    return {
        'document': 'Primary identity document',
        'selfie': 'Verification selfie',
    }.get(document_key, document_key.replace('_', ' ').title())


def _get_individual_reupload_requests(records):
    """Build user-facing replacement links without exposing KYC record IDs."""
    requests = []
    for record in records:
        request_data = get_individual_reupload_request(record.compliance_notes)
        if not request_data:
            continue
        document_key = request_data.get('document_key')
        try:
            token = make_reupload_token(
                kind='individual',
                entity_id=record.id,
                owner_public_id=current_user.public_id,
                document_key=document_key,
            )
        except (TypeError, ValueError):
            continue
        requests.append({
            'token': token,
            'document_key': document_key,
            'label': _request_label(document_key),
            'reason': request_data.get('reason', ''),
            'record_type': record.record_type or record.id_type or 'Identity verification',
        })
    return requests


def _get_organisation_reupload_requests(user_orgs):
    """Build replacement links for every requested KYB document the user can access."""
    requests = []
    for org in user_orgs:
        if not org:
            continue
        documents = OrganisationKYBDocument.query.filter_by(
            organisation_id=org.id,
            is_deleted=False,
        ).all()
        by_document_id = get_organisation_reupload_requests(org.compliance_notes)
        for document in documents:
            request_data = by_document_id.get(str(document.id))
            if not request_data:
                continue
            try:
                token = make_reupload_token(
                    kind='organisation',
                    entity_id=document.id,
                    owner_public_id=current_user.public_id,
                    document_key='document',
                    organisation_id=org.id,
                )
            except (TypeError, ValueError):
                continue
            requests.append({
                'token': token,
                'document_key': 'document',
                'label': request_data.get('document_type') or document.document_type,
                'reason': request_data.get('reason', ''),
                'organisation_name': getattr(org, 'legal_name', None) or getattr(org, 'name', 'Organisation'),
            })
    return requests


def _load_reupload_target(token):
    """Resolve and authorise a replacement token against live database state."""
    payload = load_reupload_token(token, current_user.public_id)
    if payload['kind'] == 'individual':
        record = db.session.get(KycRecord, payload['entity_id'])
        if not record or record.user_id != current_user.id:
            raise ValueError('The requested KYC record is not available')
        request_data = get_individual_reupload_request(record.compliance_notes)
        if not request_data or request_data.get('document_key') != payload.get('document_key'):
            raise ValueError('This KYC replacement request is no longer active')
        return payload, record, None, request_data

    organisation_id = payload.get('organisation_id')
    user_orgs = _get_user_organisations()
    if not any(org.id == organisation_id for org in user_orgs):
        raise ValueError('You are not authorised to replace this organisation document')
    document = db.session.get(OrganisationKYBDocument, payload['entity_id'])
    if not document or document.organisation_id != organisation_id:
        raise ValueError('The requested organisation document is not available')
    org = next(org for org in user_orgs if org.id == organisation_id)
    request_data = get_organisation_reupload_requests(org.compliance_notes).get(
        str(document.id)
    )
    if not request_data:
        raise ValueError('This organisation replacement request is no longer active')
    return payload, document, org, request_data


def _save_uploaded_file(file_storage, doc_key):
    """
    Save an uploaded FileStorage (device photo/PDF) via the media service and
    return a stable reference string for the KYC record.

    The raw file is persisted synchronously by MediaService.upload_photo, so the
    returned media_id is usable immediately — no client-side polling required.
    Falls back to the original filename in the rare case the service is unavailable.
    """
    if not file_storage:
        return None
    filename = getattr(file_storage, 'filename', '') or ''
    if not filename:
        return None
    try:
        result = MediaService.upload_photo(
            file=file_storage,
            module='kyc',
            entity_id=current_user.public_id,
            uploader_user_id=current_user.id,
        )
        # Prefer a ready URL (async processing may not have finished yet, so
        # fall back to resolving a servable URL from the Media record so the
        # stored document_url is always viewable in the compliance review UI).
        urls = result.get('urls') or {}
        url = urls.get('original') or (list(urls.values())[0] if urls else None)
        if url:
            return url
        media_id = result.get('media_id')
        if media_id:
            from app.media.models import Media
            from app.media.storage import get_storage_backend
            media = db.session.query(Media).filter(
                Media.public_id == media_id, Media.is_deleted == False
            ).first()
            if media and media.storage_key:
                try:
                    return get_storage_backend().get_url(media.storage_key)
                except Exception:
                    pass
        return filename
    except ValueError as e:
        # Validation / scan failure — surface to caller via exception.
        raise
    except Exception as e:
        current_app.logger.warning(f"KYC file upload failed for {doc_key}: {e}")
        return filename


@kyc_bp.route('/verify/upload', methods=['GET', 'POST'], endpoint='upload')
@login_required
@require_fresh_user
def verify_upload():
    """Upload KYC documents for individuals or organization KYB."""
    user_orgs = _get_user_organisations()
    records = KycRecord.query.filter_by(user_id=current_user.id).order_by(
        KycRecord.id.desc()
    ).all()
    individual_reupload_requests = _get_individual_reupload_requests(records)
    organisation_reupload_requests = _get_organisation_reupload_requests(user_orgs)

    preselect_id_type = request.args.get('preselect', '').strip().lower() if request.method == 'GET' else ''

    if request.method == 'POST':
        replacement_token = request.form.get('reupload_token', '').strip()
        if replacement_token:
            try:
                payload, target, organisation, request_data = _load_reupload_target(
                    replacement_token
                )
                replacement_file = request.files.get('replacement_file')
                replacement_ref = None
                if replacement_file and replacement_file.filename:
                    replacement_ref = _save_uploaded_file(
                        replacement_file, payload.get('document_key', 'document')
                    )
                if not replacement_ref:
                    replacement_ref = request.form.get('replacement_url', '').strip() or None
                if not replacement_ref:
                    raise ValueError('Please upload the requested replacement document.')

                if payload['kind'] == 'individual':
                    document_key = payload['document_key']
                    if document_key == 'document':
                        target.document_url = replacement_ref
                    else:
                        target.selfie_url = replacement_ref
                    target.status = 'pending'
                    target.compliance_status = 'pending'
                    target.compliance_notes = clear_individual_reupload_request(
                        target.compliance_notes
                    )
                    target.checked_by = None
                    target.compliance_reviewed_at = None
                    target.compliance_reviewed_by = None
                    target.rejection_reason = None
                else:
                    target.storage_key = replacement_ref
                    target.checksum = hashlib.md5(replacement_ref.encode()).hexdigest()
                    target.verification_status = 'pending'
                    organisation.compliance_notes = clear_organisation_reupload_request(
                        organisation.compliance_notes,
                        document_id=target.id,
                    )
                    organisation.compliance_status = 'pending'
                    organisation.compliance_reviewed_at = None
                    organisation.compliance_reviewed_by = None

                db.session.commit()
                flash(
                    'The requested replacement was submitted and is back in compliance review.',
                    'success',
                )
                return redirect(url_for('kyc.status'))
            except ValueError as exc:
                db.session.rollback()
                flash_form_error(str(exc))
                return redirect(url_for('kyc.upload', reupload=replacement_token))
            except Exception as exc:
                db.session.rollback()
                current_app.logger.exception('KYC replacement submission failed')
                flash_form_error(f'Could not submit the replacement document: {exc}')
                return redirect(url_for('kyc.upload', reupload=replacement_token))

        kyc_type = request.form.get('kyc_type', 'individual')
        pending_requests = (
            individual_reupload_requests
            if kyc_type == 'individual'
            else organisation_reupload_requests
        )
        if pending_requests:
            flash_form_error(
                'A compliance reviewer requested a specific replacement. '
                'Please use the replacement link shown below instead of starting a new submission.'
            )
            return redirect(url_for('kyc.upload', reupload=pending_requests[0]['token']))

        if kyc_type == 'organization':
            # ── Organization KYB ────────────────────────────────────────────
            org_id = request.form.get('org_id')
            org_doc_type = request.form.get('org_doc_type')
            org_doc_number = request.form.get('org_doc_number', '')

            # Prefer an uploaded file; fall back to a pasted URL.
            org_document_ref = None
            org_doc_file = request.files.get('org_doc_file')
            if org_doc_file and org_doc_file.filename:
                try:
                    org_document_ref = _save_uploaded_file(org_doc_file, 'org_document')
                except ValueError as exc:
                    db.session.rollback()
                    flash_form_error(str(exc))
                    return redirect(url_for('kyc.upload'))
            if not org_document_ref:
                org_document_ref = request.form.get('org_document_url', '').strip() or None

            if not all([org_id, org_doc_type, org_document_ref]):
                flash_form_error('Organization, document type, and a document (uploaded file or URL) are required')
                return redirect(url_for('kyc.upload'))

            # Verify user belongs to the org
            org_id_int = int(org_id)
            if not any(o.id == org_id_int for o in user_orgs):
                flash_form_error('You are not authorized to submit documents for this organization.')
                return redirect(url_for('kyc.upload'))

            try:
                checksum = hashlib.md5(org_document_ref.encode()).hexdigest()
                kyb_doc = OrganisationKYBDocument(
                    organisation_id=org_id_int,
                    document_type=org_doc_type,
                    storage_key=org_document_ref,
                    checksum=checksum,
                    verification_status="pending"
                )
                db.session.add(kyb_doc)
                db.session.commit()
                flash('Organization KYB document submitted successfully! It will be reviewed shortly.', 'success')
                return redirect(url_for('kyc.status'))
            except Exception as e:
                db.session.rollback()
                flash_form_error(f'Error submitting organization document: {str(e)}')
                return redirect(url_for('kyc.upload'))

        else:
            # ── Individual KYC ──────────────────────────────────────────────
            id_type = request.form.get('id_type')
            id_number = request.form.get('id_number')

            # Reject document types the Owner/Super Admin have disabled.
            from app.kyc_config_schema import get_kyc_settings
            accepted_id_types = [
                t.lower() for t in get_kyc_settings().get(
                    "kyc_accepted_id_types",
                    ["national_id", "passport", "driver_license", "voter_card"],
                )
            ]
            if id_type and id_type.lower() not in accepted_id_types:
                flash_form_error(
                    f'{id_type} verification is not currently accepted. '
                    'Please choose an accepted document type.'
                )
                return redirect(url_for('kyc.upload'))

            # Per-type gate: do not re-accept a document type compliance has
            # already verified. Users must use the compliance-issued replacement
            # link instead of starting a fresh submission for that type.
            if id_type and id_type.lower() in _get_verified_id_types(current_user.id):
                flash_form_error(
                    f'You have already verified a {id_type} document. '
                    'If compliance requested a clearer copy, use the replacement '
                    'link shown on this page.'
                )
                return redirect(url_for('kyc.upload'))

            # Prefer an uploaded file; fall back to a pasted URL. A file is
            # uploaded server-side in this same request (no client polling).
            document_url = None
            doc_file = request.files.get('kyc_doc_file')
            selfie_url = None
            selfie_file = request.files.get('selfie_file')
            try:
                if doc_file and doc_file.filename:
                    document_url = _save_uploaded_file(doc_file, 'document')
                if selfie_file and selfie_file.filename:
                    selfie_url = _save_uploaded_file(selfie_file, 'selfie')
            except ValueError as exc:
                db.session.rollback()
                flash_form_error(str(exc))
                return redirect(url_for('kyc.upload'))

            if not document_url:
                document_url = request.form.get('document_url', '').strip() or None
            if not selfie_url:
                selfie_url = request.form.get('selfie_url', '').strip() or None

            if not all([id_type, id_number, document_url]):
                flash_form_error('ID type, ID number, and a document (uploaded file or URL) are required')
                return redirect(url_for('kyc.upload'))

            try:
                record = KycService.submit_kyc(
                    user_id=current_user.id,
                    id_type=id_type,
                    id_number=id_number,
                    document_url=document_url,
                    selfie_url=selfie_url,
                    record_type=f"{id_type}_verification",
                    address_line1=request.form.get('address_line1'),
                    address_line2=request.form.get('address_line2'),
                    city=request.form.get('city'),
                    state=request.form.get('state'),
                    postal_code=request.form.get('postal_code'),
                    country=request.form.get('country'),
                )
                flash('Documents uploaded successfully! They will be reviewed shortly.', 'success')
                return redirect(url_for('kyc.status'))
            except Exception as e:
                flash_form_error(f'Error uploading documents: {str(e)}')
                return redirect(url_for('kyc.upload'))

    requested_reupload = None
    replacement_token = request.args.get('reupload', '').strip()
    if replacement_token:
        try:
            payload, target, organisation, request_data = _load_reupload_target(
                replacement_token
            )
            requested_reupload = {
                'token': replacement_token,
                'kind': payload['kind'],
                'document_key': payload.get('document_key', 'document'),
                'label': (
                    _request_label(payload.get('document_key', 'document'))
                    if payload['kind'] == 'individual'
                    else request_data.get('document_type') or target.document_type
                ),
                'reason': request_data.get('reason', ''),
                'record': target if payload['kind'] == 'individual' else None,
                'organisation_name': (
                    getattr(organisation, 'legal_name', None)
                    or getattr(organisation, 'name', 'Organisation')
                    if organisation else None
                ),
            }
        except ValueError as exc:
            flash_form_error(str(exc))

    if not requested_reupload:
        all_requests = individual_reupload_requests + organisation_reupload_requests
        if len(all_requests) == 1:
            replacement_token = all_requests[0]['token']
            try:
                payload, target, organisation, request_data = _load_reupload_target(
                    replacement_token
                )
                requested_reupload = {
                    'token': replacement_token,
                    'kind': payload['kind'],
                    'document_key': payload.get('document_key', 'document'),
                    'label': all_requests[0]['label'],
                    'reason': request_data.get('reason', ''),
                    'record': target if payload['kind'] == 'individual' else None,
                    'organisation_name': all_requests[0].get('organisation_name'),
                }
            except ValueError:
                pass

    in_org_context = is_acting_as_organization()
    active_org_id = get_current_org_id() if in_org_context else None
    # Show only the form relevant to the active context.
    # Org context  -> Organization KYB only (no individual form).
    # Individual   -> Individual KYC only (no organization form).
    show_individual = not in_org_context
    show_organization = in_org_context

    verified_id_types = _get_verified_id_types(current_user.id)

    from app.kyc_config_schema import get_kyc_settings
    accepted_id_types = get_kyc_settings().get(
        "kyc_accepted_id_types",
        ["national_id", "passport", "driver_license", "voter_card"],
    )

    return render_template('kyc/verify_upload.html',
                            user_orgs=user_orgs,
                            in_org_context=in_org_context,
                            active_org_id=active_org_id,
                            show_individual=show_individual,
                            show_organization=show_organization,
                            verified_id_types=verified_id_types,
                            accepted_id_types=accepted_id_types,
                            reupload_requests=individual_reupload_requests,
                            organisation_reupload_requests=organisation_reupload_requests,
                            requested_reupload=requested_reupload,
                            preselect_id_type=preselect_id_type)


# ============================================================================
# MODERATOR ROUTES (VIEW ONLY)
# ============================================================================

@kyc_bp.route("/moderate")
@login_required
@require_moderator
def moderate():
    """Show all KYC records for moderators (same data as admin view)"""
    
    # Show all records, not just pending
    all_records = KycRecord.query.order_by(KycRecord.created_at.desc()).all()
    
    # Audit log for moderator viewing
    from app.audit.comprehensive_audit import AuditService
    AuditService.security(
        event_type="moderator_view_kyc",
        severity="info",
        description=f"Moderator {current_user.id} viewed all KYC records",
        user_id=current_user.id,
        ip_address=request.remote_addr,
    )
    
    return render_template('kyc/moderate.html', records=all_records, is_moderator=True)


@kyc_bp.route("/moderate/document/<int:id>")
@login_required
@require_moderator
def moderate_document(id):
    """Show single KYC document for review (view-only for moderators)"""
    
    record = KycRecord.query.get_or_404(id)
    
    return render_template('kyc/moderate_document.html', record=record)
