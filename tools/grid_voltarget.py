"""Grid vol targeting: target vol x pos cap, pada gate ETH (config diadopsi).
Read-only terhadap config beku; tidak mengubah logic.core.
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
base_cfg = CryptoConfig()

rows = []
variants = [("tanpa VT (baseline)", None, 0.20)]
for cap in (0.15, 0.12):
    variants.append((f"pos cap {cap:.2f}", None, cap))
for tv in (0.20, 0.25, 0.30, 0.35, 0.40):
    variants.append((f"VT {tv:.0%} + cap 0.20", tv, 0.20))
for tv in (0.25, 0.30, 0.35):
    variants.append((f"VT {tv:.0%} + cap 0.15", tv, 0.15))

w_raw = build_crypto_weights(panels, base_cfg)  # bobot dasar, dipakai ulang

for name, tv, cap in variants:
    w = cap_position_weights(w_raw, cap)
    scale = pd.Series(1.0, index=w.index)
    if tv is not None:
        scale = vol_target_scale(w, panels["close"], target_vol=tv)
        w = w.mul(scale, axis=0)
    res = run_backtest(panels, w, base_cfg, base_cfg.capital)
    m = metrics(res["equity"])
    ts = trade_stats(panels, w, base_cfg)
    h = {}
    for k, (s, e) in {"H1": ("2021-01-01", "2024-01-01"), "H2": ("2024-01-01", None)}.items():
        mh = metrics(res["equity"].loc[s:e])
        h[k] = round(mh["cagr"], 4), round(mh["mdd"], 4)
    rows.append({
        "varian": name, "cagr": round(m["cagr"], 4), "mdd": round(m["mdd"], 4),
        "calmar": round(m["calmar"], 3), "pf": round(ts["profit_factor"], 3),
        "n": ts["n_trades"], "expo": round(float(w.sum(axis=1).mean()), 3),
        "vt_mean": round(float(scale.mean()), 3) if tv is not None else 1.0,
        "H1_mdd": h["H1"][1], "H2_mdd": h["H2"][1],
    })

df = pd.DataFrame(rows).sort_values("calmar", ascending=False)
pd.set_option("display.width", 220)
print(df.to_string(index=False))
df.to_csv(HERE / "reports" / "grid_voltarget.csv", index=False)
print("\nsaved reports/grid_voltarget.csv")
