from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, current_app)
from flask_login import login_user, logout_user, login_required, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.extensions import db, limiter
from app.forms import SignUpForm, SignInForm, ForgotPasswordForm, ResetPasswordForm
from app.models.user import User

auth_bp = Blueprint("auth", __name__)


def _is_safe_next(target: str) -> bool:
    """Prevent open-redirect via ?next="""
    if not target:
        return False
    parsed = urlparse(target)
    return parsed.scheme == "" and parsed.netloc == "" and target.startswith("/")


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="password-reset")


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    form = SignUpForm()
    if form.validate_on_submit():
        user = User(full_name=form.full_name.data.strip(),
                    email=form.email.data.strip().lower())
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash("Account created successfully. Please sign in.", "success")
        return redirect(url_for("auth.signin"))
    return render_template("signup.html", form=form)


@auth_bp.route("/signin", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def signin():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    form = SignInForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.strip().lower()).first()
        # Same message for unknown email / wrong password (no account enumeration)
        if user is None or not user.check_password(form.password.data) or not user.is_active:
            flash("Invalid email or password.", "danger")
            return render_template("signin.html", form=form), 401
        login_user(user, remember=form.remember_me.data)
        user.last_login_at = datetime.now(timezone.utc)
        db.session.commit()
        next_url = request.args.get("next")
        return redirect(next_url if _is_safe_next(next_url) else url_for("main.dashboard"))
    return render_template("signin.html", form=form)


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("main.index"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.strip().lower()).first()
        if user:
            token = _serializer().dumps(user.id)
            link = url_for("auth.reset_password", token=token, _external=True)
            # No SMTP configured yet: log the link in development.
            # In production, plug an email provider in here.
            current_app.logger.info("Password reset link for %s: %s", user.email, link)
        flash("If an account exists for that email, a reset link has been sent.", "info")
        return redirect(url_for("auth.signin"))
    return render_template("forgot_password.html", form=form)


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        user_id = _serializer().loads(
            token, max_age=current_app.config["PASSWORD_RESET_MAX_AGE"])
    except (SignatureExpired, BadSignature):
        flash("That reset link is invalid or has expired.", "danger")
        return redirect(url_for("auth.forgot_password"))
    user = db.session.get(User, user_id)
    if user is None:
        flash("That reset link is invalid.", "danger")
        return redirect(url_for("auth.forgot_password"))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash("Password updated. Please sign in.", "success")
        return redirect(url_for("auth.signin"))
    return render_template("reset_password.html", form=form)