"""Volatility targeting adapter (lapisan non-core, khusus crypto).

Equal-weight 20% per nama diskalakan untuk volatilitas saham (20-40%/tahun).
Di crypto (52-118%) bobot tetap itu berarti risiko per nama 2-3x lebih besar.
Adapter ini men-scale GROSS exposure per bar supaya ex-ante vol portofolio
mendekati target tahunan, tanpa mengubah ranking, bobot relatif, gate, atau
time-exit (semuanya tetap di logic.core).

Sigma dibentuk D R D dengan R = korelasi rolling, karena korelasi antar pair
crypto ~0.54 sehingga asumsi diagonal (independen) akan salah besar.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

BARS_PER_YEAR = 365 * 6  # 4h bar, crypto 24/7


def vol_target_scale(
    w: pd.DataFrame,
    close: pd.DataFrame,
    *,
    target_vol: float = 0.35,
    vol_window: int = 63,
    corr_window: int = 250,
    corr_refresh: int = 60,
    scale_cap: float = 1.0,
    floor: float = 0.0,
) -> pd.Series:
    """Faktor skala gross per bar = target_vol / ex-ante vol portofolio.

    scale_cap=1.0 -> hanya boleh menurunkan eksposur (de-risking), tidak pernah
    menaikkan di atas bobot dasar. floor membatasi skala minimum.
    corr_refresh: matriks korelasi dihitung ulang tiap N bar (mahal, dan bergerak
    lambat pada window 250 bar).
    """
    ret = np.log(close.where(close > 0)).diff()
    sig = ret.rolling(vol_window, min_periods=max(5, vol_window // 2)).std() * np.sqrt(BARS_PER_YEAR)
    cols = list(w.columns)
    out = np.ones(len(w.index))
    C = None

    for i, t in enumerate(w.index):
        row = w.iloc[i]
        act = (row > 0).to_numpy(dtype=bool)
        if not act.any():
            out[i] = 0.0
            continue
        if t not in sig.index:
            continue
        s_all = sig.loc[t].reindex(cols).to_numpy(dtype=float)
        if not np.isfinite(s_all[act]).all():
            continue

        if C is None or i % corr_refresh == 0:
            win = ret.iloc[max(0, i - corr_window + 1): i + 1]
            Cm = win.corr(min_periods=max(10, vol_window // 2)).reindex(index=cols, columns=cols)
            C = np.array(Cm.to_numpy(dtype=float, copy=True))
            C[~np.isfinite(C)] = 0.0
            np.fill_diagonal(C, 1.0)

        idx = np.flatnonzero(act)
        v = row.to_numpy(dtype=float)[idx]
        s = s_all[idx]
        cov = np.outer(s, s) * C[np.ix_(idx, idx)]
        pvol = float(np.sqrt(max(v @ cov @ v, 0.0)))
        if not np.isfinite(pvol) or pvol <= 1e-9:
            continue
        out[i] = float(np.clip(target_vol / pvol, floor, scale_cap))

    return pd.Series(out, index=w.index).fillna(1.0)
