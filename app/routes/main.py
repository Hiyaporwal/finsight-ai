from flask import Blueprint, render_template
from flask_login import login_required, current_user

main_bp = Blueprint("main", __name__)


def _stocks():
    from app import SUPPORTED_STOCKS  # imported lazily to avoid a circular import
    return [{"symbol": s, "name": n, "sector": sec} for s, n, sec in SUPPORTED_STOCKS]


@main_bp.route("/")
def index():
    return render_template("index.html", stocks=_stocks())


@main_bp.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", user=current_user, stocks=_stocks())


@main_bp.route("/profile")
@login_required
def profile():
    return render_template("profile.html", user=current_user)