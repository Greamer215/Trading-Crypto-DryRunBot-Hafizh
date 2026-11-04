"""Pipeline crypto: panels 4h -> target weight harian-bot. Core import dari logic.core.

Urutan identik IDX (build_target_weights): universe -> signal -> weighting ->
scale-in -> gate (proxy ETH/IDR) -> time exit. Fraksi lot, ARA/ARB, gap kalender
libur TIDAK dipakai (crypto 24/7, tanpa lot, tanpa ARA).

PERBEDAAN DISENGAJA dari core IDX (keputusan user 2026-11-04, opsi 2):
`crypto_trend_score` memakai slope murni tanpa pengali t-stat. Alasan terukur
(tools/diag_score.py): skor core = slope * max(0,tstat) = slope^2/se, sehingga
50.7% observasi bernilai 0 PERSIS, dan di 13.9% bar SEMUA pair skor <= 0 ->
equal_weights jatuh ke tie-break method="first" = urutan kolom = bot membeli
BTC/ETH/BNB/DOGE/ADA 100% konsisten bukan karena sinyal. Ditambah 35.9% bar
hanya 1-4 kandidat positif: ~49.8% bar seleksinya sebagian/seluruhnya arbitrer.
Varian slope murni menang di KEDUA paruh (Calmar median 0.430 vs 0.320, H2
0.238 vs 0.175, H2-min 0.156 vs 0.097, turnover turun, sd fase sama).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import CryptoConfig
from .core import (
    hold_every,
    liquid_universe_mask,
    scale_in_overlay,
    soft_market_gate,
    time_exit_overlay,
    equal_weights,
    _rolling_ols_slope_tstat,
)


def crypto_trend_score(close: pd.DataFrame, lookback: int = 60) -> pd.DataFrame:
    """score = OLS slope(log close) murni. Sign-aware, tanpa pengali t-stat.

    Bedanya dari core ``trend_reg_score``: t-stat tidak di-clip ke 0, jadi pair
    yang tren turun mendapat skor NEGATIF (bukan 0). Ini yang menghilangkan
    gerombolan nilai 0 yang membuat seleksi jatuh ke urutan kolom.
    """
    log_close = np.log(close.replace(0.0, np.nan))
    slope, _ = _rolling_ols_slope_tstat(log_close, lookback)
    return slope.where(np.isfinite(slope))


def build_crypto_weights(panels, cfg: CryptoConfig | None = None):
    cfg = cfg or CryptoConfig()
    close, open_px, turnover = panels["close"], panels["open"], panels["turnover"]

    # Universe PIT: trailing median turnover; pair dipilih top-N di awal (fixed).
    liq = liquid_universe_mask(
        turnover, close, n_top=None,
        lookback=cfg.universe_lookback,
        min_turnover_idr=cfg.min_turnover_idr,
        min_vol_ann=cfg.min_vol_ann,
    )
    fixed = set(panels.get("universe_fixed", list(close.columns)))
    import pandas as pd
    keep_cols = pd.Series({c: (c in fixed) for c in close.columns})
    mask = liq & keep_cols.reindex(close.columns)
    mask = mask.reindex(index=close.index, columns=close.columns).fillna(False)

    score = crypto_trend_score(close, cfg.signal_lookback)
    eligible = score.notna() & close.notna() & (close > 0) & mask.reindex_like(score)
    base = equal_weights(score, eligible, close, n_top=cfg.n_top,
                         vol_window=cfg.vol_window)
    base = hold_every(base, cfg.every)
    wgrid = scale_in_overlay(
        base, open_px, close, eligible,
        z_window=cfg.z_window, entry_z=cfg.entry_z,
        max_scale=cfg.max_scale, max_entry_gap=None,
    )

    proxy = close[[cfg.gate_proxy]].where(close[[cfg.gate_proxy]] > 0)
    gate = soft_market_gate(proxy, k=cfg.gate_k, b=cfg.gate_b,
                            window=cfg.gate_window).reindex(wgrid.index).fillna(0.0)
    gate = gate.clip(lower=cfg.gate_floor)
    w = wgrid.mul(gate, axis=0)

    if cfg.time_exit_hold is not None:
        w = time_exit_overlay(w, close, max_hold_bars=cfg.time_exit_hold,
                              min_gain=cfg.time_exit_min_gain)
    return w
