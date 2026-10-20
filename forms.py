from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, DecimalField, DateField, TextAreaField, HiddenField
from wtforms.validators import DataRequired, Email, EqualTo, Regexp, Optional, NumberRange, Length

PASSWORD_REGEX = Regexp(
    r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&#^()_\-+=]).{8,}$',
    message="Password must be 8+ chars with uppercase, lowercase, digit & special character."
)


PHONE_REGEX = Regexp(
    r'^\+?[0-9\s\-]{10,20}$',
    message="Enter a valid phone number (e.g., +923001234567 or 03001234567)."
)


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])


class SignupForm(FlaskForm):
    full_name = StringField("Full Name", validators=[DataRequired(), Length(min=2, max=100)])
    phone = StringField("Phone", validators=[DataRequired(), Length(max=20), PHONE_REGEX])
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), PASSWORD_REGEX])
    confirm_password = PasswordField("Confirm Password", validators=[DataRequired(), EqualTo("password")])


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


class StaffForm(FlaskForm):
    full_name = StringField("Full Name", validators=[DataRequired(), Length(max=100)])
    phone = StringField("Phone", validators=[DataRequired(), Length(max=20)])
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), PASSWORD_REGEX])
    qualification = StringField("Qualification", validators=[DataRequired(), Length(max=120)])
    shift_timing = SelectField("Shift", choices=[("Morning", "Morning"), ("Evening", "Evening"), ("Night", "Night")])
    joining_date = DateField("Joining Date", validators=[DataRequired()])


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


class PaymentForm(FlaskForm):
    payment_method = SelectField("Payment Method", choices=[
        ("Cash_At_Counter", "Cash at Counter"), ("Card", "Card"), ("Online", "Online")
    ])


class ToggleStaffForm(FlaskForm):
    user_id = HiddenField(validators=[DataRequired()])
