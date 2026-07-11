"""
Placeholder routes for navigation links that haven't been implemented yet.
"""
from flask import Blueprint, render_template

placeholder_bp = Blueprint('placeholder', __name__, url_prefix='/placeholder')

@placeholder_bp.route('/coming_soon')
def coming_soon():
    return render_template('placeholder/coming_soon.html'), 200

# Add more placeholder routes as needed
@placeholder_bp.route('/profile')
def profile():
    return render_template('placeholder/coming_soon.html', page_name="Profile"), 200

@placeholder_bp.route('/trips')
def trips():
    return render_template('placeholder/coming_soon.html', page_name="Trips"), 200

@placeholder_bp.route('/stays')
def stays():
    return render_template('placeholder/coming_soon.html', page_name="Stays"), 200

@placeholder_bp.route('/account_settings')
def account_settings():
    return render_template('placeholder/coming_soon.html', page_name="Account Settings"), 200
