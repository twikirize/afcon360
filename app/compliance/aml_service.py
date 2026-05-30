"""
Anti-Money Laundering (AML) Screening Service

Implements AML screening, transaction monitoring, and regulatory reporting.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON, Float
from app.extensions import db
from flask import current_app
import hashlib
import json


class AMLRiskLevel(Enum):
    """AML risk level classification."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    PROHIBITED = "prohibited"


class AMLAlertType(Enum):
    """AML alert types."""
    LARGE_TRANSACTION = "large_transaction"
    HIGH_FREQUENCY = "high_frequency"
    SUSPICIOUS_PATTERN = "suspicious_pattern"
    SANCTIONS_HIT = "sanctions_hit"
    PEP_MATCH = "pep_match"
    UNUSUAL_LOCATION = "unusual_location"
    ROUNDING = "rounding_amounts"
    STRUCTURING = "transaction_structuring"


class AMLScreeningResult(db.Model):
    """AML screening results storage."""
    __tablename__ = 'aml_screening_results'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    transaction_id = Column(String(100), nullable=True, index=True)
    
    # Screening details
    screening_type = Column(String(50), nullable=False)  # user, transaction, beneficiary
    screening_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    risk_level = Column(String(20), nullable=False, index=True)
    risk_score = Column(Float, nullable=False)
    
    # Sanctions check results
    sanctions_checked = Column(Boolean, default=False, nullable=False)
    sanctions_matches = Column(JSON, nullable=True)
    
    # PEP check results
    pep_checked = Column(Boolean, default=False, nullable=False)
    pep_matches = Column(JSON, nullable=True)
    
    # Risk factors
    risk_factors = Column(JSON, nullable=True)
    alerts_triggered = Column(JSON, nullable=True)
    
    # Review status
    reviewed = Column(Boolean, default=False, nullable=False)
    reviewed_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    reviewed_date = Column(DateTime, nullable=True)
    review_notes = Column(Text, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AMLTransactionMonitor(db.Model):
    """Transaction monitoring for AML."""
    __tablename__ = 'aml_transaction_monitor'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    
    # Monitoring period
    monitoring_date = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    period_type = Column(String(20), nullable=False)  # daily, weekly, monthly
    
    # Transaction statistics
    total_transactions = Column(Integer, default=0, nullable=False)
    total_amount = Column(Float, default=0.0, nullable=False)
    average_amount = Column(Float, default=0.0, nullable=False)
    max_amount = Column(Float, default=0.0, nullable=False)
    
    # Risk indicators
    large_transactions_count = Column(Integer, default=0, nullable=False)
    high_frequency_flag = Column(Boolean, default=False, nullable=False)
    unusual_pattern_flag = Column(Boolean, default=False, nullable=False)
    rounding_flag = Column(Boolean, default=False, nullable=False)
    structuring_flag = Column(Boolean, default=False, nullable=False)
    
    # Geographic analysis
    countries_involved = Column(JSON, nullable=True)
    high_risk_countries = Column(JSON, nullable=True)
    
    # Alert status
    alert_level = Column(String(20), nullable=False, default='none')  # none, low, medium, high
    alerts_generated = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AMLService:
    """Anti-Money Laundering service."""
    
    def __init__(self):
        self.risk_thresholds = {
            'large_transaction_usd': 10000,
            'daily_transaction_limit': 50000,
            'weekly_transaction_limit': 200000,
            'monthly_transaction_limit': 500000,
            'high_frequency_daily': 50,
            'high_frequency_weekly': 200,
            'rounding_tolerance': 0.95,
            'structuring_threshold': 5  # Multiple similar amounts
        }
        
        self.high_risk_countries = [
            'AFG', 'IRN', 'PRK', 'SYR', 'MMR', 'SSD', 'VEN', 'YEM',
            'CUB', 'LBY', 'SOM', 'SDN', 'IRQ', 'ERI'
        ]
    
    def screen_user(self, user_id: int) -> AMLScreeningResult:
        """Screen user against sanctions and PEP lists."""
        from app.identity.models.user import User
        user = User.query.get(user_id)
        
        if not user:
            raise ValueError("User not found")
        
        # Create screening record
        screening = AMLScreeningResult(
            user_id=user_id,
            screening_type='user',
            screening_date=datetime.utcnow(),
            risk_level=AMLRiskLevel.MEDIUM.value,
            risk_score=0.5
        )
        
        # Perform sanctions check
        sanctions_result = self._check_sanctions(user)
        screening.sanctions_checked = True
        screening.sanctions_matches = sanctions_result
        
        # Perform PEP check
        pep_result = self._check_pep(user)
        screening.pep_checked = True
        screening.pep_matches = pep_result
        
        # Calculate overall risk
        risk_score, risk_level, risk_factors = self._calculate_user_risk(user, sanctions_result, pep_result)
        screening.risk_score = risk_score
        screening.risk_level = risk_level.value
        screening.risk_factors = risk_factors
        
        # Generate alerts
        alerts = self._generate_user_alerts(user, risk_factors)
        screening.alerts_triggered = alerts
        
        db.session.add(screening)
        db.session.commit()
        
        return screening
    
    def screen_transaction(self, user_id: int, transaction_data: Dict[str, Any]) -> AMLScreeningResult:
        """Screen transaction for AML risks."""
        screening = AMLScreeningResult(
            user_id=user_id,
            transaction_id=transaction_data.get('transaction_id'),
            screening_type='transaction',
            screening_date=datetime.utcnow(),
            risk_level=AMLRiskLevel.LOW.value,
            risk_score=0.1
        )
        
        # Check transaction amount
        amount = transaction_data.get('amount', 0)
        currency = transaction_data.get('currency', 'USD')
        amount_usd = self._convert_to_usd(amount, currency)
        
        risk_score = 0.1
        risk_factors = []
        alerts = []
        
        # Large transaction check
        if amount_usd > self.risk_thresholds['large_transaction_usd']:
            risk_score += 0.3
            risk_factors.append('large_transaction')
            alerts.append({
                'type': AMLAlertType.LARGE_TRANSACTION.value,
                'severity': 'medium',
                'details': f'Transaction amount ${amount_usd:,.2f} exceeds threshold'
            })
        
        # Check for rounding (potential structuring)
        if self._is_rounded_amount(amount):
            risk_score += 0.2
            risk_factors.append('rounding')
            alerts.append({
                'type': AMLAlertType.ROUNDING.value,
                'severity': 'low',
                'details': 'Transaction amount appears rounded'
            })
        
        # Geographic risk
        country = transaction_data.get('country')
        if country in self.high_risk_countries:
            risk_score += 0.4
            risk_factors.append('high_risk_country')
            alerts.append({
                'type': AMLAlertType.UNUSUAL_LOCATION.value,
                'severity': 'high',
                'details': f'Transaction involves high-risk country: {country}'
            })
        
        # Determine risk level
        if risk_score >= 0.8:
            risk_level = AMLRiskLevel.HIGH
        elif risk_score >= 0.5:
            risk_level = AMLRiskLevel.MEDIUM
        else:
            risk_level = AMLRiskLevel.LOW
        
        screening.risk_score = risk_score
        screening.risk_level = risk_level.value
        screening.risk_factors = risk_factors
        screening.alerts_triggered = alerts
        
        db.session.add(screening)
        db.session.commit()
        
        return screening
    
    def monitor_user_transactions(self, user_id: int, period: str = 'daily') -> AMLTransactionMonitor:
        """Monitor user transactions for AML patterns."""
        from app.wallet.models.transaction import Transaction
        
        # Calculate date range
        end_date = datetime.utcnow()
        if period == 'daily':
            start_date = end_date - timedelta(days=1)
        elif period == 'weekly':
            start_date = end_date - timedelta(weeks=1)
        elif period == 'monthly':
            start_date = end_date - timedelta(days=30)
        else:
            start_date = end_date - timedelta(days=1)
        
        # Get user transactions
        transactions = Transaction.query.filter(
            Transaction.user_id == user_id,
            Transaction.created_at >= start_date,
            Transaction.created_at <= end_date
        ).all()
        
        # Calculate statistics
        total_amount = sum(float(t.amount) for t in transactions)
        total_transactions = len(transactions)
        average_amount = total_amount / total_transactions if total_transactions > 0 else 0
        max_amount = max((float(t.amount) for t in transactions), default=0)
        
        # Create monitor record
        monitor = AMLTransactionMonitor(
            user_id=user_id,
            monitoring_date=end_date,
            period_type=period,
            total_transactions=total_transactions,
            total_amount=total_amount,
            average_amount=average_amount,
            max_amount=max_amount
        )
        
        # Risk analysis
        alerts = []
        alert_level = 'none'
        
        # High frequency check
        threshold = self.risk_thresholds[f'high_frequency_{period}']
        if total_transactions > threshold:
            monitor.high_frequency_flag = True
            alerts.append({
                'type': AMLAlertType.HIGH_FREQUENCY.value,
                'severity': 'medium',
                'details': f'{total_transactions} transactions in {period} (threshold: {threshold})'
            })
            alert_level = 'medium'
        
        # Large amount check
        threshold = self.risk_thresholds[f'{period}_transaction_limit']
        if total_amount > threshold:
            alerts.append({
                'type': AMLAlertType.LARGE_TRANSACTION.value,
                'severity': 'high',
                'details': f'Total amount ${total_amount:,.2f} exceeds threshold ${threshold:,.2f}'
            })
            alert_level = 'high'
        
        # Check for structuring (multiple similar amounts)
        if self._detect_structuring(transactions):
            monitor.structuring_flag = True
            alerts.append({
                'type': AMLAlertType.STRUCTURING.value,
                'severity': 'high',
                'details': 'Potential transaction structuring detected'
            })
            alert_level = 'high'
        
        monitor.alert_level = alert_level
        monitor.alerts_generated = alerts
        
        db.session.add(monitor)
        db.session.commit()
        
        return monitor
    
    def _check_sanctions(self, user) -> Dict[str, Any]:
        """Check user against sanctions lists."""
        # Placeholder implementation
        # In production, integrate with real sanctions databases
        # (OFAC, UN, EU, etc.)
        
        name_to_check = f"{user.first_name} {user.last_name}".lower()
        
        # Simulated sanctions check
        sanctions_list = [
            'osama bin laden',
            'al qaeda',
            'taliban',
            'isis',
            'hezbollah'
        ]
        
        matches = []
        for sanctioned_name in sanctions_list:
            if sanctioned_name in name_to_check:
                matches.append({
                    'list': 'simulated',
                    'name': sanctioned_name,
                    'confidence': 0.8
                })
        
        return {
            'screened': True,
            'matches': matches,
            'confidence': max([m['confidence'] for m in matches], default=0.0) if matches else 0.0
        }
    
    def _check_pep(self, user) -> Dict[str, Any]:
        """Check user against Politically Exposed Persons list."""
        # Placeholder implementation
        # In production, integrate with real PEP databases
        
        name_to_check = f"{user.first_name} {user.last_name}".lower()
        
        # Simulated PEP check
        pep_list = [
            'john doe president',
            'jane smith minister',
            'robert johnson ambassador'
        ]
        
        matches = []
        for pep_name in pep_list:
            if pep_name in name_to_check:
                matches.append({
                    'position': 'simulated_position',
                    'confidence': 0.7
                })
        
        return {
            'screened': True,
            'matches': matches,
            'confidence': max([m['confidence'] for m in matches], default=0.0) if matches else 0.0
        }
    
    def _calculate_user_risk(self, user, sanctions_result: Dict, pep_result: Dict) -> Tuple[float, AMLRiskLevel, List[str]]:
        """Calculate overall user risk score."""
        risk_score = 0.0
        risk_factors = []
        
        # Age risk
        if user.date_of_birth:
            age = datetime.utcnow().year - user.date_of_birth.year
            if age < 18:
                risk_score += 0.8
                risk_factors.append('under_18')
            elif age < 21:
                risk_score += 0.3
                risk_factors.append('under_21')
        
        # Country risk
        if hasattr(user, 'country') and user.country:
            if user.country in self.high_risk_countries:
                risk_score += 0.7
                risk_factors.append('high_risk_country')
        
        # Sanctions risk
        sanctions_confidence = sanctions_result.get('confidence', 0.0)
        if sanctions_confidence > 0.5:
            risk_score += sanctions_confidence
            risk_factors.append('sanctions_match')
        
        # PEP risk
        pep_confidence = pep_result.get('confidence', 0.0)
        if pep_confidence > 0.5:
            risk_score += pep_confidence * 0.6  # PEP is serious but less than sanctions
            risk_factors.append('pep_match')
        
        # Determine risk level
        if risk_score >= 0.8:
            risk_level = AMLRiskLevel.PROHIBITED
        elif risk_score >= 0.6:
            risk_level = AMLRiskLevel.HIGH
        elif risk_score >= 0.3:
            risk_level = AMLRiskLevel.MEDIUM
        else:
            risk_level = AMLRiskLevel.LOW
        
        return risk_score, risk_level, risk_factors
    
    def _generate_user_alerts(self, user, risk_factors: List[str]) -> List[Dict[str, Any]]:
        """Generate alerts based on risk factors."""
        alerts = []
        
        for factor in risk_factors:
            if factor == 'sanctions_match':
                alerts.append({
                    'type': AMLAlertType.SANCTIONS_HIT.value,
                    'severity': 'critical',
                    'details': 'User matches sanctions list'
                })
            elif factor == 'pep_match':
                alerts.append({
                    'type': AMLAlertType.PEP_MATCH.value,
                    'severity': 'high',
                    'details': 'User is a Politically Exposed Person'
                })
            elif factor == 'high_risk_country':
                alerts.append({
                    'type': AMLAlertType.UNUSUAL_LOCATION.value,
                    'severity': 'medium',
                    'details': f'User from high-risk country'
                })
        
        return alerts
    
    def _convert_to_usd(self, amount: float, currency: str) -> float:
        """Convert amount to USD (simplified)."""
        # Placeholder implementation
        # In production, use real FX rates
        conversion_rates = {
            'USD': 1.0,
            'EUR': 1.1,
            'GBP': 1.25,
            'UGX': 0.00027,
            'KES': 0.0080,
            'NGN': 0.0013,
            'ZAR': 0.055
        }
        
        return amount * conversion_rates.get(currency, 1.0)
    
    def _is_rounded_amount(self, amount: float) -> bool:
        """Check if amount is suspiciously rounded."""
        # Check if amount is a round number (no cents or minimal cents)
        cents = amount % 1
        return cents < 0.05 or cents > 0.95
    
    def _detect_structuring(self, transactions: List) -> bool:
        """Detect potential transaction structuring."""
        if len(transactions) < self.risk_thresholds['structuring_threshold']:
            return False
        
        # Check for multiple similar amounts
        amounts = [float(t.amount) for t in transactions]
        amounts.sort()
        
        # Look for amounts within 5% of each other
        for i in range(len(amounts) - self.risk_thresholds['structuring_threshold']):
            similar_count = 1
            for j in range(i + 1, len(amounts)):
                if abs(amounts[i] - amounts[j]) / amounts[i] < 0.05:
                    similar_count += 1
                else:
                    break
            
            if similar_count >= self.risk_thresholds['structuring_threshold']:
                return True
        
        return False
    
    def get_sar_eligible_transactions(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get transactions eligible for Suspicious Activity Report."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        results = AMLScreeningResult.query.filter(
            AMLScreeningResult.screening_date >= cutoff_date,
            AMLScreeningResult.risk_level.in_(['high', 'prohibited']),
            AMLScreeningResult.reviewed == False
        ).all()
        
        return [
            {
                'id': result.id,
                'user_id': result.user_id,
                'transaction_id': result.transaction_id,
                'risk_level': result.risk_level,
                'risk_score': result.risk_score,
                'alerts': result.alerts_triggered,
                'screening_date': result.screening_date
            }
            for result in results
        ]


# AML decorators
def require_aml_screening(f):
    """Decorator to require AML screening for financial operations."""
    from functools import wraps
    from flask import session, redirect, url_for, flash, request
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if user_id:
            from app.compliance.aml_service import AMLService
            
            aml_service = AMLService()
            
            # Check if user has recent screening
            recent_screening = AMLScreeningResult.query.filter_by(
                user_id=user_id,
                screening_type='user'
            ).order_by(AMLScreeningResult.screening_date.desc()).first()
            
            # Screen if no recent screening or if screening is old
            if not recent_screening or (datetime.utcnow() - recent_screening.screening_date).days > 7:
                screening = aml_service.screen_user(user_id)
                
                # Block high-risk users
                if screening.risk_level in ['high', 'prohibited']:
                    flash('Transaction blocked due to compliance requirements', 'error')
                    return redirect(url_for('wallet.dashboard'))
        
        return f(*args, **kwargs)
    
    return decorated_function
