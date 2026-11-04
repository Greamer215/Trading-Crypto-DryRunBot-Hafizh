"""Dekomposisi TURNOVER: dari mana churn berasal.
Kandidat sumber: (a) re-rank every, (b) gate yang bergerak tiap bar,
(c) scale_in_overlay yang bergerak tiap bar.

hold_every membekukan bobot dasar antar re-rank, jadi (a) seharusnya kecil.
Kalau turnover tetap tinggi saat (b)/(c) dimatikan -> ketemu sumbernya.
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
panels = load_4h(sel)
panels["universe_fixed"] = sel
base = CryptoConfig()
op = panels["open"]


def turnover(w):
    wd = w.shift(1).fillna(0.0)
    yrs = (w.index[-1] - w.index[0]).days / 365.25
    return float(wd.diff().abs().sum(axis=1).sum() / yrs)


def sim(w):
    wd = w.reindex(index=op.index, columns=op.columns).fillna(0.0).shift(1).fillna(0.0)
    ret = op.pct_change().shift(-1).fillna(0.0)
    W, R = wd.to_numpy(float), ret.to_numpy(float)
    eq, held = base.capital, np.zeros(W.shape[1])
    out = np.empty(len(W))
    for i in range(len(W)):
        tgt = W[i]
        dw = tgt - held
        eq *= (1.0 + float(tgt @ R[i]) - (dw[dw > 0].sum() * base.total_buy
                                          + (-dw[dw < 0]).sum() * base.total_sell))
        held = tgt
        out[i] = eq
    s = pd.Series(out, index=op.index)
    yrs = (s.index[-1] - s.index[0]).days / 365.25
    cagr = (s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1
    mdd = float((s / s.cummax() - 1).min())
    return cagr, mdd, cagr / abs(mdd), s


VAR = [
    ("baseline every10", dict()),
    ("gate mati (floor 1)", dict(gate_floor=1.0)),
    ("scale-in mati", dict(max_scale=1.0)),
    ("gate + scale-in mati", dict(gate_floor=1.0, max_scale=1.0)),
    ("gate mati, every 60", dict(gate_floor=1.0, every=60)),
    ("semua mati, every 60", dict(gate_floor=1.0, max_scale=1.0, every=60)),
]

rows = []
for name, kw in VAR:
    cfg = replace(base, **kw)
    w = cap_position_weights(build_crypto_weights(panels, cfg), cfg.position_weight_cap)
    c, m, cal, s = sim(w)
    rows.append({"varian": name, "turn_yr": round(turnover(w), 1),
                 "cagr": round(c, 4), "mdd": round(m, 4), "calmar": round(cal, 3),
                 "expo": round(float(w.sum(axis=1).mean()), 3)})

df = pd.DataFrame(rows)
pd.set_option("display.width", 200)
print(df.to_string(index=False))
df.to_csv(HERE / "reports" / "diag_turnover.csv", index=False)

# berapa banyak perubahan bobot berasal dari gross yang bergerak tiap bar
cfg = base
w = cap_position_weights(build_crypto_weights(panels, cfg), cfg.position_weight_cap)
gross = w.sum(axis=1)
print(f"\ngross exposure: berubah tiap bar rata2 {float(gross.diff().abs().mean()):.5f}, "
      f"sd {float(gross.std()):.4f}, rentang {float(gross.min()):.2f}-{float(gross.max()):.2f}")
print(f"jumlah bar dengan gross berubah >0.001: {int((gross.diff().abs()>0.001).sum())} "
      f"dari {len(gross)} ({float((gross.diff().abs()>0.001).mean())*100:.0f}%)")