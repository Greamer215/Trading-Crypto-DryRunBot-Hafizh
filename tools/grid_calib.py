"""Grid kalibrasi lapisan non-core (lookback BEKU 120/40/44).
Grid: min_turnover_idr x min_order_idr x n_top. Metrik: Calmar + PF + WR + n_trades."""
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
    "min_turnover_idr": [2e7, 5e7, 1e8, 2e8],
    "min_order_idr": [25_000, 100_000, 500_000],
    "n_top": [3, 5, 7],
}
rows = []
for to, mo, nt in itertools.product(*GRID.values()):
    cfg = CryptoConfig(min_turnover_idr=to, min_order_idr=mo, n_top=nt)
    w = cap_position_weights(build_crypto_weights(panels, cfg), 0.20)
    res = run_backtest(panels, w, cfg, cfg.capital)
    m = metrics(res["equity"])
    ts = trade_stats(panels, w, cfg)
    rows.append({"turnover": to, "min_order": mo, "n_top": nt,
                 "cagr": round(m["cagr"], 4), "mdd": round(m["mdd"], 4),
                 "calmar": round(m["calmar"], 4), "sharpe": round(m["sharpe"], 3),
                 "n": ts["n_trades"], "wr": round(ts["win_rate"], 3),
                 "pf": round(ts["profit_factor"], 3),
                 "final": round(m["final"])})
df = pd.DataFrame(rows).sort_values("calmar", ascending=False)
print(df.to_string(index=False))
df.to_csv(HERE / "reports" / "grid_calib.csv", index=False)
print("\nsaved reports/grid_calib.csv")
print("\nTOP-3 vs BASE (5e7/25rb/n5):")
base = df[(df.turnover == 5e7) & (df.min_order == 25000) & (df.n_top == 5)].iloc[0]
print(base.to_string())
