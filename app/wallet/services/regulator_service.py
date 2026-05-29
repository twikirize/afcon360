# app/wallet/services/regulator_service.py
"""
Regulator and Aggregator Communication Service

Provides secure, compliant API access for regulatory bodies and payment aggregators.
Implements legal requirements for data sharing, audit trails, and compliance reporting.
"""

import json
import hashlib
import hmac
import secrets
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from flask import current_app
from cryptography.fernet import Fernet

from app.extensions import db
from app.wallet.models.wallet import WalletTransaction
from app.wallet.models.transaction import TransactionModel
from app.audit.comprehensive_audit import AuditService


class RegulatorAccessCode:
    """Temporary access codes for regulators"""
    
    def __init__(self, code: str, expires_at: datetime, 
                 permissions: List[str], created_by: int):
        self.code = code
        self.expires_at = expires_at
        self.permissions = permissions
        self.created_by = created_by
        self.created_at = datetime.now(timezone.utc)
        self.is_active = True
        self.access_count = 0
        self.max_accesses = 10  # Limit number of uses

    def is_valid(self) -> bool:
        """Check if access code is still valid"""
        return (self.is_active and 
                self.expires_at > datetime.now(timezone.utc) and
                self.access_count < self.max_accesses)

    def use_access(self) -> bool:
        """Mark access as used"""
        if self.is_valid():
            self.access_count += 1
            return True
        return False


class RegulatorService:
    """
    Service for managing regulator and aggregator communications.
    
    Implements:
    - Secure API key management
    - Time-limited access codes
    - Comprehensive audit logging
    - Legal compliance requirements
    - Data encryption and protection
    """

    def __init__(self):
        self.encryption_key = current_app.config.get('REGULATOR_ENCRYPTION_KEY')
        self.fernet = Fernet(self.encryption_key.encode()) if self.encryption_key else None

    def generate_access_code(self, regulator_id: str, permissions: List[str], 
                          duration_hours: int = 24, created_by: int = 1) -> Dict[str, Any]:
        """
        Generate secure access code for regulator.
        
        Args:
            regulator_id: Unique identifier for regulator
            permissions: List of allowed permissions
            duration_hours: How long the code should be valid
            created_by: User ID creating the access code
            
        Returns:
            Dict with access code and metadata
        """
        try:
            # Generate secure random code
            code = f"REG-{secrets.token_urlsafe(16).upper()}"
            
            # Set expiration
            expires_at = datetime.now(timezone.utc) + timedelta(hours=duration_hours)
            
            # Create access code object
            access_code = RegulatorAccessCode(
                code=code,
                expires_at=expires_at,
                permissions=permissions,
                created_by=created_by
            )
            
            # Store in cache/database (simplified - would use proper storage)
            self._store_access_code(regulator_id, access_code)
            
            # Log access code generation
            AuditService.compliance(
                action="access_code_generated",
                regulator_id=regulator_id,
                permissions=permissions,
                expires_at=expires_at.isoformat(),
                created_by=created_by,
                metadata={
                    "access_code": code,
                    "duration_hours": duration_hours
                }
            )
            
            return {
                'success': True,
                'access_code': code,
                'expires_at': expires_at.isoformat(),
                'permissions': permissions,
                'duration_hours': duration_hours,
                'max_accesses': access_code.max_accesses
            }
            
        except Exception as e:
            current_app.logger.error(f"Failed to generate access code: {e}")
            return {
                'success': False,
                'error': 'Failed to generate access code'
            }

    def validate_access_code(self, code: str, ip_address: str, 
                          user_agent: str) -> Dict[str, Any]:
        """
        Validate and use access code.
        
        Args:
            code: Access code to validate
            ip_address: Requesting IP address
            user_agent: Requesting user agent
            
        Returns:
            Dict with validation result and permissions
        """
        try:
            # Retrieve access code
            access_code = self._get_access_code(code)
            
            if not access_code:
                return {
                    'valid': False,
                    'error': 'Invalid access code'
                }
            
            if not access_code.is_valid():
                return {
                    'valid': False,
                    'error': 'Access code expired or exceeded usage limit'
                }
            
            # Mark as used
            if not access_code.use_access():
                return {
                    'valid': False,
                    'error': 'Access code usage limit exceeded'
                }
            
            # Log access
            AuditService.compliance(
                action="access_code_used",
                access_code=code,
                ip_address=ip_address,
                user_agent=user_agent,
                remaining_uses=access_code.max_accesses - access_code.access_count,
                metadata={
                    "permissions": access_code.permissions
                }
            )
            
            return {
                'valid': True,
                'permissions': access_code.permissions,
                'expires_at': access_code.expires_at.isoformat(),
                'remaining_uses': access_code.max_accesses - access_code.access_count
            }
            
        except Exception as e:
            current_app.logger.error(f"Failed to validate access code: {e}")
            return {
                'valid': False,
                'error': 'Validation failed'
            }

    def generate_compliance_report(self, report_type: str, start_date: datetime, 
                               end_date: datetime, regulator_id: str,
                               access_code: str) -> Dict[str, Any]:
        """
        Generate compliance report for regulator.
        
        Args:
            report_type: Type of report (daily, weekly, monthly, aml, kyc, etc.)
            start_date: Report start date
            end_date: Report end date
            regulator_id: Requesting regulator ID
            access_code: Valid access code
            
        Returns:
            Dict with report data
        """
        try:
            # Validate access code
            validation = self.validate_access_code(access_code, "127.0.0.1", "Regulator API")
            
            if not validation['valid']:
                return {
                    'success': False,
                    'error': 'Invalid or expired access code'
                }
            
            # Check permissions
            if f"report_{report_type}" not in validation['permissions']:
                return {
                    'success': False,
                    'error': f'Insufficient permissions for {report_type} report'
                }
            
            # Generate report based on type
            if report_type == 'daily':
                report_data = self._generate_daily_report(start_date, end_date)
            elif report_type == 'weekly':
                report_data = self._generate_weekly_report(start_date, end_date)
            elif report_type == 'monthly':
                report_data = self._generate_monthly_report(start_date, end_date)
            elif report_type == 'aml':
                report_data = self._generate_aml_report(start_date, end_date)
            elif report_type == 'kyc':
                report_data = self._generate_kyc_report(start_date, end_date)
            elif report_type == 'suspicious':
                report_data = self._generate_suspicious_report(start_date, end_date)
            elif report_type == 'compliance':
                report_data = self._generate_full_compliance_report(start_date, end_date)
            else:
                return {
                    'success': False,
                    'error': f'Unsupported report type: {report_type}'
                }
            
            # Encrypt sensitive data
            if self.fernet:
                encrypted_data = self.fernet.encrypt(json.dumps(report_data).encode()).decode()
            else:
                encrypted_data = report_data
            
            # Log report generation
            AuditService.compliance(
                action="report_generated",
                report_type=report_type,
                regulator_id=regulator_id,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                access_code=access_code,
                metadata={
                    "record_count": len(report_data.get('transactions', [])),
                    "data_encrypted": self.fernet is not None
                }
            )
            
            return {
                'success': True,
                'report_type': report_type,
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'data': encrypted_data,
                'record_count': len(report_data.get('transactions', [])),
                'is_encrypted': self.fernet is not None
            }
            
        except Exception as e:
            current_app.logger.error(f"Failed to generate compliance report: {e}")
            return {
                'success': False,
                'error': 'Failed to generate report'
            }

    def setup_aggregator_webhook(self, aggregator_id: str, webhook_url: str,
                               secret_key: str, events: List[str]) -> Dict[str, Any]:
        """
        Configure webhook for payment aggregator.
        
        Args:
            aggregator_id: Unique aggregator identifier
            webhook_url: URL to send events to
            secret_key: Secret key for webhook signature
            events: List of events to send
            
        Returns:
            Dict with setup result
        """
        try:
            # Validate webhook URL
            if not webhook_url.startswith(('http://', 'https://')):
                return {
                    'success': False,
                    'error': 'Invalid webhook URL format'
                }
            
            # Generate webhook secret
            webhook_secret = secrets.token_urlsafe(32)
            
            # Store webhook configuration
            webhook_config = {
                'aggregator_id': aggregator_id,
                'webhook_url': webhook_url,
                'secret_key': secret_key,
                'events': events,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'is_active': True
            }
            
            self._store_webhook_config(aggregator_id, webhook_config)
            
            # Log webhook setup
            AuditService.compliance(
                action="webhook_configured",
                aggregator_id=aggregator_id,
                webhook_url=webhook_url,
                events=events,
                metadata={
                    "webhook_secret": webhook_secret[:8] + "...",  # Log partial secret
                    "full_url": webhook_url
                }
            )
            
            return {
                'success': True,
                'webhook_secret': webhook_secret,
                'aggregator_id': aggregator_id,
                'events': events,
                'webhook_url': webhook_url
            }
            
        except Exception as e:
            current_app.logger.error(f"Failed to setup aggregator webhook: {e}")
            return {
                'success': False,
                'error': 'Failed to configure webhook'
            }

    def send_aggregator_event(self, aggregator_id: str, event_type: str,
                           event_data: Dict[str, Any]) -> bool:
        """
        Send event to aggregator webhook.
        
        Args:
            aggregator_id: Target aggregator
            event_type: Type of event
            event_data: Event payload
            
        Returns:
            bool indicating success
        """
        try:
            # Get webhook configuration
            webhook_config = self._get_webhook_config(aggregator_id)
            
            if not webhook_config or not webhook_config.get('is_active'):
                return False
            
            # Check if event type is subscribed
            if event_type not in webhook_config.get('events', []):
                return False
            
            # Prepare webhook payload
            payload = {
                'event_type': event_type,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'aggregator_id': aggregator_id,
                'data': event_data
            }
            
            # Generate signature
            signature = self._generate_webhook_signature(
                payload, webhook_config['secret_key']
            )
            
            # Send webhook
            import requests
            response = requests.post(
                webhook_config['webhook_url'],
                json=payload,
                headers={
                    'X-Aggregator-Signature': signature,
                    'X-Event-Type': event_type,
                    'Content-Type': 'application/json'
                },
                timeout=30
            )
            
            success = response.status_code == 200
            
            # Log webhook delivery
            AuditService.compliance(
                action="webhook_sent",
                aggregator_id=aggregator_id,
                event_type=event_type,
                webhook_url=webhook_config['webhook_url'],
                response_status=response.status_code,
                metadata={
                    "success": success,
                    "response_time": response.elapsed.total_seconds() if hasattr(response, 'elapsed') else None
                }
            )
            
            return success
            
        except Exception as e:
            current_app.logger.error(f"Failed to send aggregator event: {e}")
            return False

    def _generate_daily_report(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Generate daily transaction report"""
        transactions = self._get_transactions_by_date_range(start_date, end_date)
        
        return {
            'report_type': 'daily',
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'summary': {
                'total_transactions': len(transactions),
                'total_volume': sum(t.amount for t in transactions),
                'successful_transactions': len([t for t in transactions if t.status == 'completed']),
                'failed_transactions': len([t for t in transactions if t.status == 'failed']),
                'success_rate': len([t for t in transactions if t.status == 'completed']) / len(transactions) * 100
            },
            'transactions': [self._serialize_transaction(t) for t in transactions]
        }

    def _generate_weekly_report(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Generate weekly transaction report"""
        transactions = self._get_transactions_by_date_range(start_date, end_date)
        
        # Group by day
        daily_breakdown = {}
        for transaction in transactions:
            date_key = transaction.created_at.date().isoformat()
            if date_key not in daily_breakdown:
                daily_breakdown[date_key] = []
            daily_breakdown[date_key].append(transaction)
        
        return {
            'report_type': 'weekly',
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'summary': {
                'total_transactions': len(transactions),
                'total_volume': sum(t.amount for t in transactions),
                'average_daily_transactions': len(transactions) / 7,
                'peak_day': max(daily_breakdown.keys(), key=lambda k: len(daily_breakdown[k])) if daily_breakdown else None
            },
            'daily_breakdown': {
                date: {
                    'transactions': len(day_transactions),
                    'volume': sum(t.amount for t in day_transactions)
                }
                for date, day_transactions in daily_breakdown.items()
            }
        }

    def _generate_monthly_report(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Generate monthly transaction report"""
        transactions = self._get_transactions_by_date_range(start_date, end_date)
        
        # Group by gateway
        gateway_breakdown = {}
        for transaction in transactions:
            gateway = transaction.gateway_type or 'unknown'
            if gateway not in gateway_breakdown:
                gateway_breakdown[gateway] = []
            gateway_breakdown[gateway].append(transaction)
        
        return {
            'report_type': 'monthly',
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'summary': {
                'total_transactions': len(transactions),
                'total_volume': sum(t.amount for t in transactions),
                'unique_users': len(set(t.user_id for t in transactions)),
                'gateways_used': list(gateway_breakdown.keys())
            },
            'gateway_breakdown': {
                gateway: {
                    'transactions': len(gateway_transactions),
                    'volume': sum(t.amount for t in gateway_transactions),
                    'success_rate': len([t for t in gateway_transactions if t.status == 'completed']) / len(gateway_transactions) * 100
                }
                for gateway, gateway_transactions in gateway_breakdown.items()
            }
        }

    def _generate_aml_report(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Generate AML compliance report"""
        transactions = self._get_transactions_by_date_range(start_date, end_date)
        
        # Flag suspicious transactions
        suspicious_transactions = []
        for transaction in transactions:
            if self._is_suspicious_transaction(transaction):
                suspicious_transactions.append(transaction)
        
        return {
            'report_type': 'aml',
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'summary': {
                'total_transactions': len(transactions),
                'suspicious_transactions': len(suspicious_transactions),
                'suspicious_percentage': len(suspicious_transactions) / len(transactions) * 100,
                'high_value_transactions': len([t for t in transactions if t.amount > 100000])
            },
            'suspicious_transactions': [self._serialize_transaction(t) for t in suspicious_transactions]
        }

    def _generate_kyc_report(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Generate KYC compliance report"""
        # This would integrate with KYC system
        return {
            'report_type': 'kyc',
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'summary': {
                'total_users': 0,  # Would get from KYC system
                'verified_users': 0,
                'pending_verification': 0,
                'verification_rate': 0
            },
            'note': 'KYC integration required for detailed reporting'
        }

    def _generate_suspicious_report(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Generate suspicious activity report"""
        transactions = self._get_transactions_by_date_range(start_date, end_date)
        
        suspicious_activities = []
        for transaction in transactions:
            if self._is_suspicious_transaction(transaction):
                suspicious_activities.append({
                    'transaction': self._serialize_transaction(transaction),
                    'suspicious_indicators': self._get_suspicious_indicators(transaction)
                })
        
        return {
            'report_type': 'suspicious',
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'summary': {
                'total_activities': len(suspicious_activities),
                'high_risk_activities': len([a for a in suspicious_activities if 'high_risk' in a['suspicious_indicators']])
            },
            'suspicious_activities': suspicious_activities
        }

    def _generate_full_compliance_report(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Generate comprehensive compliance report"""
        return {
            'report_type': 'compliance',
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'sections': {
                'daily': self._generate_daily_report(start_date, end_date),
                'aml': self._generate_aml_report(start_date, end_date),
                'kyc': self._generate_kyc_report(start_date, end_date),
                'suspicious': self._generate_suspicious_report(start_date, end_date)
            }
        }

    def _get_transactions_by_date_range(self, start_date: datetime, end_date: datetime) -> List:
        """Get transactions within date range"""
        return TransactionModel.query.filter(
            TransactionModel.created_at >= start_date,
            TransactionModel.created_at <= end_date
        ).all()

    def _serialize_transaction(self, transaction) -> Dict[str, Any]:
        """Serialize transaction for reporting"""
        return {
            'id': transaction.id,
            'transaction_id': transaction.transaction_id,
            'user_id': transaction.user_id,
            'amount': float(transaction.amount),
            'currency': transaction.currency,
            'status': transaction.status,
            'gateway_type': transaction.gateway_type,
            'created_at': transaction.created_at.isoformat(),
            'updated_at': transaction.updated_at.isoformat()
        }

    def _is_suspicious_transaction(self, transaction) -> bool:
        """Check if transaction appears suspicious"""
        # Simple rules - would be more sophisticated in production
        return (
            transaction.amount > 1000000 or  # High value
            transaction.status == 'failed' and  # Multiple failures
            len([t for t in self._get_user_recent_transactions(transaction.user_id) if t.status == 'failed']) > 3
        )

    def _get_suspicious_indicators(self, transaction) -> List[str]:
        """Get suspicious indicators for transaction"""
        indicators = []
        if transaction.amount > 1000000:
            indicators.append('high_risk')
        if transaction.amount > 5000000:
            indicators.append('extreme_risk')
        return indicators

    def _get_user_recent_transactions(self, user_id: int, days: int = 7) -> List:
        """Get user's recent transactions"""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        return TransactionModel.query.filter(
            TransactionModel.user_id == user_id,
            TransactionModel.created_at >= cutoff_date
        ).all()

    def _generate_webhook_signature(self, payload: Dict[str, Any], secret: str) -> str:
        """Generate HMAC signature for webhook"""
        payload_str = json.dumps(payload, separators=(',', ':'), sort_keys=True)
        return hmac.new(
            secret.encode(),
            payload_str.encode(),
            hashlib.sha256
        ).hexdigest()

    def _store_access_code(self, regulator_id: str, access_code: RegulatorAccessCode):
        """Store access code (simplified - would use proper database)"""
        # In production, this would store in database
        pass

    def _get_access_code(self, code: str) -> Optional[RegulatorAccessCode]:
        """Retrieve access code (simplified)"""
        # In production, this would retrieve from database
        return None

    def _store_webhook_config(self, aggregator_id: str, config: Dict[str, Any]):
        """Store webhook configuration (simplified)"""
        # In production, this would store in database
        pass

    def _get_webhook_config(self, aggregator_id: str) -> Optional[Dict[str, Any]]:
        """Get webhook configuration (simplified)"""
        # In production, this would retrieve from database
        return None
