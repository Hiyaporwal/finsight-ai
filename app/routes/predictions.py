from flask import Blueprint, jsonify, request
from flask_login import current_user
from app.extensions import limiter
from app.services import prediction_service as ps

predictions_bp = Blueprint("predictions", __name__, url_prefix="/api/predictions")


def _supported():
    from app import SUPPORTED_STOCKS
    return {s for s, _, _ in SUPPORTED_STOCKS}


@predictions_bp.before_request
def _guard():
    if not current_user.is_authenticated:
        return jsonify(error="Authentication required"), 401


def _validate(symbol):
    if symbol not in _supported():
        return jsonify(error="Unsupported symbol"), 404
    return None


@predictions_bp.route("/<symbol>/<int:horizon>/forecast")
@limiter.limit("30 per minute")
def forecast(symbol, horizon):
    bad = _validate(symbol)
    if bad:
        return bad
    kind = request.args.get("model", "xgboost")
    try:
        return jsonify(ps.forecast(symbol, horizon, kind))
    except ps.PredictionError as e:
        return jsonify(error=str(e)), e.status


@predictions_bp.route("/<symbol>/<int:horizon>/comparison")
@limiter.limit("30 per minute")
def comparison(symbol, horizon):
    bad = _validate(symbol)
    if bad:
        return bad
    try:
        return jsonify(ps.comparison(symbol, horizon))
    except ps.PredictionError as e:
        return jsonify(error=str(e)), e.status