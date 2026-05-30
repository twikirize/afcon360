"""
Regulatory Reporting Service
Generates Suspicious Transaction Reports (STR) and Currency Transaction Reports (CTR)
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from flask import current_app

from app.extensions import db
from app.wallet.models.transaction import TransactionModel, TransactionStatus, TransactionType
from app.wallet.models.ledger import AccountModel


@dataclass
class STRReport:
    """Suspicious Transaction Report"""
    report_id: str
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    suspicious_transactions: List[Dict[str, Any]]
    total_count: int
    total_amount: float
    report_format: str = "JSON"


@dataclass
class CTRReport:
    """Currency Transaction Report - for large cash transactions"""
    report_id: str
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    large_transactions: List[Dict[str, Any]]
    total_count: int
    total_amount: float
    threshold: float
    report_format: str = "JSON"


class RegulatoryReportingService:
    """Service for generating regulatory reports"""
    
    # CTR threshold - typically $10,000 USD or equivalent
    CTR_THRESHOLD = 10000
    
    # AML threshold for suspicious patterns
    AML_THRESHOLD = 10000
    
    @classmethod
    def generate_str_report(
        cls,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        currency: Optional[str] = None
    ) -> STRReport:
        """
        Generate Suspicious Transaction Report (STR)
        Identifies transactions with suspicious patterns
        """
        if end_date is None:
            end_date = datetime.now(timezone.utc)
        if start_date is None:
            start_date = end_date - timedelta(days=30)
        
        # Find suspicious transactions
        suspicious_txns = cls._identify_suspicious_transactions(start_date, end_date, currency)
        
        total_amount = sum(tx['amount'] for tx in suspicious_txns)
        
        report = STRReport(
            report_id=cls._generate_report_id("STR"),
            generated_at=datetime.now(timezone.utc),
            period_start=start_date,
            period_end=end_date,
            suspicious_transactions=suspicious_txns,
            total_count=len(suspicious_txns),
            total_amount=total_amount
        )
        
        current_app.logger.info(
            f"Generated STR report {report.report_id} with {report.total_count} transactions"
        )
        
        return report
    
    @classmethod
    def generate_ctr_report(
        cls,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        threshold: Optional[float] = None,
        currency: Optional[str] = None
    ) -> CTRReport:
        """
        Generate Currency Transaction Report (CTR)
        Reports large transactions above threshold
        """
        if end_date is None:
            end_date = datetime.now(timezone.utc)
        if start_date is None:
            start_date = end_date - timedelta(days=30)
        
        threshold = threshold or cls.CTR_THRESHOLD
        
        # Find large transactions
        large_txns = cls._identify_large_transactions(start_date, end_date, threshold, currency)
        
        total_amount = sum(tx['amount'] for tx in large_txns)
        
        report = CTRReport(
            report_id=cls._generate_report_id("CTR"),
            generated_at=datetime.now(timezone.utc),
            period_start=start_date,
            period_end=end_date,
            large_transactions=large_txns,
            total_count=len(large_txns),
            total_amount=total_amount,
            threshold=threshold
        )
        
        current_app.logger.info(
            f"Generated CTR report {report.report_id} with {report.total_count} transactions"
        )
        
        return report
    
    @classmethod
    def _identify_suspicious_transactions(
        cls,
        start_date: datetime,
        end_date: datetime,
        currency: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Identify transactions with suspicious patterns"""
        suspicious = []
        
        # Query completed transactions in date range
        query = TransactionModel.query.filter(
            TransactionModel.created_at >= start_date,
            TransactionModel.created_at <= end_date,
            TransactionModel.status == TransactionStatus.COMPLETED,
            TransactionModel.is_deleted == False
        )
        
        if currency:
            query = query.filter(TransactionModel.currency == currency)
        
        transactions = query.all()
        
        # Check for structuring (multiple transactions just below threshold)
        user_daily_txns = {}
        for tx in transactions:
            user_id = tx.user_id
            tx_date = tx.created_at.date()
            key = (user_id, tx_date)
            
            if key not in user_daily_txns:
                user_daily_txns[key] = []
            user_daily_txns[key].append(tx)
        
        # Identify structuring patterns
        for (user_id, tx_date), txns in user_daily_txns.items():
            total_amount = sum(tx.amount for tx in txns)
            
            # Pattern 1: Multiple transactions just below threshold
            structuring_txns = [tx for tx in txns 
                              if tx.amount >= cls.AML_THRESHOLD * 0.9 and 
                              tx.amount < cls.AML_THRESHOLD]
            
            if len(structuring_txns) >= 3:
                for tx in structuring_txns:
                    suspicious.append({
                        'transaction_id': tx.id,
                        'user_id': tx.user_id,
                        'amount': tx.amount,
                        'currency': tx.currency,
                        'type': tx.transaction_type.value if tx.transaction_type else None,
                        'created_at': tx.created_at.isoformat(),
                        'pattern': 'structuring',
                        'details': f'Part of {len(structuring_txns)} transactions near threshold',
                        'daily_total': total_amount
                    })
            
            # Pattern 2: Rapid succession transactions
            if len(txns) >= 5:
                # Sort by time and check time gaps
                sorted_txns = sorted(txns, key=lambda x: x.created_at)
                for i in range(len(sorted_txns) - 1):
                    time_gap = (sorted_txns[i + 1].created_at - sorted_txns[i].created_at).total_seconds()
                    if time_gap < 60:  # Less than 1 minute apart
                        suspicious.append({
                            'transaction_id': sorted_txns[i].id,
                            'user_id': sorted_txns[i].user_id,
                            'amount': sorted_txns[i].amount,
                            'currency': sorted_txns[i].currency,
                            'type': sorted_txns[i].transaction_type.value if sorted_txns[i].transaction_type else None,
                            'created_at': sorted_txns[i].created_at.isoformat(),
                            'pattern': 'rapid_succession',
                            'details': 'Multiple transactions in rapid succession',
                            'transactions_in_hour': len(txns)
                        })
                        break  # Only flag once per rapid succession group
        
        # Pattern 3: Large transactions above threshold
        for tx in transactions:
            if tx.amount >= cls.AML_THRESHOLD:
                suspicious.append({
                    'transaction_id': tx.id,
                    'user_id': tx.user_id,
                    'amount': tx.amount,
                    'currency': tx.currency,
                    'type': tx.transaction_type.value if tx.transaction_type else None,
                    'created_at': tx.created_at.isoformat(),
                    'pattern': 'large_transaction',
                    'details': f'Transaction above reporting threshold ({cls.AML_THRESHOLD})'
                })
        
        return suspicious
    
    @classmethod
    def _identify_large_transactions(
        cls,
        start_date: datetime,
        end_date: datetime,
        threshold: float,
        currency: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Identify transactions above CTR threshold"""
        query = TransactionModel.query.filter(
            TransactionModel.created_at >= start_date,
            TransactionModel.created_at <= end_date,
            TransactionModel.status == TransactionStatus.COMPLETED,
            TransactionModel.amount >= threshold,
            TransactionModel.is_deleted == False
        )
        
        if currency:
            query = query.filter(TransactionModel.currency == currency)
        
        transactions = query.all()
        
        return [
            {
                'transaction_id': tx.id,
                'user_id': tx.user_id,
                'amount': tx.amount,
                'currency': tx.currency,
                'type': tx.transaction_type.value if tx.transaction_type else None,
                'status': tx.status.value if tx.status else None,
                'created_at': tx.created_at.isoformat(),
                'reference': tx.reference,
                'description': tx.description
            }
            for tx in transactions
        ]
    
    @classmethod
    def _generate_report_id(cls, report_type: str) -> str:
        """Generate unique report ID"""
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
        return f"{report_type}_{timestamp}"
    
    @classmethod
    def export_report_to_dict(cls, report: Any) -> Dict[str, Any]:
        """Convert report to dictionary format for API/JSON export"""
        if isinstance(report, STRReport):
            return {
                'report_type': 'STR',
                'report_id': report.report_id,
                'generated_at': report.generated_at.isoformat(),
                'period': {
                    'start': report.period_start.isoformat(),
                    'end': report.period_end.isoformat()
                },
                'summary': {
                    'total_transactions': report.total_count,
                    'total_amount': report.total_amount
                },
                'transactions': report.suspicious_transactions
            }
        elif isinstance(report, CTRReport):
            return {
                'report_type': 'CTR',
                'report_id': report.report_id,
                'generated_at': report.generated_at.isoformat(),
                'period': {
                    'start': report.period_start.isoformat(),
                    'end': report.period_end.isoformat()
                },
                'threshold': report.threshold,
                'summary': {
                    'total_transactions': report.total_count,
                    'total_amount': report.total_amount
                },
                'transactions': report.large_transactions
            }
        else:
            raise ValueError(f"Unknown report type: {type(report)}")


# Convenience functions for easy import
def generate_str_report(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    currency: Optional[str] = None
) -> STRReport:
    """Generate Suspicious Transaction Report"""
    return RegulatoryReportingService.generate_str_report(start_date, end_date, currency)


def generate_ctr_report(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    threshold: Optional[float] = None,
    currency: Optional[str] = None
) -> CTRReport:
    """Generate Currency Transaction Report"""
    return RegulatoryReportingService.generate_ctr_report(start_date, end_date, threshold, currency)


__all__ = [
    'STRReport', 'CTRReport', 'RegulatoryReportingService',
    'generate_str_report', 'generate_ctr_report'
]
