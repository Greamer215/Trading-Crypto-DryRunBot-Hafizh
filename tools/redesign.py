"""Kandidat redesign crypto (izin user: logic boleh diubah untuk UAS).

Diagnosis yang mendasari tiap kandidat:
 - Gate slope tidak punya daya prediksi di crypto (rank corr ~0.00 vs IDX +0.17)
 - Equal-weight 20% diskalakan untuk vol saham -> risiko per nama 2-3x
 - Vol targeting gagal: vol tinggi crypto = fase tren naik, memotong pemenang
 - Drawdown berasal dari crash serempak (korelasi 0.54), bukan dari nama jelek

Kandidat:
 A baseline ETH gate (pembanding)
 B tanpa gate (gate_floor=0, bobot gate diganti 1)
 C tanpa gate + inverse-vol weight (capped), pengganti equal-weight
 D ETH gate + DD governor portofolio (adaptif, bukan prediktif)
 E tanpa gate + DD governor
 F tanpa gate + DD governor + pos cap 0.15

DD governor: kalau equity < peak*(1-d), gross dikali faktor turun bertahap.
Dihitung dari equity baseline (satu iterasi, bukan rekursif penuh) -> dicatat
sebagai aproksimasi di laporan.
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
from tools.backtest_4h import load_4h, run_backtest, trade_stats, metrics

sel = json.loads((HERE / "data" / "universe_selected.json").read_text())["selected"]
panels = load_4h(sel)
panels["universe_fixed"] = sel
cfg = CryptoConfig()


def weights_nogate(panels, cfg, invvol=False):
    """Bobot dasar tanpa gate. invvol=True -> bobot 1/sigma, dinormalisasi ke
    gross yang sama dengan equal-weight (bukan leverage tambahan)."""
    c = replace(cfg, gate_floor=1.0)  # gate dipaksa 1 = dimatikan
    w = build_crypto_weights(panels, c)
    if not invvol:
        return w
    ret = np.log(panels["close"].where(panels["close"] > 0)).diff()
    sig = ret.rolling(cfg.vol_window, min_periods=cfg.vol_window // 2).std() * np.sqrt(365 * 6)
    iv = (1.0 / sig).where(w > 0)
    iv = iv.div(iv.sum(axis=1).replace(0, np.nan), axis=0)
    iv = iv.fillna(0.0)
    n_act = (w > 0).sum(axis=1).replace(0, np.nan)
    gross_target = n_act / cfg.n_top          # gross equal-weight yang setara
    return iv.mul(gross_target, axis=0).fillna(0.0)


def dd_governor(equity: pd.Series, *, start_dd=0.15, full_dd=0.35, floor=0.25) -> pd.Series:
    """Skala gross dari drawdown equity berjalan (causal: pakai peak s/d t)."""
    peak = equity.cummax()
    dd = (equity / peak - 1.0).abs()
    frac = ((dd - start_dd) / max(full_dd - start_dd, 1e-9)).clip(0.0, 1.0)
    return (1.0 - frac * (1.0 - floor)).fillna(1.0)


def bt(w, cfg):
    res = run_backtest(panels, w, cfg, cfg.capital)
    m = metrics(res["equity"])
    ts = trade_stats(panels, w, cfg)
    halves = {}
    for k, (a, b) in {"H1": ("2021-01-01", "2024-01-01"), "H2": ("2024-01-01", None)}.items():
        mh = metrics(res["equity"].loc[a:b])
        halves[k] = (round(mh["cagr"], 4), round(mh["mdd"], 4))
    return res, m, ts, halves


rows = []
w_gate = cap_position_weights(build_crypto_weights(panels, cfg), 0.20)
w_nogate = cap_position_weights(weights_nogate(panels, cfg, invvol=False), 0.20)
w_invvol = cap_position_weights(weights_nogate(panels, cfg, invvol=True), 0.20)

cands = [("A baseline gate ETH", w_gate), ("B tanpa gate", w_nogate),
         ("C tanpa gate + invvol", w_invvol)]

for name, w in cands:
    res, m, ts, h = bt(w, cfg)
    rows.append({"varian": name, "cagr": round(m["cagr"], 4), "mdd": round(m["mdd"], 4),
                 "calmar": round(m["calmar"], 3), "pf": round(ts["profit_factor"], 3),
                 "expo": round(float(w.sum(axis=1).mean()), 3),
                 "H1": h["H1"], "H2": h["H2"], "governor": "tidak"})

# governor: turunkan dari equity baseline masing-masing kandidat
for base_name, w0 in [("D gate ETH + governor", w_gate), ("E tanpa gate + governor", w_nogate)]:
    res0, _, _, _ = bt(w0, cfg)
    gov = dd_governor(res0["equity"])
    w = w0.mul(gov, axis=0)
    res, m, ts, h = bt(w, cfg)
    rows.append({"varian": base_name, "cagr": round(m["cagr"], 4), "mdd": round(m["mdd"], 4),
                 "calmar": round(m["calmar"], 3), "pf": round(ts["profit_factor"], 3),
                 "expo": round(float(w.sum(axis=1).mean()), 3),
                 "H1": h["H1"], "H2": h["H2"], "governor": f"mean {float(gov.mean()):.2f}"})

# F: tanpa gate + governor + cap .15
res0, _, _, _ = bt(w_nogate, cfg)
gov = dd_governor(res0["equity"])
w = cap_position_weights(w_nogate.mul(gov, axis=0), 0.15)
res, m, ts, h = bt(w, cfg)
rows.append({"varian": "F tanpa gate + gov + cap .15", "cagr": round(m["cagr"], 4),
             "mdd": round(m["mdd"], 4), "calmar": round(m["calmar"], 3),
             "pf": round(ts["profit_factor"], 3), "expo": round(float(w.sum(axis=1).mean()), 3),
             "H1": h["H1"], "H2": h["H2"], "governor": "ya, cap .15"})

df = pd.DataFrame(rows)
pd.set_option("display.width", 240)
print(df.to_string(index=False))
df.to_csv(HERE / "reports" / "redesign.csv", index=False)
print("\nsaved reports/redesign.csv")