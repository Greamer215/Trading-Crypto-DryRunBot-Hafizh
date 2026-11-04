import json, sys
import numpy as np, pandas as pd
sys.path.insert(0, '.')
from logic import CryptoConfig
from logic.pipeline import crypto_trend_score
from tools.backtest_4h import load_4h

sel = json.loads(open('data/universe_selected.json').read())['selected']
P = load_4h(sel)
cfg = CryptoConfig()
sc = crypto_trend_score(P['close'][sel], cfg.signal_lookback)
ok = sc.notna() & (P['close'][sel] > 0)

dup_all, n = 0, 0
for t in sc.index:
    row = sc.loc[t][ok.loc[t]]
    if len(row) < 5:
        continue
    n += 1
    top5 = row.nlargest(5)
    if top5.duplicated().any():
        dup_all += 1
print(f"bar diperiksa: {n}")
print(f"bar dengan TIE di top-5 (tie-break aktif): {dup_all} = {dup_all/n*100:.3f}%")

cnt, dist = 0, 0
for t in sc.index:
    row = sc.loc[t][ok.loc[t]]
    if len(row) < 5 or row.max() > 0:
        continue
    cnt += 1
    if row.nlargest(5).nunique() == 5:
        dist += 1
print(f"bar semua <=0: {cnt}; top-5 nilai distinct: {dist} ({dist/max(cnt,1)*100:.1f}%)")
flat = sc.to_numpy().ravel()
flat = flat[np.isfinite(flat)]
print(f"skor == 0: {float((flat==0).mean())*100:.2f}%  |  skor negatif: {float((flat<0).mean())*100:.1f}%")