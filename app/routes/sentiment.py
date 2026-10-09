from flask import Blueprint, jsonify, current_app
from flask_login import current_user
from app.extensions import limiter
from app.services.sentiment_service import sentiment_service, SentimentModelError

sentiment_bp = Blueprint("sentiment", __name__, url_prefix="/api/sentiment")


@sentiment_bp.before_request
def _guard():
    if not current_user.is_authenticated:
        return jsonify(error="Authentication required"), 401


@sentiment_bp.route("/<symbol>")
@limiter.limit("15 per minute")
def sentiment(symbol):
    from app import SUPPORTED_STOCKS
    if symbol not in {s for s, _, _ in SUPPORTED_STOCKS}:
        return jsonify(error="Unsupported symbol"), 404
    try:
        data = sentiment_service.analyze(symbol)
    except SentimentModelError as exc:
        return jsonify(error=str(exc)), 503
    except Exception:
        current_app.logger.exception("Sentiment failed")
        return jsonify(error="Unexpected server error. Check the server log."), 500
    return jsonify(data), (502 if "error" in data else 200)