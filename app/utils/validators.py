#app/utils/validators.py
"""
Transport Module Validators
Data validation and sanitization for AFCON360 Transport
"""
import re
import json
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional, Tuple, Union
from decimal import Decimal, InvalidOperation
import phonenumbers
from email_validator import validate_email, EmailNotValidError
from flask import current_app

from app.utils.exceptions import ValidationError


class TransportValidators:
    """Transport-specific validation utilities"""

    # Regex patterns
    PHONE_REGEX = r'^\+?[1-9]\d{1,14}$'  # E.164 format
    LICENSE_REGEX = r'^[A-Z0-9]{6,20}$'  # Driver license format
    PLATE_REGEX = r'^[A-Z0-9\s\-]{5,15}$'  # Vehicle plate format
    VAT_REGEX = r'^[A-Z0-9]{9,15}$'  # VAT/TIN format
    COORDINATE_REGEX = r'^-?\d+(\.\d+)?$'  # Latitude/Longitude

    # Country codes for AFCON (African Cup of Nations)
    AFCON_COUNTRIES = {
        'CM', 'SN', 'NG', 'EG', 'DZ', 'MA', 'TN', 'GH', 'CI', 'ML',
        'BF', 'GN', 'RW', 'ZW', 'GA', 'CG', 'CD', 'BI', 'ET', 'KE'
    }

    @staticmethod
    def validate_driver_registration(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate driver registration data.

        Args:
            data: Driver registration data

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Required fields
        required_fields = [
            'full_name', 'license_number', 'phone_number',
            'email', 'date_of_birth', 'nationality'
        ]

        for field in required_fields:
            if field not in data or not data.get(field):
                errors.append(f"{field.replace('_', ' ').title()} is required")

        # Validate individual fields
        if 'full_name' in data and data['full_name']:
            if len(data['full_name'].strip()) < 3:
                errors.append("Full name must be at least 3 characters")

        if 'license_number' in data and data['license_number']:
            if not re.match(TransportValidators.LICENSE_REGEX, data['license_number']):
                errors.append("Invalid license number format")

        if 'phone_number' in data and data['phone_number']:
            is_valid, phone_error = TransportValidators.validate_phone(
                data['phone_number']
            )
            if not is_valid:
                errors.append(phone_error)

        if 'email' in data and data['email']:
            is_valid, email_error = TransportValidators.validate_email(
                data['email']
            )
            if not is_valid:
                errors.append(email_error)

        if 'date_of_birth' in data and data['date_of_birth']:
            is_valid, dob_error = TransportValidators.validate_date_of_birth(
                data['date_of_birth']
            )
            if not is_valid:
                errors.append(dob_error)

        if 'nationality' in data and data['nationality']:
            if data['nationality'] not in TransportValidators.AFCON_COUNTRIES:
                errors.append(f"Nationality must be an AFCON country code")

        # Optional fields validation
        if 'emergency_contact' in data and data['emergency_contact']:
            is_valid, ec_error = TransportValidators.validate_phone(
                data['emergency_contact']
            )
            if not is_valid:
                errors.append(f"Emergency contact: {ec_error}")

        if 'years_of_experience' in data and data['years_of_experience']:
            try:
                years = int(data['years_of_experience'])
                if years < 0 or years > 50:
                    errors.append("Years of experience must be between 0 and 50")
            except ValueError:
                errors.append("Years of experience must be a valid number")

        return len(errors) == 0, errors

    @staticmethod
    def validate_vehicle_registration(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate vehicle registration data.

        Args:
            data: Vehicle registration data

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Required fields
        required_fields = [
            'plate_number', 'make', 'model', 'year',
            'vehicle_class', 'capacity', 'color'
        ]

        for field in required_fields:
            if field not in data or not data.get(field):
                errors.append(f"{field.replace('_', ' ').title()} is required")

        # Validate individual fields
        if 'plate_number' in data and data['plate_number']:
            if not re.match(TransportValidators.PLATE_REGEX, data['plate_number']):
                errors.append("Invalid license plate format")

        if 'make' in data and data['make']:
            if len(data['make'].strip()) < 2:
                errors.append("Vehicle make must be at least 2 characters")

        if 'model' in data and data['model']:
            if len(data['model'].strip()) < 1:
                errors.append("Vehicle model is required")

        if 'year' in data and data['year']:
            try:
                year = int(data['year'])
                current_year = datetime.now().year
                if year < 1990 or year > current_year + 1:
                    errors.append(f"Vehicle year must be between 1990 and {current_year + 1}")
            except ValueError:
                errors.append("Vehicle year must be a valid number")

        if 'vehicle_class' in data and data['vehicle_class']:
            valid_classes = ['ECONOMY', 'COMFORT', 'PREMIUM', 'LUXURY', 'VAN', 'BUS']
            if data['vehicle_class'].upper() not in valid_classes:
                errors.append(f"Vehicle class must be one of: {', '.join(valid_classes)}")

        if 'capacity' in data and data['capacity']:
            try:
                capacity = int(data['capacity'])
                if capacity < 1 or capacity > 50:
                    errors.append("Vehicle capacity must be between 1 and 50")
            except ValueError:
                errors.append("Vehicle capacity must be a valid number")

        if 'color' in data and data['color']:
            if len(data['color'].strip()) < 3:
                errors.append("Vehicle color must be at least 3 characters")

        # Optional fields validation
        if 'vin' in data and data['vin']:
            if len(data['vin']) != 17:
                errors.append("VIN must be 17 characters")

        if 'insurance_expiry' in data and data['insurance_expiry']:
            is_valid, date_error = TransportValidators.validate_future_date(
                data['insurance_expiry']
            )
            if not is_valid:
                errors.append(f"Insurance expiry: {date_error}")

        if 'registration_expiry' in data and data['registration_expiry']:
            is_valid, date_error = TransportValidators.validate_future_date(
                data['registration_expiry']
            )
            if not is_valid:
                errors.append(f"Registration expiry: {date_error}")

        return len(errors) == 0, errors

    @staticmethod
    def validate_organisation_transport(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate organisation transport profile data.

        Args:
            data: Organisation transport data

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Required fields
        required_fields = [
            'organisation_name', 'registration_number',
            'contact_email', 'phone_number', 'country'
        ]

        for field in required_fields:
            if field not in data or not data.get(field):
                errors.append(f"{field.replace('_', ' ').title()} is required")

        # Validate individual fields
        if 'organisation_name' in data and data['organisation_name']:
            if len(data['organisation_name'].strip()) < 3:
                errors.append("Organisation name must be at least 3 characters")

        if 'registration_number' in data and data['registration_number']:
            if len(data['registration_number'].strip()) < 5:
                errors.append("Registration number must be at least 5 characters")

        if 'contact_email' in data and data['contact_email']:
            is_valid, email_error = TransportValidators.validate_email(
                data['contact_email']
            )
            if not is_valid:
                errors.append(email_error)

        if 'phone_number' in data and data['phone_number']:
            is_valid, phone_error = TransportValidators.validate_phone(
                data['phone_number']
            )
            if not is_valid:
                errors.append(phone_error)

        if 'country' in data and data['country']:
            if data['country'] not in TransportValidators.AFCON_COUNTRIES:
                errors.append(f"Country must be an AFCON country code")

        # Optional fields validation
        if 'vat_number' in data and data['vat_number']:
            if not re.match(TransportValidators.VAT_REGEX, data['vat_number']):
                errors.append("Invalid VAT/TIN format")

        if 'website' in data and data['website']:
            is_valid, url_error = TransportValidators.validate_url(
                data['website']
            )
            if not is_valid:
                errors.append(f"Website: {url_error}")

        if 'fleet_size' in data and data['fleet_size']:
            try:
                fleet_size = int(data['fleet_size'])
                if fleet_size < 1 or fleet_size > 1000:
                    errors.append("Fleet size must be between 1 and 1000")
            except ValueError:
                errors.append("Fleet size must be a valid number")

        return len(errors) == 0, errors

    @staticmethod
    def validate_booking_request(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate transport booking request.

        Args:
            data: Booking request data

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Required fields
        required_fields = [
            'pickup_location', 'dropoff_location',
            'passenger_count', 'service_type', 'preferred_vehicle_class'
        ]

        for field in required_fields:
            if field not in data or not data.get(field):
                errors.append(f"{field.replace('_', ' ').title()} is required")

        # Validate coordinates if provided
        if 'pickup_lat' in data and 'pickup_lng' in data:
            if not TransportValidators.validate_coordinates(
                    data['pickup_lat'], data['pickup_lng']
            ):
                errors.append("Invalid pickup coordinates")

        if 'dropoff_lat' in data and 'dropoff_lng' in data:
            if not TransportValidators.validate_coordinates(
                    data['dropoff_lat'], data['dropoff_lng']
            ):
                errors.append("Invalid dropoff coordinates")

        # Validate passenger count
        if 'passenger_count' in data:
            try:
                count = int(data['passenger_count'])
                if count < 1 or count > 20:
                    errors.append("Passenger count must be between 1 and 20")
            except ValueError:
                errors.append("Passenger count must be a valid number")

        # Validate service type
        valid_service_types = ['INSTANT', 'SCHEDULED', 'CHARTER', 'SHUTTLE']
        if 'service_type' in data and data['service_type']:
            if data['service_type'].upper() not in valid_service_types:
                errors.append(f"Service type must be one of: {', '.join(valid_service_types)}")

        # Validate vehicle class
        valid_classes = ['ECONOMY', 'COMFORT', 'PREMIUM', 'LUXURY', 'VAN', 'BUS']
        if 'preferred_vehicle_class' in data and data['preferred_vehicle_class']:
            if data['preferred_vehicle_class'].upper() not in valid_classes:
                errors.append(f"Vehicle class must be one of: {', '.join(valid_classes)}")

        # Validate scheduled time if provided
        if 'scheduled_time' in data and data['scheduled_time']:
            is_valid, time_error = TransportValidators.validate_future_datetime(
                data['scheduled_time']
            )
            if not is_valid:
                errors.append(f"Scheduled time: {time_error}")

        # Validate special requirements
        if 'special_requirements' in data and data['special_requirements']:
            if len(data['special_requirements']) > 500:
                errors.append("Special requirements cannot exceed 500 characters")

        return len(errors) == 0, errors

    @staticmethod
    def validate_payment(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate payment data.

        Args:
            data: Payment data

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Required fields
        required_fields = ['amount', 'currency', 'payment_method']

        for field in required_fields:
            if field not in data or not data.get(field):
                errors.append(f"{field.replace('_', ' ').title()} is required")

        # Validate amount
        if 'amount' in data and data['amount']:
            try:
                amount = Decimal(str(data['amount']))
                if amount <= 0:
                    errors.append("Amount must be greater than 0")
                if amount > Decimal('1000000'):  # 1 million limit
                    errors.append("Amount cannot exceed 1,000,000")
            except (InvalidOperation, ValueError):
                errors.append("Amount must be a valid number")

        # Validate currency
        valid_currencies = ['USD', 'EUR', 'XAF', 'XOF', 'NGN', 'GHS', 'KES', 'EGP']
        if 'currency' in data and data['currency']:
            if data['currency'].upper() not in valid_currencies:
                errors.append(f"Currency must be one of: {', '.join(valid_currencies)}")

        # Validate payment method
        valid_methods = ['CASH', 'CARD', 'MOBILE_MONEY', 'WALLET', 'VOUCHER']
        if 'payment_method' in data and data['payment_method']:
            if data['payment_method'].upper() not in valid_methods:
                errors.append(f"Payment method must be one of: {', '.join(valid_methods)}")

        return len(errors) == 0, errors

    @staticmethod
    def validate_rating(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate rating data.

        Args:
            data: Rating data

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Required fields
        required_fields = ['rating', 'booking_id']

        for field in required_fields:
            if field not in data or not data.get(field):
                errors.append(f"{field.replace('_', ' ').title()} is required")

        # Validate rating value
        if 'rating' in data and data['rating']:
            try:
                rating = float(data['rating'])
                if rating < 1 or rating > 5:
                    errors.append("Rating must be between 1 and 5")
            except ValueError:
                errors.append("Rating must be a valid number")

        # Validate comment length
        if 'comment' in data and data['comment']:
            if len(data['comment']) > 500:
                errors.append("Comment cannot exceed 500 characters")

        return len(errors) == 0, errors

    @staticmethod
    def validate_phone(phone_number: str) -> Tuple[bool, str]:
        """
        Validate phone number format.

        Args:
            phone_number: Phone number to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not phone_number:
            return False, "Phone number is required"

        # Clean phone number
        phone = re.sub(r'[^\d+]', '', phone_number)

        # Check E.164 format
        if not re.match(TransportValidators.PHONE_REGEX, phone):
            return False, "Invalid phone number format. Use international format (e.g., +1234567890)"

        # Try to parse with phonenumbers if available
        try:
            parsed = phonenumbers.parse(phone)
            if not phonenumbers.is_valid_number(parsed):
                return False, "Invalid phone number"
        except:
            # Fallback: basic validation
            if len(phone) < 10 or len(phone) > 15:
                return False, "Phone number must be 10-15 digits"

        return True, ""

    @staticmethod
    def validate_email(email: str) -> Tuple[bool, str]:
        """
        Validate email address.

        Args:
            email: Email address to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not email:
            return False, "Email is required"

        try:
            # Validate email format
            valid = validate_email(email)
            # Normalize email
            normalized_email = valid.email
            return True, ""
        except EmailNotValidError as e:
            return False, str(e)

    @staticmethod
    def validate_url(url: str) -> Tuple[bool, str]:
        """
        Validate URL format.

        Args:
            url: URL to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not url:
            return True, ""  # URL is optional

        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)

        if not url_pattern.match(url):
            return False, "Invalid URL format"

        return True, ""

    @staticmethod
    def validate_date_of_birth(dob: str) -> Tuple[bool, str]:
        """
        Validate date of birth (must be at least 18 years old).

        Args:
            dob: Date of birth string (YYYY-MM-DD)

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            birth_date = datetime.strptime(dob, '%Y-%m-%d').date()
            today = date.today()
            age = today.year - birth_date.year - (
                    (today.month, today.day) < (birth_date.month, birth_date.day)
            )

            if age < 18:
                return False, "Must be at least 18 years old"
            if age > 100:
                return False, "Invalid date of birth"

            return True, ""
        except ValueError:
            return False, "Invalid date format. Use YYYY-MM-DD"

    @staticmethod
    def validate_future_date(date_str: str) -> Tuple[bool, str]:
        """
        Validate that date is in the future.

        Args:
            date_str: Date string (YYYY-MM-DD)

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            check_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            today = date.today()

            if check_date < today:
                return False, "Date must be in the future"

            return True, ""
        except ValueError:
            return False, "Invalid date format. Use YYYY-MM-DD"

    @staticmethod
    def validate_future_datetime(datetime_str: str) -> Tuple[bool, str]:
        """
        Validate that datetime is in the future.

        Args:
            datetime_str: Datetime string (ISO format)

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            check_datetime = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
            now = datetime.now(check_datetime.tzinfo) if check_datetime.tzinfo else datetime.now()

            # Allow 5 minutes buffer for scheduling
            buffer = timedelta(minutes=5)
            if check_datetime < (now - buffer):
                return False, "Datetime must be in the future"

            # Don't allow too far in the future (1 year max)
            max_future = timedelta(days=365)
            if check_datetime > (now + max_future):
                return False, "Datetime cannot be more than 1 year in the future"

            return True, ""
        except ValueError:
            return False, "Invalid datetime format. Use ISO format (YYYY-MM-DDTHH:MM:SS)"

    @staticmethod
    def validate_coordinates(lat: Any, lng: Any) -> bool:
        """
        Validate latitude and longitude coordinates.

        Args:
            lat: Latitude
            lng: Longitude

        Returns:
            Boolean indicating if coordinates are valid
        """
        try:
            latitude = float(lat)
            longitude = float(lng)

            # Validate ranges
            if not (-90 <= latitude <= 90):
                return False
            if not (-180 <= longitude <= 180):
                return False

            # Validate format
            lat_str = str(latitude)
            lng_str = str(longitude)

            if not re.match(TransportValidators.COORDINATE_REGEX, lat_str):
                return False
            if not re.match(TransportValidators.COORDINATE_REGEX, lng_str):
                return False

            return True
        except (ValueError, TypeError):
            return False

    @staticmethod
    def validate_json(data: str) -> Tuple[bool, str]:
        """
        Validate JSON string.

        Args:
            data: JSON string to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            json.loads(data)
            return True, ""
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON: {str(e)}"

    @staticmethod
    def validate_numeric_range(value: Any, min_val: float, max_val: float) -> Tuple[bool, str]:
        """
        Validate numeric value is within range.

        Args:
            value: Value to validate
            min_val: Minimum allowed value
            max_val: Maximum allowed value

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            num = float(value)
            if min_val <= num <= max_val:
                return True, ""
            else:
                return False, f"Value must be between {min_val} and {max_val}"
        except (ValueError, TypeError):
            return False, "Value must be a valid number"


# Convenience functions
def validate_driver_registration(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Convenience wrapper for driver registration validation"""
    return TransportValidators.validate_driver_registration(data)


def validate_vehicle_registration(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Convenience wrapper for vehicle registration validation"""
    return TransportValidators.validate_vehicle_registration(data)


def validate_organisation_transport(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Convenience wrapper for organisation transport validation"""
    return TransportValidators.validate_organisation_transport(data)


def validate_booking_request(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Convenience wrapper for booking request validation"""
    return TransportValidators.validate_booking_request(data)


def validate_payment(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Convenience wrapper for payment validation"""
    return TransportValidators.validate_payment(data)


def validate_rating(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Convenience wrapper for rating validation"""
    return TransportValidators.validate_rating(data)
