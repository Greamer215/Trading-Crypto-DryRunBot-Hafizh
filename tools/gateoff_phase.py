"""Uji fase penuh untuk kandidat gate-mati + every 60, plus split-half.

Gate terbukti tidak prediktif di crypto (rank corr +0.002). Kalau mematikannya
membantu, itu harus tahan di SEMUA offset fase, bukan cuma satu.

Kandidat:
  A baseline (gate ETH, every 10, te 88)
  B gate mati, every 10, te 88
  C gate mati, every 60, te 88
  D gate mati, every 30, te 88
  E gate mati, every 60, te 132
  F gate BTC (bukan mati, ganti proxy), every 60
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

sel = json.loads((HERE / "data" / "universe_selected.json").read_text())["selected"]
PA = load_4h(sel)
PA["universe_fixed"] = sel
base = CryptoConfig()
KEYS = ("open", "close", "high", "low", "volume", "turnover")


def run(kw, offset, split=None):
    panels = dict(PA)
    for k in KEYS:
        panels[k] = PA[k].iloc[offset:]
    cfg = replace(base, **kw)
    w = cap_position_weights(build_crypto_weights(panels, cfg), cfg.position_weight_cap)
    op = panels["open"]
    wd = w.reindex(index=op.index, columns=op.columns).fillna(0.0).shift(1).fillna(0.0)
    ret = op.pct_change().shift(-1).fillna(0.0)
    W, R = wd.to_numpy(float), ret.to_numpy(float)
    eq, held = base.capital, np.zeros(W.shape[1])
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
    tr = pd.Series(turn, index=op.index)

    def m(x):
        yrs = (x.index[-1] - x.index[0]).days / 365.25
        c = (x.iloc[-1] / x.iloc[0]) ** (1 / yrs) - 1
        d = float((x / x.cummax() - 1).min())
        return c, d, c / abs(d)

    c, d, cal = m(s)
    h1 = m(s.loc[:"2023-12-31"])
    h2 = m(s.loc["2024-01-01":])
    return dict(cagr=c, mdd=d, calmar=cal, h1_cal=h1[2], h2_cagr=h2[0],
                h2_mdd=h2[1], h2_cal=h2[2],
                turn=float(tr.sum()) / ((s.index[-1] - s.index[0]).days / 365.25))


CAND = [
    ("A baseline (gate ETH, ev10, te88)", dict()),
    ("B gate mati, ev10", dict(gate_floor=1.0)),
    ("C gate mati, ev60", dict(gate_floor=1.0, every=60)),
    ("D gate mati, ev30", dict(gate_floor=1.0, every=30)),
    ("E gate mati, ev60, te132", dict(gate_floor=1.0, every=60, time_exit_hold=132)),
    ("F gate BTC, ev60", dict(gate_proxy="BTCIDR", every=60)),
]

rows = []
for name, kw in CAND:
    every = kw.get("every", base.every)
    offs = range(every)
    res = [run(kw, o) for o in offs]
    c = np.array([r["cagr"] for r in res])
    cal = np.array([r["calmar"] for r in res])
    h2 = np.array([r["h2_cal"] for r in res])
    rows.append({
        "kandidat": name, "n_off": len(res),
        "cagr_med": round(float(np.median(c)), 4),
        "cal_med": round(float(np.median(cal)), 3),
        "cal_sd": round(float(cal.std()), 3),
        "cal_min": round(float(cal.min()), 3),
        "cal_max": round(float(cal.max()), 3),
        "h2cal_med": round(float(np.median(h2)), 3),
        "h2cal_min": round(float(h2.min()), 3),
        "turn_med": round(float(np.median([r["turn"] for r in res])), 1),
    })
    print(f"{name:34s} cal {cal.min():.3f}..{cal.max():.3f} med {np.median(cal):.3f} "
          f"sd {cal.std():.3f} | H2 cal med {np.median(h2):.3f} min {h2.min():.3f}")

df = pd.DataFrame(rows)
print()
pd.set_option("display.width", 240)
print(df.to_string(index=False))
df.to_csv(HERE / "reports" / "gateoff_phase.csv", index=False)
print("\nsaved reports/gateoff_phase.csv")