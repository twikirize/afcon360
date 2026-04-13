# app/kyc/services.py
from datetime import datetime, date, timezone
from typing import List, Dict, Optional, Tuple
from flask import current_app, request
from app.extensions import db
from app.kyc.models import KycRecord
from app.compliance.logger import ComplianceLogger
from app.audit.forensic_audit import ForensicAuditService
# User import is moved inside methods to avoid circular imports
from app.profile.models import UserProfile, get_profile_by_user
from app.identity.models.user import User
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import or_, and_

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

        record = KycRecord.query.get(record_id)
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

        # Update user profile verification status
        # KycRecord.user_id is internal ID (BigInteger), but UserProfile.user_id is a String(64) FK to users.public_id
        # So we need to look up the User first to get their public_id
        _user = User.query.filter_by(id=record.user_id).first()
        profile = get_profile_by_user(_user) if _user else None
        if profile:
            profile.verification_status = "verified"
            profile.verified_at = datetime.now(timezone.utc)
            db.session.add(profile)

        db.session.commit()

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
        record = KycRecord.query.get(record_id)
        if not record:
            raise ValueError(f"KYC record {record_id} not found")

        record.status = "rejected"
        record.checked_by = str(reviewer_id)
        record.verified_at = datetime.now(timezone.utc)
        record.rejection_reason = rejection_reason

        db.session.commit()

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

        latest_record = None
        for record in records:
            status_counts[record.status] = status_counts.get(record.status, 0) + 1
            if not latest_record or record.created_at > latest_record.created_at:
                latest_record = record

        return {
            "counts": status_counts,
            "latest_record": latest_record,
            "is_verified": status_counts["approved"] > 0,
            "has_pending": status_counts["pending"] > 0
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
                record = KycRecord.query.get(record_id)
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
