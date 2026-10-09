"""Inference only. Loads artifacts trained offline (Colab); never trains anything."""
import json
import logging
import os
import re
import threading
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from app.ml.preprocessing import FEATURE_COLUMNS, build_features
from app.services.stock_data_service import market_data

log = logging.getLogger(__name__)

ARTIFACT_DIR = Path(os.environ.get(
    "ARTIFACT_DIR", Path(__file__).resolve().parents[2] / "artifacts"))
MODEL_KEYS = ("random_forest", "xgboost", "lstm", "gru")
DEEP_KEYS = ("lstm", "gru")
HORIZONS = (1, 5)
DISCLAIMER = ("Experimental forecast for educational purposes. It is not a guaranteed outcome "
              "and not investment advice.")

_cache = {}
_lock = threading.Lock()


class PredictionError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def _bundle_dir(symbol: str, horizon: int) -> Path:
    if horizon not in HORIZONS:
        raise PredictionError(f"horizon must be one of {HORIZONS}", 400)
    if not re.fullmatch(r"[A-Z0-9&\-]+\.NS", symbol):
        raise PredictionError("Invalid symbol", 400)
    d = ARTIFACT_DIR / symbol / f"h{horizon}"
    if not (d / "metrics.json").exists():
        raise PredictionError(
            f"No trained models found for {symbol} (horizon {horizon}). "
            "Train them in the Colab notebook and copy the artifacts folder.", 404)
    return d


def _load_bundle(symbol, horizon):
    key = (symbol, horizon, "bundle")
    with _lock:
        if key in _cache:
            return _cache[key]
    d = _bundle_dir(symbol, horizon)
    try:
        meta = json.loads((d / "metrics.json").read_text())
        cols = json.loads((d / "feature_columns.json").read_text())
        scaler = joblib.load(d / "scaler.joblib")
    except Exception as exc:
        log.exception("Could not load bundle in %s", d)
        raise PredictionError(f"Could not read saved artifacts: {exc}", 500)
    if cols != FEATURE_COLUMNS:
        raise PredictionError(
            "Feature columns in the saved artifacts differ from the current preprocessing "
            "code. Retrain the models with the current code.", 409)
    bundle = {"dir": d, "meta": meta, "scaler": scaler}
    with _lock:
        _cache[key] = bundle
    return bundle


def _load_model(symbol, horizon, kind):
    key = (symbol, horizon, kind)
    with _lock:
        if key in _cache:
            return _cache[key]
    d = _bundle_dir(symbol, horizon)

    if kind in DEEP_KEYS:
        path = d / f"{kind}.keras"
        if not path.exists():
            raise PredictionError(f"{kind} was not trained for {symbol} h{horizon}", 404)
        try:
            from tensorflow import keras  # lazy: heavy, and may be missing locally
        except Exception:
            raise PredictionError(
                "LSTM/GRU need TensorFlow, which is not available in this environment "
                "(it requires Python 3.12 or lower).", 503)
        try:
            model = keras.models.load_model(path)
        except Exception as exc:
            log.exception("Could not load %s", path)
            raise PredictionError(f"Could not load {kind}: {exc}", 500)

    elif kind == "xgboost":
        try:
            from xgboost import XGBRegressor
        except Exception:
            raise PredictionError("xgboost is not installed (pip install xgboost).", 503)
        jpath = d / "xgboost.json"
        lpath = d / "xgboost.joblib"
        if jpath.exists():
            try:
                model = XGBRegressor()
                model.load_model(str(jpath))
            except Exception as exc:
                log.exception("Could not load %s", jpath)
                raise PredictionError(f"Could not load xgboost: {exc}", 500)
        elif lpath.exists():  # fallback to the old pickle format
            try:
                model = joblib.load(lpath)
            except Exception as exc:
                log.exception("Could not load %s", lpath)
                raise PredictionError(
                    "Could not load xgboost.joblib. Convert it to xgboost.json in Colab "
                    f"(see instructions). Details: {exc}", 500)
        else:
            raise PredictionError(f"xgboost was not trained for {symbol} h{horizon}", 404)

    else:  # random_forest
        path = d / f"{kind}.joblib"
        if not path.exists():
            raise PredictionError(f"{kind} was not trained for {symbol} h{horizon}", 404)
        try:
            model = joblib.load(path)
        except Exception as exc:
            log.exception("Could not load %s", path)
            raise PredictionError(
                f"Could not load {kind} (library version mismatch?): {exc}", 500)

    with _lock:
        _cache[key] = model
    return model


def _version_warnings(meta):
    warnings = []
    saved = meta.get("library_versions", {})
    local = {}
    try:
        import sklearn
        local["sklearn"] = sklearn.__version__
    except Exception:
        pass
    try:
        import xgboost
        local["xgboost"] = xgboost.__version__
    except Exception:
        pass
    for lib, v in local.items():
        if lib in saved and saved[lib] != v:
            warnings.append(f"{lib} version differs (trained with {saved[lib]}, running {v}).")
    return warnings


def forecast(symbol: str, horizon: int, kind: str) -> dict:
    if kind not in MODEL_KEYS:
        raise PredictionError(f"model must be one of {MODEL_KEYS}", 400)
    bundle = _load_bundle(symbol, horizon)
    meta = bundle["meta"]
    mm = meta["metrics"].get(kind)
    if mm is None:
        raise PredictionError(f"{kind} was not trained for {symbol} h{horizon}", 404)

    res = market_data.get_history(symbol, "5y")
    if not res.ok:
        raise PredictionError(f"Could not load recent prices: {res.error}", 502)
    feats = build_features(res.data).dropna(subset=FEATURE_COLUMNS)
    if feats.empty:
        raise PredictionError("Not enough recent history to compute indicators", 502)

    model = _load_model(symbol, horizon, kind)
    try:
        if kind in DEEP_KEYS:
            seq_len = int(mm["seq_len"])
            if len(feats) < seq_len:
                raise PredictionError("Not enough recent history for the model window", 502)
            window = bundle["scaler"].transform(
                feats[FEATURE_COLUMNS].tail(seq_len))[np.newaxis]
            pred_ret = (float(model.predict(window, verbose=0).ravel()[0]) * mm["target_sd"]
                        + mm["target_mu"])
        else:
            pred_ret = float(model.predict(feats[FEATURE_COLUMNS].tail(1))[0])
    except PredictionError:
        raise
    except Exception as exc:
        log.exception("Prediction failed for %s h%s %s", symbol, horizon, kind)
        raise PredictionError(f"Prediction failed: {exc}", 500)

    if not np.isfinite(pred_ret):
        raise PredictionError("Model produced a non-finite prediction", 500)

    last_close = float(feats["Close"].iloc[-1])
    as_of = feats.index[-1]
    base = meta["metrics"]["naive_baseline"]
    warnings = _version_warnings(meta)
    data_end = pd.Timestamp(meta["data_end"])
    if (as_of - data_end).days > 90:
        warnings.append(
            "Models were trained more than 90 days before the latest data; consider retraining.")

    return {
        "symbol": symbol, "model": kind, "horizon_sessions": horizon,
        "latest_close": last_close, "latest_date": as_of.strftime("%Y-%m-%d"),
        "predicted_price": last_close * (1 + pred_ret),
        "predicted_change_pct": pred_ret * 100,
        "data_status": "Delayed / end-of-day data (not live)",
        "trained_at": meta["trained_at"], "test_range": meta["test_range"],
        "metrics": {k: mm[k] for k in ("mae", "rmse", "mape", "directional_accuracy")},
        "baseline": {k: base[k] for k in ("mae", "rmse", "mape")},
        "beats_baseline": bool(mm["mape"] < base["mape"]),
        "warnings": warnings, "disclaimer": DISCLAIMER,
    }


def comparison(symbol: str, horizon: int) -> dict:
    bundle = _load_bundle(symbol, horizon)
    meta, d = bundle["meta"], bundle["dir"]
    series = None
    for name in ("test_predictions_trees.csv", "test_predictions_dl.csv"):
        p = d / name
        if p.exists():
            df = pd.read_csv(p)
            series = df if series is None else series.merge(
                df, on=["date", "close_t", "actual_price"], how="outer").sort_values("date")
    chart = None
    if series is not None:
        chart = series.astype(object).where(series.notna(), None).to_dict("list")
    return {
        "symbol": symbol, "horizon_sessions": horizon,
        "trained_at": meta["trained_at"], "deep_trained_at": meta.get("deep_trained_at"),
        "train_range": meta["train_range"], "val_range": meta["val_range"],
        "test_range": meta["test_range"],
        "metrics": {k: {m: v[m] for m in ("mae", "rmse", "mape", "directional_accuracy") if m in v}
                    for k, v in meta["metrics"].items()},
        "test_series": chart, "disclaimer": DISCLAIMER,
    }
EXPLAINABLE = ("random_forest", "xgboost")
FEATURE_HELP = {
    "Open": "Opening price", "High": "Day high", "Low": "Day low", "Close": "Closing price",
    "Volume": "Trading volume", "return_1d": "Latest 1-day return",
    "sma_10": "10-day simple average price", "sma_20": "20-day simple average price",
    "sma_50": "50-day simple average price", "ema_10": "10-day exponential average price",
    "ema_20": "20-day exponential average price", "ema_50": "50-day exponential average price",
    "rsi_14": "RSI (14-day momentum)", "macd": "MACD line", "macd_signal": "MACD signal line",
    "macd_hist": "MACD histogram", "bb_mid": "Bollinger middle band",
    "bb_upper": "Bollinger upper band", "bb_lower": "Bollinger lower band",
    "bb_pctb": "Position inside Bollinger Bands", "bb_width": "Bollinger Band width",
    "volatility_20": "20-day volatility",
}


def _explainer(symbol, horizon, model):
    key = (symbol, horizon, "shap_explainer")
    with _lock:
        if key in _cache:
            return _cache[key]
    import shap
    explainer = shap.TreeExplainer(model)
    with _lock:
        _cache[key] = explainer
    return explainer


def explain(symbol: str, horizon: int, kind: str, top_n: int = 6) -> dict:
    if kind in DEEP_KEYS:
        try:
            return _explain_deep(symbol, horizon, kind, top_n)
        except PredictionError:
            raise
        except Exception as exc:
            log.exception("Deep explanation failed for %s h%s %s", symbol, horizon, kind)
            raise PredictionError(f"Explanation failed: {exc}", 500)
    if kind not in EXPLAINABLE:
        raise PredictionError("Unknown model", 400)
    _load_bundle(symbol, horizon)  # validates symbol, horizon and artifacts
    res = market_data.get_history(symbol, "5y")
    if not res.ok:
        raise PredictionError(f"Could not load recent prices: {res.error}", 502)
    feats = build_features(res.data).dropna(subset=FEATURE_COLUMNS)
    if feats.empty:
        raise PredictionError("Not enough recent history to compute indicators", 502)
    row = feats[FEATURE_COLUMNS].tail(1)
    model = _load_model(symbol, horizon, kind)

    try:
        if kind == "xgboost":
            import xgboost as xgb
            contrib = model.get_booster().predict(xgb.DMatrix(row), pred_contribs=True)[0]
            values, base = np.asarray(contrib[:-1], float), float(contrib[-1])
        else:
            explainer = _explainer(symbol, horizon, model)
            values = np.asarray(explainer.shap_values(row, check_additivity=False)[0], float)
            base = float(np.ravel(explainer.expected_value)[0])
    except PredictionError:
        raise
    except Exception as exc:
        log.exception("Explanation failed for %s h%s %s", symbol, horizon, kind)
        raise PredictionError(f"Explanation failed: {exc}", 500)

    predicted = base + float(values.sum())
    order = np.argsort(-np.abs(values))
    top = []
    for i in order[:top_n]:
        name = FEATURE_COLUMNS[i]
        top.append({
            "feature": name, "label": FEATURE_HELP.get(name, name),
            "value": float(row.iloc[0][name]),
            "contribution_pct_points": float(values[i] * 100),
            "direction": "up" if values[i] >= 0 else "down",
        })
    rest = float(values[order[top_n:]].sum() * 100) if len(order) > top_n else 0.0
    return {
        "symbol": symbol, "model": kind, "horizon_sessions": horizon,
        "as_of": feats.index[-1].strftime("%Y-%m-%d"),
        "base_return_pct": base * 100,
        "predicted_return_pct": predicted * 100,
        "top_features": top, "other_features_pct_points": rest,
        "note": ("SHAP values describe how this trained model reached its forecast. They do not "
                 "prove that a feature causes price moves. Contributions are in percentage "
                 "points of predicted return."),
        "disclaimer": DISCLAIMER,
    }
def _explain_deep(symbol, horizon, kind, top_n=6):
    bundle = _load_bundle(symbol, horizon)
    mm = bundle["meta"]["metrics"].get(kind)
    if mm is None:
        raise PredictionError(f"{kind} was not trained for {symbol} h{horizon}", 404)
    res = market_data.get_history(symbol, "5y")
    if not res.ok:
        raise PredictionError(f"Could not load recent prices: {res.error}", 502)
    feats = build_features(res.data).dropna(subset=FEATURE_COLUMNS)
    seq_len = int(mm["seq_len"])
    if len(feats) < seq_len:
        raise PredictionError("Not enough recent history for the model window", 502)
    model = _load_model(symbol, horizon, kind)

    window = bundle["scaler"].transform(feats[FEATURE_COLUMNS].tail(seq_len))  # (seq_len, n_features)
    n = window.shape[1]
    batch = [window.copy(), np.zeros_like(window)]      # original, all features at training mean
    for i in range(n):
        w = window.copy()
        w[:, i] = 0.0                                   # scaled 0 = training average
        batch.append(w)
    out = model.predict(np.stack(batch), verbose=0).ravel() * mm["target_sd"] + mm["target_mu"]
    original, neutral, ablated = float(out[0]), float(out[1]), out[2:]
    effects = original - ablated                        # forecast change caused by each feature

    order = np.argsort(-np.abs(effects))
    last_row = feats[FEATURE_COLUMNS].iloc[-1]
    top = []
    for i in order[:top_n]:
        name = FEATURE_COLUMNS[i]
        top.append({
            "feature": name, "label": FEATURE_HELP.get(name, name),
            "value": float(last_row[name]),
            "contribution_pct_points": float(effects[i] * 100),
            "direction": "up" if effects[i] >= 0 else "down",
        })
    return {
        "symbol": symbol, "model": kind, "horizon_sessions": horizon,
        "as_of": feats.index[-1].strftime("%Y-%m-%d"),
        "method": "Feature ablation (not SHAP)",
        "base_return_pct": neutral * 100,
        "predicted_return_pct": original * 100,
        "top_features": top, "other_features_pct_points": 0.0,
        "note": ("Each bar shows how much the forecast changes when that feature is replaced by its "
                 "training average over the whole input window. Effects overlap and do not add up "
                 "exactly to the forecast. This describes the model's behaviour, not market causes."),
        "disclaimer": DISCLAIMER,
    }