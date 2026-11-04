"""Optimasi non-core lanjutan: position cap x filter korelasi x time_exit.
Base: K5 60/80/88 (lolos split-half). Lookback DIKUNCI di 60/80/88."""
import itertools, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
from logic import CryptoConfig, build_crypto_weights
from logic.core import cap_position_weights
from tools.backtest_4h import load_4h, run_backtest, trade_stats, metrics

sel = json.loads((HERE / "data" / "universe_selected.json").read_text())["selected"]
panels = load_4h(sel)
panels["universe_fixed"] = sel

# korelasi 60 bar log-return, pasangan dgn corr > thr: buang yang skor lebih rendah
logp = np.log(panels["close"])
GRID = {"pos_cap": [0.20, 0.12, 0.08], "corr_thr": [1.01, 0.85, 0.70], "te": [88, 132]}

rows = []
for pc, ct, te in itertools.product(*GRID.values()):
    cfg = CryptoConfig(signal_lookback=60, universe_lookback=80, time_exit_hold=te)
    w = cap_position_weights(build_crypto_weights(panels, cfg), pc)
    if ct < 1.0:
        corr = (logp / logp.shift(1)).apply(np.log).rolling(60).corr() if False else None
        ret = np.log(panels["close"] / panels["close"].shift(1))
        rc = ret.rolling(60).corr()
        wv = w.copy()
        for t in w.index[::10]:
            try:
                c = rc.loc[t]
            except KeyError:
                continue
            held = list(wv.columns[wv.loc[t] > 0])
            drop = set()
            for i in range(len(held)):
                for j in range(i + 1, len(held)):
                    try:
                        v = c.loc[held[i], held[j]]
                    except KeyError:
                        continue
                    if pd.notna(v) and v > ct:
                        drop.add(held[j])
            if drop:
                wv.loc[t, list(drop)] = 0.0
        w = wv
    res = run_backtest(panels, w, cfg, cfg.capital)
    m = metrics(res["equity"])
    ts = trade_stats(panels, w, cfg)
    rows.append({"cap": pc, "corr": ct, "te": te, "cagr": round(m["cagr"], 4),
                 "mdd": round(m["mdd"], 4), "calmar": round(m["calmar"], 4),
                 "n": ts["n_trades"], "pf": round(ts["profit_factor"], 3),
                 "expo": round(float((w > 0).sum(axis=1).mean()), 2)})
df = pd.DataFrame(rows).sort_values("calmar", ascending=False)
print(df.to_string(index=False))
df.to_csv(HERE / "reports" / "grid_opt2.csv", index=False)
print("\nsaved reports/grid_opt2.csv")
