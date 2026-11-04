"""Uji lever penurun drawdown pada config ETH-gate. Core beku; hanya
position cap, gross cap, kekerasan gate, dan max_scale yang diuji."""
import json, sys
from pathlib import Path
from dataclasses import replace
import pandas as pd
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
from logic import CryptoConfig, build_crypto_weights
from logic.core import cap_position_weights, cap_gross_exposure
from tools.backtest_4h import load_4h, run_backtest, trade_stats, metrics

sel = json.loads((HERE / "data" / "universe_selected.json").read_text())["selected"]
panels = load_4h(sel)
panels["universe_fixed"] = sel

VARIANTS = [
    ("BASE (cap .20, gate b.5 k4000, scale 1.25)", {}, 0.20, None),
    ("pos cap .15", {}, 0.15, None),
    ("pos cap .12", {}, 0.12, None),
    ("pos cap .10", {}, 0.10, None),
    ("gross cap .80", {}, 0.20, 0.80),
    ("gross cap .60", {}, 0.20, 0.60),
    ("gross cap .60 + pos .15", {}, 0.15, 0.60),
    ("gate b.35 k6000", {"gate_b": 0.35, "gate_k": 6000.0}, 0.20, None),
    ("gate b.20 k8000", {"gate_b": 0.20, "gate_k": 8000.0}, 0.20, None),
    ("max_scale 1.0 (tanpa avg-down)", {"max_scale": 1.0}, 0.20, None),
    ("gate keras + pos .15", {"gate_b": 0.35, "gate_k": 6000.0}, 0.15, None),
    ("gate keras + gross .70", {"gate_b": 0.35, "gate_k": 6000.0}, 0.20, 0.70),
]
rows = []
for name, kw, pc, gc in VARIANTS:
    cfg = replace(CryptoConfig(), **kw)
    w = cap_position_weights(build_crypto_weights(panels, cfg), pc)
    w = cap_gross_exposure(w, gc)
    res = run_backtest(panels, w, cfg, cfg.capital)
    m = metrics(res["equity"])
    ts = trade_stats(panels, w, cfg)
    h = {}
    for k, (s, e) in {"H1": ("2021-01-01", "2024-01-01"), "H2": ("2024-01-01", None)}.items():
        mh = metrics(res["equity"].loc[s:e])
        h[k] = (round(mh["cagr"], 4), round(mh["mdd"], 4), round(mh["calmar"], 3))
    rows.append({"varian": name, "cagr": round(m["cagr"], 4), "mdd": round(m["mdd"], 4),
                 "calmar": round(m["calmar"], 3), "pf": round(ts["profit_factor"], 3),
                 "n": ts["n_trades"], "expo": round(float(w.sum(axis=1).mean()), 3),
                 "H1_cagr": h["H1"][0], "H1_mdd": h["H1"][1], "H2_cagr": h["H2"][0],
                 "H2_mdd": h["H2"][1]})
df = pd.DataFrame(rows).sort_values("calmar", ascending=False)
pd.set_option("display.width", 200)
print(df.to_string(index=False))
df.to_csv(HERE / "reports" / "grid_dd.csv", index=False)
print("\nsaved reports/grid_dd.csv")
