"""Forms for the low-friction accommodation checkout and deferred roster."""

from flask_wtf import FlaskForm
from wtforms import DateField, IntegerField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional


class StayPartyForm(FlaskForm):
    """Step 1: stay dates and party size; never asks for guest identity."""

    booking_type = SelectField(
        choices=[('self', 'Myself'), ('third_party', 'Someone else'), ('group', 'Group')],
        validators=[DataRequired()],
    )
    check_in = DateField(validators=[DataRequired()])
    check_out = DateField(validators=[DataRequired()])
    num_guests = IntegerField(validators=[DataRequired(), NumberRange(min=1)])
    num_rooms = IntegerField(default=1, validators=[DataRequired(), NumberRange(min=1)])


class PaymentSelectionForm(FlaskForm):
    """Step 2: method and timing, checked against property policy server-side."""

    payment_method_id = StringField(validators=[DataRequired(), Length(max=100)])
    payment_timing = SelectField(choices=[], validators=[DataRequired()])


class GuestRosterEntryForm(FlaskForm):
    """Deferred guest identity collected by the booker or claim-link recipient."""

    guest_name = StringField(validators=[DataRequired(), Length(max=255)])
    guest_email = StringField(validators=[Optional(), Email(), Length(max=255)])
    guest_phone_country_code = StringField(validators=[DataRequired(), Length(min=1, max=6)])
    guest_phone_national = StringField(validators=[DataRequired(), Length(min=3, max=30)])
    id_document_type = SelectField(choices=[], validators=[Optional(), Length(max=30)])


class SpecialRequestsForm(FlaskForm):
    """Deferred stay preferences shown alongside the guest roster."""

    special_requests = TextAreaField(validators=[Optional(), Length(max=4000)])