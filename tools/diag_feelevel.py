import json, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, '.')
from logic import CryptoConfig, build_crypto_weights
from logic.core import cap_position_weights
from tools.backtest_4h import load_4h

sel = json.loads(Path('data/universe_selected.json').read_text())['selected']
panels = load_4h(sel); panels['universe_fixed'] = sel
cfg = CryptoConfig()
w = cap_position_weights(build_crypto_weights(panels, cfg), cfg.position_weight_cap)
op = panels['open']

def sim(tb, ts_):
    wd = w.shift(1).fillna(0.0)
    ret = op.pct_change().shift(-1).fillna(0.0)
    W, R = wd.to_numpy(float), ret.to_numpy(float)
    eq = cfg.capital; held = np.zeros(W.shape[1]); out = np.empty(len(W))
    for i in range(len(W)):
        tgt = W[i]; dw = tgt - held
        eq *= (1.0 + float(tgt @ R[i]) - (dw[dw>0].sum()*tb + (-dw[dw<0]).sum()*ts_))
        held = tgt; out[i] = eq
    s = pd.Series(out, index=op.index)
    yrs = (s.index[-1]-s.index[0]).days/365.25
    cagr = (s.iloc[-1]/s.iloc[0])**(1/yrs)-1
    mdd = float((s/s.cummax()-1).min())
    return cagr, mdd, cagr/abs(mdd)

print("skenario biaya (round-trip):")
for name, tb, ts_ in [
    ("crypto tanpa biaya", 0.0, 0.0),
    ("crypto biaya IDX (0.1513/0.2513 + slip 0.1%)", 0.001513+0.001, 0.002513+0.001),
    ("crypto biaya resmi Indodax (0.31/0.30 + slip)", cfg.total_buy, cfg.total_sell),
]:
    c, m, cal = sim(tb, ts_)
    print(f"  {name:46s} CAGR {c:7.2%} MDD {m:7.2%} Cal {cal:.2f}")
