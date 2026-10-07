from concurrent.futures import ThreadPoolExecutor
from flask import Blueprint, jsonify, request
from app.extensions import limiter
from app.services.stock_data_service import market_data, VALID_PERIODS

stocks_bp = Blueprint("stocks", __name__, url_prefix="/api/stocks")


def _supported():
    from app import SUPPORTED_STOCKS
    return {s: {"name": n, "sector": sec} for s, n, sec in SUPPORTED_STOCKS}


def _check(symbol):
    if symbol not in _supported():
        return jsonify(error="Unsupported symbol"), 404
    return None


@stocks_bp.route("")
def list_stocks():
    return jsonify(stocks=[{"symbol": s, **meta} for s, meta in _supported().items()])


@stocks_bp.route("/overview")
@limiter.limit("30 per minute")
def overview():
    supported = _supported()

    def one(sym):
        return {"symbol": sym, **supported[sym], **{k: v for k, v in market_data.summary(sym).items() if k != "symbol"}}

    with ThreadPoolExecutor(max_workers=5) as pool:
        stocks = list(pool.map(one, supported.keys()))
    return jsonify(stocks=stocks)


@stocks_bp.route("/<symbol>/summary")
@limiter.limit("60 per minute")
def summary(symbol):
    bad = _check(symbol)
    if bad:
        return bad
    data = market_data.summary(symbol)
    return jsonify(data), (502 if "error" in data else 200)


@stocks_bp.route("/<symbol>/history")
@limiter.limit("60 per minute")
def history(symbol):
    bad = _check(symbol)
    if bad:
        return bad
    period = request.args.get("period", "1y")
    if period not in VALID_PERIODS:
        return jsonify(error=f"period must be one of {sorted(VALID_PERIODS)}"), 400
    data = market_data.history_json(symbol, period)
    return jsonify(data), (502 if "error" in data else 200)