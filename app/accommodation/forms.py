"""WTForms definitions for accommodation module."""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Sequence

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DecimalField,
    IntegerField,
    SelectField,
    StringField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class PropertyForm(FlaskForm):
    """Form used by hosts to create or edit property listings."""

    title = StringField(
        "Listing title",
        validators=[DataRequired(), Length(min=3, max=200)],
    )
    summary = TextAreaField(
        "Short summary",
        validators=[Optional(), Length(max=500)],
    )
    description = TextAreaField(
        "Full description",
        validators=[DataRequired(), Length(min=30)],
    )
    property_type = SelectField(
        "Property type",
        choices=[],
        validators=[DataRequired()],
    )

    address_line1 = StringField(
        "Address line 1",
        validators=[DataRequired(), Length(min=3, max=255)],
    )
    address_line2 = StringField(
        "Address line 2",
        validators=[Optional(), Length(max=255)],
    )
    city = StringField(
        "City",
        validators=[DataRequired(), Length(min=2, max=100)],
    )
    state = StringField(
        "State / Region",
        validators=[Optional(), Length(max=100)],
    )
    country = StringField(
        "Country code",
        validators=[DataRequired(), Length(min=2, max=2)],
    )
    postal_code = StringField(
        "Postal code",
        validators=[Optional(), Length(max=20)],
    )

    base_price_per_night = DecimalField(
        "Nightly rate",
        places=2,
        rounding=None,
        validators=[DataRequired(), NumberRange(min=0)],
    )
    currency = SelectField(
        "Currency",
        choices=[],
        validators=[DataRequired(), Length(min=3, max=3)],
    )
    cleaning_fee = DecimalField(
        "Cleaning fee",
        places=2,
        rounding=None,
        validators=[Optional(), NumberRange(min=0)],
        default=Decimal("0"),
    )
    service_fee_pct = DecimalField(
        "Service fee %",
        places=2,
        rounding=None,
        validators=[Optional(), NumberRange(min=0, max=100)],
        default=Decimal("10"),
    )

    max_guests = IntegerField(
        "Maximum guests",
        validators=[DataRequired(), NumberRange(min=1, max=50)],
        default=2,
    )
    bedrooms = IntegerField(
        "Bedrooms",
        validators=[Optional(), NumberRange(min=0, max=25)],
        default=1,
    )
    beds = IntegerField(
        "Beds",
        validators=[Optional(), NumberRange(min=0, max=30)],
        default=1,
    )
    bathrooms = DecimalField(
        "Bathrooms",
        places=1,
        rounding=None,
        validators=[Optional(), NumberRange(min=0, max=20)],
        default=Decimal("1"),
    )

    min_stay_nights = IntegerField(
        "Minimum nights",
        validators=[DataRequired(), NumberRange(min=1, max=90)],
        default=1,
    )
    max_stay_nights = IntegerField(
        "Maximum nights",
        validators=[Optional(), NumberRange(min=1, max=180)],
    )

    cancellation_policy = SelectField(
        "Cancellation policy",
        choices=[],
        validators=[DataRequired()],
    )
    check_in_time = StringField(
        "Check-in time",
        validators=[Optional(), Length(max=20)],
        default="14:00",
    )
    check_out_time = StringField(
        "Check-out time",
        validators=[Optional(), Length(max=20)],
        default="11:00",
    )

    instant_book = BooleanField("Enable instant booking")
    allow_pets = BooleanField("Pets allowed")
    allow_smoking = BooleanField("Smoking allowed")
    allow_events = BooleanField("Events allowed")

    house_rules = TextAreaField(
        "House rules",
        validators=[Optional(), Length(max=2000)],
    )
    main_image = StringField(
        "Cover image URL",
        validators=[Optional(), Length(max=500)],
    )
    gallery_urls = TextAreaField(
        "Gallery image URLs",
        description="One URL per line",
        validators=[Optional(), Length(max=4000)],
    )

    meta_title = StringField(
        "SEO title",
        validators=[Optional(), Length(max=255)],
    )
    meta_description = TextAreaField(
        "SEO description",
        validators=[Optional(), Length(max=500)],
    )

    def set_choices(
        self,
        *,
        property_types: Sequence[tuple[str, str]],
        currencies: Sequence[str],
        cancellation_policies: Sequence[tuple[str, str]],
    ) -> None:
        """Helper to populate select field choices in a single call."""

        self.property_type.choices = list(property_types)
        self.currency.choices = [(code, code) for code in currencies]
        self.cancellation_policy.choices = list(cancellation_policies)
