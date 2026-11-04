import json, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, '.')
from logic import CryptoConfig
from tools.backtest_4h import load_4h
sel = json.loads(Path('data/universe_selected.json').read_text())['selected']
panels = load_4h(sel)
cfg = CryptoConfig()
close = panels['close'][sel]
turn = panels['turnover'][sel]
turn = turn.rolling(cfg.universe_lookback).median()
rvol = close.pct_change().rolling(cfg.universe_lookback).std() * np.sqrt(365 * 6)
elig = (turn >= cfg.min_turnover_idr) & (rvol >= cfg.min_vol_ann)
n_elig = elig.sum(axis=1).dropna()
print(f"CRYPTO eligible/bar: mean {n_elig.mean():.1f} dari {len(sel)}, median {n_elig.median():.0f}")
print(f"  bar eligible <=5 (top5 = semua yg lolos): {(n_elig <= 5).mean() * 100:.1f}%")
print(f"  bar eligible <=3 (slot tak penuh):        {(n_elig <= 3).mean() * 100:.1f}%")
print(f"  bar eligible ==10 (benchuh penuh):        {(n_elig == 10).mean() * 100:.1f}%")
