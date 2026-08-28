"""
Policy Evaluation Layer - Bridges booking and payment state machines.

This layer evaluates whether a booking transition has prerequisites involving
payment or host approval, based on configured policies.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
from app.accommodation.models.booking import AccommodationBooking, AccommodationBookingStatus
from app.accommodation.models.booking_policy import PropertyBookingPolicy
from app.accommodation.state_machine.payment_states import PaymentState


@dataclass
class PolicyDecision:
    """Result of a policy evaluation"""
    allowed: bool
    reason: str = ""
    required_payment: Optional[Decimal] = None
    required_approval: bool = False
    missing_requirements: list = None
    
    def __post_init__(self):
        if self.missing_requirements is None:
            self.missing_requirements = []


@dataclass
class PaymentRequirement:
    """Payment requirement for a booking transition"""
    required: bool
    amount: Optional[Decimal] = None
    percentage: Optional[float] = None
    timing: Optional[str] = None  # pay_now, deposit, pay_on_arrival, etc.
    reason: str = ""


class BookingPolicyEvaluator:
    """
    Evaluates booking policy requirements for state transitions.
    
    This is the ONLY place where payment state influences booking transitions.
    The BookingStateMachine itself knows nothing about payment.
    """
    
    @staticmethod
    def can_confirm(booking: AccommodationBooking, payment_being_made: bool = False) -> PolicyDecision:
        """
        Evaluate whether a booking can be confirmed.
        
        Checks:
        1. Booking policy (host approval required, instant book, etc.)
        2. Payment policy (payment required before confirmation, deposit, etc.)
        3. Current payment state
        4. Host approval status
        
        Args:
            booking: The booking to evaluate
            payment_being_made: If True, payment is being provided as part of this confirmation
            
        Returns PolicyDecision with allowed=True/False and details.
        """
        missing = []
        
        # 1. Get property booking policy
        policy = PropertyBookingPolicy.query.filter_by(property_id=booking.property_id).first()
        if not policy:
            # No policy = use defaults (instant book, pay now allowed)
            policy = PropertyBookingPolicy(property_id=booking.property_id)
        
        # 2. Check host approval requirement
        booking_policy = getattr(booking.accommodation_property, 'booking_mode', 'instant')
        host_approval_required = (
            booking_policy == 'host_approval' or
            getattr(booking.accommodation_property, 'require_host_approval', False)
        )
        
        # Also check booking flow type (set at creation)
        flow_type = getattr(booking, 'booking_flow_type', None)
        approval_required_flows = {
            'host_approval',
            'pay_on_arrival_approval',
            'deposit_approval',
            'invoice_approval',
        }
        if flow_type in approval_required_flows:
            host_approval_required = True
        
        if host_approval_required:
            if not getattr(booking, 'host_approved_at', None):
                missing.append("Host approval required")
                return PolicyDecision(
                    allowed=False,
                    reason="Host approval required before confirmation",
                    required_approval=True,
                    missing_requirements=missing,
                )
        
        # 3. Check payment policy requirements
        payment_req = BookingPolicyEvaluator._evaluate_payment_requirement(booking, policy, payment_being_made)
        if payment_req.required:
            missing.append(payment_req.reason)
            return PolicyDecision(
                allowed=False,
                reason=payment_req.reason,
                required_payment=payment_req.amount,
                missing_requirements=missing,
            )
        
        # 4. Check if booking has expired
        if booking.expires_at:
            from datetime import datetime, timezone
            expires_at = booking.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < datetime.now(timezone.utc):
                return PolicyDecision(
                    allowed=False,
                    reason="Booking has expired",
                    missing_requirements=["Booking expired"],
                )
        
        return PolicyDecision(allowed=True, reason="All requirements satisfied")
    
    @staticmethod
    def _evaluate_payment_requirement(
        booking: AccommodationBooking,
        policy: PropertyBookingPolicy,
        payment_being_made: bool = False
    ) -> PaymentRequirement:
        """
        Evaluate payment requirement for confirmation based on payment policy.
        
        Payment policies that can gate confirmation:
        - require_payment_guarantee: wallet/card authorization required
        - allow_deposit_payment + deposit_percentage: deposit required
        - allow_pay_on_arrival only: no payment required before confirmation
        """
        payment_timing = getattr(booking, 'payment_timing', 'pay_now') or 'pay_now'
        
        # If payment is being made as part of this confirmation, skip payment requirement checks
        if payment_being_made:
            return PaymentRequirement(
                required=False,
                timing=payment_timing,
                reason="Payment being processed in this confirmation"
            )
        
        # If payment is pay_on_arrival or invoice, no upfront payment required
        if payment_timing in ('pay_on_arrival', 'invoice'):
            return PaymentRequirement(
                required=False,
                timing=payment_timing,
                reason="Payment on arrival/invoice - no upfront payment required"
            )
        
        # If payment is deposit, check deposit percentage
        if payment_timing == 'deposit':
            deposit_pct = float(policy.deposit_percentage or 0)
            if deposit_pct > 0:
                required_amount = (Decimal(str(booking.total_amount or 0)) * Decimal(str(deposit_pct))) / Decimal('100')
                amount_paid = Decimal(str(getattr(booking, 'amount_paid', 0) or 0))
                if amount_paid < required_amount:
                    return PaymentRequirement(
                        required=True,
                        amount=required_amount,
                        percentage=deposit_pct,
                        timing='deposit',
                        reason=f"Deposit of {deposit_pct}% ({required_amount}) required before confirmation"
                    )
            return PaymentRequirement(
                required=False,
                timing='deposit',
                reason="Deposit amount satisfied or no deposit required"
            )
        
        # For pay_now, check if payment guarantee is required
        if payment_timing == 'pay_now':
            if policy.require_payment_guarantee:
                # Need wallet balance authorization or card authorization
                if not getattr(booking, 'payment_guaranteed', False):
                    return PaymentRequirement(
                        required=True,
                        amount=Decimal(str(booking.total_amount or 0)),
                        timing='pay_now',
                        reason="Payment guarantee required before confirmation"
                    )
            # Even without guarantee, check if payment was actually made
            payment_state = PaymentState(getattr(booking, 'payment_status', 'unpaid'))
            if payment_state not in (PaymentState.PAID, PaymentState.PARTIALLY_PAID):
                return PaymentRequirement(
                    required=True,
                    amount=Decimal(str(booking.total_amount or 0)),
                    timing='pay_now',
                    reason="Full payment required before confirmation"
                )
        
        return PaymentRequirement(
            required=False,
            timing=payment_timing,
            reason="Payment requirement satisfied"
        )
    
    @staticmethod
    def can_check_in(booking: AccommodationBooking) -> PolicyDecision:
        """
        Evaluate whether a booking can be checked in.
        
        Payment is NOT universally required for check-in.
        Only required if payment policy explicitly requires it.
        """
        missing = []
        
        # Basic booking state checks (also done in BookingStateMachine)
        if booking.status != AccommodationBookingStatus.CONFIRMED.value:
            return PolicyDecision(
                allowed=False,
                reason=f"Booking must be confirmed (currently {booking.status})",
                missing_requirements=["Booking not confirmed"],
            )
        
        from datetime import date
        if booking.check_in > date.today():
            return PolicyDecision(
                allowed=False,
                reason=f"Check-in date is {booking.check_in} - too early",
                missing_requirements=["Check-in date not reached"],
            )
        
        # Registration check
        from app.accommodation.state_machine.booking_states import BookingStateMachine
        if not BookingStateMachine._registration_satisfied(booking):
            missing.append("Guest registration incomplete")
        
        # Payment policy check for check-in
        policy = PropertyBookingPolicy.query.filter_by(property_id=booking.property_id).first()
        payment_timing = getattr(booking, 'payment_timing', 'pay_now') or 'pay_now'
        
        # If payment policy requires payment before check-in
        if policy and policy.require_payment_guarantee and payment_timing == 'pay_now':
            payment_state = PaymentState(getattr(booking, 'payment_status', 'unpaid'))
            if payment_state not in (PaymentState.PAID, PaymentState.PARTIALLY_PAID):
                # Check cash eligibility for pay-on-arrival
                if payment_timing != 'pay_on_arrival':
                    missing.append("Payment required before check-in per property policy")
        
        if missing:
            return PolicyDecision(
                allowed=False,
                reason="; ".join(missing),
                missing_requirements=missing,
            )
        
        return PolicyDecision(allowed=True, reason="Check-in allowed")
    
    @staticmethod
    def get_booking_requirements(booking: AccommodationBooking) -> dict:
        """
        Get all requirements for a booking's current state.
        
        Returns a comprehensive view for frontend display.
        """
        policy = PropertyBookingPolicy.query.filter_by(property_id=booking.property_id).first()
        if not policy:
            policy = PropertyBookingPolicy(property_id=booking.property_id)
        
        payment_timing = getattr(booking, 'payment_timing', 'pay_now') or 'pay_now'
        payment_state = PaymentState(getattr(booking, 'payment_status', 'unpaid'))
        
        return {
            "booking_status": booking.status,
            "payment_status": payment_state.value,
            "payment_timing": payment_timing,
            "booking_policy": {
                "confirmation_mode": "host_approval" if getattr(booking.accommodation_property, 'booking_mode', 'instant') == 'host_approval' else "automatic",
                "host_approval_required": getattr(booking.accommodation_property, 'require_host_approval', False),
                "host_approved": bool(getattr(booking, 'host_approved_at', None)),
            },
            "payment_policy": {
                "requires_payment_before_confirmation": policy.require_payment_guarantee and payment_timing == 'pay_now',
                "requires_deposit_before_confirmation": payment_timing == 'deposit' and float(policy.deposit_percentage or 0) > 0,
                "required_deposit_amount": (Decimal(str(booking.total_amount or 0)) * Decimal(str(policy.deposit_percentage or 0))) / Decimal('100') if payment_timing == 'deposit' else Decimal('0'),
                "requires_payment_before_checkin": policy.require_payment_guarantee and payment_timing == 'pay_now',
                "allow_pay_on_arrival": policy.allow_pay_on_arrival,
            },
            "financial_summary": {
                "total_amount": Decimal(str(booking.total_amount or 0)),
                "amount_paid": Decimal(str(getattr(booking, 'amount_paid', 0) or 0)),
                "amount_due": Decimal(str(getattr(booking, 'amount_due', 0) or 0)),
                "deposit_amount": Decimal(str(getattr(booking, 'deposit_amount', 0) or 0)),
            },
            "can_confirm": BookingPolicyEvaluator.can_confirm(booking).__dict__,
            "can_check_in": BookingPolicyEvaluator.can_check_in(booking).__dict__,
        }


class PaymentPolicyEvaluator:
    """
    Evaluates payment policy requirements independently.
    """
    
    @staticmethod
    def get_required_payment_for_confirmation(booking: AccommodationBooking) -> PaymentRequirement:
        """Get payment requirement for booking confirmation"""
        policy = PropertyBookingPolicy.query.filter_by(property_id=booking.property_id).first()
        if not policy:
            policy = PropertyBookingPolicy(property_id=booking.property_id)
        return BookingPolicyEvaluator._evaluate_payment_requirement(booking, policy)
    
    @staticmethod
    def get_allowed_payment_timings(property_id: int) -> list:
        """Get allowed payment timings for a property"""
        policy = PropertyBookingPolicy.query.filter_by(property_id=property_id).first()
        if not policy:
            return ['pay_now', 'pay_on_arrival', 'deposit', 'invoice']
        
        timings = []
        if policy.allow_pay_now:
            timings.append('pay_now')
        if policy.allow_pay_on_arrival:
            timings.append('pay_on_arrival')
        if policy.allow_deposit_payment:
            timings.append('deposit')
        timings.append('invoice')  # Always available as fallback
        return timings
    
    @staticmethod
    def calculate_deposit_amount(booking: AccommodationBooking) -> Decimal:
        """Calculate required deposit amount"""
        policy = PropertyBookingPolicy.query.filter_by(property_id=booking.property_id).first()
        if not policy or not policy.deposit_percentage:
            return Decimal('0')
        return (Decimal(str(booking.total_amount or 0)) * Decimal(str(policy.deposit_percentage))) / Decimal('100')