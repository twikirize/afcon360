# app/kyc/services.py
from datetime import datetime, date, timezone
from typing import List, Dict, Optional, Tuple
from flask import current_app, request
from app.extensions import cache, db
from app.kyc.models import KycRecord
# Try to import ComplianceLogger, but make it optional
try:
    from app.compliance.logger import ComplianceLogger
    COMPLIANCE_LOGGER_AVAILABLE = True
except ImportError:
    COMPLIANCE_LOGGER_AVAILABLE = False
    # Create a mock ComplianceLogger for fallback
    class ComplianceLogger:
        @staticmethod
        def log_decision(*args, **kwargs):
            pass

# Import ForensicAuditService - this should be available
from app.audit.forensic_audit import ForensicAuditService
# User import is moved inside methods to avoid circular imports
from app.profile.models import UserProfile, get_profile_by_user
from app.identity.models.user import User
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import or_, and_
from app.admin.compliance.services import ComplianceCaseService
from app.admin.compliance.models import ComplianceCaseType, ComplianceCasePriority

class KycService:
    """
    Enhanced KYC service layer for comprehensive operations.
    Handles creation, approval, rejection, and logging for all user types.
    """

    @staticmethod
    def submit_kyc(user_id: int, id_type: str, id_number: str,
                   document_url: str, selfie_url: str = None,
                   address_line1: str = None, address_line2: str = None,
                   city: str = None, state: str = None, postal_code: str = None,
                   country: str = None, provider: str = None,
                   record_type: str = "national_id", document_type: str = "image",
                   ip_address: Optional[str] = None, user_agent: Optional[str] = None):
        """
        Create a new KYC record for the user with enhanced fields.
        """
        # Log attempt
        audit_id = ForensicAuditService.log_attempt(
            entity_type="kyc",
            entity_id=str(user_id),
            action="submit",
            user_id=user_id,
            details={
                "id_type": id_type,
                "record_type": record_type,
                "provider": provider
            },
            ip_address=ip_address or (request.remote_addr if request else None),
            user_agent=user_agent or (request.user_agent.string if request else None)
        )

        try:
            # Mask ID number for display
            if id_number and len(id_number) > 4:
                id_number_masked = id_number[:2] + "*" * (len(id_number) - 4) + id_number[-2:]
            else:
                id_number_masked = id_number

            record = KycRecord(
                user_id=user_id,
                record_type=record_type,
                document_type=document_type,
                id_type=id_type,
                id_number=id_number,
                id_number_masked=id_number_masked,
                document_url=document_url,
                selfie_url=selfie_url,
                address_line1=address_line1,
                address_line2=address_line2,
                city=city,
                state=state,
                postal_code=postal_code,
                country=country,
                status="pending",
                provider=provider or "manual_upload",
                checked_by=None,
                verified_at=None,
                rejection_reason=None,
                created_at=datetime.now(timezone.utc)
            )
            db.session.add(record)
            db.session.commit()
            KycService.invalidate_user_kyc_cache(user_id)

            # Emit notification signal for submitted KYC
            try:
                from app.notifications.signals import kyc_submitted
                kyc_submitted.send(record, user_id=user_id, record=record)
            except Exception as sig_err:
                current_app.logger.warning(f"kyc_submitted signal failed: {sig_err}")

            # Log using the correct method
            try:
                ComplianceLogger.log_decision(
                    entity_id=record.id,
                    entity_type="kyc_record",
                    operation="create",
                    decision="submitted",
                    requirement_key="kyc_verification",
                    context={"user_id": user_id, "id_type": id_type, "record_type": record_type}
                )
            except Exception as e:
                current_app.logger.warning(f"Could not log KYC submission: {e}")

            # Log completion
            ForensicAuditService.log_completion(
                audit_id=audit_id,
                status="completed",
                result_details={"record_id": record.id, "status": "pending"}
            )

            return record
        except SQLAlchemyError as e:
            db.session.rollback()
            # Log failure
            ForensicAuditService.log_completion(
                audit_id=audit_id,
                status="failed",
                result_details={"error": str(e)}
            )
            raise e

    @staticmethod
    def _sync_kyc_level_snapshot(user_id: Optional[int]) -> Optional[int]:
        """Recompute User.kyc_level from the canonical tier authority.

        User.kyc_level is a legacy snapshot column; the effective tier is
        always calculated by calculate_kyc_tier() at read time. Rewriting the
        snapshot after each compliance decision keeps the column truthful for
        reporting and legacy consumers without making it authoritative.
        """
        if not user_id:
            return None
        user = db.session.get(User, user_id)
        if not user:
            return None
        try:
            from app.auth.kyc_compliance import calculate_kyc_tier
            tier = calculate_kyc_tier(user_id)["tier"]
        except Exception:
            return None
        try:
            user.kyc_level = int(tier)
            db.session.commit()
            return user.kyc_level
        except Exception:
            db.session.rollback()
            return None

    @staticmethod
    def _backfill_profile_from_kyc_record(record) -> bool:
        """Backfill only missing canonical profile facts from approved KYC evidence.

        UserProfile remains the single person-identity authority. The KYC row is
        evidence, not a second identity store: it may supply missing DOB and
        nationality from its structured scope, while an already-approved
        address_verification row may supply a missing address and city.

        Existing canonical values are never overwritten. Verified profiles are
        treated as immutable. The nested transaction makes this best-effort:
        a backfill failure is rolled back to its savepoint and must not prevent
        the separate KYC approval decision from being committed.
        """
        if record is None or not getattr(record, "user_id", None):
            return False

        try:
            changed = False

            with db.session.begin_nested():
                user = User.query.filter_by(id=record.user_id).first()
                if user is None:
                    return False

                profile = get_profile_by_user(user)
                if profile is None:
                    return False

                if (getattr(profile, "verification_status", "") or "").lower() == "verified":
                    return False

                scope = getattr(record, "scope", None) or {}
                if isinstance(scope, str):
                    import json
                    try:
                        scope = json.loads(scope)
                    except (TypeError, ValueError):
                        scope = {}
                if not isinstance(scope, dict):
                    scope = {}

                scope_sources = [scope]
                for key in ("identity", "personal", "person", "personal_details", "verification"):
                    nested_scope = scope.get(key)
                    if isinstance(nested_scope, dict):
                        scope_sources.append(nested_scope)

                def scope_value(*keys):
                    for source in scope_sources:
                        for key in keys:
                            value = source.get(key)
                            if value is not None and str(value).strip():
                                return value
                    return None

                # Date of birth is a canonical identity fact. Accept real date
                # values and ISO strings only; malformed evidence is ignored.
                if getattr(profile, "date_of_birth", None) is None:
                    dob_value = scope_value("date_of_birth", "dob", "birth_date", "dateOfBirth")
                    if isinstance(dob_value, datetime):
                        dob_value = dob_value.date()
                    elif isinstance(dob_value, str):
                        try:
                            dob_value = date.fromisoformat(dob_value.strip()[:10])
                        except ValueError:
                            dob_value = None
                    if isinstance(dob_value, date):
                        profile.date_of_birth = dob_value
                        changed = True

                # Nationality is distinct from the country on an address
                # document; only the explicit nationality/citizenship field
                # in the KYC scope may populate it.
                if not (getattr(profile, "nationality", None) or "").strip():
                    nationality = scope_value("nationality", "citizenship", "country_of_citizenship")
                    if isinstance(nationality, str) and nationality.strip():
                        profile.nationality = nationality.strip()[:64]
                        changed = True

                # Address and city are sourced only from an approved address
                # verification record for the same account. Never infer
                # nationality from the document's country field.
                if (
                    not (getattr(profile, "address", None) or "").strip()
                    or not (getattr(profile, "city", None) or "").strip()
                ):
                    address_record = (
                        KycRecord.query.filter_by(
                            user_id=record.user_id,
                            record_type="address_verification",
                        )
                        .filter(
                            KycRecord.is_deleted.is_(False),
                            KycRecord.status.in_(("approved", "verified")),
                        )
                        .order_by(KycRecord.created_at.desc(), KycRecord.id.desc())
                        .first()
                    )
                    if address_record is not None:
                        address_parts = [
                            (getattr(address_record, "address_line1", None) or "").strip(),
                            (getattr(address_record, "address_line2", None) or "").strip(),
                        ]
                        address = ", ".join(part for part in address_parts if part)
                        if not (getattr(profile, "address", None) or "").strip() and address:
                            profile.address = address[:256]
                            changed = True

                        city = (getattr(address_record, "city", None) or "").strip()
                        if not (getattr(profile, "city", None) or "").strip() and city:
                            profile.city = city[:128]
                            changed = True

                if changed:
                    db.session.add(profile)

            return changed
        except Exception:
            # The nested transaction has already rolled back its savepoint.
            # Do not roll back the outer transaction containing the approval.
            current_app.logger.warning(
                "Canonical profile backfill from approved KYC evidence skipped",
                exc_info=True,
            )
            return False

    @staticmethod
    def approve_kyc(record_id: int, reviewer_id: int, kyc_level: int = 2,
                    ip_address: Optional[str] = None, user_agent: Optional[str] = None):
        """
        Approve a KYC record and update user profile.
        """
        # Log attempt
        audit_id = ForensicAuditService.log_attempt(
            entity_type="kyc",
            entity_id=str(record_id),
            action="approve",
            user_id=reviewer_id,
            details={"kyc_level": kyc_level},
            ip_address=ip_address,
            user_agent=user_agent
        )

        record = db.session.get(KycRecord, record_id)
        if not record:
            ForensicAuditService.log_completion(
                audit_id=audit_id,
                status="failed",
                result_details={"error": f"KYC record {record_id} not found"}
            )
            raise ValueError(f"KYC record {record_id} not found")

        record.status = "approved"
        record.checked_by = str(reviewer_id)
        record.verified_at = datetime.now(timezone.utc)
        record.rejection_reason = None

        # Backfill missing canonical facts before the profile becomes immutable.
        KycService._backfill_profile_from_kyc_record(record)

        # Update the profile from the same record used by the account and dashboard.
        # KycRecord.user_id is internal ID; UserProfile.user_id stores public_id.
        _user = User.query.filter_by(id=record.user_id).first()
        profile = get_profile_by_user(_user) if _user else None
        if profile:
            profile.verification_status = "verified"
            profile.rejected_reason = None
            profile.verified_by = str(reviewer_id)
            profile.last_reviewed_at = datetime.now(timezone.utc)
            db.session.add(profile)

        db.session.commit()
        KycService.invalidate_user_kyc_cache(record.user_id)
        KycService._sync_kyc_level_snapshot(record.user_id)

        # Log compliance
        try:
            ComplianceLogger.log_decision(
                entity_id=record.id,
                entity_type="kyc_record",
                operation="approve",
                decision="approved",
                requirement_key="kyc_verification",
                compliance_level=kyc_level,
                context={"user_id": record.user_id, "reviewer_id": reviewer_id}
            )
        except Exception as e:
            current_app.logger.warning(f"Could not log KYC approval: {e}")

        # Emit notification signal (listener dispatches to user + admins)
        try:
            from app.notifications.signals import kyc_approved
            kyc_approved.send(record, user_id=record.user_id, record=record)
        except Exception as _ne:
            current_app.logger.warning(f"kyc_approved signal failed: {_ne}")

        # Log completion
        ForensicAuditService.log_completion(
            audit_id=audit_id,
            status="completed",
            reviewed_by=reviewer_id,
            review_notes=f"KYC approved with level {kyc_level}",
            result_details={"record_id": record.id, "status": "approved", "kyc_level": kyc_level}
        )

        return record

    @staticmethod
    def reject_kyc(record_id: int, reviewer_id: int, rejection_reason: str):
        """
        Reject a KYC record.
        """
        record = db.session.get(KycRecord, record_id)
        if not record:
            raise ValueError(f"KYC record {record_id} not found")

        record.status = "rejected"
        record.checked_by = str(reviewer_id)
        record.verified_at = datetime.now(timezone.utc)
        record.rejection_reason = rejection_reason

        _user = User.query.filter_by(id=record.user_id).first()
        profile = get_profile_by_user(_user) if _user else None
        if profile:
            profile.verification_status = "rejected"
            profile.rejected_reason = rejection_reason
            profile.verified_by = str(reviewer_id)
            profile.last_reviewed_at = datetime.now(timezone.utc)
            db.session.add(profile)

        db.session.commit()
        KycService.invalidate_user_kyc_cache(record.user_id)
        KycService._sync_kyc_level_snapshot(record.user_id)

        # Log compliance
        try:
            ComplianceLogger.log_decision(
                entity_id=record.id,
                entity_type="kyc_record",
                operation="reject",
                decision="rejected",
                requirement_key="kyc_verification",
                compliance_level=0,
                context={
                    "user_id": record.user_id,
                    "reviewer_id": reviewer_id,
                    "rejection_reason": rejection_reason
                }
            )
        except Exception as e:
            current_app.logger.warning(f"Could not log KYC rejection: {e}")

        # Emit notification signal
        try:
            from app.notifications.signals import kyc_rejected
            kyc_rejected.send(record, user_id=record.user_id, reason=rejection_reason, record=record)
        except Exception as _ne:
            current_app.logger.warning(f"kyc_rejected signal failed: {_ne}")

        return record

    @staticmethod
    def revert_kyc(record_id: int, reviewer_id: int, reason: str,
                   ip_address: Optional[str] = None, user_agent: Optional[str] = None):
        """
        Re-cancel/revert an approved KYC record due to error or discovery of invalid documents.
        Resets status to 'rejected' and revokes user profile verification status.
        """
        audit_id = ForensicAuditService.log_attempt(
            entity_type="kyc",
            entity_id=str(record_id),
            action="revert_approval",
            user_id=reviewer_id,
            details={"reason": reason},
            ip_address=ip_address,
            user_agent=user_agent
        )

        record = db.session.get(KycRecord, record_id)
        if not record:
            ForensicAuditService.log_completion(
                audit_id=audit_id,
                status="failed",
                result_details={"error": f"KYC record {record_id} not found"}
            )
            raise ValueError(f"KYC record {record_id} not found")

        old_status = record.status
        record.status = "rejected"
        record.checked_by = str(reviewer_id)
        record.verified_at = datetime.now(timezone.utc)
        record.rejection_reason = f"[Reverted from {old_status}] {reason}"

        # Revert user profile verification status if verified
        _user = User.query.filter_by(id=record.user_id).first()
        profile = get_profile_by_user(_user) if _user else None
        if profile:
            profile.verification_status = "rejected"
            profile.rejected_reason = reason
            profile.verified_by = str(reviewer_id)
            profile.last_reviewed_at = datetime.now(timezone.utc)
            db.session.add(profile)

        db.session.commit()
        KycService.invalidate_user_kyc_cache(record.user_id)

        # Log compliance
        try:
            ComplianceLogger.log_decision(
                entity_id=record.id,
                entity_type="kyc_record",
                operation="revert",
                decision="rejected",
                requirement_key="kyc_verification",
                compliance_level=0,
                context={"user_id": record.user_id, "reviewer_id": reviewer_id, "reason": reason}
            )
        except Exception as e:
            current_app.logger.warning(f"Could not log KYC reversion: {e}")

        # Emit notification signal (re-cancel / requirements not fulfilled)
        try:
            from app.notifications.signals import kyc_rejected
            kyc_rejected.send(record, user_id=record.user_id, reason=reason, record=record)
        except Exception as _ne:
            current_app.logger.warning(f"kyc_rejected signal failed: {_ne}")

        ForensicAuditService.log_completion(
            audit_id=audit_id,
            status="completed",
            reviewed_by=reviewer_id,
            review_notes=f"KYC approval reverted. Reason: {reason}",
            result_details={"record_id": record.id, "status": "rejected", "reason": reason}
        )

        return record

    @staticmethod
    def get_user_kyc(user_id: int) -> List[KycRecord]:
        """
        Return all KYC records for a user.
        """
        records = KycRecord.query.filter_by(user_id=user_id).order_by(KycRecord.created_at.desc()).all()

        # Log access
        try:
            ComplianceLogger.log_decision(
                entity_id=user_id,
                entity_type="user",
                operation="kyc_lookup",
                decision="accessed",
                requirement_key="data_access",
                context={"purpose": "kyc_lookup"}
            )
        except Exception as e:
            current_app.logger.warning(f"Could not log KYC lookup: {e}")

        return records

    @staticmethod
    def _record_sort_key(record):
        """Return a timezone-safe ordering key for KYC submissions."""
        created_at = getattr(record, "created_at", None)
        if created_at is None:
            created_at = datetime.min.replace(tzinfo=timezone.utc)
        elif created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return created_at, getattr(record, "id", 0) or 0

    @staticmethod
    def invalidate_user_kyc_cache(user_id: int):
        """Drop the dashboard KYC context after a status-changing action."""
        cache.delete(f"kyc_ctx_{user_id}")

    @staticmethod
    def get_pending_kyc(limit: int = 50) -> List[KycRecord]:
        """
        Return pending KYC records for review.
        """
        return KycRecord.query.filter_by(status="pending").order_by(KycRecord.created_at.asc()).limit(limit).all()

    @staticmethod
    def get_approved_kyc(user_id: Optional[int] = None, limit: int = 100) -> List[KycRecord]:
        """
        Get approved KYC records, optionally filtered by user.
        """
        query = KycRecord.query.filter_by(status="approved")
        if user_id:
            query = query.filter_by(user_id=user_id)
        return query.order_by(KycRecord.verified_at.desc()).limit(limit).all()

    @staticmethod
    def get_rejected_kyc(user_id: Optional[int] = None, limit: int = 100) -> List[KycRecord]:
        """
        Get rejected KYC records, optionally filtered by user.
        """
        query = KycRecord.query.filter_by(status="rejected")
        if user_id:
            query = query.filter_by(user_id=user_id)
        return query.order_by(KycRecord.verified_at.desc()).limit(limit).all()

    @staticmethod
    def search_kyc_records(search_term: str = None, status: str = None,
                          id_type: str = None, start_date: date = None,
                          end_date: date = None, limit: int = 100) -> List[KycRecord]:
        """
        Search KYC records with various filters.
        """
        query = KycRecord.query

        if search_term:
            query = query.filter(
                or_(
                    KycRecord.id_number.contains(search_term),
                    KycRecord.id_number_masked.contains(search_term),
                    KycRecord.id_type.contains(search_term)
                )
            )

        if status:
            query = query.filter_by(status=status)

        if id_type:
            query = query.filter_by(id_type=id_type)

        if start_date:
            query = query.filter(KycRecord.created_at >= start_date)

        if end_date:
            query = query.filter(KycRecord.created_at <= end_date)

        return query.order_by(KycRecord.created_at.desc()).limit(limit).all()

    @staticmethod
    def get_user_verification_status(user_id: int) -> Dict:
        """
        Get comprehensive verification status for a user.
        """
        records = KycRecord.query.filter_by(user_id=user_id).all()

        status_counts = {
            "total": len(records),
            "pending": 0,
            "approved": 0,
            "rejected": 0
        }

        for record in records:
            status_counts[record.status] = status_counts.get(record.status, 0) + 1

        latest_record = (
            max(records, key=KycService._record_sort_key)
            if records else None
        )
        latest_status = getattr(latest_record, "status", None) if latest_record else None
        latest_status = latest_status.lower() if isinstance(latest_status, str) else latest_status

        return {
            "counts": status_counts,
            "latest_record": latest_record,
            "status": latest_status,
            "is_verified": latest_status in {"approved", "verified"},
            "has_pending": latest_status in {
                "pending", "manual_review", "processing", "in_review"
            }
        }

    @staticmethod
    def get_kyc_stats() -> Dict:
        """
        Get KYC statistics for dashboard.
        """
        from datetime import timedelta

        total = KycRecord.query.count()
        pending = KycRecord.query.filter_by(status="pending").count()
        approved = KycRecord.query.filter_by(status="approved").count()
        rejected = KycRecord.query.filter_by(status="rejected").count()

        # Recent activity (last 7 days)
        week_ago = datetime.now(timezone.utc).date() - timedelta(days=7)
        recent = KycRecord.query.filter(KycRecord.created_at >= week_ago).count()

        return {
            "total": total,
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "approval_rate": (approved / total * 100) if total > 0 else 0,
            "recent_activity": recent
        }

    @staticmethod
    def bulk_update_status(record_ids: List[int], status: str, reviewer_id: int,
                          rejection_reason: str = None) -> Tuple[int, List[str]]:
        """
        Bulk update KYC record status.
        Returns (updated_count, errors)
        """
        updated = 0
        errors = []

        for record_id in record_ids:
            try:
                record = db.session.get(KycRecord, record_id)
                if not record:
                    errors.append(f"Record {record_id} not found")
                    continue

                record.status = status
                record.checked_by = str(reviewer_id)
                record.verified_at = datetime.now(timezone.utc)

                if status == "rejected" and rejection_reason:
                    record.rejection_reason = rejection_reason
                elif status == "approved":
                    record.rejection_reason = None

                db.session.add(record)
                updated += 1

            except Exception as e:
                errors.append(f"Error updating record {record_id}: {str(e)}")

        if updated > 0:
            db.session.commit()

        return updated, errors

    @staticmethod
    def refer_to_compliance(record_id: int, referred_by: int, reason: str, 
                           priority: ComplianceCasePriority = ComplianceCasePriority.MEDIUM):
        """
        Refer a KYC record to compliance for further review.
        Creates a compliance case and updates the KYC record.
        """
        record = db.session.get(KycRecord, record_id)
        if not record:
            raise ValueError(f"KYC record {record_id} not found")

        # Create compliance case
        compliance_case = ComplianceCaseService.create_case(
            case_type=ComplianceCaseType.KYC_REVIEW,
            title=f'KYC Review - ID#{record.id}',
            description=f'KYC record referred for compliance review: {reason}',
            created_by=referred_by,
            user_id=record.user_id,
            kyc_id=record_id,
            priority=priority,
            escalated_from=referred_by,
            escalation_reason=reason
        )

        # Update KYC record
        record.referred_to_compliance = True
        record.referred_at = datetime.now(timezone.utc)
        record.referred_by = referred_by
        record.compliance_case_id = compliance_case.id
        record.compliance_status = 'pending'

        db.session.commit()

        # Log audit
        ForensicAuditService.log_action(
            action='refer_kyc_to_compliance',
            user_id=referred_by,
            resource_type='kyc_record',
            resource_id=record.id,
            details={
                'compliance_case_id': compliance_case.id,
                'reason': reason,
                'priority': priority.value
            }
        )

        return compliance_case

    @staticmethod
    def compliance_approve_kyc(record_id: int, reviewer_id: int, notes: str = None):
        """
        Approve a KYC record from compliance perspective.
        Updates both KYC status and compliance status.
        """
        record = db.session.get(KycRecord, record_id)
        if not record:
            raise ValueError(f"KYC record {record_id} not found")

        # Update KYC record
        record.status = "approved"
        record.checked_by = str(reviewer_id)
        record.verified_at = datetime.now(timezone.utc)
        record.rejection_reason = None
        record.compliance_status = 'approved'
        record.compliance_reviewed_at = datetime.now(timezone.utc)
        record.compliance_reviewed_by = reviewer_id
        record.compliance_notes = notes

        # Backfill missing canonical facts before the profile becomes immutable.
        KycService._backfill_profile_from_kyc_record(record)

        # Update user profile verification status
        _user = User.query.filter_by(id=record.user_id).first()
        profile = get_profile_by_user(_user) if _user else None
        if profile:
            profile.verification_status = "verified"
            profile.rejected_reason = None
            profile.verified_by = str(reviewer_id)
            profile.last_reviewed_at = datetime.now(timezone.utc)
            db.session.add(profile)

        # Update compliance case if exists
        if record.compliance_case_id:
            from app.compliance.models import ComplianceCaseStatus
            ComplianceCaseService.update_case_status(
                record.compliance_case_id,
                ComplianceCaseStatus.APPROVED,
                reviewer_id,
                resolution=notes
            )

        db.session.commit()
        KycService.invalidate_user_kyc_cache(record.user_id)
        KycService._sync_kyc_level_snapshot(record.user_id)

        # Emit notification signals for email and in-app notifications
        try:
            from app.notifications.signals import kyc_approved
            kyrid = record.user_id
            kyc_approved.send(
                None,
                user_id=kyrid,
                record_id=record.id,
                notes=notes
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to send kyc_approved signal: {e}")

        # Log audit
        ForensicAuditService.log_attempt(
            entity_type='kyc_record',
            entity_id=record.id,
            action='compliance_approve_kyc',
            user_id=reviewer_id,
            details={
                'compliance_case_id': record.compliance_case_id,
                'notes': notes
            }
        )
        ForensicAuditService.log_completion(
            audit_id=str(record.id),
            status='completed',
            reviewed_by=reviewer_id,
            review_notes=notes,
            result_details={'status': 'approved'}
        )

        return record

    @staticmethod
    def compliance_reject_kyc(record_id: int, reviewer_id: int, rejection_reason: str):
        """
        Reject a KYC record from compliance perspective.
        Updates both KYC status and compliance status.
        """
        record = db.session.get(KycRecord, record_id)
        if not record:
            raise ValueError(f"KYC record {record_id} not found")

        # Update KYC record
        record.status = "rejected"
        record.checked_by = str(reviewer_id)
        record.verified_at = datetime.now(timezone.utc)
        record.rejection_reason = rejection_reason
        record.compliance_status = 'rejected'
        record.compliance_reviewed_at = datetime.now(timezone.utc)
        record.compliance_reviewed_by = reviewer_id
        record.compliance_notes = rejection_reason

        # Update compliance case if exists
        if record.compliance_case_id:
            from app.compliance.models import ComplianceCaseStatus
            ComplianceCaseService.update_case_status(
                record.compliance_case_id,
                ComplianceCaseStatus.REJECTED,
                reviewer_id,
                resolution=rejection_reason
            )

        _user = User.query.filter_by(id=record.user_id).first()
        profile = get_profile_by_user(_user) if _user else None
        if profile:
            profile.verification_status = "rejected"
            profile.rejected_reason = rejection_reason
            profile.verified_by = str(reviewer_id)
            profile.last_reviewed_at = datetime.now(timezone.utc)
            db.session.add(profile)

        db.session.commit()
        KycService.invalidate_user_kyc_cache(record.user_id)
        KycService._sync_kyc_level_snapshot(record.user_id)

        # Emit notification signals for email and in-app notifications
        try:
            from app.notifications.signals import kyc_rejected
            kyrid = record.user_id
            kyc_rejected.send(
                None,
                user_id=kyrid,
                record_id=record.id,
                reason=rejection_reason
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to send kyc_rejected signal: {e}")

        # Log audit
        ForensicAuditService.log_attempt(
            entity_type='kyc_record',
            entity_id=record.id,
            action='compliance_reject_kyc',
            user_id=reviewer_id,
            details={
                'compliance_case_id': record.compliance_case_id,
                'rejection_reason': rejection_reason
            }
        )
        ForensicAuditService.log_completion(
            audit_id=str(record.id),
            status='completed',
            reviewed_by=reviewer_id,
            review_notes=rejection_reason,
            result_details={'status': 'rejected'}
        )

        return record

    @staticmethod
    def get_referred_to_compliance(limit: int = 50) -> List[KycRecord]:
        """
        Get KYC records that have been referred to compliance.
        """
        return KycRecord.query.filter_by(
            referred_to_compliance=True
        ).order_by(
            KycRecord.referred_at.desc()
        ).limit(limit).all()

    @staticmethod
    def get_compliance_pending_kyc(limit: int = 50) -> List[KycRecord]:
        """
        Get KYC records pending compliance review.
        """
        return KycRecord.query.filter_by(
            referred_to_compliance=True,
            compliance_status='pending'
        ).order_by(
            KycRecord.referred_at.asc()
        ).limit(limit).all()

