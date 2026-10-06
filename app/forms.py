import re
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError
from app.models.user import User


def strong_password(form, field):
    pw = field.data or ""
    problems = []
    if len(pw) < 8:
        problems.append("at least 8 characters")
    if not re.search(r"[A-Z]", pw):
        problems.append("an uppercase letter")
    if not re.search(r"[a-z]", pw):
        problems.append("a lowercase letter")
    if not re.search(r"\d", pw):
        problems.append("a digit")
    if problems:
        raise ValidationError("Password needs " + ", ".join(problems) + ".")


class SignUpForm(FlaskForm):
    full_name = StringField("Full name", validators=[DataRequired(), Length(2, 120)])
    email = StringField("Email address", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired(), strong_password])
    confirm_password = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords do not match.")],
    )
    accept_terms = BooleanField(
        "I accept the terms and conditions",
        validators=[DataRequired(message="You must accept the terms to continue.")],
    )
    submit = SubmitField("Create account")

    def validate_email(self, field):
        if User.query.filter_by(email=field.data.strip().lower()).first():
            raise ValidationError("An account with this email already exists.")


class SignInForm(FlaskForm):
    email = StringField("Email address", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember_me = BooleanField("Remember me")
    submit = SubmitField("Sign in")


class ForgotPasswordForm(FlaskForm):
    email = StringField("Email address", validators=[DataRequired(), Email()])
    submit = SubmitField("Send reset link")


class ResetPasswordForm(FlaskForm):
    password = PasswordField("New password", validators=[DataRequired(), strong_password])
    confirm_password = PasswordField(
        "Confirm new password",
        validators=[DataRequired(), EqualTo("password", message="Passwords do not match.")],
    )
    submit = SubmitField("Reset password")