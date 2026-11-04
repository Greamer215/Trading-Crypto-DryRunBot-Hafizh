"""Grid lookback (eksplorasi atas permintaan user): signal_lookback x universe_lookback
x time_exit_hold. Core beku, hanya angka. Validasi split-half menyusul."""
import itertools, json, sys
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

GRID = {
    "signal_lookback": [60, 90, 120, 180],
    "universe_lookback": [20, 40, 80],
    "time_exit_hold": [22, 44, 88],
}
rows = []
for sl, ul, te in itertools.product(*GRID.values()):
    cfg = CryptoConfig(signal_lookback=sl, universe_lookback=ul, time_exit_hold=te)
    w = cap_position_weights(build_crypto_weights(panels, cfg), 0.20)
    res = run_backtest(panels, w, cfg, cfg.capital)
    m = metrics(res["equity"])
    ts = trade_stats(panels, w, cfg)
    rows.append({"sl": sl, "ul": ul, "te": te,
                 "cagr": round(m["cagr"], 4), "mdd": round(m["mdd"], 4),
                 "calmar": round(m["calmar"], 4), "n": ts["n_trades"],
                 "pf": round(ts["profit_factor"], 3)})
df = pd.DataFrame(rows).sort_values("calmar", ascending=False)
print(df.to_string(index=False))
df.to_csv(HERE / "reports" / "grid_lookback.csv", index=False)
print("\nBASE (120/40/44):")
print(df[(df.sl == 120) & (df.ul == 40) & (df.te == 44)].to_string(index=False))
