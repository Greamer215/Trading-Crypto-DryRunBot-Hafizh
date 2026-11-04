"""Per tahun: apakah edge crypto hanya ada di 2021-2023 (rezim) atau meluruh
karena strategi makin dikenal (decay)?

Baseline beku: gate ETH, cap 0.12, every 10, te 88.
Pembanding: IDX per tahun pada config beku IDX.
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

sel = json.loads((HERE / "data" / "universe_selected.json").read_text())["selected"]
panels = load_4h(sel)
panels["universe_fixed"] = sel
cfg = CryptoConfig()
w = cap_position_weights(build_crypto_weights(panels, cfg), cfg.position_weight_cap)
op = panels["open"]

wd = w.reindex(index=op.index, columns=op.columns).fillna(0.0).shift(1).fillna(0.0)
ret = op.pct_change().shift(-1).fillna(0.0)
W, R = wd.to_numpy(float), ret.to_numpy(float)
eq, held = cfg.capital, np.zeros(W.shape[1])
out, cost_s, expo_s = np.empty(len(W)), np.empty(len(W)), np.empty(len(W))
for i in range(len(W)):
    tgt = W[i]
    dw = tgt - held
    c = dw[dw > 0].sum() * cfg.total_buy + (-dw[dw < 0]).sum() * cfg.total_sell
    eq *= (1.0 + float(tgt @ R[i]) - c)
    held = tgt
    out[i], cost_s[i], expo_s[i] = eq, c, tgt.sum()

eqs = pd.Series(out, index=op.index)
cost = pd.Series(cost_s, index=op.index)
expo = pd.Series(expo_s, index=op.index)

print("CRYPTO per tahun (baseline beku)")
print(f"{'tahun':6s} {'return':>9s} {'biaya':>8s} {'net':>9s} {'expo':>6s} {'BTC':>9s}")
btc = panels["close"]["BTCIDR"]
for yr, g in eqs.groupby(eqs.index.year):
    start_eq = cfg.capital if yr == eqs.index[0].year else eqs.loc[:f"{yr-1}-12-31"].iloc[-1]
    r = g.iloc[-1] / start_eq - 1
    c = float(cost.loc[str(yr)].sum())
    b = btc.loc[str(yr)]
    br = float(b.iloc[-1] / b.iloc[0] - 1) if len(b) > 1 else np.nan
    print(f"{yr:<6d} {r:>9.2%} {c:>8.2%} {r-c:>9.2%} {expo.loc[str(yr)].mean():>6.2f} {br:>9.2%}")

# --- IDX per tahun
IDXD = Path(r"C:\Users\Greamer\Downloads\trading-desk-hafizh")
sys.path.insert(0, str(IDXD))
for m in [m for m in list(sys.modules) if m.split(".")[0] in ("logic", "backtest", "data", "core")]:
    del sys.modules[m]
sys.path.remove(str(HERE))

from logic import ProductionConfig, build_target_weights
from backtest.engine import IDX_COST_T1, run_backtest
from data.loader_idx import build_panels_idx

icfg = ProductionConfig()
ip = build_panels_idx(membership_path=IDXD / "data" / "kompas100" / "pit" / "membership_pit_loader.csv")
iw = build_target_weights(ip, icfg)
res = run_backtest(ip["open"], iw, IDX_COST_T1, capital=icfg.capital, start="2007-08-01")
ie = res.equity
print("\nIDX per tahun")
print(f"{'tahun':6s} {'return':>9s}")
for yr, g in ie.groupby(ie.index.year):
    prev = ie.loc[:f"{yr-1}-12-31"]
    start_eq = prev.iloc[-1] if len(prev) else ie.iloc[0]
    print(f"{yr:<6d} {g.iloc[-1]/start_eq - 1:>9.2%}")