"""
NIRA (National Identification and Registration Authority) verification for Uganda.
Provides National ID verification for KYC compliance.
"""

import re
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from flask import current_app

from app.audit.comprehensive_audit import AuditService, AuditSeverity


def validate_nin_format(nin: str) -> Tuple[bool, str]:
    """
    Validate Ugandan National Identification Number format.

    NIN format: CM1234567890AB (example)
    - First 2 characters: Letters (Citizenship/Military indicator)
    - Next 10 characters: Digits
    - Last 2 characters: Alphanumeric (Check digits)

    Returns: (is_valid, error_message)
    """
    if not nin:
        return False, "NIN cannot be empty"

    nin = nin.upper().strip()

    # Basic length check
    if len(nin) != 14:
        return False, f"NIN must be 14 characters, got {len(nin)}"

    # Pattern validation
    pattern = r'^[A-Z]{2}\d{10}[A-Z0-9]{2}$'
    if not re.match(pattern, nin):
        return False, "Invalid NIN format. Expected format: AA1234567890AB"

    # Check first two letters (should be valid citizenship codes)
    citizenship_codes = ['CF', 'CM', 'CI', 'CR', 'CX']  # Common codes
    if nin[:2] not in citizenship_codes:
        current_app.logger.warning(f"Unusual NIN citizenship code: {nin[:2]}")
        # Not rejecting, just warning

    return True, "Valid NIN format"


def verify_national_id(
    id_number: str,
    surname: str,
    given_names: str,
    date_of_birth: Optional[str] = None
) -> Dict[str, any]:
    """
    Verify National ID against NIRA database (placeholder for actual API integration).

    Currently implements manual verification workflow with format validation.
    In production, this would integrate with NIRA's API.

    Returns:
        {
            'verified': bool,
            'manual_review_required': bool,
            'id_number': str (masked),
            'names_match': bool or None,
            'is_valid_format': bool,
            'requires_review_by': str,
            'verification_id': str (for tracking),
            'timestamp': datetime
        }
    """
    # Validate NIN format
    is_valid_format, format_error = validate_nin_format(id_number)

    if not is_valid_format:
        return {
            'verified': False,
            'manual_review_required': False,
            'id_number': id_number[:4] + "******" + id_number[-2:] if len(id_number) >= 6 else "****",
            'names_match': None,
            'is_valid_format': False,
            'format_error': format_error,
            'requires_review_by': None,
            'verification_id': None,
            'timestamp': datetime.utcnow().isoformat()
        }

    # Log verification attempt for compliance audit
    AuditService.security(
        event_type="nira_verification_attempt",
        severity=AuditSeverity.INFO,
        description=f"NIRA verification attempt for NIN: {id_number[:4]}******",
        user_id=None,  # Will be set by caller
        ip_address=None,  # Will be set by caller
        extra_data={
            'id_number_masked': id_number[:4] + "******" + id_number[-2:],
            'surname_length': len(surname),
            'given_names_length': len(given_names),
            'has_dob': bool(date_of_birth)
        }
    )

    # Placeholder for actual NIRA API integration
    # In production, this would make an API call to NIRA

    # For now, return manual review required
    return {
        'verified': False,
        'manual_review_required': True,
        'id_number': id_number[:4] + "******" + id_number[-2:],
        'names_match': None,  # API would verify this
        'is_valid_format': True,
        'requires_review_by': 'compliance_officer',
        'verification_id': f"NIRA_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{id_number[:4]}",
        'timestamp': datetime.utcnow().isoformat(),
        'notes': 'Manual review required - NIRA API integration pending'
    }


def check_id_against_watchlist(id_number: str) -> Dict[str, any]:
    """
    Check National ID against internal watchlists (PEP, sanctions, etc.).

    Returns:
        {
            'on_watchlist': bool,
            'watchlist_type': Optional[str],
            'risk_score': int (0-100),
            'match_reason': Optional[str],
            'recommended_action': str
        }
    """
    # This would integrate with various watchlist databases
    # For now, return a placeholder

    # Simple check for test/demo purposes
    risk_score = 0
    on_watchlist = False
    watchlist_type = None

    # Check for suspicious patterns (demo only)
    suspicious_patterns = [
        ('CF', 20),  # Foreign citizens might need extra scrutiny
        ('CX', 30),  # Special cases
    ]

    for pattern, risk in suspicious_patterns:
        if id_number.startswith(pattern):
            risk_score += risk

    # Check last digits (demo pattern matching)
    if id_number[-2:] in ['99', '00', 'XX']:
        risk_score += 10
        on_watchlist = True
        watchlist_type = 'suspicious_pattern'

    # Determine recommended action
    if risk_score >= 50:
        recommended_action = 'block_and_investigate'
    elif risk_score >= 30:
        recommended_action = 'enhanced_monitoring'
    elif risk_score >= 10:
        recommended_action = 'standard_monitoring'
    else:
        recommended_action = 'no_action'

    return {
        'on_watchlist': on_watchlist,
        'watchlist_type': watchlist_type,
        'risk_score': risk_score,
        'match_reason': 'Pattern match' if on_watchlist else None,
        'recommended_action': recommended_action,
        'checked_at': datetime.utcnow().isoformat()
    }


def generate_nira_report(user_id: int, verification_data: Dict) -> Dict[str, any]:
    """
    Generate a NIRA verification report for compliance records.

    This would be stored in the database for audit purposes.
    """
    report = {
        'report_id': f"NIRA_REPORT_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{user_id}",
        'user_id': user_id,
        'verification_data': verification_data,
        'generated_at': datetime.utcnow().isoformat(),
        'report_type': 'nira_verification',
        'compliance_level': 'tier_2',  # NIRA verification enables Tier 2
        'valid_until': (datetime.utcnow() + timedelta(days=365)).isoformat(),  # 1 year validity
        'status': 'pending_review' if verification_data.get('manual_review_required') else 'completed'
    }

    # Log report generation
    AuditService.security(
        event_type="nira_report_generated",
        severity=AuditSeverity.INFO,
        description=f"NIRA verification report generated for user {user_id}",
        user_id=user_id,
        extra_data={
            'report_id': report['report_id'],
            'status': report['status'],
            'compliance_level': report['compliance_level']
        }
    )

    return report


# Helper function for KYC integration
def get_nira_verification_status(user_id: int) -> Optional[Dict]:
    """
    Check if user has completed NIRA verification.

    This would query the database for existing NIRA verification records.
    """
    # Placeholder - in production, query the database
    return None


if __name__ == "__main__":
    # Test the validation function
    test_nins = [
        "CM1234567890AB",
        "CF9876543210XY",
        "invalid",
        "AB123",
        "CM1234567890",  # Too short
        "CM1234567890123",  # Too long
    ]

    for nin in test_nins:
        is_valid, error = validate_nin_format(nin)
        print(f"{nin}: {'Valid' if is_valid else 'Invalid'} - {error}")
