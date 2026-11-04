"""Backtest ulang pada jendela 10 hari forward (syarat rubrik: sinyal identik
candle demi candle). Jalankan setelah forward selesai: python tools/backtest_window.py <start> <end>"""
import json, sys
from pathlib import Path
import pandas as pd
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
from logic import CryptoConfig, build_crypto_weights
from logic.core import cap_position_weights
from tools.backtest_4h import load_4h, run_backtest, trade_stats, metrics

START, END = sys.argv[1], sys.argv[2]  # mis. 2026-11-04 2026-11-14
sel = json.loads((HERE / "data" / "universe_selected.json").read_text())["selected"]
panels = load_4h(sel)
panels["universe_fixed"] = sel
cfg = CryptoConfig()
w = cap_position_weights(build_crypto_weights(panels, cfg), cfg.position_weight_cap).loc[START:END]
res = run_backtest(panels, w, cfg, cfg.capital, start=START)
m = metrics(res["equity"].loc[:END] if END else res["equity"])
ts = trade_stats(panels, w, cfg)
out = {"window": [START, END], "cagr_window": m["cagr"], "mdd": m["mdd"],
       "return_total": m["final"] / cfg.capital - 1, "n_trades": ts["n_trades"],
       "pf": ts["profit_factor"], "wr": ts["win_rate"]}
(HERE / "reports" / "backtest_forward_window.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
