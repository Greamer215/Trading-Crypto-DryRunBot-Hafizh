"""Validasi freeze baru (score = slope murni):
 1. uji fase penuh (10 offset)
 2. split-half H1 vs H2
 3. cek tie-break: apakah gerombolan skor 0 hilang
 4. per tahun
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from logic import CryptoConfig, build_crypto_weights
from logic.pipeline import crypto_trend_score
from logic.core import cap_position_weights
from tools.backtest_4h import load_4h

sel = json.loads((HERE / "data" / "universe_selected.json").read_text())["selected"]
PA = load_4h(sel)
PA["universe_fixed"] = sel
cfg = CryptoConfig()
KEYS = ("open", "close", "high", "low", "volume", "turnover")


def backtest(w, op):
    wd = w.reindex(index=op.index, columns=op.columns).fillna(0.0).shift(1).fillna(0.0)
    ret = op.pct_change().shift(-1).fillna(0.0)
    W, R = wd.to_numpy(float), ret.to_numpy(float)
    eq, held = cfg.capital, np.zeros(W.shape[1])
    out = np.empty(len(W))
    for i in range(len(W)):
        tgt = W[i]
        dw = tgt - held
        eq *= (1.0 + float(tgt @ R[i]) - (dw[dw > 0].sum() * cfg.total_buy
                                          + (-dw[dw < 0]).sum() * cfg.total_sell))
        held = tgt
        out[i] = eq
    return pd.Series(out, index=op.index)


def m(s):
    yrs = (s.index[-1] - s.index[0]).days / 365.25
    c = (s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1
    d = float((s / s.cummax() - 1).min())
    return c, d, c / abs(d)


# 1. uji fase
cals, cagrs, h2cals = [], [], []
for off in range(cfg.every):
    p = dict(PA)
    for k in KEYS:
        p[k] = PA[k].iloc[off:]
    w = cap_position_weights(build_crypto_weights(p, cfg), cfg.position_weight_cap)
    s = backtest(w, p["open"])
    c, d, cal = m(s)
    cals.append(cal); cagrs.append(c)
    h2cals.append(m(s.loc["2024-01-01":])[2])

cals, cagrs, h2cals = map(np.array, (cals, cagrs, h2cals))
print("=== uji fase (10 offset re-rank) ===")
print(f"Calmar  min {cals.min():.3f}  med {np.median(cals):.3f}  max {cals.max():.3f}  sd {cals.std():.3f}")
print(f"CAGR    min {cagrs.min():.2%}  med {np.median(cagrs):.2%}  max {cagrs.max():.2%}")
print(f"H2 Cal  min {h2cals.min():.3f}  med {np.median(h2cals):.3f}  max {h2cals.max():.3f}")

# 2. split-half penuh
w = cap_position_weights(build_crypto_weights(PA, cfg), cfg.position_weight_cap)
s = backtest(w, PA["open"])
print("\n=== split-half (run penuh) ===")
for name, sl in [("FULL", slice(None)), ("H1 2021-2023", slice("2021-01-01", "2023-12-31")),
                 ("H2 2024-2026", slice("2024-01-01", None))]:
    c, d, cal = m(s.loc[sl])
    print(f"  {name:14s} CAGR {c:7.2%}  MDD {d:7.2%}  Calmar {cal:.3f}")

# 3. tie-break check
score = crypto_trend_score(PA["close"][sel], cfg.signal_lookback)
ok = score.notna() & (PA["close"][sel] > 0)
n_all_nonpos = 0
tot = 0
for t in score.index:
    row = score.loc[t][ok.loc[t]]
    if len(row) < 5:
        continue
    tot += 1
    if float(row.max()) <= 0:
        n_all_nonpos += 1
flat = score.to_numpy().ravel(); flat = flat[np.isfinite(flat)]
print("\n=== cek tie-break ===")
print(f"  bar semua skor <= 0: {n_all_nonpos} / {tot} = {n_all_nonpos/tot*100:.2f}% (sebelumnya 13.9%)")
print(f"  pangsa skor == 0  : {float((flat==0).mean())*100:.2f}% (sebelumnya 50.7%)")
print(f"  skor negatif      : {float((flat<0).mean())*100:.1f}% dari observasi")

# 4. per tahun
print("\n=== per tahun ===")
for yr, g in s.groupby(s.index.year):
    prev = s.loc[:f"{yr-1}-12-31"]
    start_eq = prev.iloc[-1] if len(prev) else s.iloc[0]
    b = PA["close"]["BTCIDR"].loc[str(yr)]
    br = float(b.iloc[-1]/b.iloc[0]-1) if len(b) > 1 else np.nan
    print(f"  {yr}  {g.iloc[-1]/start_eq-1:>8.2%}   BTC {br:>8.2%}")