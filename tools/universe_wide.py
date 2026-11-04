"""Jalur 2: universitas lebih luas supaya top-5 kembali selektif.

Masalah yang diukur: 10 pair, eligible 8.4/bar, top-5 = 60% populasi.
IDX: top-5 dari ~100 = 5%. Uji: pakai 18 pair yang sudah terunduh, ranking
berbasis likuiditas (bukan beku 10), n_top tetap 5.

Hipotesis: seleksi lebih tajam -> IC efektif naik -> PF/Calmar naik meski biaya
tetap (karena jumlah posisi tetap 5, turnover tidak otomatis naik).

Semua diuji dengan uji fase (offset 0..every-1) supaya tidak tertipu fase.
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
from logic.core import cap_position_weights
from tools.backtest_4h import load_4h

base = CryptoConfig()
AVAIL = sorted(p.stem for p in (HERE / "data" / "indodax_4h").glob("*.csv"))
KEYS = ("open", "close", "high", "low", "volume", "turnover")


def eligible_stats(panels, cfg):
    close, turn = panels["close"], panels["turnover"]
    med = turn.rolling(cfg.universe_lookback, min_periods=cfg.universe_lookback // 2).median()
    rvol = close.pct_change().rolling(cfg.universe_lookback).std() * np.sqrt(365 * 6)
    elig = (med >= cfg.min_turnover_idr) & (rvol >= cfg.min_vol_ann) & close.notna()
    n = elig.sum(axis=1).dropna()
    return float(n.mean()), len(close.columns), float((n <= 5).mean())


def run(panels, cfg, offset=0):
    p = dict(panels)
    for k in KEYS:
        p[k] = panels[k].iloc[offset:]
    w = cap_position_weights(build_crypto_weights(p, cfg), cfg.position_weight_cap)
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
    return dict(cagr=c, mdd=d, calmar=cal, h2_cagr=h2[0], h2_mdd=h2[1], h2_cal=h2[2],
                turn=float(turn.sum()) / yrs, expo=float(w.sum(axis=1).mean()))


SEL10 = json.loads((HERE / "data" / "universe_selected.json").read_text())["selected"]
SETS = [
    ("10 pair beku (baseline)", SEL10),
    ("18 pair tersedia", AVAIL),
    ("12 pair likuid", [s for s in ["BTCIDR", "ETHIDR", "BNBIDR", "DOGEIDR", "ADAIDR",
                                     "XRPIDR", "TRXIDR", "LTCIDR", "SOLIDR", "DOTIDR",
                                     "LINKIDR", "BCHIDR"]]),
]

rows = []
for name, syms in SETS:
    panels = load_4h(syms)
    panels["universe_fixed"] = syms   # semua pair di set dianggap kandidat
    e_mean, n_cols, pct_le5 = eligible_stats(panels, base)
    res = [run(panels, base, o) for o in range(base.every)]
    cal = np.array([r["calmar"] for r in res])
    c = np.array([r["cagr"] for r in res])
    h2 = np.array([r["h2_cal"] for r in res])
    rows.append({
        "set": name, "n_pair": n_cols, "elig_mean": round(e_mean, 1),
        "pct_le5": round(pct_le5 * 100, 1),
        "cagr_med": round(float(np.median(c)), 4),
        "cal_med": round(float(np.median(cal)), 3), "cal_sd": round(float(cal.std()), 3),
        "cal_min": round(float(cal.min()), 3), "cal_max": round(float(cal.max()), 3),
        "h2cal_med": round(float(np.median(h2)), 3),
        "turn_med": round(float(np.median([r["turn"] for r in res])), 1),
        "expo": round(float(np.median([r["expo"] for r in res])), 3),
    })
    print(f"{name:26s} elig {e_mean:.1f}/{n_cols} (<=5: {pct_le5*100:.0f}%) | "
          f"cal med {np.median(cal):.3f} [{cal.min():.3f}..{cal.max():.3f}] sd {cal.std():.3f} "
          f"| H2 {np.median(h2):.3f}")

df = pd.DataFrame(rows)
print()
pd.set_option("display.width", 240)
print(df.to_string(index=False))
df.to_csv(HERE / "reports" / "universe_wide.csv", index=False)
print("\nsaved reports/universe_wide.csv")