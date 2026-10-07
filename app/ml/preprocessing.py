"""Feature engineering, targets, chronological split and scaling.

Rules enforced here:
  * indicators use only past/current data (no look-ahead)
  * the target is the only column built from future data
  * chronological split, never shuffled
  * the scaler is fitted on the training rows only
"""
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

FEATURE_COLUMNS = [
    "Open", "High", "Low", "Close", "Volume",
    "return_1d", "sma_10", "sma_20", "sma_50",
    "ema_10", "ema_20", "ema_50",
    "rsi_14", "macd", "macd_signal", "macd_hist",
    "bb_mid", "bb_upper", "bb_lower", "bb_pctb", "bb_width",
    "volatility_20",
]


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI. Result is in [0, 100]."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    # No losses at all in the window means RSI is 100; no movement at all means neutral 50
    rsi = rsi.where(~((avg_loss == 0) & (avg_gain > 0)), 100.0)
    rsi = rsi.where(~((avg_loss == 0) & (avg_gain == 0)), 50.0)
    return rsi


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add technical indicators. Needs columns Open, High, Low, Close, Volume.

    Leading rows contain NaN while rolling windows warm up (about 50 rows).
    The last row is kept, so it can be used for inference.
    """
    required = {"Open", "High", "Low", "Close", "Volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    out = df[["Open", "High", "Low", "Close", "Volume"]].astype(float).copy()
    out = out[~out.index.duplicated(keep="last")].sort_index()
    close = out["Close"]

    out["return_1d"] = close.pct_change()

    for n in (10, 20, 50):
        out[f"sma_{n}"] = close.rolling(n).mean()
        out[f"ema_{n}"] = close.ewm(span=n, adjust=False, min_periods=n).mean()

    out["rsi_14"] = _rsi(close, 14)

    ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
    out["macd"] = ema12 - ema26
    out["macd_signal"] = out["macd"].ewm(span=9, adjust=False, min_periods=9).mean()
    out["macd_hist"] = out["macd"] - out["macd_signal"]

    mid = close.rolling(20).mean()
    std = close.rolling(20).std()
    out["bb_mid"] = mid
    out["bb_upper"] = mid + 2 * std
    out["bb_lower"] = mid - 2 * std
    band = (out["bb_upper"] - out["bb_lower"]).replace(0, np.nan)
    out["bb_pctb"] = (close - out["bb_lower"]) / band
    out["bb_width"] = band / mid

    out["volatility_20"] = out["return_1d"].rolling(20).std()

    return out.replace([np.inf, -np.inf], np.nan)


def add_targets(features: pd.DataFrame, horizon: int = 1) -> pd.DataFrame:
    """Attach the future close and the future return. Last `horizon` rows get NaN."""
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    out = features.copy()
    out["target_close"] = out["Close"].shift(-horizon)
    out["target_return"] = out["target_close"] / out["Close"] - 1
    return out


def chronological_split_indices(n: int, train_frac: float = 0.70, val_frac: float = 0.15):
    """Return (train_end, val_end). Rows [0:train_end] train, [train_end:val_end] val, rest test."""
    if not 0 < train_frac < 1 or not 0 < val_frac < 1 or train_frac + val_frac >= 1:
        raise ValueError("Invalid split fractions")
    train_end = int(n * train_frac)
    val_end = train_end + int(n * val_frac)
    return train_end, val_end


def make_sequences(X: np.ndarray, y: np.ndarray, seq_len: int, lo: int, hi: int):
    """Build windows ending at each row i in [lo, hi). Window i = X[i-seq_len+1 : i+1].

    Returns (X_seq, y_seq, end_positions). Rows without a full window are skipped.
    """
    start = max(lo, seq_len - 1)
    positions = np.arange(start, hi)
    if len(positions) == 0:
        return (np.empty((0, seq_len, X.shape[1])), np.empty((0,)), positions)
    X_seq = np.stack([X[i - seq_len + 1: i + 1] for i in positions])
    return X_seq, y[positions], positions


@dataclass
class PreparedData:
    horizon: int
    seq_len: int
    feature_columns: list
    scaler: StandardScaler
    data: pd.DataFrame            # cleaned rows (features + targets), chronological
    train_end: int
    val_end: int
    # Tabular (unscaled, for tree models). y = target_return.
    X_train: pd.DataFrame
    X_val: pd.DataFrame
    X_test: pd.DataFrame
    y_train: pd.Series
    y_val: pd.Series
    y_test: pd.Series
    # Scaled arrays (for neural networks) over all rows, plus sequences per split
    X_scaled: np.ndarray
    seq: dict                     # {"train": (X, y, pos), "val": ..., "test": ...}

    def split_frame(self, name: str) -> pd.DataFrame:
        sl = {"train": slice(0, self.train_end),
              "val": slice(self.train_end, self.val_end),
              "test": slice(self.val_end, None)}[name]
        return self.data.iloc[sl]


def prepare_data(df: pd.DataFrame, horizon: int = 1, seq_len: int = 60,
                 train_frac: float = 0.70, val_frac: float = 0.15,
                 min_rows: int = 250) -> PreparedData:
    feats = build_features(df)
    data = add_targets(feats, horizon).dropna(subset=FEATURE_COLUMNS + ["target_close", "target_return"])

    if len(data) < min_rows:
        raise ValueError(
            f"Only {len(data)} usable rows after indicator warm-up; need at least {min_rows}. "
            "Use a longer history period (e.g. 5y).")

    train_end, val_end = chronological_split_indices(len(data), train_frac, val_frac)

    X = data[FEATURE_COLUMNS]
    y = data["target_return"]

    # Leakage guard: the scaler only ever sees training rows
    scaler = StandardScaler().fit(X.iloc[:train_end])
    X_scaled = scaler.transform(X)

    y_arr = y.to_numpy()
    seq = {
        "train": make_sequences(X_scaled, y_arr, seq_len, 0, train_end),
        "val": make_sequences(X_scaled, y_arr, seq_len, train_end, val_end),
        "test": make_sequences(X_scaled, y_arr, seq_len, val_end, len(data)),
    }

    return PreparedData(
        horizon=horizon, seq_len=seq_len, feature_columns=list(FEATURE_COLUMNS),
        scaler=scaler, data=data, train_end=train_end, val_end=val_end,
        X_train=X.iloc[:train_end], X_val=X.iloc[train_end:val_end], X_test=X.iloc[val_end:],
        y_train=y.iloc[:train_end], y_val=y.iloc[train_end:val_end], y_test=y.iloc[val_end:],
        X_scaled=X_scaled, seq=seq,
    )


def latest_inference_row(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Features for the newest row (no target). Used later to forecast beyond the data."""
    feats = build_features(df).dropna(subset=FEATURE_COLUMNS)
    return feats.tail(1)[FEATURE_COLUMNS] if not feats.empty else None


if __name__ == "__main__":  # python -m app.ml.preprocessing
    from app.services.stock_data_service import market_data

    res = market_data.get_history("TCS.NS", "5y")
    if not res.ok:
        raise SystemExit(f"Could not load data: {res.error}")
    p = prepare_data(res.data, horizon=1, seq_len=60)
    print(f"Usable rows: {len(p.data)}  ({p.data.index[0].date()} to {p.data.index[-1].date()})")
    for name, (Xs, ys, pos) in p.seq.items():
        frame = p.split_frame(name)
        print(f"{name:5} rows={len(frame):4}  {frame.index[0].date()} to {frame.index[-1].date()}  "
              f"seq X={Xs.shape}  y={ys.shape}")
    print("Train-only scaler mean of Close:", round(float(p.scaler.mean_[FEATURE_COLUMNS.index('Close')]), 2))
    print("NaNs in features:", int(p.data[FEATURE_COLUMNS].isna().sum().sum()))