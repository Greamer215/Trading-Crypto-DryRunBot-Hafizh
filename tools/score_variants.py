"""Konfirmasi: dampak sifat struktural trend_reg_score.

Fakta terukur (tools/diag_score.py):
 - 13.9% bar SEMUA skor <= 0 -> tie-break method='first' memilih kolom 1-5
   (BTC, ETH, BNB, DOGE, ADA) 100% konsisten = urutan file data, bukan pilihan.
 - 35.9% bar hanya 1-4 kandidat positif -> slot sisa diisi skor 0 (sembarang).
 - Total ~49.8% bar seleksinya sebagian/seluruhnya arbitrer.
 - skor = slope * clip(tstat,0,inf), eksponen terukur 1.758 -> konveks,
   pangsa skor teratas 41.6% dari total (merata = 20%).

Varian yang diuji (semua lewat uji fase, offset 0..every-1):
 A baseline (skor beku)
 B tanpa pick arbitrer: kalau max skor <= 0 -> kas (bobot 0)
 C skor = slope saja (tanpa kali tstat)
 D skor = slope * clip(tstat, 0, 2)  (tstat dijinakkan, kurangi konveksitas)
 E skor = rank skor (cross-sectional, rata konkavitas)
"""
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from logic import CryptoConfig, build_crypto_weights
from logic.core import (
    cap_position_weights, equal_weights, hold_every, liquid_universe_mask,
    scale_in_overlay, soft_market_gate, time_exit_overlay, _rolling_ols_slope_tstat,
)
from tools.backtest_4h import load_4h

sel = json.loads((HERE / "data" / "universe_selected.json").read_text())["selected"]
PA = load_4h(sel)
PA["universe_fixed"] = sel
base = CryptoConfig()
KEYS = ("open", "close", "high", "low", "volume", "turnover")


def score_variant(close, lb, kind):
    logc = np.log(close.replace(0.0, np.nan))
    slope, tstat = _rolling_ols_slope_tstat(logc, lb)
    if kind == "base":
        s = slope * tstat.clip(lower=0.0)
    elif kind == "slope":
        s = slope
    elif kind == "damped":
        s = slope * tstat.clip(lower=0.0, upper=2.0)
    elif kind == "rank":
        s0 = slope * tstat.clip(lower=0.0)
        s = s0.rank(axis=1, pct=True)
    else:
        raise ValueError(kind)
    return s.where(np.isfinite(s))


def weights(panels, cfg, kind, cash_when_none):
    close, open_px, turn = panels["close"], panels["open"], panels["turnover"]
    liq = liquid_universe_mask(turn, close, n_top=None, lookback=cfg.universe_lookback,
                               min_turnover_idr=cfg.min_turnover_idr,
                               min_vol_ann=cfg.min_vol_ann)
    fixed = set(panels.get("universe_fixed", list(close.columns)))
    keep = pd.Series({c: (c in fixed) for c in close.columns})
    mask = liq & keep.reindex(close.columns)
    mask = mask.reindex(index=close.index, columns=close.columns).fillna(False)

    score = score_variant(close, cfg.signal_lookback, kind)
    elig = score.notna() & close.notna() & (close > 0) & mask.reindex_like(score)
    if cash_when_none:
        # buang kandidat yang skor <= 0: kalau tak ada yang positif, bobot 0
        elig = elig & (score > 0)
    w = equal_weights(score, elig, close, n_top=cfg.n_top, vol_window=cfg.vol_window)
    w = hold_every(w, cfg.every)
    w = scale_in_overlay(w, open_px, close, elig, z_window=cfg.z_window,
                         entry_z=cfg.entry_z, max_scale=cfg.max_scale,
                         max_entry_gap=None)
    proxy = close[[cfg.gate_proxy]].where(close[[cfg.gate_proxy]] > 0)
    g = soft_market_gate(proxy, k=cfg.gate_k, b=cfg.gate_b,
                         window=cfg.gate_window).reindex(w.index).fillna(0.0)
    w = w.mul(g.clip(lower=cfg.gate_floor), axis=0)
    if cfg.time_exit_hold is not None:
        w = time_exit_overlay(w, close, max_hold_bars=cfg.time_exit_hold,
                              min_gain=cfg.time_exit_min_gain)
    return w


def run(panels, cfg, kind, cash, offset):
    p = dict(panels)
    for k in KEYS:
        p[k] = panels[k].iloc[offset:]
    w = cap_position_weights(weights(p, cfg, kind, cash), cfg.position_weight_cap)
    op = p["open"]
    wd = w.reindex(index=op.index, columns=op.columns).fillna(0.0).shift(1).fillna(0.0)
    ret = op.pct_change().shift(-1).fillna(0.0)
    W, R = wd.to_numpy(float), ret.to_numpy(float)
    eq, held = cfg.capital, np.zeros(W.shape[1])
    out = np.empty(len(W))
    turn = np.empty(len(W))
    for i in range(len(W)):
        tgt = W[i]
        dw = tgt - held
        eq *= (1.0 + float(tgt @ R[i]) - (dw[dw > 0].sum() * cfg.total_buy
                                          + (-dw[dw < 0]).sum() * cfg.total_sell))
        held = tgt
        out[i] = eq
        turn[i] = np.abs(dw).sum()
    s = pd.Series(out, index=op.index)

    def m(x):
        yrs = (x.index[-1] - x.index[0]).days / 365.25
        c = (x.iloc[-1] / x.iloc[0]) ** (1 / yrs) - 1
        d = float((x / x.cummax() - 1).min())
        return c, d, c / abs(d)

    c, d, cal = m(s)
    h2 = m(s.loc["2024-01-01":])
    yrs = (s.index[-1] - s.index[0]).days / 365.25
    return dict(cagr=c, mdd=d, calmar=cal, h2_cagr=h2[0], h2_cal=h2[2],
                turn=float(turn.sum()) / yrs, expo=float(w.sum(axis=1).mean()))


CAND = [
    ("A baseline (skor beku)", "base", False),
    ("B tanpa pick arbitrer (kas)", "base", True),
    ("C slope saja", "slope", False),
    ("D slope x clip(tstat,0,2)", "damped", False),
    ("E skor jadi rank", "rank", False),
    ("F slope saja + kas", "slope", True),
]

rows = []
for name, kind, cash in CAND:
    res = [run(PA, base, kind, cash, o) for o in range(base.every)]
    c = np.array([r["cagr"] for r in res])
    cal = np.array([r["calmar"] for r in res])
    h2 = np.array([r["h2_cal"] for r in res])
    rows.append({
        "kandidat": name,
        "cagr_med": round(float(np.median(c)), 4),
        "cal_med": round(float(np.median(cal)), 3),
        "cal_sd": round(float(cal.std()), 3),
        "cal_min": round(float(cal.min()), 3),
        "cal_max": round(float(cal.max()), 3),
        "h2cal_med": round(float(np.median(h2)), 3),
        "h2cal_min": round(float(h2.min()), 3),
        "turn": round(float(np.median([r["turn"] for r in res])), 1),
        "expo": round(float(np.median([r["expo"] for r in res])), 3),
    })
    print(f"{name:30s} cal med {np.median(cal):.3f} [{cal.min():.3f}..{cal.max():.3f}] "
          f"sd {cal.std():.3f} | H2 cal med {np.median(h2):.3f} min {h2.min():.3f}")

df = pd.DataFrame(rows)
print()
pd.set_option("display.width", 250)
print(df.to_string(index=False))
df.to_csv(HERE / "reports" / "score_variants.csv", index=False)
print("\nsaved reports/score_variants.csv")