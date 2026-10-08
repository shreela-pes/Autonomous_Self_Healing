"""
Feature extraction for one metric: hourly day-features, seasonal baseline maths and
multi-day history features (trend / step / seasonality).

Everything here is deterministic, dependency-light (numpy) and NaN-safe.  It is shared by the
statistical engine (per-metric alert enrichment) and the RCA engine (root-cause evidence).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import numpy as np

_EPS = 1e-9


# ── basic helpers ────────────────────────────────────────────────────────────

def hourly_values(mdata: dict) -> np.ndarray:
    """The metric's latest 24 hourly values as a float array (NaN where missing)."""
    pts = (mdata or {}).get("latest_points") or []
    out = []
    for p in pts:
        v = p.get("value") if isinstance(p, dict) else None
        out.append(float(v) if v is not None and v == v else np.nan)
    return np.array(out, dtype=float)


def _date_key(d) -> str:
    return d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]


def _weekday(d) -> Optional[int]:
    if hasattr(d, "weekday"):
        return d.weekday()
    try:
        return datetime.strptime(str(d)[:10], "%Y-%m-%d").weekday()
    except Exception:
        return None


def _nz(x):
    return float(x) if x is not None and x == x else None


# ── hourly seasonal baseline (per weekday, learned from healthy days) ────────

def update_hourly_baseline(prev: Optional[dict], values: np.ndarray, alpha: float) -> dict:
    """
    EWMA of hourly mean and mean-absolute-deviation, one entry per weekday.
    The first samples are averaged (alpha = max(alpha, 1/(n+1))) so it converges fast.
    """
    n_prev = int((prev or {}).get("n") or 0)
    mean = list((prev or {}).get("mean") or [None] * 24)
    scale = list((prev or {}).get("scale") or [None] * 24)
    a = max(alpha, 1.0 / (n_prev + 1))
    for h in range(min(24, len(values))):
        v = values[h]
        if v != v:
            continue
        if mean[h] is None:
            mean[h] = float(v)
            scale[h] = max(abs(float(v)) * 0.08, _EPS)
        else:
            resid = abs(float(v) - mean[h])
            mean[h] = (1 - a) * mean[h] + a * float(v)
            scale[h] = (1 - a) * (scale[h] if scale[h] is not None else resid) + a * resid
        scale[h] = max(scale[h], abs(mean[h]) * 0.02, _EPS)
    return {"mean": mean, "scale": scale, "n": n_prev + 1}


def baseline_arrays(b: Optional[dict], min_samples: int):
    """(mean[24], scale[24]) as float arrays or (None, None) if not trusted yet."""
    if not b or int(b.get("n") or 0) < min_samples:
        return None, None
    mean = np.array([np.nan if x is None else x for x in b["mean"]], dtype=float)
    scale = np.array([np.nan if x is None else x for x in b["scale"]], dtype=float)
    return mean, scale


# ── per-day features ─────────────────────────────────────────────────────────

def day_features(values: np.ndarray, base_mean: Optional[np.ndarray], base_scale: Optional[np.ndarray]) -> dict:
    v = np.asarray(values, dtype=float)
    ok = ~np.isnan(v)
    f: dict = {"n_points": int(ok.sum())}
    if ok.sum() == 0:
        return f
    f.update(avg=float(np.nanmean(v)), max=float(np.nanmax(v)), min=float(np.nanmin(v)),
             std=float(np.nanstd(v)))

    # jumps between consecutive VALID hours
    idx = np.where(ok)[0]
    if len(idx) >= 2:
        vv = v[idx]
        d = np.diff(vv)
        f["max_up_jump"] = float(max(d.max(), 0.0))
        f["max_down_jump"] = float(max((-d).max(), 0.0))
        f["mono_frac"] = float((d > 0).mean())
        prev = vv[:-1]
        with np.errstate(divide="ignore", invalid="ignore"):
            ratios = np.where(prev > _EPS, vv[1:] / prev, np.nan)
        f["max_up_ratio"] = _nz(np.nanmax(ratios)) if np.isfinite(ratios).any() else None
        # cheap spearman: correlation of ranks with time
        if len(vv) >= 6 and np.std(vv) > _EPS:
            ranks = vv.argsort().argsort().astype(float)
            t = np.arange(len(vv), dtype=float)
            f["spearman_time"] = float(np.corrcoef(ranks, t)[0, 1])

    if base_mean is not None and len(base_mean) == len(v):
        bm = np.where(np.isnan(base_mean), np.nan, base_mean)
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(np.abs(bm) > _EPS, v / bm, np.nan)
            resid = (v - bm) / np.where(np.isnan(base_scale), np.nan, np.maximum(base_scale, _EPS))
        f["baseline_avg"] = _nz(np.nanmean(bm))
        if np.isfinite(ratio).any():
            f["ratio_mean"] = _nz(np.nanmean(ratio))
            f["ratio_max"] = _nz(np.nanmax(ratio))
            f["ratio_min"] = _nz(np.nanmin(ratio))
        if np.isfinite(resid).any():
            f["resid_z_max"] = _nz(np.nanmax(np.abs(resid)))
            f["resid_hours_high"] = int((np.abs(resid[np.isfinite(resid)]) >= 3.0).sum())
        f["has_baseline"] = True
    else:
        f["has_baseline"] = False
    return f


def hourly_ratio(values: np.ndarray, base_mean: Optional[np.ndarray]) -> np.ndarray:
    if base_mean is None:
        return np.full(len(values), np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(np.abs(base_mean) > _EPS, np.asarray(values, dtype=float) / base_mean, np.nan)


# ── multi-day history features ───────────────────────────────────────────────

def _linfit(y: np.ndarray):
    t = np.arange(len(y), dtype=float)
    if len(y) < 3 or np.std(y) < _EPS:
        return 0.0, float(np.var(y) * len(y)), 0.0
    slope, icpt = np.polyfit(t, y, 1)
    fit = slope * t + icpt
    sse = float(((y - fit) ** 2).sum())
    sst = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - sse / sst if sst > _EPS else 0.0
    return float(slope), sse, float(r2)


def classify_shape(y: np.ndarray) -> dict:
    """
    Shape of a short daily series: flat | step | linear_up | linear_down | irregular.
    Compares a linear fit with the best single change-point (two-level) fit.
    """
    y = np.asarray(y, dtype=float)
    y = y[~np.isnan(y)]
    k = len(y)
    out = {"shape": "unknown", "n": k, "slope": None, "r2": None, "step_size": None}
    if k < 5:
        return out
    rng = float(y.max() - y.min())
    slope, sse_lin, r2 = _linfit(y)
    out.update(slope=slope, r2=r2)
    if rng < max(1.0, 0.03 * abs(float(y.mean()))):
        out["shape"] = "flat"
        return out
    best_sse, best_size = np.inf, 0.0
    for c in range(2, k):
        a, b = y[:c], y[c:]
        sse = float(((a - a.mean()) ** 2).sum() + ((b - b.mean()) ** 2).sum())
        if sse < best_sse:
            best_sse, best_size = sse, float(b.mean() - a.mean())
    out["step_size"] = best_size
    if best_sse < 0.6 * sse_lin and abs(best_size) >= max(3.0, 0.25 * rng):
        out["shape"] = "step"
    elif abs(slope) * k >= 3.0 and r2 >= 0.75:
        out["shape"] = "linear_up" if slope > 0 else "linear_down"
    else:
        out["shape"] = "irregular"
    return out


def history_features(history: list, today_date, today_avg: Optional[float],
                     exclude_today: bool = True) -> dict:
    """
    history: [{date, avg, max, min}] oldest -> newest (may include today's entry).
    Returns trend + seasonality features.  Today's entry is excluded from baselines.
    """
    tkey = _date_key(today_date) if today_date is not None else None
    rows = []
    for h in history or []:
        a = h.get("avg")
        if a is None or a != a or h.get("date") is None:
            continue
        rows.append((_date_key(h["date"]), h["date"], float(a), h.get("max"), h.get("min")))
    rows.sort(key=lambda r: r[0])
    past = [r for r in rows if not (exclude_today and r[0] == tkey)]
    f: dict = {"n_history_days": len(past)}
    if not past:
        return f

    avgs = np.array([r[2] for r in past])
    f["hist_mean"] = float(avgs.mean())
    f["hist_std"] = float(avgs.std())
    f["hist_median"] = float(np.median(avgs))

    # trend over recent windows (include today's value as the last point when known)
    series_all = list(avgs) + ([float(today_avg)] if today_avg is not None and today_avg == today_avg else [])
    for w in (7, 14, 30):
        seg = np.array(series_all[-w:], dtype=float)
        if len(seg) >= max(4, w // 2):
            slope, _, r2 = _linfit(seg)
            f[f"slope_{w}d"] = slope
            f[f"r2_{w}d"] = r2
    f["shape10"] = classify_shape(np.array(series_all[-10:], dtype=float))

    # seasonal (same weekday) robust baseline
    wd = _weekday(today_date) if today_date is not None else None
    if wd is not None:
        same = np.array([r[2] for r in past if _weekday(r[1]) == wd], dtype=float)
        f["n_same_weekday"] = int(len(same))
        if len(same) >= 1:
            f["seasonal_median"] = float(np.median(same))
            mad = float(np.median(np.abs(same - np.median(same))) * 1.4826)
            f["seasonal_mad"] = mad
    # biggest day-over-day drop in the last 21 days (restart / cleanup evidence)
    if len(avgs) >= 3:
        d = np.diff(avgs[-22:])
        f["max_daily_drop_21d"] = float(max((-d).max(), 0.0))
        f["max_daily_rise_21d"] = float(max(d.max(), 0.0))
    return f


def robust_z(x: Optional[float], hist: dict) -> tuple[Optional[float], Optional[float]]:
    """(z, baseline_used).  Same-weekday robust baseline if enough samples, else overall."""
    if x is None or x != x:
        return None, None
    if hist.get("n_same_weekday", 0) >= 4 and hist.get("seasonal_median") is not None:
        med = hist["seasonal_median"]
        scale = max(hist.get("seasonal_mad") or 0.0, 0.02 * abs(med), 1e-6)
        return abs(x - med) / scale, med
    if hist.get("n_history_days", 0) >= 5:
        med = hist["hist_median"]
        scale = max(hist.get("hist_std") or 0.0, 0.02 * abs(med), 1e-6)
        return abs(x - med) / scale, med
    return None, None


def pearson(a: np.ndarray, b: np.ndarray, min_n: int = 8) -> Optional[float]:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    m = ~(np.isnan(a) | np.isnan(b))
    if m.sum() < min_n or np.std(a[m]) < _EPS or np.std(b[m]) < _EPS:
        return None
    return float(np.corrcoef(a[m], b[m])[0, 1])
