from datetime import datetime, timezone, timedelta, date
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, DecimalField, DateField, TextAreaField, HiddenField
from wtforms.validators import DataRequired, Email, EqualTo, Regexp, Optional, NumberRange, Length, ValidationError

PKT = timezone(timedelta(hours=5))

PASSWORD_REGEX = Regexp(
    r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&#^()_\-+=]).{8,128}$',
    message="Password must be 8-128 chars with uppercase, lowercase, digit & special character."
)

PHONE_REGEX = Regexp(
    r'^\+?[0-9\s\-]{10,20}$',
    message="Enter a valid phone number (e.g., +923001234567 or 03001234567)."
)

COMMON_PASSWORDS = {
    "password", "password123", "password@123", "p@ssword", "p@ssword123",
    "admin123", "welcome123", "welcome@123", "12345678", "medlab123",
    "medlab@123", "testing123", "secret123", "letmein123"
}


def _check_password_security(password_val, email_val=None):
    if not password_val:
        return
    if password_val.lower() in COMMON_PASSWORDS:
        raise ValidationError("This password is on the common password blocklist. Please choose a stronger password.")
    if email_val and "@" in email_val:
        local_part = email_val.split("@")[0].strip().lower()
        if len(local_part) >= 3 and local_part in password_val.lower():
            raise ValidationError("Password cannot contain your email address prefix.")


class LoginForm(FlaskForm):
    email = StringField("Email or Username", validators=[DataRequired(), Length(max=120)])
    password = PasswordField("Password", validators=[DataRequired(), Length(max=128)])


class SignupForm(FlaskForm):
    full_name = StringField("Full Name", validators=[DataRequired(), Length(min=2, max=100)])
    phone = StringField("Phone", validators=[DataRequired(), Length(max=20), PHONE_REGEX])
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, max=128), PASSWORD_REGEX])
    confirm_password = PasswordField("Confirm Password", validators=[DataRequired(), EqualTo("password")])

    def validate_password(self, field):
        _check_password_security(field.data, self.email.data)


class CompleteProfilePhoneForm(FlaskForm):
    phone = StringField("Phone", validators=[DataRequired(), Length(max=20), PHONE_REGEX])


class ForgotPasswordForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])


class ProfileForm(FlaskForm):
    full_name = StringField("Full Name", validators=[DataRequired(), Length(max=100)])


class PatientProfileForm(FlaskForm):
    full_name = StringField("Full Name", validators=[DataRequired(), Length(max=100)])
    date_of_birth = DateField("Date of Birth", validators=[Optional()])
    gender = SelectField("Gender", choices=[("", "Select..."), ("Male", "Male"), ("Female", "Female"), ("Other", "Other")], validators=[Optional()])
    blood_group = SelectField("Blood Group", choices=[
        ("", "Select..."), ("A+", "A+"), ("A-", "A-"), ("B+", "B+"), ("B-", "B-"),
        ("AB+", "AB+"), ("AB-", "AB-"), ("O+", "O+"), ("O-", "O-")
    ], validators=[Optional()])
    address = TextAreaField("Address", validators=[Optional(), Length(max=255)])

    def validate_date_of_birth(self, field):
        if field.data:
            today_pkt = datetime.now(PKT).date()
            if field.data > today_pkt:
                raise ValidationError("Date of birth cannot be in the future.")
            if field.data < date(1900, 1, 1):
                raise ValidationError("Date of birth cannot be earlier than 1900.")


class StaffForm(FlaskForm):
    full_name = StringField("Full Name", validators=[DataRequired(), Length(max=100)])
    phone = StringField("Phone", validators=[DataRequired(), Length(max=20), PHONE_REGEX])
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, max=128), PASSWORD_REGEX])
    qualification = StringField("Qualification", validators=[DataRequired(), Length(max=120)])
    shift_timing = SelectField("Shift", choices=[("Morning", "Morning"), ("Evening", "Evening"), ("Night", "Night")])
    joining_date = DateField("Joining Date", validators=[DataRequired()])

    def validate_password(self, field):
        _check_password_security(field.data, self.email.data)


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current Password", validators=[DataRequired()])
    new_password = PasswordField("New Password", validators=[DataRequired(), Length(min=8, max=128), PASSWORD_REGEX])
    confirm_password = PasswordField("Confirm New Password", validators=[DataRequired(), EqualTo("new_password")])

    def validate_new_password(self, field):
        _check_password_security(field.data)


class AddTestForm(FlaskForm):
    category_id = SelectField("Category", coerce=int, validators=[DataRequired()])
    test_code = StringField("Test Code", validators=[DataRequired(), Length(max=20)])
    test_name = StringField("Test Name", validators=[DataRequired(), Length(max=120)])
    sample_type = SelectField("Sample Type", choices=[
        ("Blood (EDTA)", "Blood (EDTA)"), ("Blood (Serum)", "Blood (Serum)"),
        ("Fasting Blood", "Fasting Blood"), ("Urine", "Urine"), ("Swab", "Swab")
    ])
    price = DecimalField("Price (PKR)", validators=[DataRequired(), NumberRange(min=0)])
    turnaround_hours = DecimalField("Turnaround (hrs)", validators=[DataRequired(), NumberRange(min=1)])
    pre_test_instructions = TextAreaField("Instructions", validators=[Optional()])


class AddParamForm(FlaskForm):
    test_id = SelectField("Test", coerce=int, validators=[DataRequired()])
    param_name = StringField("Parameter Name", validators=[DataRequired(), Length(max=100)])
    unit = StringField("Unit", validators=[DataRequired(), Length(max=30)])
    min_range = DecimalField("Min Range", validators=[DataRequired()])
    max_range = DecimalField("Max Range", validators=[DataRequired()])
    display_order = DecimalField("Order", validators=[Optional(), NumberRange(min=1)])


class BookTestForm(FlaskForm):
    appointment_date = DateField("Appointment Date", validators=[DataRequired()])
    appointment_slot = SelectField("Time Slot", choices=[
        ("08:00 AM - 10:00 AM", "08:00 AM – 10:00 AM"),
        ("10:00 AM - 12:00 PM", "10:00 AM – 12:00 PM"),
        ("02:00 PM - 04:00 PM", "02:00 PM – 04:00 PM"),
        ("04:00 PM - 06:00 PM", "04:00 PM – 06:00 PM"),
    ])

    def validate_appointment_date(self, field):
        if field.data:
            today_pkt = datetime.now(PKT).date()
            if field.data < today_pkt:
                raise ValidationError("Appointment date cannot be in the past. Please select today or a future date.")


class PaymentForm(FlaskForm):
    payment_method = SelectField("Payment Method", choices=[
        ("Cash_At_Counter", "Cash at Counter"), ("Card", "Card"), ("Online", "Online")
    ])


class ToggleStaffForm(FlaskForm):
    user_id = HiddenField(validators=[DataRequired()])
