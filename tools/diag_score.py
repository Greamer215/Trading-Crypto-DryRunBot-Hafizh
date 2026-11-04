"""Diagnostik trend_reg_score: sifat struktural yang menentukan apakah skor
bisa dioptimasi sama sekali.

Perhatian: score = slope * clip(tstat, 0, inf) dan tstat = slope/se, sehingga
untuk slope > 0 skor = slope^2 / se (konveks, sangat sensitif outlier), dan
untuk slope <= 0 skor = 0 PERSIS. Konsekuensinya: pair yang datar dan pair yang
jatuh bebas mendapat skor yang sama (0). Di IDX ~100 nama hampir selalu ada yang
tren naik; di crypto 10 pair berkorelasi 0.54, semua bisa 0 serentak.

Yang diukur:
 1. berapa bar di mana SEMUA eligible berskor 0 (tidak ada kandidat nyata)?
 2. saat itu terjadi, siapa yang dipilih (tie-break method='first' = urutan kolom)?
 3. berapa kontribusi slope vs tstat terhadap ranking?
 4. seberapa konveks distribusi skor (kontribusi skor teratas)?
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from logic import CryptoConfig
from logic.core import trend_reg_score, _rolling_ols_slope_tstat
from tools.backtest_4h import load_4h

sel = json.loads((HERE / "data" / "universe_selected.json").read_text())["selected"]
panels = load_4h(sel)
cfg = CryptoConfig()
close = panels["close"][sel]

score = trend_reg_score(close, cfg.signal_lookback)
logc = np.log(close.replace(0.0, np.nan))
slope, tstat = _rolling_ols_slope_tstat(logc, cfg.signal_lookback)

# eligible kasar: cukup data
ok = score.notna() & (close > 0)

n_all_zero = 0
n_pos = 0
tie_pick = {}
total_rows = 0
for t in score.index:
    row = score.loc[t][ok.loc[t]]
    if len(row) < 5:
        continue
    total_rows += 1
    if float(row.max()) <= 0:
        n_all_zero += 1
        # siapa yang dipilih: tie-break 'first' -> urutan kolom
        chosen = list(row.index[:5])
        for c in chosen:
            tie_pick[c] = tie_pick.get(c, 0) + 1
    if float(row.max()) > 0:
        n_pos += 1

print(f"bar dengan >=5 kandidat: {total_rows}")
print(f"  semua skor <= 0 (tak ada tren naik): {n_all_zero} bar = {n_all_zero/total_rows*100:.1f}%")
print(f"  ada minimal 1 skor > 0            : {n_pos} bar = {n_pos/total_rows*100:.1f}%")
if tie_pick:
    print("\n  saat semua skor 0, yang dipilih (tie-break = urutan kolom):")
    for c, n in sorted(tie_pick.items(), key=lambda kv: -kv[1]):
        print(f"    {c:9s} {n:5d} bar ({n/max(n_all_zero,1)*100:5.1f}%)")

# berapa bar dengan skor > 0 tapi < 5 kandidat positif
few = 0
for t in score.index:
    row = score.loc[t][ok.loc[t]]
    if len(row) < 5:
        continue
    if 0 < int((row > 0).sum()) < 5:
        few += 1
print(f"\n  bar dengan 1-4 kandidat positif (slot diisi skor 0): {few} = {few/total_rows*100:.1f}%")

# kontribusi slope vs tstat ke ranking
def rankcorr(a, b):
    a = pd.Series(a); b = pd.Series(b)
    m = a.notna() & b.notna()
    if m.sum() < 5:
        return np.nan
    return float(a[m].rank().corr(b[m].rank()))


print("\n--- kontribusi slope vs tstat ke ranking (bar dengan >=5 positif) ---")
comp_s = []
comp_t = []
for t in score.index:
    m = ok.loc[t]
    if int((score.loc[t][m] > 0).sum()) < 6:
        continue
    s = slope.loc[t][m]
    ts = tstat.loc[t][m]
    sc = score.loc[t][m]
    cs, ct = rankcorr(s, sc), rankcorr(ts, sc)
    if np.isfinite(cs):
        comp_s.append(cs)
    if np.isfinite(ct):
        comp_t.append(ct)
print(f"  rank corr(slope, score) : mean {np.nanmean(comp_s):+.3f}  n {len(comp_s)}")
print(f"  rank corr(tstat, score) : mean {np.nanmean(comp_t):+.3f}")

# konkavitas/konveksitas: pangsa skor teratas
print("\n--- konsentrasi skor (bar dengan >=5 positif) ---")
shares = []
for t in score.index:
    row = score.loc[t][ok.loc[t]]
    row = row[row > 0]
    if len(row) < 5:
        continue
    tot = row.sum()
    shares.append(float(row.max() / tot))
print(f"  pangsa skor TERTINGGI dari total: mean {np.mean(shares):.1%} "
      f"(kalau merata 1/5 = 20%)")

# distribusi skor
flat = score.to_numpy().ravel()
flat = flat[np.isfinite(flat)]
print(f"\n  skor: p50 {np.percentile(flat,50):.2e} p90 {np.percentile(flat,90):.2e} "
      f"p99 {np.percentile(flat,99):.2e} max {flat.max():.2e}")
print(f"  pangsa skor=0: {float((flat==0).mean())*100:.1f}%")

# eksponen: apakah skor ~ slope^2?
both = pd.DataFrame({"s": slope.to_numpy().ravel(), "sc": score.to_numpy().ravel()})
both = both[np.isfinite(both["s"]) & np.isfinite(both["sc"]) & (both["s"] > 0) & (both["sc"] > 0)]
if len(both) > 100:
    x = np.log(both["s"]); y = np.log(both["sc"])
    beta = float(np.polyfit(x, y, 1)[0])
    print(f"\n  regresi log(score) ~ log(slope): eksponen {beta:.3f} "
          f"(2.0 = skor setara slope^2/se, makin besar makin konveks)")