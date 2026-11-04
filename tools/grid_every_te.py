"""Uji diagnosis: every (frekuensi re-rank) x time_exit (kesabaran hold).

Hipotesis: churn berasal dari every=10 bar (40 jam) sedangkan edge baru muncul
di ~88 bar. Perbaikan: perpanjang jeda re-rank dan/atau perpanjang time exit.

Semua kandidat diukur full-sample DAN H2 (2024-2026), karena kandidat yang
cuma menang H1 adalah artefak bull 2021-23.
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


def sim(w):
    wd = w.reindex(index=op.index, columns=op.columns).fillna(0.0).shift(1).fillna(0.0)
    ret = op.pct_change().shift(-1).fillna(0.0)
    W, R = wd.to_numpy(float), ret.to_numpy(float)
    eq = base.capital
    held = np.zeros(W.shape[1])
    out = np.empty(len(W))
    turn = np.empty(len(W))
    for i in range(len(W)):
        tgt = W[i]
        dw = tgt - held
        cost = dw[dw > 0].sum() * base.total_buy + (-dw[dw < 0]).sum() * base.total_sell
        eq *= (1.0 + float(tgt @ R[i]) - cost)
        held = tgt
        out[i] = eq
        turn[i] = np.abs(dw).sum()
    return pd.Series(out, index=op.index), pd.Series(turn, index=op.index)


def met(eq):
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1
    mdd = float((eq / eq.cummax() - 1).min())
    return cagr, mdd, cagr / abs(mdd), yrs


def n_trades(w):
    wd = w.shift(1).fillna(0.0)
    return int(((wd > 1e-9).astype(int).diff().fillna(0) == 1).sum().sum())


rows = []
for every in (10, 20, 30, 40, 60):
    for te in (88, 132, 176, None):
        cfg = replace(base, every=every, time_exit_hold=te)
        w = cap_position_weights(build_crypto_weights(panels, cfg), cfg.position_weight_cap)
        eq, turn = sim(w)
        c, m, cal, yrs = met(eq)
        h1 = met(eq.loc[:"2023-12-31"])
        h2 = met(eq.loc["2024-01-01":])
        rows.append({
            "every": every, "te": te or "none",
            "cagr": round(c, 4), "mdd": round(m, 4), "calmar": round(cal, 3),
            "ntr": n_trades(w), "turn_yr": round(float(turn.sum()) / yrs, 1),
            "expo": round(float(w.sum(axis=1).mean()), 3),
            "H1_cal": round(h1[2], 3), "H2_cagr": round(h2[0], 4),
            "H2_mdd": round(h2[1], 4), "H2_cal": round(h2[2], 3),
        })

df = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(df.to_string(index=False))
df.to_csv(HERE / "reports" / "grid_every_te.csv", index=False)
print("\nsaved reports/grid_every_te.csv")