from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from app.events.services import EventService
from app.wallet.services import WalletService
import datetime

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route("/dashboard")
@login_required
def unified_dashboard():
    """Unified user dashboard showing all user activities"""
    try:
        # Get current date for filtering
        current_date = datetime.date.today().isoformat()
        
        # Get user's event registrations
        registrations = []
        try:
            # This would need to be implemented in EventService
            from app.events.models import EventRegistration
            user_registrations = EventRegistration.query.filter_by(user_id=current_user.id).all()
            for reg in user_registrations:
                registrations.append({
                    'event': {
                        'name': reg.event.name,
                        'start_date': reg.event.start_date.isoformat() if reg.event.start_date else None,
                        'city': reg.event.city,
                        'venue': reg.event.venue,
                        'slug': reg.event.slug
                    },
                    'status': reg.status,
                    'ticket_type': reg.ticket_type or 'General',
                    'registration_ref': reg.registration_ref
                })
        except Exception as e:
            print(f"Error fetching registrations: {e}")
        
        # Get wallet information
        wallet_balance = "0.00"
        wallet_currency = "UGX"
        wallet_transactions = []
        try:
            wallet = WalletService.get_user_wallet(current_user.id)
            if wallet:
                wallet_balance = str(wallet.balance)
                wallet_currency = wallet.currency
                
                # Get recent transactions
                transactions = WalletService.get_recent_transactions(current_user.id, limit=10)
                for tx in transactions:
                    wallet_transactions.append({
                        'type': 'credit' if tx.amount > 0 else 'debit',
                        'description': tx.description or 'Transaction',
                        'reference': tx.reference or tx.id,
                        'amount': f"{abs(tx.amount):.2f} {wallet_currency}",
                        'date': tx.created_at.strftime('%Y-%m-%d') if tx.created_at else 'Unknown',
                        'icon': 'fa-arrow-down' if tx.amount > 0 else 'fa-arrow-up'
                    })
        except Exception as e:
            print(f"Error fetching wallet data: {e}")
        
        # Calculate stats
        upcoming_events_count = len([r for r in registrations if r['event']['start_date'] and r['event']['start_date'] >= current_date])
        events_change = "+0%"  # This would be calculated based on historical data
        
        # Mock data for other sections (to be implemented)
        bookings_count = 0
        bookings_change = "+0%"
        transport_count = 0
        transport_change = "+0%"
        transactions_count = len(wallet_transactions)
        
        # Recent activities (combine all user activities)
        recent_activities = []
        
        # Add event registrations to recent activities
        for reg in registrations[:5]:
            recent_activities.append({
                'type': 'credit',
                'title': f"Registered for {reg['event']['name']}",
                'description': f"Ticket: {reg['ticket_type']}",
                'amount': "Event Registration",
                'date': reg['event']['start_date'][:10] if reg['event']['start_date'] else 'Unknown',
                'icon': 'fa-calendar-check'
            })
        
        # Add wallet transactions to recent activities
        for tx in wallet_transactions[:3]:
            recent_activities.append({
                'type': tx['type'],
                'title': tx['description'],
                'description': tx['reference'],
                'amount': tx['amount'],
                'date': tx['date'],
                'icon': tx['icon']
            })
        
        # Sort recent activities by date (most recent first)
        recent_activities.sort(key=lambda x: x['date'], reverse=True)
        
        return render_template('dashboard/unified_dashboard.html',
            # User info
            user=current_user,
            
            # Stats
            upcoming_events_count=upcoming_events_count,
            events_change=events_change,
            wallet_balance=wallet_balance,
            wallet_change="+0%",  # Would calculate based on historical data
            bookings_count=bookings_count,
            bookings_change=bookings_change,
            transport_count=transport_count,
            transport_change=transport_change,
            
            # Event data
            registrations=registrations,
            
            # Wallet data
            wallet_balance=wallet_balance,
            wallet_currency=wallet_currency,
            wallet_transactions=wallet_transactions,
            transactions_count=transactions_count,
            
            # Recent activities
            recent_activities=recent_activities[:10]
        )
        
    except Exception as e:
        # Log error and show basic dashboard
        print(f"Dashboard error: {e}")
        return render_template('dashboard/unified_dashboard.html',
            user=current_user,
            upcoming_events_count=0,
            events_change="+0%",
            wallet_balance="0.00",
            wallet_change="+0%",
            bookings_count=0,
            bookings_change="+0%",
            transport_count=0,
            transport_change="+0%",
            registrations=[],
            wallet_transactions=[],
            transactions_count=0,
            recent_activities=[]
        )
