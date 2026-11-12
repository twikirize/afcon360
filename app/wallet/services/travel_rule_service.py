"""
Travel Rule Compliance Service
FATF Travel Rule implementation for crypto/fiat transfers
"""

from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from decimal import Decimal

from app.extensions import db
from app.wallet.models.travel_rule import TravelRuleConfig, TravelRuleTransfer
from app.wallet.services.admin_audit_service import AdminAuditService


class TravelRuleService:
    """Service for managing Travel Rule compliance"""
    
    @staticmethod
    def update_config(
        admin_id: int,
        admin_name: str,
        admin_role: str,
        **updates
    ) -> TravelRuleConfig:
        """
        Update Travel Rule configuration
        
        Args:
            admin_id: ID of admin making changes
            admin_name: Name of admin
            admin_role: Role of admin
            **updates: Fields to update
            
        Returns:
            Updated configuration
        """
        try:
            config = TravelRuleConfig.query.first()
            
            if not config:
                config = TravelRuleConfig()
                db.session.add(config)
                db.session.flush()  # Get ID for audit
            
            # Store old value for audit
            old_snapshot = config.to_audit_dict()
            
            # Update fields
            for key, value in updates.items():
                if hasattr(config, key):
                    setattr(config, key, value)
            
            with AdminAuditService.audited_change():
                AdminAuditService.log_action(
                    admin_id=admin_id,
                    admin_name=admin_name,
                    admin_role=admin_role,
                    action_type='modify',
                    action_category='travel_rule',
                    target_type='travel_rule_config',
                    target_id=str(config.id),
                    target_name='Travel Rule Configuration',
                    old_value=old_snapshot,
                    new_value=config.to_audit_dict(),
                    reason='Travel rule configuration updated'
                )
            
            return config
        except Exception as e:
            raise e
    
    @staticmethod
    def check_travel_rule_required(
        amount: int,
        currency: str,
        is_crypto: bool = False
    ) -> Dict[str, Any]:
        """
        Check if Travel Rule applies to a transaction
        
        Args:
            amount: Transaction amount in smallest currency unit
            currency: Currency code
            is_crypto: Whether this is a crypto transaction
            
        Returns:
            Dictionary with check result
        """
        try:
            config = TravelRuleConfig.query.first()
            
            if not config or not config.enabled:
                return {
                    'required': False,
                    'reason': 'Travel rule disabled',
                    'action': 'proceed'
                }
            
            # Convert to USD for threshold comparison (simplified - would need real FX conversion)
            amount_usd = amount  # Simplified - would convert based on currency
            
            # Check threshold
            if is_crypto:
                threshold = config.crypto_threshold_usd
            else:
                threshold = config.fiat_threshold_usd
            
            if amount_usd < threshold:
                return {
                    'required': False,
                    'reason': f'Amount below threshold (${amount_usd} < ${threshold})',
                    'action': 'proceed'
                }
            
            return {
                'required': True,
                'reason': f'Amount above threshold (${amount_usd} >= ${threshold})',
                'action': 'collect_info'
            }
        except Exception as e:
            current_app.logger.error(f"Travel rule check error: {e}")
            return {
                'required': False,
                'reason': 'Travel rule check failed',
                'action': 'proceed'
            }
    
    @staticmethod
    def create_travel_rule_transfer(
        transaction_id: str,
        originator_info: Dict[str, Any],
        beneficiary_info: Dict[str, Any],
        amount: int,
        currency: str,
        transaction_purpose: Optional[str] = None,
        originator_vasp: Optional[Dict[str, str]] = None,
        beneficiary_vasp: Optional[Dict[str, str]] = None
    ) -> TravelRuleTransfer:
        """
        Create a Travel Rule transfer record for compliance tracking
        
        Args:
            transaction_id: Associated transaction UUID
            originator_info: Originator details (name, account, address, dob, id_number, nationality)
            beneficiary_info: Beneficiary details
            amount: Transaction amount in smallest currency unit
            currency: Currency code
            transaction_purpose: Purpose of transaction
            originator_vasp: Originator VASP details (name, address)
            beneficiary_vasp: Beneficiary VASP details (name, address)
            
        Returns:
            Created TravelRuleTransfer record
        """
        try:
            transfer = TravelRuleTransfer(
                transaction_id=transaction_id,
                originator_name=originator_info.get('name'),
                originator_account_number=originator_info.get('account_number'),
                originator_address=originator_info.get('address'),
                originator_dob=originator_info.get('dob'),
                originator_id_number=originator_info.get('id_number'),
                originator_nationality=originator_info.get('nationality'),
                beneficiary_name=beneficiary_info.get('name'),
                beneficiary_account_number=beneficiary_info.get('account_number'),
                beneficiary_address=beneficiary_info.get('address'),
                beneficiary_dob=beneficiary_info.get('dob'),
                beneficiary_id_number=beneficiary_info.get('id_number'),
                beneficiary_nationality=beneficiary_info.get('nationality'),
                amount=amount,
                currency=currency,
                transaction_purpose=transaction_purpose,
                originator_vasp_name=originator_vasp.get('name') if originator_vasp else None,
                originator_vasp_address=originator_vasp.get('address') if originator_vasp else None,
                beneficiary_vasp_name=beneficiary_vasp.get('name') if beneficiary_vasp else None,
                beneficiary_vasp_address=beneficiary_vasp.get('address') if beneficiary_vasp else None,
                status='pending'
            )
            
            db.session.add(transfer)
            db.session.commit()
            
            return transfer
        except Exception as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def verify_travel_rule_transfer(
        transfer_id: int,
        verification_score: int,
        admin_id: int,
        admin_name: str,
        admin_role: str,
        status: str = 'verified',
        rejection_reason: Optional[str] = None
    ) -> TravelRuleTransfer:
        """
        Verify or reject a Travel Rule transfer
        
        Args:
            transfer_id: ID of transfer to verify
            verification_score: Verification score (0-100)
            admin_id: ID of admin performing verification
            admin_name: Name of admin
            admin_role: Role of admin
            status: 'verified' or 'rejected'
            rejection_reason: Reason for rejection (if rejected)
            
        Returns:
            Updated TravelRuleTransfer record
        """
        try:
            transfer = db.session.get(TravelRuleTransfer, transfer_id)
            if not transfer:
                raise ValueError(f"Travel rule transfer {transfer_id} not found")
            
            old_snapshot = transfer.to_dict() if hasattr(transfer, 'to_dict') else {
                'status': transfer.status,
                'verification_score': transfer.verification_score,
                'rejection_reason': transfer.rejection_reason
            }
            
            transfer.verification_score = verification_score
            transfer.status = status
            transfer.rejection_reason = rejection_reason
            
            if status == 'verified':
                transfer.reported_to_vasp = True
                transfer.vasp_reported_at = datetime.now(timezone.utc)
            
            db.session.commit()
            
            # Log audit
            AdminAuditService.log_action(
                admin_id=admin_id,
                admin_name=admin_name,
                admin_role=admin_role,
                action_type='verify',
                action_category='travel_rule',
                target_type='travel_rule_transfer',
                target_id=str(transfer.id),
                target_name=f'Travel Rule Transfer {transfer.id}',
                old_value=old_snapshot,
                new_value=transfer.to_dict() if hasattr(transfer, 'to_dict') else {
                    'status': transfer.status,
                    'verification_score': transfer.verification_score,
                    'rejection_reason': transfer.rejection_reason
                },
                reason=f'Travel rule transfer {status}: {rejection_reason or "verified"}'
            )
            
            return transfer
        except Exception as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def report_to_vasp(
        transfer_id: int,
        vasp_response: str,
        admin_id: int,
        admin_name: str,
        admin_role: str
    ) -> TravelRuleTransfer:
        """
        Mark transfer as reported to VASP
        
        Args:
            transfer_id: ID of transfer
            vasp_response: VASP response
            admin_id: ID of admin
            admin_name: Name of admin
            admin_role: Role of admin
            
        Returns:
            Updated TravelRuleTransfer record
        """
        try:
            transfer = db.session.get(TravelRuleTransfer, transfer_id)
            if not transfer:
                raise ValueError(f"Travel rule transfer {transfer_id} not found")
            
            old_snapshot = transfer.to_dict() if hasattr(transfer, 'to_dict') else {
                'reported_to_vasp': transfer.reported_to_vasp,
                'vasp_response': transfer.vasp_response,
                'vasp_reported_at': transfer.vasp_reported_at
            }
            
            transfer.reported_to_vasp = True
            transfer.vasp_response = vasp_response
            transfer.vasp_reported_at = datetime.now(timezone.utc)
            
            db.session.commit()
            
            # Log audit
            AdminAuditService.log_action(
                admin_id=admin_id,
                admin_name=admin_name,
                admin_role=admin_role,
                action_type='report_to_vasp',
                action_category='travel_rule',
                target_type='travel_rule_transfer',
                target_id=str(transfer.id),
                target_name=f'Travel Rule Transfer {transfer.id}',
                old_value=old_snapshot,
                new_value=transfer.to_dict() if hasattr(transfer, 'to_dict') else {
                    'reported_to_vasp': transfer.reported_to_vasp,
                    'vasp_response': transfer.vasp_response,
                    'vasp_reported_at': transfer.vasp_reported_at
                },
                reason=f'Reported travel rule transfer to VASP'
            )
            
            return transfer
        except Exception as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def get_config() -> Optional[TravelRuleConfig]:
        """Get current Travel Rule configuration"""
        return TravelRuleConfig.query.first()
    
    @staticmethod
    def get_pending_transfers(limit: int = 100) -> List[TravelRuleTransfer]:
        """Get pending Travel Rule transfers requiring verification"""
        return TravelRuleTransfer.query.filter_by(
            status='pending'
        ).order_by(TravelRuleTransfer.created_at.asc()).limit(limit).all()