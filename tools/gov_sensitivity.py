"""Sensitivitas governor di sekitar 10/30/floor .30 + kontrol parameter yang
PASTI dipertanyakan dosen: krasiscope, iterasi pertama (baseline eq), H2 saja.
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
from tools.backtest_4h import load_4h
from tools.gov_sim import run_gov, stats

sel = json.loads((HERE / "data" / "universe_selected.json").read_text())["selected"]
panels = load_4h(sel)
panels["universe_fixed"] = sel
cfg = CryptoConfig()
op = panels["open"]
w = cap_position_weights(build_crypto_weights(panels, cfg), 0.20)

GRID = []
for s in (0.05, 0.10, 0.15):
    for f in (0.25, 0.30, 0.35):
        for fl in (0.20, 0.30, 0.40):
            GRID.append((s, f, fl))

rows = []
for s, f, fl in GRID:
    d = run_gov(op, w, total_buy=cfg.total_buy, total_sell=cfg.total_sell,
                capital=cfg.capital, start_dd=s, full_dd=f, floor=fl)
    st = stats(d)
    h2 = stats(d.loc["2024-01-01":])
    rows.append({"start": s, "full": f, "floor": fl,
                 "cagr": round(st["cagr"], 4), "mdd": round(st["mdd"], 4),
                 "calmar": round(st["calmar"], 3), "gov": round(st["gov_mean"], 2),
                 "H2_cagr": round(h2["cagr"], 4), "H2_mdd": round(h2["mdd"], 4)})

df = pd.DataFrame(rows).sort_values("calmar", ascending=False)
pd.set_option("display.width", 200)
print(df.head(15).to_string(index=False))
print("\n=== distribusi (27 kombinasi) ===")
print("calmar min/median/max:", df["calmar"].min(), df["calmar"].median(), df["calmar"].max())
print("cagr  min/median/max:", df["cagr"].min(), df["cagr"].median(), df["cagr"].max())
print("mdd   best/worst    :", df["mdd"].max(), df["mdd"].min())
df.to_csv(HERE / "reports" / "gov_sensitivity.csv", index=False)
print("\nsaved reports/gov_sensitivity.csv")
