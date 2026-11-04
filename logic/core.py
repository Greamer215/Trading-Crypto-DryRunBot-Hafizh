"""Pure strategy primitives -- DataFrames in, DataFrames out. No I/O.

This module is the algorithm. It reads no files, writes no files, prints
nothing and imports nothing from the rest of the repo: only numpy/pandas. That
makes it directly embeddable in a trading-desk dashboard (feed it OHLCV panels,
get daily target weights back).

All primitives are CAUSAL: every value at bar t uses only data up to and
including close[t]. Execution is modelled elsewhere at open[t+1].

No TA indicators (no EMA/RSI/MACD/Bollinger/Stochastic) -- raw price
statistics only: OLS slope of log price, realised volatility, z-scores,
rolling medians and the market proxy slope.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------
def liquid_universe_mask(
    turnover: pd.DataFrame,
    close: pd.DataFrame,
    *,
    n_top: int | None = 50,
    lookback: int = 60,
    min_turnover_idr: float = 5e9,
    min_vol_ann: float = 0.05,
) -> pd.DataFrame:
    """Boolean mask: name is among the top-N by TRAILING median turnover.

    Point-in-time by construction (rolling median uses only bars up to t). A
    trailing realised-vol floor drops pegged/suspended-like series with big
    turnover but no momentum to capture. ``n_top=None`` keeps every name above
    the turnover floor.
    """
    med = turnover.rolling(lookback, min_periods=lookback // 2).median()
    med = med.where(med >= min_turnover_idr)
    vol = close.pct_change().replace([np.inf, -np.inf], np.nan) \
               .rolling(lookback, min_periods=lookback // 2).std()
    tradable = close.notna() & (vol * np.sqrt(252) >= min_vol_ann)
    if n_top is None:
        return (med.notna() & tradable).fillna(False)
    ranks = med.rank(axis=1, ascending=False, method="first")
    mask = (ranks <= n_top) & tradable
    return mask.fillna(False)


# ---------------------------------------------------------------------------
# Signal: regularised cross-sectional trend factor
# ---------------------------------------------------------------------------
def _rolling_ols_slope_tstat(y: pd.DataFrame, window: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rolling OLS of ``y`` on a deterministic time index -> (slope, t-stat).

    Point-in-time: the window ending at bar t uses y[t-window+1 .. t]. Fully
    vectorised (no Python loop over bars).
    """
    if window < 3:
        raise ValueError("window must be >= 3")
    w = window
    x = np.arange(w, dtype=float) - (w - 1) / 2.0
    sum_x2 = float((x * x).sum())

    g = pd.Series(np.arange(len(y), dtype=float), index=y.index)
    sum_y = y.rolling(w, min_periods=w).sum()
    sum_yg = y.mul(g, axis=0).rolling(w, min_periods=w).sum()
    offset = g - (w - 1) / 2.0
    sum_xy = sum_yg.sub(sum_y.mul(offset, axis=0))
    slope = sum_xy / sum_x2

    var_y = y.rolling(w, min_periods=w).var(ddof=0)
    ss_tot = var_y * w
    sse = (ss_tot - (slope ** 2) * sum_x2).clip(lower=0.0)
    var_resid = sse / max(w - 2, 1)
    se_slope = np.sqrt(var_resid / sum_x2)
    se_safe = se_slope.where(se_slope > 0, np.where(slope.abs() > 1e-12, 1e-12, np.nan))
    tstat = slope / se_safe
    return slope, tstat


def trend_reg_score(close: pd.DataFrame, lookback: int = 120) -> pd.DataFrame:
    """score = OLS-slope(log close) * max(0, t-stat).  Long-only trend factor."""
    log_close = np.log(close.replace(0.0, np.nan))
    slope, tstat = _rolling_ols_slope_tstat(log_close, lookback)
    score = slope * tstat.clip(lower=0.0)
    return score.where(np.isfinite(score))


# ---------------------------------------------------------------------------
# Weighting: inverse-volatility (risk parity) inside the top-K
# ---------------------------------------------------------------------------
def inverse_vol_weights(
    score: pd.DataFrame,
    eligible: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    n_top: int = 5,
    vol_window: int = 63,
    cap: float | None = None,
) -> pd.DataFrame:
    """Inverse-vol weights over the top-``n_top`` names by score, per bar.

    Fully vectorised (bit-identical to the previous per-row loop, verified to
    max abs diff ~1e-16): inverse-vol is built on the whole panel, then names
    outside each bar's top-``n_top`` by score are zeroed via a cross-sectional
    rank, then every row is renormalised to gross 1.
    """
    ret = prices.pct_change().rolling(vol_window).std()
    inv = (1.0 / ret).where(eligible)
    sc = score.where(eligible)
    ranks = sc.rank(axis=1, ascending=False, method="first")
    keep = eligible & (ranks <= n_top) & inv.notna()
    w = inv.where(keep)

    s = w.sum(axis=1)
    s[s < 1e-12] = np.nan
    w = w.div(s, axis=0)
    if cap:
        w = w.clip(0.0, cap)
        w = w.div(w.sum(axis=1), axis=0).fillna(0.0)
    return w.fillna(0.0)


def equal_weights(
    score: pd.DataFrame,
    eligible: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    n_top: int = 5,
    vol_window: int = 63,
    cap: float | None = None,
) -> pd.DataFrame:
    """Equal (1/K) weights over the top-``n_top`` names by score, per bar.

    Same selection rule as :func:`inverse_vol_weights` (top-K by score among
    eligible), flat 1/K inside the K names. ``vol_window``/``prices`` are kept
    for signature parity so the weighting scheme is switchable in the pipeline.
    Validated 2026-10-29: CAGR 24.19% vs IV 21.66%, equal-weight wins 5/5
    purged k-folds, 9/9 sensitivity cells, 5/6 walk-forward windows; median
    yearly return 10.62% vs 7.63%. Combined with universe_lookback=40 it is
    super-additive (EQ+L40 26.89% vs parts +4.88 pp predicted, +5.23 actual).
    """
    sc = score.where(eligible)
    ranks = sc.rank(axis=1, ascending=False, method="first")
    keep = eligible & (ranks <= n_top)
    w = keep.astype(float)
    s = w.sum(axis=1)
    s[s < 1e-12] = np.nan
    w = w.div(s, axis=0)
    if cap:
        w = w.clip(0.0, cap)
        w = w.div(w.sum(axis=1), axis=0).fillna(0.0)
    return w.fillna(0.0)


# ---------------------------------------------------------------------------
# Scale-in overlay: averaging-down grid on an OU z-score
# ---------------------------------------------------------------------------
def scale_in_overlay(
    base: pd.DataFrame,
    open_px: pd.DataFrame,
    close: pd.DataFrame,
    eligible: pd.DataFrame,
    *,
    z_window: int = 63,
    entry_z: float = 1.5,
    max_scale: float = 2.0,
    max_entry_gap: float = 0.10,
    stop_mode: str = "entry",
) -> pd.DataFrame:
    """Down-only ramp with an entry-only gap filter.

    ``max_entry_gap`` compares today's known open with yesterday's close and
    only blocks a *new* entry (where the previous base target was zero). It
    never suppresses an already-held position and never uses the next open.
    """
    mean = close.rolling(z_window).mean()
    std = close.rolling(z_window).std()
    z = ((close - mean) / std).where(eligible)

    s = 1.0 + ((-z).clip(lower=0.0) / entry_z).clip(upper=max_scale - 1.0)
    s = s.where(eligible, 0.0).fillna(0.0)

    if stop_mode == "entry":
        s = s * entry_gap_filter(
            base, open_px, close, max_entry_gap=max_entry_gap
        )

    return base * s


def entry_gap_filter(
    base: pd.DataFrame,
    open_px: pd.DataFrame,
    close: pd.DataFrame,
    *,
    max_entry_gap: float | None = 0.10,
) -> pd.DataFrame:
    """Pure causal mask for entry execution filters.

    A gap is measured at open[t] versus close[t-1], which is observable before
    the order decided at close[t] can execute at open[t+1]. Existing positions
    (base[t-1] > 0) are always allowed to persist.
    """
    allowed = pd.DataFrame(True, index=base.index, columns=base.columns)
    if max_entry_gap is None:
        return allowed
    prev_close = close.shift(1).reindex_like(base)
    gap = (open_px.reindex_like(base) - prev_close).abs().div(prev_close.abs())
    new_entry = base.gt(0) & base.shift(1).fillna(0).le(0)
    return (~new_entry | gap.le(max_entry_gap)).fillna(True)


def cap_gross_exposure(weights: pd.DataFrame, cap: float | None) -> pd.DataFrame:
    """Scale each row down to ``cap`` gross exposure; ``None`` disables it."""
    if cap is None:
        return weights
    if cap < 0:
        raise ValueError("gross exposure cap must be non-negative")
    gross = weights.abs().sum(axis=1)
    scale = (cap / gross.replace(0.0, np.nan)).clip(upper=1.0).fillna(1.0)
    return weights.mul(scale, axis=0)


def cap_position_weights(
    weights: pd.DataFrame, cap: float | None
) -> pd.DataFrame:
    """Apply an explicit per-name absolute weight cap without renormalising."""
    if cap is None:
        return weights
    if cap < 0:
        raise ValueError("position weight cap must be non-negative")
    return weights.clip(lower=-cap, upper=cap)


def slow_trend_sleeve(
    close: pd.DataFrame,
    eligible: pd.DataFrame,
    *,
    lookback: int = 300,
    n_top: int = 5,
    vol_window: int = 63,
    cap: float = 0.25,
) -> pd.DataFrame:
    """Causal slow-trend sleeve, capped per name before allocation.

    This is deliberately a primitive rather than a production setting.  The
    score and inverse-vol weights use only information available at close[t].
    The cap is non-renormalising, so a sleeve cannot silently exceed its risk
    budget when fewer names are available.
    """
    if lookback < 3:
        raise ValueError("lookback must be >= 3")
    if cap < 0:
        raise ValueError("cap must be non-negative")
    score = trend_reg_score(close, lookback)
    weights = inverse_vol_weights(
        score, eligible & score.gt(0), close,
        n_top=n_top, vol_window=vol_window, cap=None,
    )
    return cap_position_weights(weights, cap)


def winner_preserving_exit_overlay(
    weights: pd.DataFrame,
    close: pd.DataFrame,
    *,
    activation_return: float = 0.20,
    partial_exit_fraction: float = 0.50,
    trailing_distance: float = 0.15,
) -> pd.DataFrame:
    """Reduce winners and trail the remainder without a fixed take-profit.

    At the first close after a position gains ``activation_return`` from its
    entry, ``partial_exit_fraction`` is removed.  The remaining target is
    closed only after a causal peak-to-close drawdown reaches
    ``trailing_distance``.  State resets when the upstream target is flat.
    """
    if activation_return < 0 or not 0 <= partial_exit_fraction < 1:
        raise ValueError("activation_return >= 0 and fraction must be in [0, 1)")
    if not 0 < trailing_distance < 1:
        raise ValueError("trailing_distance must be in (0, 1)")
    w, px = weights.align(close, join="left", axis=0)
    px = px.reindex_like(w)
    out = np.zeros(w.shape, dtype=float)
    entry = np.full(w.shape[1], np.nan)
    peak = np.full(w.shape[1], np.nan)
    trimmed = np.zeros(w.shape[1], dtype=bool)
    stopped = np.zeros(w.shape[1], dtype=bool)
    for i, (target, price) in enumerate(zip(w.to_numpy(), px.to_numpy())):
        valid = np.isfinite(target) & (target > 0) & np.isfinite(price) & (price > 0)
        reset = ~valid
        entry[reset] = np.nan
        peak[reset] = np.nan
        trimmed[reset] = False
        stopped[reset] = False
        new = valid & np.isnan(entry)
        entry[new] = price[new]
        peak[new] = price[new]
        cont = valid & ~new
        peak[cont] = np.maximum(peak[cont], price[cont])
        activate = valid & ~trimmed & (price >= entry * (1 + activation_return))
        trimmed[activate] = True
        fire = valid & ~stopped & (price <= peak * (1 - trailing_distance))
        stopped[fire] = True
        keep = valid & ~stopped
        out[i, keep] = target[keep] * np.where(
            trimmed[keep], 1.0 - partial_exit_fraction, 1.0
        )
    return pd.DataFrame(out, index=w.index, columns=w.columns)


def time_exit_overlay(
    weights: pd.DataFrame,
    close: pd.DataFrame,
    *,
    max_hold_bars: int,
    min_gain: float,
) -> pd.DataFrame:
    """Stall-kill: drop positions that fail to make money fast enough.

    A run is killed at the first close where it has been held more than
    ``max_hold_bars`` bars and its return from the entry close is still below
    ``min_gain``.  The kill persists until the upstream target lets the name go
    flat, so a killed name cannot silently re-enter the next bar (no churn
    loop) -- it can only be re-picked at a later re-rank if the trend signal
    is still strong.

    This is the time-stop family validated on 2026-10-17: plateau over
    40-52 bars x +3..+12% on IS, improved both IS sub-periods and OOS,
    walk-forward 5/5 windows, frozen config beat per-fold selection.
    Decisions use close[t]; execution is at open[t+1] as everywhere.
    """
    if max_hold_bars < 1:
        raise ValueError("max_hold_bars must be >= 1")
    w, px = weights.align(close, join="left", axis=0)
    px = px.reindex_like(w)
    out = np.zeros(w.shape, dtype=float)
    entry = np.full(w.shape[1], np.nan)
    entry_bar = np.full(w.shape[1], -1, dtype=int)
    killed = np.zeros(w.shape[1], dtype=bool)
    for i, (target, price) in enumerate(zip(w.to_numpy(), px.to_numpy())):
        valid = np.isfinite(target) & (target > 0) & np.isfinite(price) & (price > 0)
        reset = ~valid
        entry[reset] = np.nan
        entry_bar[reset] = -1
        killed[reset] = False
        new = valid & np.isnan(entry)
        entry[new] = price[new]
        entry_bar[new] = i
        cont = valid & ~new
        hold = np.where(cont, i - entry_bar + 1, 0)
        ret = np.where(cont, price / np.where(np.isnan(entry), 1.0, entry) - 1.0, 0.0)
        fire = cont & ~killed & (hold > max_hold_bars) & (ret < min_gain)
        killed |= fire
        keep = valid & ~killed
        out[i, keep] = target[keep]
    return pd.DataFrame(out, index=w.index, columns=w.columns)


def cap_turnover(weights: pd.DataFrame, max_turnover: float | None) -> pd.DataFrame:
    """Causally limit daily target turnover by moving part-way to each target."""
    if max_turnover is None:
        return weights
    if max_turnover < 0:
        raise ValueError("max_turnover must be non-negative")
    out = np.zeros(weights.shape, dtype=float)
    previous = np.zeros(weights.shape[1], dtype=float)
    for i, target in enumerate(weights.to_numpy(dtype=float)):
        delta = target - previous
        gross = np.nansum(np.abs(delta))
        step = min(1.0, max_turnover / gross) if gross > 0 else 1.0
        previous = previous + np.nan_to_num(delta, nan=0.0) * step
        out[i] = previous
    return pd.DataFrame(out, index=weights.index, columns=weights.columns)


def volatility_stop_overlay(
    weights: pd.DataFrame,
    close: pd.DataFrame,
    *,
    vol_window: int = 20,
    vol_multiplier: float = 3.0,
    min_distance: float = 0.08,
    max_distance: float = 0.30,
    enabled: bool = True,
) -> pd.DataFrame:
    """Causal close-to-next-open stop and trailing-stop overlay.

    For each continuous target position, the peak close is tracked from the
    first entry.  At close[t], a stop fires when close[t] is below the peak by
    ``clip(volatility[t] * vol_multiplier, min_distance, max_distance)``;
    volatility is trailing annualised close-to-close volatility.  A fired
    position stays flat until the upstream target goes flat, preventing an
    immediate same-signal re-entry.  The result is therefore safe to execute
    at open[t+1] and uses no future bar.
    """
    if not enabled:
        return weights
    if vol_window < 2:
        raise ValueError("vol_window must be >= 2")
    if vol_multiplier < 0:
        raise ValueError("vol_multiplier must be non-negative")
    if min_distance < 0 or max_distance < min_distance:
        raise ValueError("stop distances must satisfy 0 <= min <= max")

    w, px = weights.align(close, join="left", axis=0)
    px = px.reindex_like(w)
    vol = px.pct_change().rolling(vol_window, min_periods=vol_window).std()
    vol = vol * np.sqrt(252.0)
    distance = (vol * vol_multiplier).clip(
        lower=min_distance, upper=max_distance
    ).fillna(min_distance)

    # The peak/blocked state is path-dependent in time, but independent across
    # names.  Keep the unavoidable bar loop and vectorise the cross-section;
    # this is materially faster on the IDX panel while preserving the exact
    # reset and stop ordering of the original nested loop.
    out = np.zeros(w.shape, dtype=float)
    targets = w.to_numpy(dtype=float, copy=False)
    prices = px.to_numpy(dtype=float, copy=False)
    distances = distance.to_numpy(dtype=float, copy=False)
    peaks = np.full(w.shape[1], np.nan, dtype=float)
    blocked = np.zeros(w.shape[1], dtype=bool)
    active = np.zeros(w.shape[1], dtype=bool)
    for i in range(len(w)):
        target = targets[i]
        price = prices[i]
        valid = np.isfinite(target) & (target > 0) & np.isfinite(price) & (price > 0)
        reset = ~valid
        peaks[reset] = np.nan
        blocked[reset] = False
        active[reset] = False

        new = valid & ~active
        peaks[new] = price[new]
        active[valid] = True
        continuing = valid & ~new
        peaks[continuing] = np.maximum(peaks[continuing], price[continuing])

        fire = valid & ~blocked & (price <= peaks * (1.0 - distances[i]))
        blocked[fire] = True
        keep = valid & ~blocked
        out[i, keep] = target[keep]
    out = pd.DataFrame(out, index=w.index, columns=w.columns)
    return out


def volatility_stop_diagnostics(
    weights: pd.DataFrame,
    close: pd.DataFrame,
    *,
    vol_window: int = 20,
    vol_multiplier: float = 3.0,
    min_distance: float = 0.08,
    max_distance: float = 0.30,
) -> dict[str, object]:
    """Return trigger and effective-distance diagnostics for the stop state.

    The state transitions intentionally mirror :func:`volatility_stop_overlay`.
    This is a research-only observability helper; it does not alter target
    weights or production defaults.
    """
    if vol_window < 2:
        raise ValueError("vol_window must be >= 2")
    if vol_multiplier < 0:
        raise ValueError("vol_multiplier must be non-negative")
    if min_distance < 0 or max_distance < min_distance:
        raise ValueError("stop distances must satisfy 0 <= min <= max")

    w, px = weights.align(close, join="left", axis=0)
    px = px.reindex_like(w)
    vol = px.pct_change().rolling(vol_window, min_periods=vol_window).std() * np.sqrt(252.0)
    distance = (vol * vol_multiplier).clip(
        lower=min_distance, upper=max_distance
    ).fillna(min_distance)

    targets = w.to_numpy(dtype=float, copy=False)
    prices = px.to_numpy(dtype=float, copy=False)
    distances = distance.to_numpy(dtype=float, copy=False)
    peaks = np.full(w.shape[1], np.nan, dtype=float)
    blocked = np.zeros(w.shape[1], dtype=bool)
    active = np.zeros(w.shape[1], dtype=bool)
    triggers = np.zeros(w.shape[1], dtype=int)
    blocked_bars = np.zeros(w.shape[1], dtype=int)
    effective = []
    for i in range(len(w)):
        target = targets[i]
        price = prices[i]
        valid = np.isfinite(target) & (target > 0) & np.isfinite(price) & (price > 0)
        reset = ~valid
        peaks[reset] = np.nan
        blocked[reset] = False
        active[reset] = False

        new = valid & ~active
        peaks[new] = price[new]
        active[valid] = True
        continuing = valid & ~new
        peaks[continuing] = np.maximum(peaks[continuing], price[continuing])

        fire = valid & ~blocked & (price <= peaks * (1.0 - distances[i]))
        triggers += fire.astype(int)
        effective.extend(distances[i, valid & np.isfinite(distances[i])].tolist())
        blocked[fire] = True
        blocked_bars += (valid & blocked).astype(int)

    dist = np.asarray(effective, dtype=float)
    return {
        "trigger_count": int(triggers.sum()),
        "triggered_tickers": int((triggers > 0).sum()),
        "blocked_bars": int(blocked_bars.sum()),
        "distance_min": float(np.min(dist)) if len(dist) else np.nan,
        "distance_median": float(np.median(dist)) if len(dist) else np.nan,
        "distance_max": float(np.max(dist)) if len(dist) else np.nan,
        "distance_at_min_clip": int(np.isclose(dist, min_distance).sum()) if len(dist) else 0,
        "distance_at_max_clip": int(np.isclose(dist, max_distance).sum()) if len(dist) else 0,
    }


# ---------------------------------------------------------------------------
# Market gate: soft regime filter
# ---------------------------------------------------------------------------
def ols_slope(y: pd.Series, window: int) -> pd.Series:
    """Rolling OLS slope of ``y`` over ``window`` bars (causal)."""
    if len(y) < window:
        return pd.Series(np.nan, index=y.index)

    def _fit(z: np.ndarray) -> float:
        x = np.arange(len(z), dtype=float)
        x -= x.mean()
        zc = z - z.mean()
        denom = (x * x).sum()
        return float((x * zc).sum() / denom) if denom > 1e-18 else np.nan

    return y.rolling(window).apply(_fit, raw=True)


def soft_market_gate(
    close: pd.DataFrame,
    *,
    k: float = 4000.0,
    b: float = 0.5,
    window: int = 120,
    shift: int = 1,
) -> pd.Series:
    """Gross scalar in [0, 1]: ``clip(b + k * slope120, 0, 1)``.

    slope120 = OLS slope of log(equal-weight market proxy). Shifted by one bar
    so the gate decided at close[t] applies from open[t+1].
    """
    proxy = np.log(close.where(close > 0)).mean(axis=1)
    slope = ols_slope(proxy, window)
    scale = (b + k * slope).clip(0.0, 1.0)
    if shift:
        scale = scale.shift(shift)
    return scale.fillna(0.0)


# ---------------------------------------------------------------------------
# Rebalance cadence
# ---------------------------------------------------------------------------
def hold_every(base: pd.DataFrame, every: int = 10) -> pd.DataFrame:
    """Freeze weights to the first rebalance bar of each ``every``-bar block."""
    first_pos = int(np.argmax(base.abs().sum(axis=1).values > 0))
    out = base.copy()
    reb = list(range(first_pos, len(base), every))
    for a, b in zip(reb, reb[1:] + [len(base)]):
        out.iloc[a:b] = base.iloc[[a]].values
    return out


# ---------------------------------------------------------------------------
# Optional pullback tilt (research optimisation)
# ---------------------------------------------------------------------------
def pullback_depth(close: pd.DataFrame, lookback: int = 60) -> pd.DataFrame:
    """Causal pullback depth from the rolling ``lookback``-day peak, in [0, 1]."""
    peak = close.rolling(lookback, min_periods=lookback).max()
    depth = (peak - close) / peak
    return depth.clip(lower=0.0).fillna(0.0)


def pullback_tilt(
    weights: pd.DataFrame,
    close: pd.DataFrame,
    *,
    alpha: float = -0.3,
    peak_lookback: int = 60,
    depth_scale: float = 0.20,
    regime_window: int = 200,
    renormalize: bool = True,
) -> pd.DataFrame:
    """Gross-neutral cross-sectional tilt on top of production weights.

    Uptrend names (close > MA200) get ``mult = 1 + alpha*clip(depth/depth_scale,
    0, 1)``; others get 1.0. The row gross (which carries the market gate) is
    preserved when ``renormalize`` is True, so only the per-name allocation
    changes. ``mult`` is frozen within each rebalance block.
    """
    rowsum = weights.sum(axis=1)
    comp = weights.div(rowsum.replace(0.0, np.nan), axis=0).fillna(0.0)

    ma = close.rolling(regime_window, min_periods=regime_window).mean()
    up = (close > ma).fillna(False)
    depth = pullback_depth(close, peak_lookback)
    ramp = (depth / depth_scale).clip(lower=0.0, upper=1.0)

    eligible = weights.abs() > 0
    up_ok = up & eligible.reindex_like(close).fillna(False)
    mult = pd.DataFrame(1.0, index=close.index, columns=close.columns)
    mult = mult.where(~up_ok, 1.0 + alpha * ramp)

    # freeze mult per rebalance block (rows where the composition changes)
    chg = weights.diff().abs().sum(axis=1) > 1e-9
    fa = int(np.argmax(weights.abs().sum(axis=1).values > 0))
    if len(chg):
        chg.iloc[fa] = True
    reb = np.where(chg.values)[0]
    mf = pd.DataFrame(1.0, index=weights.index, columns=weights.columns)
    for i, pos in enumerate(reb):
        end = reb[i + 1] if i + 1 < len(reb) else len(weights)
        mf.iloc[pos:end] = mult.iloc[pos].values

    raw = comp * mf
    if renormalize:
        raw = raw.div(raw.sum(axis=1).replace(0.0, np.nan), axis=0).mul(rowsum, axis=0)
    return raw.fillna(0.0)
