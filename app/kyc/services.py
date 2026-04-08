# app/kyc/services.py
from datetime import datetime
from app.extensions import db
from app.kyc.models import KycRecord
from app.compliance.logger import ComplianceLogger
from sqlalchemy.exc import SQLAlchemyError

class KycService:
    """
    Service layer for KYC operations.
    Handles creation, approval, rejection, and logging.
    """

    @staticmethod
    def submit_kyc(user_id: int, id_type: str, id_number: str,
                   document_url: str, selfie_url: str = None,
                   address_line1: str = None, address_line2: str = None,
                   city: str = None, state: str = None, postal_code: str = None,
                   country: str = None, provider: str = None):
        """
        Create a new KYC record for the user.
        """
        try:
            record = KycRecord(
                user_id=user_id,
                id_type=id_type,
                id_number=id_number,
                document_url=document_url,
                selfie_url=selfie_url,
                address_line1=address_line1,
                address_line2=address_line2,
                city=city,
                state=state,
                postal_code=postal_code,
                country=country,
                status="pending",
                provider=provider,
                checked_by=None,
                verified_at=None,
                rejection_reason=None
            )
            db.session.add(record)
            db.session.commit()

            # Log system access to KYC document
            ComplianceLogger.log_kyc_data_access(
                accessed_by=None,  # system
                subject_user_id=user_id,
                purpose="kyc_submission"
            )

            return record
        except SQLAlchemyError as e:
            db.session.rollback()
            raise e

    @staticmethod
    def approve_kyc(record_id: int, reviewer_id: int, kyc_level: int = 2):
        """
        Approve a KYC record.
        """
        record = KycRecord.query.get(record_id)
        if not record:
            raise ValueError(f"KYC record {record_id} not found")

        record.status = "approved"
        record.checked_by = str(reviewer_id)
        record.verified_at = datetime.utcnow()
        record.rejection_reason = None

        db.session.commit()

        # Log compliance and audit
        ComplianceLogger.log_kyc_decision(
            user_id=record.user_id,
            decision="approved",
            kyc_level=kyc_level,
            reviewer_id=reviewer_id
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
        record.verified_at = datetime.utcnow()
        record.rejection_reason = rejection_reason

        db.session.commit()

        # Log compliance and audit
        ComplianceLogger.log_kyc_decision(
            user_id=record.user_id,
            decision="rejected",
            kyc_level=0,
            reviewer_id=reviewer_id,
            rejection_reason=rejection_reason
        )

        return record

    @staticmethod
    def get_user_kyc(user_id: int):
        """
        Return all KYC records for a user.
        """
        records = KycRecord.query.filter_by(user_id=user_id).all()
        # Log access
        ComplianceLogger.log_kyc_data_access(
            accessed_by=None,  # system
            subject_user_id=user_id,
            purpose="kyc_lookup"
        )
        return records

    @staticmethod
    def get_pending_kyc(limit: int = 50):
        """
        Return pending KYC records for review.
        """
        return KycRecord.query.filter_by(status="pending").order_by(KycRecord.id.asc()).limit(limit).all()
