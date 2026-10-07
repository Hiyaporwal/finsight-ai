import numpy as np
import pandas as pd
import pytest
from app.ml.preprocessing import (
    FEATURE_COLUMNS, build_features, add_targets, prepare_data,
    make_sequences, chronological_split_indices)


def synthetic(n=600, seed=0):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, n)))
    idx = pd.date_range("2022-01-03", periods=n, freq="B")
    return pd.DataFrame({
        "Open": close * 0.999, "High": close * 1.01, "Low": close * 0.99,
        "Close": close, "Volume": rng.integers(1_000, 5_000, n)}, index=idx)


def test_rsi_in_bounds():
    f = build_features(synthetic())
    rsi = f["rsi_14"].dropna()
    assert rsi.between(0, 100).all()


def test_features_do_not_look_ahead():
    """Changing a future price must not change an earlier feature row."""
    df = synthetic()
    a = build_features(df)
    df2 = df.copy()
    df2.iloc[-1, df2.columns.get_loc("Close")] *= 3
    b = build_features(df2)
    pd.testing.assert_frame_equal(a.iloc[:-1], b.iloc[:-1])


def test_target_alignment():
    df = synthetic()
    t = add_targets(build_features(df), horizon=1)
    assert t["target_close"].iloc[10] == pytest.approx(df["Close"].iloc[11])
    assert t["target_close"].iloc[-1] != t["target_close"].iloc[-1]  # NaN at the end


def test_split_is_chronological_and_complete():
    p = prepare_data(synthetic(), horizon=1, seq_len=30)
    assert p.X_train.index.max() < p.X_val.index.min()
    assert p.X_val.index.max() < p.X_test.index.min()
    assert len(p.X_train) + len(p.X_val) + len(p.X_test) == len(p.data)


def test_scaler_fitted_on_train_only():
    p = prepare_data(synthetic(), horizon=1, seq_len=30)
    train_mean = p.X_train.mean().to_numpy()
    all_mean = p.data[FEATURE_COLUMNS].mean().to_numpy()
    assert np.allclose(p.scaler.mean_, train_mean)
    assert not np.allclose(p.scaler.mean_, all_mean)


def test_sequence_shapes_and_alignment():
    p = prepare_data(synthetic(), horizon=1, seq_len=30)
    Xs, ys, pos = p.seq["test"]
    assert Xs.shape[1:] == (30, len(FEATURE_COLUMNS))
    assert len(Xs) == len(ys) == len(pos)
    # last step of window i equals scaled row i
    assert np.allclose(Xs[0][-1], p.X_scaled[pos[0]])
    assert ys[0] == pytest.approx(p.data["target_return"].iloc[pos[0]])


def test_too_little_data_raises():
    with pytest.raises(ValueError):
        prepare_data(synthetic(n=120), horizon=1)


def test_bad_split_fractions():
    with pytest.raises(ValueError):
        chronological_split_indices(100, 0.9, 0.2)