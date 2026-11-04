"""Perbandingan setara: setiap kandidat diukur full-sample DAN di H2 (2024-2026),
karena kandidat yang hanya menang di H1 adalah artefak rezim bull 2021.
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
from tools.gov_peakvar import run, stats

sel = json.loads((HERE / "data" / "universe_selected.json").read_text())["selected"]
panels = load_4h(sel)
panels["universe_fixed"] = sel
cfg = CryptoConfig()
op = panels["open"]
w_raw = build_crypto_weights(panels, cfg)

CAND = [
    ("A base cap .20", cap_position_weights(w_raw, 0.20), dict(start_dd=1e9, full_dd=1e18), None),
    ("B cap .15", cap_position_weights(w_raw, 0.15), dict(start_dd=1e9, full_dd=1e18), None),
    ("C cap .12", cap_position_weights(w_raw, 0.12), dict(start_dd=1e9, full_dd=1e18), None),
    ("D cap .10", cap_position_weights(w_raw, 0.10), dict(start_dd=1e9, full_dd=1e18), None),
    ("E cap .20 + gov P_all", cap_position_weights(w_raw, 0.20), {}, None),
    ("F cap .15 + gov P_all", cap_position_weights(w_raw, 0.15), {}, None),
]

rows = []
for name, w, kw, _ in CAND:
    d = run(op, w, total_buy=cfg.total_buy, total_sell=cfg.total_sell,
            capital=cfg.capital, **kw)
    s = stats(d)
    h1 = stats(d.loc[:"2023-12-31"]); h2 = stats(d.loc["2024-01-01":])
    rows.append({"varian": name, "cagr": round(s["cagr"], 4), "mdd": round(s["mdd"], 4),
                 "calmar": round(s["calmar"], 3), "expo": round(s["expo"], 3),
                 "H1_cal": round(h1["calmar"], 3), "H2_cagr": round(h2["cagr"], 4),
                 "H2_mdd": round(h2["mdd"], 4), "H2_cal": round(h2["calmar"], 3),
                 "H2_expo": round(h2["expo"], 3)})

df = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(df.to_string(index=False))
df.to_csv(HERE / "reports" / "cand_equal.csv", index=False)
print("\nsaved reports/cand_equal.csv")