"""Uji FASE re-rank: hold_every membekukan bobot pada grid fase tetap yang
ditentukan awal data. Kalau CAGR/Calmar berubah drastis hanya karena grid
digeser beberapa bar, kandidat itu artefak fase, bukan edge.

Metode: untuk tiap `every`, jalankan semua offset 0..every-1 (dengan membuang
offset bar pertama supaya grid fase bergeser), lalu lihat distribusinya.
Kandidat yang baik harus STABIL di semua offset.
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
panels_all = load_4h(sel)
panels_all["universe_fixed"] = sel
base = CryptoConfig()


def run(every, te, offset):
    # geser watchdog: buang `offset` bar pertama -> grid fase hold_every bergeser
    panels = dict(panels_all)
    for k in ("open", "close", "high", "low", "volume", "turnover"):
        panels[k] = panels_all[k].iloc[offset:]
    cfg = replace(base, every=every, time_exit_hold=te)
    w = cap_position_weights(build_crypto_weights(panels, cfg), cfg.position_weight_cap)
    op = panels["open"]
    wd = w.reindex(index=op.index, columns=op.columns).fillna(0.0).shift(1).fillna(0.0)
    ret = op.pct_change().shift(-1).fillna(0.0)
    W, R = wd.to_numpy(float), ret.to_numpy(float)
    eq, held = base.capital, np.zeros(W.shape[1])
    out = np.empty(len(W))
    for i in range(len(W)):
        tgt = W[i]
        dw = tgt - held
        eq *= (1.0 + float(tgt @ R[i]) - (dw[dw > 0].sum() * base.total_buy
                                          + (-dw[dw < 0]).sum() * base.total_sell))
        held = tgt
        out[i] = eq
    s = pd.Series(out, index=op.index)
    yrs = (s.index[-1] - s.index[0]).days / 365.25
    cagr = (s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1
    mdd = float((s / s.cummax() - 1).min())
    return cagr, mdd, cagr / abs(mdd)


rows = []
for every, te in [(10, 88), (30, 132), (40, 132), (60, 88), (60, 132)]:
    res = [run(every, te, off) for off in range(every)]
    c = np.array([r[0] for r in res])
    m = np.array([r[1] for r in res])
    cal = np.array([r[2] for r in res])
    rows.append({
        "every": every, "te": te, "n_off": every,
        "cagr_med": round(float(np.median(c)), 4),
        "cagr_min": round(float(c.min()), 4), "cagr_max": round(float(c.max()), 4),
        "cagr_sd": round(float(c.std()), 4),
        "mdd_med": round(float(np.median(m)), 4),
        "cal_med": round(float(np.median(cal)), 3),
        "cal_min": round(float(cal.min()), 3), "cal_max": round(float(cal.max()), 3),
        "cal_sd": round(float(cal.std()), 3),
    })
    print(f"every {every:2d} te {str(te):3s}: calmar {cal.min():.3f}..{cal.max():.3f} "
          f"(med {np.median(cal):.3f}, sd {cal.std():.3f}) | cagr med {np.median(c):.2%}")

df = pd.DataFrame(rows)
print()
pd.set_option("display.width", 220)
print(df.to_string(index=False))
df.to_csv(HERE / "reports" / "phase_test.csv", index=False)
print("\nsaved reports/phase_test.csv")