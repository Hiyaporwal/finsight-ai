from flask import Blueprint, jsonify
from flask_login import current_user
from app.extensions import limiter
from app.services.financial_metrics import financial_service

financial_bp = Blueprint("financial", __name__, url_prefix="/api/financials")


@financial_bp.before_request
def _guard():
    if not current_user.is_authenticated:
        return jsonify(error="Authentication required"), 401


@financial_bp.route("/<symbol>")
@limiter.limit("20 per minute")
def analysis(symbol):
    from app import SUPPORTED_STOCKS
    sectors = {s: sec for s, _, sec in SUPPORTED_STOCKS}
    if symbol not in sectors:
        return jsonify(error="Unsupported symbol"), 404
    try:
        data = financial_service.analyze(symbol, sectors[symbol])
    except Exception:
        from flask import current_app
        current_app.logger.exception("Financial analysis failed")
        return jsonify(error="Unexpected server error. Check the server log."), 500
    return jsonify(data), (502 if "error" in data else 200)