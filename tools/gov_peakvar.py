"""Uji varian governor yang BISA PULIH.

Cacat versi 1: DD diukur dari puncak sepanjang sejarah. Setelah crash dalam,
ekuitas yang dikecilkan sulit membuat puncak baru -> governor terkunci di lantai
-> strategi kekurangan investasi permanen (eksposur 0.15, H2 CAGR ~1%).

Varian yang diuji:
 P_all  : peak sepanjang sejarah (versi 1, pembanding)
 P_365  : peak bergulir 365 hari
 P_180  : peak bergulir 180 hari
 P_90   : peak bergulir 90 hari
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

BARS_PER_DAY = 6


def run(open_px, w_base, *, total_buy, total_sell, capital,
        start_dd=0.10, full_dd=0.30, floor=0.25, peak_bars=None):
    px = open_px.sort_index()
    wd = w_base.reindex(index=px.index, columns=px.columns).fillna(0.0).shift(1).fillna(0.0)
    ret = px.pct_change().shift(-1).fillna(0.0)
    W, R = wd.to_numpy(float), ret.to_numpy(float)
    T, N = W.shape

    eq = capital
    held = np.zeros(N)
    eqs = np.empty(T)
    govs = np.empty(T)
    expos = np.empty(T)
    turns = np.empty(T)
    span = max(full_dd - start_dd, 1e-12)
    eq_hist = []

    for i in range(T):
        eq_hist.append(eq)
        if peak_bars is None:
            peak = max(eq_hist)
        else:
            peak = max(eq_hist[-peak_bars:])
        dd = 1.0 - eq / peak if peak > 0 else 0.0
        frac = min(max((dd - start_dd) / span, 0.0), 1.0)
        gov = 1.0 - frac * (1.0 - floor)

        target = W[i] * gov
        dw = target - held
        buys, sells = dw[dw > 0].sum(), -dw[dw < 0].sum()
        eq = eq * (1.0 + float(target @ R[i]) - (buys * total_buy + sells * total_sell))
        held = target
        eqs[i], govs[i], expos[i], turns[i] = eq, gov, target.sum(), buys + sells

    return pd.DataFrame({"equity": eqs, "gov": govs, "expo": expos,
                         "turnover": turns}, index=px.index)


def stats(d):
    eq = d["equity"]
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1
    mdd = float((eq / eq.cummax() - 1).min())
    return {"cagr": cagr, "mdd": mdd, "calmar": cagr / abs(mdd), "years": yrs,
            "expo": float(d["expo"].mean()), "gov": float(d["gov"].mean()),
            "turn": float(d["turnover"].sum()) / yrs, "final": float(eq.iloc[-1])}


if __name__ == "__main__":
    sel = json.loads((HERE / "data" / "universe_selected.json").read_text())["selected"]
    panels = load_4h(sel)
    panels["universe_fixed"] = sel
    cfg = CryptoConfig()
    op = panels["open"]
    w = cap_position_weights(build_crypto_weights(panels, cfg), 0.20)

    rows = []
    VAR = [("tanpa gov", None, dict(start_dd=1e9, full_dd=1e18)),
           ("P_all (v1)", None, {}),
           ("P_365", 365 * BARS_PER_DAY, {}),
           ("P_180", 180 * BARS_PER_DAY, {}),
           ("P_90", 90 * BARS_PER_DAY, {}),
           ("P_90 floor .35", 90 * BARS_PER_DAY, dict(floor=0.35)),
           ("P_180 floor .35", 180 * BARS_PER_DAY, dict(floor=0.35))]

    for name, pb, kw in VAR:
        d = run(op, w, total_buy=cfg.total_buy, total_sell=cfg.total_sell,
                capital=cfg.capital, peak_bars=pb, **kw)
        s = stats(d)
        h1 = stats(d.loc[:"2023-12-31"]); h2 = stats(d.loc["2024-01-01":])
        rows.append({"varian": name, "cagr": round(s["cagr"], 4), "mdd": round(s["mdd"], 4),
                     "calmar": round(s["calmar"], 3), "expo": round(s["expo"], 3),
                     "gov": round(s["gov"], 2), "turn": round(s["turn"], 1),
                     "H1_cagr": round(h1["cagr"], 4), "H1_mdd": round(h1["mdd"], 4),
                     "H2_cagr": round(h2["cagr"], 4), "H2_mdd": round(h2["mdd"], 4)})

    df = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print(df.to_string(index=False))
    df.to_csv(HERE / "reports" / "gov_peakvar.csv", index=False)
    print("\nsaved reports/gov_peakvar.csv")