# app/identity/routes.py
"""
Organization routes - comprehensive organization management
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app, abort
from flask_login import login_required, current_user
from app.extensions import db
from app.identity.models.organisation import Organisation
from app.identity.models.organisation_member import OrganisationMember
from app.identity.models.organization_types import OrganizationType
from app.identity.services.organization_registration import OrganizationRegistrationService
from app.identity.services.organization_permissions import OrganizationPermissionService
from app.forms.organization_forms import (
    OrganizationRegistrationForm, OrganizationSettingsForm, 
    OrganizationMemberForm, OrganizationDocumentForm, OrganizationWalletForm
)

# Create the organization blueprint
org_bp = Blueprint('org', __name__, url_prefix='/org')


def _get_organisation_by_public_id(org_id):
    """Resolve an organisation from its public URL identifier."""
    org = Organisation.query.filter_by(
        org_id=str(org_id),
        is_deleted=False,
    ).first()
    if not org:
        abort(404)
    return org


@org_bp.route('/')
@login_required
def dashboard():
    """Organization dashboard - redirects to identity organization views"""
    # Get user's organizations
    memberships = OrganisationMember.query.filter_by(
        user_id=current_user.id,
        is_deleted=False,
        is_active=True
    ).all()
    
    if not memberships:
        flash('You are not a member of any organization.', 'info')
        return redirect(url_for('org.register'))
    
    # If only one organization, go directly to its dashboard
    if len(memberships) == 1:
        return redirect(url_for('org.org_dashboard', org_id=memberships[0].organisation.org_id))
    
    # Otherwise show organization selector
    return render_template('org/selector.html', memberships=memberships)


@org_bp.route('/register', methods=['GET', 'POST'])
@login_required
def register():
    """Register a new organization"""
    form = OrganizationRegistrationForm()
    
    if form.validate_on_submit():
        # Prepare registration data
        data = {
            'legal_name': form.legal_name.data,
            'org_type': form.org_type.data,
            'country': form.country.data,
            'region': form.region.data,
            'contact_email': form.contact_email.data,
            'contact_phone': form.contact_phone.data,
            'headquarters_address': form.headquarters_address.data,
            'website': form.website.data,
            'registration_no': form.registration_no.data,
            'tax_id': form.tax_id.data,
            'vat_number': form.vat_number.data
        }
        
        # Get system-wide organization registration mode setting
        from app.admin.models import SystemConfiguration
        org_registration_config = SystemConfiguration.query.filter_by(
            key='org_registration_mode'
        ).first()
        registration_mode = (
            org_registration_config.value if org_registration_config else 'testing'
        )
        
        # Set default settings based on owner configuration
        default_settings = {
            'registration_mode': registration_mode,
            'kyc_enabled': registration_mode == 'standard'  # Enable KYC in standard mode
        }
        
        # Create organization
        org, errors = OrganizationRegistrationService.create_organization(data, current_user, default_settings)
        
        if org:
            flash(f'Organization "{org.legal_name}" registered successfully! Your organization ID is {org.org_id}', 'success')
            return redirect(url_for('org.org_dashboard', org_id=org.org_id))
        else:
            for error in errors:
                flash(error, 'danger')
    
    return render_template('org/register.html', form=form)


@org_bp.route('/<org_id>/dashboard')
@login_required
def org_dashboard(org_id):
    """Organization-specific dashboard"""
    org = Organisation.query.filter_by(
        org_id=str(org_id),
        is_deleted=False,
    ).first()
    if not org and str(org_id).isdigit():
        # Read-only compatibility for legacy internal-ID links; immediately
        # redirect to the public organisation boundary when found.
        legacy_org = Organisation.query.get(int(org_id))
        if legacy_org and legacy_org.org_id:
            return redirect(url_for('org.org_dashboard', org_id=legacy_org.org_id))
    if not org:
        from flask import abort

        abort(404)

    # Verify membership
    if not OrganizationPermissionService.is_member(current_user, org):
        flash('You are not a member of this organization.', 'danger')
        return redirect(url_for('org.dashboard'))

    member = OrganisationMember.query.filter_by(
        user_id=current_user.id,
        organisation_id=org.id,
        is_deleted=False
    ).first()
    
    # Get organization statistics
    stats = {
        'total_members': OrganisationMember.query.filter_by(
            organisation_id=org.id,
            is_deleted=False,
            is_active=True
        ).count(),
        'active_modules': org.get_active_modules(),
        'can_create_events': org.can_create_events(),
        'can_manage_accommodation': org.can_manage_accommodation(),
        'can_manage_transport': org.can_manage_transport(),
        'can_manage_tourism': org.can_manage_tourism(),
        'can_process_payments': org.can_process_payments(),
        'requires_license': org.requires_license(),
        'requires_insurance': org.requires_insurance()
    }
    
    # Get user permissions
    user_permissions = OrganizationPermissionService.get_user_permissions(current_user, org)
    accessible_modules = OrganizationPermissionService.get_accessible_modules(current_user, org)
    organisation_role = OrganizationPermissionService.get_user_role(current_user, org)
    role_value = getattr(organisation_role, 'value', organisation_role) or 'member'
    organisation_role_label = str(role_value).replace('_', ' ').title()
    business_category = getattr(org.business_category, 'value', org.business_category)
    if role_value == 'org_manager' and str(business_category).lower() in {
        'hotel', 'accommodation_provider', 'hostel', 'vacation_rental'
    }:
        organisation_role_label = 'Hotel Manager'
    
    return render_template('org/dashboard.html', 
                         org=org, member=member, stats=stats,
                         user_permissions=user_permissions,
                         accessible_modules=accessible_modules,
                         organisation_role_label=organisation_role_label)


def _can_view_all_org_kyb() -> bool:
    u = current_user
    if getattr(u, "is_app_owner", lambda: False)():
        return True
    roles = getattr(u, "role_names", []) or []
    return any(r in roles for r in ("super_admin", "admin", "compliance", "compliance_officer"))


@org_bp.route('/<org_id>/kyb')
@login_required
def org_kyb(org_id):
    """Organisation KYB dashboard: per-org step status + (for owners/compliance)
    an overview of KYB status across all registered organisations."""
    org = Organisation.query.filter_by(org_id=str(org_id), is_deleted=False).first()
    if not org:
        abort(404)

    can_all = _can_view_all_org_kyb()
    if not can_all and not OrganizationPermissionService.is_member(current_user, org):
        flash('You are not a member of this organization.', 'danger')
        return redirect(url_for('org.dashboard'))

    from app.identity.services.organisation_kyb_service import OrganisationKYBService
    status = OrganisationKYBService.compute_status(org)
    all_summaries = OrganisationKYBService.get_all_summaries() if can_all else None

    return render_template(
        'org/kyb.html',
        org=org,
        status=status,
        all_summaries=all_summaries,
        can_view_all=can_all,
    )


@org_bp.route('/<org_id>/members', methods=['GET', 'POST'])
@login_required
def members(org_id):
    """View and manage organization members"""
    org = _get_organisation_by_public_id(org_id)
    # Verify permissions
    if not OrganizationPermissionService.can_manage_staff(current_user, org):
        flash('You do not have permission to manage members.', 'danger')
        return redirect(url_for('org.org_dashboard', org_id=org_id))
    
    # Handle member addition
    form = OrganizationMemberForm(organization_type=org.business_category)
    
    if form.validate_on_submit():
        try:
            from app.identity.models.user import User
            from app.identity.models.organization_types import OrganizationRole
            
            # Find user by email
            user = User.query.filter_by(email=form.user_email.data).first()
            if not user:
                flash('User with this email not found.', 'danger')
                return redirect(url_for('org.members', org_id=org_id))
            
            # Check if user is already a member
            existing_member = OrganisationMember.query.filter_by(
                user_id=user.id,
                organisation_id=org.id,
                is_deleted=False
            ).first()
            
            if existing_member:
                flash('User is already a member of this organization.', 'warning')
                return redirect(url_for('org.members', org_id=org_id))
            
            # Validate role assignment
            role = OrganizationRole(form.role.data)
            is_valid, error_msg = OrganizationPermissionService.validate_role_assignment(org, role)
            if not is_valid:
                flash(error_msg, 'danger')
                return redirect(url_for('org.members', org_id=org_id))
            
            # Add member
            OrganizationRegistrationService.add_org_member(org, user, role.value)
            
            if form.send_invite.data:
                # TODO: Send invitation email
                flash(f'User {user.email} added to organization with role {role.value.replace("_", " ").title()}', 'success')
            else:
                flash(f'User {user.email} added to organization with role {role.value.replace("_", " ").title()}', 'success')
            
            return redirect(url_for('org.members', org_id=org_id))
            
        except Exception as e:
            current_app.logger.error(f"Error adding member: {e}")
            flash('An error occurred while adding the member.', 'danger')
    
    # Get organization hierarchy
    hierarchy = OrganizationPermissionService.get_organization_hierarchy(org)
    
    return render_template('org/members.html', org=org, form=form, hierarchy=hierarchy)


@org_bp.route('/<org_id>/settings', methods=['GET', 'POST'])
@login_required
def settings(org_id):
    """Organization settings"""
    org = _get_organisation_by_public_id(org_id)
    # Verify permissions
    if not OrganizationPermissionService.can_manage_settings(current_user, org):
        flash('You do not have permission to manage settings.', 'danger')
        return redirect(url_for('org.org_dashboard', org_id=org_id))
    member = OrganisationMember.query.filter_by(
        user_id=current_user.id,
        organisation_id=org.id,
        is_deleted=False
    ).first()
    
    form = OrganizationSettingsForm(obj=org)
    
    if form.validate_on_submit():
        try:
            # Update organization details
            org.legal_name = form.legal_name.data
            org.contact_email = form.contact_email.data
            org.contact_phone = form.contact_phone.data
            org.headquarters_address = form.headquarters_address.data
            org.website = form.website.data
            
            # Update organization settings
            org.set_setting('business_description', form.business_description.data)
            org.set_setting('email_notifications', form.email_notifications.data)
            org.set_setting('sms_notifications', form.sms_notifications.data)
            org.set_setting('public_profile', form.public_profile.data)
            org.set_setting('allow_member_invites', form.allow_member_invites.data)
            
            db.session.commit()
            flash('Organization settings updated successfully.', 'success')
            return redirect(url_for('org.settings', org_id=org_id))
            
        except Exception as e:
            current_app.logger.error(f"Error updating settings: {e}")
            flash('An error occurred while updating settings.', 'danger')
    
    # Populate form with current settings
    form.business_description.data = org.get_setting('business_description', '')
    form.email_notifications.data = org.get_setting('email_notifications', True)
    form.sms_notifications.data = org.get_setting('sms_notifications', False)
    form.public_profile.data = org.get_setting('public_profile', False)
    form.allow_member_invites.data = org.get_setting('allow_member_invites', True)
    
    return render_template('org/settings.html', org=org, member=member, form=form)


@org_bp.route('/<org_id>/settings/kyc', methods=['POST'])
@login_required
def kyc_settings(org_id):
    """Save KYC settings for organization"""
    org = _get_organisation_by_public_id(org_id)
    # Verify permissions
    if not OrganizationPermissionService.can_manage_settings(current_user, org):
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        import json
        data = json.loads(request.data)
        
        # Save KYC settings
        org.set_setting('kyc_enabled', data.get('kyc_enabled', False))
        org.set_setting('kyc_strict', data.get('kyc_strict', False))
        org.set_setting('kyc_auto_approve', data.get('kyc_auto_approve', True))
        org.set_setting('default_kyc_level', data.get('default_kyc_level', 0))
        org.set_setting('max_kyc_level', data.get('max_kyc_level', 3))
        org.set_setting('registration_mode', data.get('registration_mode', 'standard'))
        org.set_setting('kyc_require_identity', data.get('kyc_require_identity', True))
        org.set_setting('kyc_require_address', data.get('kyc_require_address', False))
        org.set_setting('kyc_require_business', data.get('kyc_require_business', False))
        org.set_setting('kyc_require_financial', data.get('kyc_require_financial', False))
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'KYC settings saved successfully'})
        
    except Exception as e:
        current_app.logger.error(f"Error saving KYC settings: {str(e)}")
        return jsonify({'success': False, 'message': 'Error saving settings'}), 500


@org_bp.route('/<org_id>/wallet', methods=['GET', 'POST'])
@login_required
def wallet(org_id):
    """Organization wallet management"""
    org = _get_organisation_by_public_id(org_id)
    # Verify permissions
    if not OrganizationPermissionService.can_manage_wallet(current_user, org):
        flash('You do not have permission to manage wallet.', 'danger')
        return redirect(url_for('org.org_dashboard', org_id=org_id))
    
    # Get organization wallet
    from app.wallet.models.ledger import AccountModel, AccountOwnerType
    wallet = AccountModel.query.filter_by(
        user_id=org.id,
        owner_type=AccountOwnerType.ORGANISATION
    ).first()
    
    if not wallet:
        flash('Organization wallet not found.', 'warning')
        return redirect(url_for('org.org_dashboard', org_id=org_id))
    
    # Get wallet balance
    try:
        from app.wallet.services.wallet_service import WalletService
        balance = WalletService.get_balance(wallet.id)
    except Exception:
        balance = 0
    
    form = OrganizationWalletForm()
    
    if form.validate_on_submit():
        try:
            # Update wallet settings
            wallet.currency = form.default_currency.data
            org.set_setting('auto_settlement', form.auto_settlement.data)
            org.set_setting('settlement_frequency', form.settlement_frequency.data)
            org.set_setting('require_approval_for_large_transactions', form.require_approval_for_large_transactions.data)
            org.set_setting('large_transaction_threshold', form.large_transaction_threshold.data)
            
            db.session.commit()
            flash('Wallet settings updated successfully.', 'success')
            return redirect(url_for('org.wallet', org_id=org_id))
            
        except Exception as e:
            current_app.logger.error(f"Error updating wallet settings: {e}")
            flash('An error occurred while updating wallet settings.', 'danger')
    
    # Populate form with current settings
    form.default_currency.data = wallet.currency
    form.auto_settlement.data = org.get_setting('auto_settlement', False)
    form.settlement_frequency.data = org.get_setting('settlement_frequency', 'monthly')
    form.require_approval_for_large_transactions.data = org.get_setting('require_approval_for_large_transactions', False)
    form.large_transaction_threshold.data = org.get_setting('large_transaction_threshold', '')
    
    return render_template('org/wallet.html', org=org, wallet=wallet, balance=balance, form=form)


@org_bp.route('/<org_id>/events')
@login_required
def events(org_id):
    """Organization events management"""
    org = _get_organisation_by_public_id(org_id)
    # Verify permissions
    if not OrganizationPermissionService.can_create_events(current_user, org):
        flash('You do not have permission to manage events.', 'danger')
        return redirect(url_for('org.org_dashboard', org_id=org_id))
    
    # Get organization events (Owned or Operated by the selected organization)
    from app.events.models import Event
    from sqlalchemy import or_, and_
    events = Event.query.filter(
        Event.is_deleted.is_(False),
        or_(
            Event.organization_id == org.id, # Operated by the organisation
            and_(
                Event.current_owner_type == 'organization',
                Event.current_owner_id == org.id, # Owned by the organisation
            ),
        ),
    ).order_by(Event.start_date.desc()).all()
    
    return render_template('org/events.html', org=org, events=events)


@org_bp.route('/<org_id>/accommodation')
@login_required
def accommodation(org_id):
    """Organization accommodation management"""
    org = _get_organisation_by_public_id(org_id)
    # Verify permissions
    if not OrganizationPermissionService.can_manage_accommodation(current_user, org):
        flash('You do not have permission to manage accommodation.', 'danger')
        return redirect(url_for('org.org_dashboard', org_id=org_id))
    
    # Get organization accommodations
    from app.accommodation.models import Property
    accommodations = Property.query.filter_by(owner_org_id=org.id, is_deleted=False).all()
    
    return render_template('org/accommodation.html', org=org, accommodations=accommodations)


@org_bp.route('/<org_id>/bookings')
@login_required
def bookings(org_id):
    """View bookings for properties owned by the selected organisation."""
    org = _get_organisation_by_public_id(org_id)
    if not OrganizationPermissionService.can_manage_accommodation(current_user, org):
        flash('You do not have permission to manage accommodation.', 'danger')
        return redirect(url_for('org.org_dashboard', org_id=org_id))

    from app.accommodation.models import AccommodationBooking, Property
    bookings = (
        AccommodationBooking.query
        .join(Property, AccommodationBooking.property_id == Property.id)
        .filter(
            Property.owner_org_id == org.id,
            Property.is_deleted.is_(False),
            AccommodationBooking.is_deleted.is_(False),
        )
        .order_by(AccommodationBooking.created_at.desc())
        .all()
    )
    return render_template('org/bookings.html', org=org, bookings=bookings)


@org_bp.route('/<org_id>/transport')
@login_required
def transport(org_id):
    """Organization transport management"""
    org = _get_organisation_by_public_id(org_id)
    # Verify permissions
    if not OrganizationPermissionService.can_manage_transport(current_user, org):
        flash('You do not have permission to manage transport.', 'danger')
        return redirect(url_for('org.org_dashboard', org_id=org_id))
    
    # Get organization transport fleet
    from app.transport.models import Vehicle
    vehicles = Vehicle.query.filter_by(operator_id=org.id).all()
    
    return render_template('org/transport.html', org=org, vehicles=vehicles)


@org_bp.route('/<org_id>/tourism')
@login_required
def tourism(org_id):
    """Organization tourism management"""
    org = _get_organisation_by_public_id(org_id)
    # Verify permissions
    if not OrganizationPermissionService.can_manage_tourism(current_user, org):
        flash('You do not have permission to manage tourism.', 'danger')
        return redirect(url_for('org.org_dashboard', org_id=org_id))
    
    # Get organization tourism offerings
    from app.tourism.models import TourismListing
    tourism_listings = TourismListing.query.filter_by(operator_id=org.id).all()
    
    return render_template('org/tourism.html', org=org, tourism_listings=tourism_listings)


@org_bp.route('/<org_id>/reports')
@login_required
def reports(org_id):
    """Organization reports"""
    org = _get_organisation_by_public_id(org_id)
    # Verify permissions
    if not OrganizationPermissionService.can_view_reports(current_user, org):
        flash('You do not have permission to view reports.', 'danger')
        return redirect(url_for('org.org_dashboard', org_id=org_id))
    
    # Generate organization reports
    reports_data = {
        'member_stats': OrganisationMember.query.filter_by(
            organisation_id=org.id,
            is_deleted=False,
            is_active=True
        ).count(),
        'wallet_balance': 0,  # TODO: Get actual wallet balance
        'active_events': 0,   # TODO: Get actual events count
        'total_transactions': 0  # TODO: Get actual transaction count
    }
    
    return render_template('org/reports.html', org=org, reports=reports_data)


# API endpoints
@org_bp.route('/api/registration-config')
def registration_config():
    """Get registration form configuration"""
    org_type = request.args.get('org_type')
    config = OrganizationRegistrationService.get_registration_form_config(org_type)
    return jsonify(config)


@org_bp.route('/api/<int:org_id>/permissions')
@login_required
def api_permissions(org_id):
    """Get user permissions for organization"""
    if not OrganizationPermissionService.is_member(current_user, org_id):
        return jsonify({'error': 'Not a member'}), 403
    
    org = Organisation.query.get_or_404(org_id)
    permissions = OrganizationPermissionService.get_user_permissions(current_user, org)
    accessible_modules = OrganizationPermissionService.get_accessible_modules(current_user, org)
    
    return jsonify({
        'permissions': list(permissions),
        'accessible_modules': accessible_modules,
        'role': OrganizationPermissionService.get_user_role(current_user, org).value if OrganizationPermissionService.get_user_role(current_user, org) else None
    })


# ---------------------------------------------------------------------------
# Provider Capability endpoints
# ---------------------------------------------------------------------------

@org_bp.route('/<org_id>/capabilities')
@login_required
def list_capabilities(org_id):
    """List provider capabilities for an organisation.

    Any active org member may view capabilities.
    """
    org = _get_organisation_by_public_id(org_id)

    if not OrganizationPermissionService.is_member(current_user, org):
        return jsonify({'error': 'Not a member'}), 403

    from app.identity.services.provider_participation_service import (
        list_organisation_intentions,
        participation_to_dict,
    )
    caps = list_organisation_intentions(org.id)
    return jsonify({
        'organisation_id': org.org_id,
        'capabilities': [participation_to_dict(c) for c in caps],
    })


@org_bp.route('/<org_id>/capabilities/<code>/activate', methods=['POST'])
@login_required
def activate_capability(org_id, code):
    """Activate a provider capability (intent → activated).

    Requires org_owner authority.
    """
    org = _get_organisation_by_public_id(org_id)

    from app.identity.services.provider_participation_service import (
        activate_organisation_intention,
        ParticipationNotFoundError,
        ParticipationPermissionError,
        ParticipationTransitionError,
        ParticipationValidationError,
        participation_to_dict,
    )
    from app.identity.models.organisation_provider_capability import ProviderCapabilityCode

    try:
        ProviderCapabilityCode(code)
    except ValueError:
        return jsonify({'error': f'Invalid capability code: {code}'}), 400

    try:
        cap = activate_organisation_intention(current_user, org.id, code)
    except ParticipationPermissionError as exc:
        return jsonify({'error': str(exc)}), 403
    except ParticipationNotFoundError as exc:
        return jsonify({'error': str(exc)}), 404
    except ParticipationTransitionError as exc:
        return jsonify({'error': str(exc)}), 409
    except ParticipationValidationError as exc:
        return jsonify({'error': str(exc)}), 400

    return jsonify({
        'message': f"Capability '{code}' activated.",
        'organisation_id': org.org_id,
        'capability': participation_to_dict(cap),
    })


@org_bp.route('/<org_id>/capabilities/<code>/deactivate', methods=['POST'])
@login_required
def deactivate_capability(org_id, code):
    """Deactivate a provider capability (activated → deactivated).

    Requires org_owner authority.  Reversible.
    """
    org = _get_organisation_by_public_id(org_id)

    from app.identity.services.provider_participation_service import (
        deactivate_organisation_intention,
        ParticipationNotFoundError,
        ParticipationPermissionError,
        ParticipationTransitionError,
        ParticipationValidationError,
        participation_to_dict,
    )
    from app.identity.models.organisation_provider_capability import ProviderCapabilityCode

    try:
        ProviderCapabilityCode(code)
    except ValueError:
        return jsonify({'error': f'Invalid capability code: {code}'}), 400

    try:
        cap = deactivate_organisation_intention(current_user, org.id, code)
    except ParticipationPermissionError as exc:
        return jsonify({'error': str(exc)}), 403
    except ParticipationNotFoundError as exc:
        return jsonify({'error': str(exc)}), 404
    except ParticipationTransitionError as exc:
        return jsonify({'error': str(exc)}), 409
    except ParticipationValidationError as exc:
        return jsonify({'error': str(exc)}), 400

    return jsonify({
        'message': f"Capability '{code}' deactivated.",
        'organisation_id': org.org_id,
        'capability': participation_to_dict(cap),
    })


@org_bp.route('/<org_id>/capabilities/<code>/suspend', methods=['POST'])
@login_required
def suspend_capability(org_id, code):
    """Suspend a provider capability (activated → suspended).

    Requires org_owner or platform admin authority.
    """
    org = _get_organisation_by_public_id(org_id)

    from app.identity.services.provider_participation_service import (
        suspend_organisation_intention,
        ParticipationNotFoundError,
        ParticipationPermissionError,
        ParticipationTransitionError,
        ParticipationValidationError,
        participation_to_dict,
    )
    from app.identity.models.organisation_provider_capability import ProviderCapabilityCode

    try:
        ProviderCapabilityCode(code)
    except ValueError:
        return jsonify({'error': f'Invalid capability code: {code}'}), 400

    try:
        cap = suspend_organisation_intention(current_user, org.id, code)
    except ParticipationPermissionError as exc:
        return jsonify({'error': str(exc)}), 403
    except ParticipationNotFoundError as exc:
        return jsonify({'error': str(exc)}), 404
    except ParticipationTransitionError as exc:
        return jsonify({'error': str(exc)}), 409
    except ParticipationValidationError as exc:
        return jsonify({'error': str(exc)}), 400

    return jsonify({
        'message': f"Capability '{code}' suspended.",
        'organisation_id': org.org_id,
        'capability': participation_to_dict(cap),
    })


@org_bp.route('/<org_id>/capabilities/<code>/revoke', methods=['POST'])
@login_required
def revoke_capability(org_id, code):
    """Revoke a provider capability (any → revoked).

    Requires org_owner or platform admin authority.
    Revoked capabilities are not re-grantable without review.
    """
    org = _get_organisation_by_public_id(org_id)

    from app.identity.services.provider_participation_service import (
        revoke_organisation_intention,
        ParticipationNotFoundError,
        ParticipationPermissionError,
        ParticipationTransitionError,
        ParticipationValidationError,
        participation_to_dict,
    )
    from app.identity.models.organisation_provider_capability import ProviderCapabilityCode

    try:
        ProviderCapabilityCode(code)
    except ValueError:
        return jsonify({'error': f'Invalid capability code: {code}'}), 400

    try:
        cap = revoke_organisation_intention(current_user, org.id, code)
    except ParticipationPermissionError as exc:
        return jsonify({'error': str(exc)}), 403
    except ParticipationNotFoundError as exc:
        return jsonify({'error': str(exc)}), 404
    except ParticipationTransitionError as exc:
        return jsonify({'error': str(exc)}), 409
    except ParticipationValidationError as exc:
        return jsonify({'error': str(exc)}), 400

    return jsonify({
        'message': f"Capability '{code}' revoked.",
        'organisation_id': org.org_id,
        'capability': participation_to_dict(cap),
    })


# Export the blueprint for the main app to register
__all__ = ['org_bp']
