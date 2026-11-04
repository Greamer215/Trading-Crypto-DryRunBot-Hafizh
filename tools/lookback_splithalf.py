"""Validasi split-half kandidat lookback vs base: menang di KEDUA paruh atau ditolak."""
import json, sys
from pathlib import Path
import pandas as pd
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
from logic import CryptoConfig, build_crypto_weights
from logic.core import cap_position_weights
from tools.backtest_4h import load_4h, run_backtest, trade_stats, metrics

sel = json.loads((HERE / "data" / "universe_selected.json").read_text())["selected"]
panels = load_4h(sel)
panels["universe_fixed"] = sel
mid = "2024-01-01"

CAND = [
    ("BASE 120/40/44", dict(signal_lookback=120, universe_lookback=40, time_exit_hold=44)),
    ("K1 90/80/44", dict(signal_lookback=90, universe_lookback=80, time_exit_hold=44)),
    ("K2 90/40/44", dict(signal_lookback=90, universe_lookback=40, time_exit_hold=44)),
    ("K3 90/20/44", dict(signal_lookback=90, universe_lookback=20, time_exit_hold=44)),
    ("K4 90/80/22", dict(signal_lookback=90, universe_lookback=80, time_exit_hold=22)),
    ("K5 60/80/88", dict(signal_lookback=60, universe_lookback=80, time_exit_hold=88)),
]
rows = []
for name, kw in CAND:
    cfg = CryptoConfig(**kw)
    w = cap_position_weights(build_crypto_weights(panels, cfg), 0.20)
    for half, (s, e) in {"H1 21-23": ("2021-01-01", mid), "H2 24-26": (mid, None)}.items():
        res = run_backtest(panels, w, cfg, cfg.capital, start=s)
        eq = res["equity"].loc[:e] if e else res["equity"]
        m = metrics(eq)
        pnl = {k: (v.loc[:e] if e else v) for k, v in panels.items() if isinstance(v, pd.DataFrame)}
        ts = trade_stats(pnl, w.loc[:e] if e else w, cfg)
        rows.append({"cfg": name, "half": half, "cagr": round(m["cagr"], 4),
                     "mdd": round(m["mdd"], 4), "calmar": round(m["calmar"], 3),
                     "n": ts["n_trades"], "pf": round(ts["profit_factor"], 3)})
df = pd.DataFrame(rows)
print(df.pivot(index="cfg", columns="half", values="cagr").round(4).to_string())
print()
print(df.pivot(index="cfg", columns="half", values="calmar").round(3).to_string())
print()
print(df.pivot(index="cfg", columns="half", values="pf").round(3).to_string())
df.to_csv(HERE / "reports" / "lookback_splithalf.csv", index=False)
print("\nsaved reports/lookback_splithalf.csv")
