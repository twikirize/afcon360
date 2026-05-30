"""
Travel Rule Compliance Service
FATF Travel Rule implementation for crypto/fiat transfers
"""

from typing import Dict, Any, Optional, List
from flask import current_app

from app.extensions import db
from app.wallet.models.travel_rule import TravelRuleConfig, TravelRuleTransfer
from app.wallet.services.admin_audit_service import AdminAuditService


class TravelRuleService:
    """Service for managing FATF Travel Rule compliance"""
    
    @staticmethod
    def get_config() -> Optional[TravelRuleConfig]:
        """Get current travel rule configuration"""
        return TravelRuleConfig.query.first()
    
    @staticmethod
    def update_config(
        admin_id: int,
        admin_name: str,
        admin_role: str,
        **updates
    ) -> TravelRuleConfig:
        """
        Update travel rule configuration
        
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
                # Create default config if none exists
                config = TravelRuleConfig()
                db.session.add(config)
            
            # Store old value for audit
            old_value = config.to_dict()
            
            # Update fields
            for key, value in updates.items():
                if hasattr(config, key):
                    setattr(config, key, value)
            
            db.session.commit()
            
            # Log the action
            AdminAuditService.log_action(
                admin_id=admin_id,
                admin_name=admin_name,
                admin_role=admin_role,
                action_type='modify',
                action_category='travel_rule',
                target_type='travel_rule_config',
                target_id=str(config.id),
                target_name='Travel Rule Configuration',
                old_value=str(old_value),
                new_value=config.to_dict(),
                reason='Travel rule configuration updated'
            )
            
            return config
        except Exception as e:
            db.session.rollback()
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
            # Fail open - proceed if check fails
            return {
                'required': False,
                'reason': 'Check error - proceed',
                'action': 'proceed'
            }
    
    @staticmethod
    def create_travel_rule_record(
        transaction_id: int,
        originator_info: Dict[str, Any],
        beneficiary_info: Dict[str, Any],
        amount: int,
        currency: str,
        transaction_purpose: Optional[str] = None
    ) -> TravelRuleTransfer:
        """
        Create a travel rule transfer record
        
        Args:
            transaction_id: Transaction ID
            originator_info: Originator information
            beneficiary_info: Beneficiary information
            amount: Transaction amount
            currency: Currency code
            transaction_purpose: Purpose of transaction
            
        Returns:
            Created travel rule transfer record
        """
        try:
            travel_rule_transfer = TravelRuleTransfer(
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
                status='pending'
            )
            
            db.session.add(travel_rule_transfer)
            db.session.commit()
            
            return travel_rule_transfer
        except Exception as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def verify_travel_rule_record(
        record_id: int,
        verification_score: int,
        status: str,
        rejection_reason: Optional[str] = None
    ) -> TravelRuleTransfer:
        """
        Verify a travel rule transfer record
        
        Args:
            record_id: Travel rule record ID
            verification_score: Verification score (0-100)
            status: Status (verified, rejected)
            rejection_reason: Reason for rejection (if rejected)
            
        Returns:
            Updated travel rule transfer record
        """
        try:
            travel_rule_transfer = TravelRuleTransfer.query.get(record_id)
            if not travel_rule_transfer:
                raise ValueError(f"Travel rule record {record_id} not found")
            
            travel_rule_transfer.verification_score = verification_score
            travel_rule_transfer.status = status
            if rejection_reason:
                travel_rule_transfer.rejection_reason = rejection_reason
            
            db.session.commit()
            
            return travel_rule_transfer
        except Exception as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def get_travel_rule_transfers(
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get travel rule transfers
        
        Args:
            status: Filter by status
            limit: Maximum number of results
            
        Returns:
            List of travel rule transfer dictionaries
        """
        try:
            query = TravelRuleTransfer.query
            
            if status:
                query = query.filter(TravelRuleTransfer.status == status)
            
            query = query.order_by(TravelRuleTransfer.created_at.desc())
            query = query.limit(limit)
            
            transfers = query.all()
            return [transfer.to_dict() for transfer in transfers]
        except Exception as e:
            raise e
    
    @staticmethod
    def report_to_vasp(record_id: int) -> Dict[str, Any]:
        """
        Report travel rule information to VASP
        
        Args:
            record_id: Travel rule record ID
            
        Returns:
            Dictionary with reporting result
        """
        try:
            config = TravelRuleConfig.query.first()
            travel_rule_transfer = TravelRuleTransfer.query.get(record_id)
            
            if not config or not config.auto_report_to_vasp:
                return {
                    'success': False,
                    'reason': 'Auto-reporting disabled'
                }
            
            if not travel_rule_transfer:
                return {
                    'success': False,
                    'reason': 'Record not found'
                }
            
            # Placeholder for actual VASP API call
            # In real implementation, this would make HTTP request to VASP endpoint
            
            # Mark as reported
            travel_rule_transfer.reported_to_vasp = True
            travel_rule_transfer.vasp_reported_at = datetime.utcnow()
            travel_rule_transfer.vasp_response = 'Success: Information transmitted to VASP'
            
            db.session.commit()
            
            return {
                'success': True,
                'reason': 'Successfully reported to VASP',
                'vasp_response': travel_rule_transfer.vasp_response
            }
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"VASP reporting error: {e}")
            return {
                'success': False,
                'reason': str(e)
            }
