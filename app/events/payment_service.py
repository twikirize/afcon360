# app/events/services/payment_service.py
"""
Event Payment Service - Integration with wallet and mobile money systems
"""
from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict, Optional, List
from flask import current_app, request

from app.wallet.services.wallet_service import WalletService
from app.wallet.payments.mobile_money import MobileMoneyService
from app.audit.comprehensive_audit import AuditService, TransactionType, APICallStatus, AuditSeverity
from app.events.models import Event, TicketType, EventRegistration
from app.events.payment_config import PaymentMethodConfig, EventPaymentPreference
from app.extensions import db
import uuid
import logging

logger = logging.getLogger(__name__)


class EventPaymentService:
    """Payment service for event ticket purchases"""
    
    def __init__(self):
        self.wallet_service = WalletService()
        
    def process_ticket_purchase(
        self,
        user_id: int,
        event_id: int,
        ticket_type_id: int,
        quantity: int = 1,
        payment_method: str = "wallet",
        mobile_money_operator: Optional[str] = None,
        mobile_money_phone: Optional[str] = None,
        group_attendees: Optional[List[Dict]] = None
    ) -> Dict:
        """
        Process ticket purchase with payment integration
        """
        try:
            # Get event and ticket type
            event = Event.query.get(event_id)
            ticket_type = TicketType.query.get(ticket_type_id)
            
            if not event or not ticket_type:
                return {"success": False, "error": "Event or ticket type not found"}
            
            if ticket_type.event_id != event_id:
                return {"success": False, "error": "Ticket type doesn't belong to this event"}
            
            # Calculate total price
            unit_price = Decimal(str(ticket_type.price))
            total_price = unit_price * quantity
            
            # Create audit transaction ID
            audit_transaction_id = f"TKT-{uuid.uuid4().hex[:12].upper()}"
            
            # Check capacity
            if ticket_type.capacity and ticket_type.capacity > 0:
                available = ticket_type.capacity - ticket_type.available_seats
                if available < quantity:
                    return {"success": False, "error": f"Only {available} tickets available"}
            
            # Process payment based on method
            payment_result = None
            if payment_method == "wallet":
                payment_result = self._process_wallet_payment(
                    user_id, total_price, event.currency, audit_transaction_id
                )
            elif payment_method == "mobile_money":
                if not mobile_money_operator or not mobile_money_phone:
                    return {"success": False, "error": "Mobile money operator and phone required"}
                payment_result = self._process_mobile_money_payment(
                    user_id, total_price, event.currency, mobile_money_operator, 
                    mobile_money_phone, audit_transaction_id
                )
            else:
                return {"success": False, "error": "Unsupported payment method"}
            
            if not payment_result.get("success"):
                return payment_result
            
            # Create registrations
            registrations = self._create_registrations(
                user_id, event_id, ticket_type_id, quantity, 
                payment_result.get("payment_reference"), group_attendees
            )
            
            # Update ticket type capacity
            if ticket_type.capacity and ticket_type.capacity > 0:
                for _ in range(quantity):
                    ticket_type.reserve_seat()
            
            db.session.commit()
            
            return {
                "success": True,
                "registrations": registrations,
                "payment_reference": payment_result.get("payment_reference"),
                "total_paid": float(total_price),
                "audit_transaction_id": audit_transaction_id
            }
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error processing ticket purchase: {e}")
            return {"success": False, "error": str(e)}
    
    def _process_wallet_payment(
        self, 
        user_id: int, 
        amount: Decimal, 
        currency: str, 
        audit_transaction_id: str
    ) -> Dict:
        """Process payment using wallet system"""
        try:
            # Get user's wallet for the currency
            wallet = self.wallet_service.get_user_wallet(user_id, currency)
            if not wallet:
                return {"success": False, "error": f"No wallet found for {currency}"}
            
            # Check balance
            if wallet.balance < amount:
                return {"success": False, "error": "Insufficient wallet balance"}
            
            # Process wallet payment
            payment_reference = f"WALLET-{uuid.uuid4().hex[:12].upper()}"
            
            # Create audit record
            AuditService.financial(
                transaction_id=audit_transaction_id,
                transaction_type=TransactionType.PAYMENT,
                amount=amount,
                currency=currency,
                status="pending",
                from_user_id=user_id,
                from_balance_before=float(wallet.balance),
                payment_method="wallet",
                payment_provider="afcon360_wallet",
                ip_address=request.remote_addr if request else None,
                user_agent=request.user_agent.string if request else None,
                metadata={
                    "payment_reference": payment_reference,
                    "purpose": "event_ticket_purchase"
                }
            )
            
            # Debit wallet
            debit_result = self.wallet_service.debit_wallet(
                user_id, amount, currency, 
                f"Event ticket purchase - {payment_reference}",
                metadata={"event_ticket_purchase": True, "reference": payment_reference}
            )
            
            if not debit_result.get("success"):
                # Update audit as failed
                AuditService.financial(
                    transaction_id=audit_transaction_id,
                    transaction_type=TransactionType.PAYMENT,
                    amount=amount,
                    currency=currency,
                    status="failed",
                    from_user_id=user_id,
                    from_balance_before=float(wallet.balance),
                    payment_method="wallet",
                    payment_provider="afcon360_wallet",
                    ip_address=request.remote_addr if request else None,
                    user_agent=request.user_agent.string if request else None,
                    metadata={"error": debit_result.get("error")}
                )
                return debit_result
            
            # Update audit as completed
            AuditService.financial(
                transaction_id=audit_transaction_id,
                transaction_type=TransactionType.PAYMENT,
                amount=amount,
                currency=currency,
                status="completed",
                from_user_id=user_id,
                from_balance_before=float(wallet.balance),
                from_balance_after=float(wallet.balance - amount),
                payment_method="wallet",
                payment_provider="afcon360_wallet",
                ip_address=request.remote_addr if request else None,
                user_agent=request.user_agent.string if request else None,
                metadata={"payment_reference": payment_reference}
            )
            
            return {
                "success": True,
                "payment_reference": payment_reference,
                "amount": float(amount)
            }
            
        except Exception as e:
            logger.error(f"Wallet payment error: {e}")
            return {"success": False, "error": str(e)}
    
    def _process_mobile_money_payment(
        self,
        user_id: int,
        amount: Decimal,
        currency: str,
        operator: str,
        phone: str,
        audit_transaction_id: str
    ) -> Dict:
        """Process payment using mobile money"""
        try:
            # Determine country based on currency
            country = self._get_country_from_currency(currency)
            if not country:
                return {"success": False, "error": "Unsupported currency for mobile money"}
            
            # Initialize mobile money service
            mobile_service = MobileMoneyService(operator, country)
            
            # Process mobile money deposit
            deposit_result = mobile_service.process_deposit(
                user_id, amount, currency, phone, audit_transaction_id
            )
            
            if deposit_result.get("success"):
                return {
                    "success": True,
                    "payment_reference": deposit_result.get("provider_reference"),
                    "amount": float(amount)
                }
            else:
                return deposit_result
                
        except Exception as e:
            logger.error(f"Mobile money payment error: {e}")
            return {"success": False, "error": str(e)}
    
    def _get_country_from_currency(self, currency: str) -> Optional[str]:
        """Map currency to country for mobile money"""
        currency_country_map = {
            "UGX": "UG",
            "KES": "KE", 
            "NGN": "NG"
        }
        return currency_country_map.get(currency.upper())
    
    def _create_registrations(
        self,
        user_id: int,
        event_id: int,
        ticket_type_id: int,
        quantity: int,
        payment_reference: str,
        group_attendees: Optional[List[Dict]] = None
    ) -> List[Dict]:
        """Create event registrations"""
        registrations = []
        
        # Primary registrant
        primary_registration = self._create_single_registration(
            user_id, event_id, ticket_type_id, payment_reference
        )
        registrations.append(primary_registration)
        
        # Group attendees
        if group_attendees:
            for attendee_data in group_attendees:
                # Create or find user for attendee
                attendee_user_id = self._get_or_create_attendee_user(attendee_data)
                
                registration = self._create_single_registration(
                    attendee_user_id, event_id, ticket_type_id, payment_reference,
                    attendee_data
                )
                registrations.append(registration)
        
        return registrations
    
    def _create_single_registration(
        self,
        user_id: int,
        event_id: int,
        ticket_type_id: int,
        payment_reference: str,
        attendee_data: Optional[Dict] = None
    ) -> Dict:
        """Create a single event registration"""
        registration = EventRegistration(
            event_id=event_id,
            ticket_type_id=ticket_type_id,
            user_id=user_id,
            full_name=attendee_data.get("name") if attendee_data else None,
            email=attendee_data.get("email") if attendee_data else None,
            phone=attendee_data.get("phone") if attendee_data else None,
            nationality=attendee_data.get("nationality") if attendee_data else None,
            payment_status="paid",
            status="confirmed",
            registration_fee=0, # Handled by ticket type price
            payment_reference=payment_reference
        )
        
        # Generate references
        registration.generate_refs()
        
        db.session.add(registration)
        db.session.flush()  # Get the ID
        
        return {
            "id": registration.id,
            "registration_ref": registration.registration_ref,
            "ticket_number": registration.ticket_number,
            "qr_token": registration.qr_token
        }
    
    def _get_or_create_attendee_user(self, attendee_data: Dict) -> int:
        """Get or create user for group attendee"""
        # This is a simplified implementation
        # In production, you'd want proper user creation logic
        from app.models.user import User
        
        email = attendee_data.get("email")
        if email:
            user = User.query.filter_by(email=email).first()
            if user:
                return user.id
        
        # Create a temporary user record or use the primary user's ID
        # For now, return the primary user's ID (this needs proper implementation)
        return attendee_data.get("primary_user_id", 1)
    
    def get_available_payment_methods(self, event_currency: str, event_id: Optional[int] = None) -> List[Dict]:
        """Get available payment methods for an event based on admin configuration"""
        methods = []
        
        # Get event payment preferences if event_id is provided
        event_preference = None
        if event_id:
            event_preference = EventPaymentPreference.query.filter_by(event_id=event_id).first()
        
        # Get all available payment methods from admin configuration
        configured_methods = PaymentMethodConfig.get_available_methods(event_currency)
        
        for method in configured_methods:
            # Check if event owner accepts this method
            if event_preference and not event_preference.accepts_method(method.method_id):
                continue
            
            method_dict = {
                "id": method.method_id,
                "name": method.display_name,
                "description": f"Pay with {method.display_name}",
                "icon": self._get_method_icon(method.method_type),
                "available": method.is_available,
                "min_amount": float(method.min_amount),
                "max_amount": float(method.max_amount),
                "transaction_fee": method.calculate_fee(1.0)  # Fee percentage
            }
            
            # Add mobile money specific details
            if method.method_type == "mobile_money":
                method_dict.update({
                    "operator": method.provider_name,
                    "country": method.country_code,
                    "requires_phone": method.requires_phone
                })
            
            # Add disabled reason if not available
            if not method.is_available:
                if not method.is_enabled:
                    method_dict["disabled_reason"] = "Payment method disabled by administrator"
                elif not method.is_active:
                    method_dict["disabled_reason"] = "Payment method not active"
                elif not method.supports_currency(event_currency):
                    method_dict["disabled_reason"] = f"Does not support {event_currency}"
                else:
                    method_dict["disabled_reason"] = "Payment method unavailable"
            
            methods.append(method_dict)
        
        # Add card payment (placeholder for future implementation)
        methods.append({
            "id": "card",
            "name": "Credit/Debit Card",
            "description": "Pay with credit or debit card",
            "icon": "💳",
            "available": False,  # Not implemented yet
            "disabled_reason": "Card payments coming soon"
        })
        
        return methods
    
    def _get_method_icon(self, method_type: str) -> str:
        """Get appropriate icon for payment method type"""
        icon_map = {
            "wallet": "💳",
            "mobile_money": "📱",
            "card": "💳",
            "bank_transfer": "🏦"
        }
        return icon_map.get(method_type, "💳")
