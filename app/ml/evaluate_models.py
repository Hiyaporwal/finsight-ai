import numpy as np


def mae(y, p):
    return float(np.mean(np.abs(np.asarray(y, float) - np.asarray(p, float))))


def rmse(y, p):
    return float(np.sqrt(np.mean((np.asarray(y, float) - np.asarray(p, float)) ** 2)))


def safe_mape(y, p, eps=1e-8, min_abs=1.0):
    """MAPE in %, skipping rows where |actual| < min_abs (avoids divide by ~0).
    Use on PRICES (never near zero). Returns nan if nothing qualifies."""
    y, p = np.asarray(y, float), np.asarray(p, float)
    mask = np.abs(y) >= max(min_abs, eps)
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs((y[mask] - p[mask]) / y[mask])) * 100)


def directional_accuracy(actual_ret, pred_ret):
    """% of rows where the predicted return has the same sign as the actual one."""
    a, p = np.sign(actual_ret), np.sign(pred_ret)
    return float(np.mean(a == p) * 100)


def evaluate(close_t, y_ret_true, y_ret_pred):
    """Evaluate on PRICE scale. Predicted price = close_t * (1 + predicted_return)."""
    close_t = np.asarray(close_t, float)
    true_price = close_t * (1 + np.asarray(y_ret_true, float))
    pred_price = close_t * (1 + np.asarray(y_ret_pred, float))
    return {
        "mae": mae(true_price, pred_price),
        "rmse": rmse(true_price, pred_price),
        "mape": safe_mape(true_price, pred_price),
        "return_mae": mae(y_ret_true, y_ret_pred),
        "directional_accuracy": directional_accuracy(y_ret_true, y_ret_pred),
    }


def naive_baseline(close_t, y_ret_true):
    """'Tomorrow = today' (predicted return 0). Any model must beat this to be useful."""
    return evaluate(close_t, y_ret_true, np.zeros(len(close_t)))