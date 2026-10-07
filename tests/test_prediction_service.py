import json
import joblib
import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timezone
from sklearn.ensemble import RandomForestRegressor

from app.ml.preprocessing import prepare_data, FEATURE_COLUMNS
from app.services import prediction_service as ps
from app.services.stock_data_service import HistoryResult


def synthetic(n=600, seed=0):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, n)))
    idx = pd.date_range("2022-01-03", periods=n, freq="B")
    return pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99,
                         "Close": close, "Volume": rng.integers(1000, 5000, n)}, index=idx)


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    df = synthetic()
    p = prepare_data(df, horizon=1, seq_len=30)
    d = tmp_path / "TEST.NS" / "h1"
    d.mkdir(parents=True)
    rf = RandomForestRegressor(n_estimators=10, random_state=0).fit(p.X_train, p.y_train)
    joblib.dump(rf, d / "random_forest.joblib")
    joblib.dump(p.scaler, d / "scaler.joblib")
    (d / "feature_columns.json").write_text(json.dumps(FEATURE_COLUMNS))
    m = {"mae": 1.0, "rmse": 1.5, "mape": 1.2, "directional_accuracy": 50.0}
    (d / "metrics.json").write_text(json.dumps({
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "data_end": str(p.data.index[-1].date()),
        "train_range": ["a", "b"], "val_range": ["c", "d"], "test_range": ["e", "f"],
        "metrics": {"random_forest": m, "naive_baseline": {**m, "mape": 1.1}}}))
    monkeypatch.setattr(ps, "ARTIFACT_DIR", tmp_path)
    ps._cache.clear()
    monkeypatch.setattr(ps.market_data, "get_history",
                        lambda s, per: HistoryResult(symbol=s, data=df, source="fake"))
    return df


def test_forecast_price_matches_return(bundle):
    out = ps.forecast("TEST.NS", 1, "random_forest")
    last = float(bundle["Close"].iloc[-1])
    assert out["latest_close"] == pytest.approx(last)
    assert out["predicted_price"] == pytest.approx(last * (1 + out["predicted_change_pct"] / 100))
    assert out["beats_baseline"] is False       # 1.2 vs 1.1
    assert "not investment advice" in out["disclaimer"]


def test_missing_artifacts_is_404(bundle):
    with pytest.raises(ps.PredictionError) as e:
        ps.forecast("NOPE.NS", 1, "random_forest")
    assert e.value.status == 404


def test_bad_horizon_and_model(bundle):
    with pytest.raises(ps.PredictionError):
        ps.forecast("TEST.NS", 3, "random_forest")
    with pytest.raises(ps.PredictionError):
        ps.forecast("TEST.NS", 1, "magic")