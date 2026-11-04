"""Final: pilih governor robust (bukan argmax), bandingkan dengan/tanpa gate,
dan cetak diagnostik biaya + turnover supaya churn tidak tersembunyi.
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
from tools.gov_sim import run_gov, stats

sel = json.loads((HERE / "data" / "universe_selected.json").read_text())["selected"]
panels = load_4h(sel)
panels["universe_fixed"] = sel
cfg = CryptoConfig()
op = panels["open"]

w_gate = cap_position_weights(build_crypto_weights(panels, cfg), 0.20)
w_nogate = cap_position_weights(
    build_crypto_weights(panels, replace(cfg, gate_floor=1.0)), 0.20)

GOV = dict(start_dd=0.10, full_dd=0.30, floor=0.25)  # titik tengah plateau

rows = []
for name, w, gov in [
    ("baseline gate ETH (tanpa gov)", w_gate, None),
    ("gate ETH + gov 10/30/.25", w_gate, GOV),
    ("tanpa gate + gov 10/30/.25", w_nogate, GOV),
    ("gate ETH + gov + cap .15", w_gate, GOV),
]:
    ww = w
    if name.endswith("cap .15"):
        ww = cap_position_weights(w, 0.15)
    kw = gov if gov else dict(start_dd=1e9, full_dd=1e18)
    d = run_gov(op, ww, total_buy=cfg.total_buy, total_sell=cfg.total_sell,
                capital=cfg.capital, **kw)
    s = stats(d)
    h1 = stats(d.loc[:"2023-12-31"]); h2 = stats(d.loc["2024-01-01":])
    rows.append({
        "varian": name, "cagr": round(s["cagr"], 4), "mdd": round(s["mdd"], 4),
        "calmar": round(s["calmar"], 3), "expo": round(s["expo_mean"], 3),
        "gov": round(s["gov_mean"], 2),
        "fee_x": round(s["fee_drag"], 2),
        "turn_yr": round(float(d["turnover"].sum()) / s["years"], 1),
        "H1_cagr": round(h1["cagr"], 4), "H1_mdd": round(h1["mdd"], 4),
        "H2_cagr": round(h2["cagr"], 4), "H2_mdd": round(h2["mdd"], 4),
    })

df = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(df.to_string(index=False))
df.to_csv(HERE / "reports" / "final_compare.csv", index=False)

# simpan equity varian terpilih untuk dashboard
d = run_gov(op, w_gate, total_buy=cfg.total_buy, total_sell=cfg.total_sell,
            capital=cfg.capital, **GOV)
d.to_csv(HERE / "reports" / "equity_gov.csv")
print("\nsaved reports/final_compare.csv equity_gov.csv")