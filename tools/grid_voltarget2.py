"""Grid vol targeting v2: skala hanya diperbarui tiap `every` bar (sama seperti
bobot dasar) supaya tidak churn tiap 4 jam. Diagnostik turnover ikut dicetak.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from logic import CryptoConfig, build_crypto_weights
from logic.core import cap_position_weights
from logic.voltarget import vol_target_scale
from tools.backtest_4h import load_4h, run_backtest, trade_stats, metrics

sel = json.loads((HERE / "data" / "universe_selected.json").read_text())["selected"]
panels = load_4h(sel)
panels["universe_fixed"] = sel
cfg = CryptoConfig()
w_raw = build_crypto_weights(panels, cfg)


def step_scale(scale: pd.Series, every: int) -> pd.Series:
    """Perbarui skala hanya tiap `every` bar, forward-fill di antaranya."""
    idx = np.arange(len(scale))
    keep = scale.where(pd.Series(idx % every == 0, index=scale.index))
    return keep.ffill().fillna(1.0)


def turnover_per_yr(w: pd.DataFrame) -> float:
    d = w.diff().abs().sum(axis=1).fillna(w.abs().sum(axis=1))
    return float(d.sum() / (len(w) / (365 * 6)))


rows = []
variants = [("baseline (no VT)", None, 0.20, False),
            ("VT 35% tiap-bar (v1)", 0.35, 0.20, False),
            ("VT 35% step10 cap .20", 0.35, 0.20, True),
            ("VT 30% step10 cap .20", 0.30, 0.20, True),
            ("VT 25% step10 cap .20", 0.25, 0.20, True),
            ("VT 20% step10 cap .20", 0.20, 0.20, True),
            ("VT 30% step10 cap .15", 0.30, 0.15, True),
            ("VT 25% step10 cap .12", 0.25, 0.12, True)]

for name, tv, cap, stepped in variants:
    w = cap_position_weights(w_raw, cap)
    smean = 1.0
    if tv is not None:
        s = vol_target_scale(w, panels["close"], target_vol=tv)
        if stepped:
            s = step_scale(s, cfg.every)
        smean = float(s.mean())
        w = w.mul(s, axis=0)
    res = run_backtest(panels, w, cfg, cfg.capital)
    m = metrics(res["equity"])
    ts = trade_stats(panels, w, cfg)
    h = {}
    for k, (a, b) in {"H1": ("2021-01-01", "2024-01-01"), "H2": ("2024-01-01", None)}.items():
        mh = metrics(res["equity"].loc[a:b])
        h[k] = round(mh["cagr"], 4)
    rows.append({"varian": name, "cagr": round(m["cagr"], 4), "mdd": round(m["mdd"], 4),
                 "calmar": round(m["calmar"], 3), "pf": round(ts["profit_factor"], 3),
                 "expo": round(float(w.sum(axis=1).mean()), 3),
                 "turn_yr": round(turnover_per_yr(w), 1), "s_mean": round(smean, 3),
                 "H1": h["H1"], "H2": h["H2"]})

df = pd.DataFrame(rows).sort_values("calmar", ascending=False)
pd.set_option("display.width", 240)
print(df.to_string(index=False))
df.to_csv(HERE / "reports" / "grid_voltarget_v2.csv", index=False)
print("\nsaved reports/grid_voltarget_v2.csv")
