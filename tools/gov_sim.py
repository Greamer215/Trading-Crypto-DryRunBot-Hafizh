"""Backtest dengan DD governor SELF-CONSISTENT: equity disimulasikan bar demi bar,
governor membaca equity realisasi (yang memang bisa diketahui bot live).

Kenapa perlu: versi pertama memakai governor dari equity baseline lalu
diterapkan ke bobot. Itu tidak konsisten (equity baseline bukan equity hasil
governor) dan menggelembungkan PF karena trade_stats menghitung PnL dari
notional penuh saat posisi sudah dikecilkan.

Di sini tidak ada trade_stats terpisah: PnL dihitung dari arus kas aktual,
jadi angkanya konsisten dengan bobot yang benar-benar dipegang.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))


def run_gov(open_px: pd.DataFrame, w_base: pd.DataFrame, *, total_buy: float,
            total_sell: float, capital: float, start_dd: float = 0.15,
            full_dd: float = 0.35, floor: float = 0.25) -> pd.DataFrame:
    """Simulasi bar-demi-bar. Governor = f(drawdown equity realisasi).

    w_base diasumsikan sudah final (gate/ranking/cap). Governor hanya men-scale
    gross. Setiap bar: hitung skala dari equity s/d t, bentuk bobot efektif,
    lalu bayar biaya transisi dan terima return.
    """
    px = open_px.sort_index()
    wb = w_base.reindex(index=px.index, columns=px.columns).fillna(0.0)
    # Target yang dieksekusi di open t adalah bobot yang DIPUTUSKAN di close t-1
    # (sama dengan w.shift(1) di backtest_4h). Tanpa shift ini ada look-ahead.
    wd = wb.shift(1).fillna(0.0)
    ret = px.pct_change().shift(-1).fillna(0.0)

    # numpy: loop bar tetap perlu (equity rekursif), tapi tanpa overhead .loc
    W = wd.to_numpy(dtype=float)
    R = ret.to_numpy(dtype=float)
    T, N = W.shape

    eq = capital
    peak = capital
    held = np.zeros(N)
    out_eq = np.empty(T)
    out_gov = np.empty(T)
    out_gross = np.empty(T)
    out_cost = np.empty(T)
    out_expo = np.empty(T)
    out_turn = np.empty(T)
    span = max(full_dd - start_dd, 1e-12)

    for i in range(T):
        dd = 1.0 - eq / peak
        frac = min(max((dd - start_dd) / span, 0.0), 1.0)
        gov = 1.0 - frac * (1.0 - floor)

        target = W[i] * gov
        dw = target - held
        buys = dw[dw > 0].sum()
        sells = -dw[dw < 0].sum()
        cost = buys * total_buy + sells * total_sell
        gross_ret = float(target @ R[i])
        eq = eq * (1.0 + gross_ret - cost)
        peak = max(peak, eq)
        held = target

        out_eq[i] = eq
        out_gov[i] = gov
        out_gross[i] = gross_ret
        out_cost[i] = cost
        out_expo[i] = target.sum()
        out_turn[i] = buys + sells

    return pd.DataFrame({"equity": out_eq, "gov": out_gov, "gross": out_gross,
                         "cost": out_cost, "expo": out_expo,
                         "turnover": out_turn}, index=px.index)


def stats(df: pd.DataFrame):
    eq = df["equity"]
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1
    mdd = float((eq / eq.cummax() - 1).min())
    return {"cagr": cagr, "mdd": mdd, "calmar": cagr / abs(mdd), "years": yrs,
            "final": float(eq.iloc[-1]), "gov_mean": float(df["gov"].mean()),
            "expo_mean": float(df["expo"].mean()),
            "fee_drag": float(df["cost"].sum())}


if __name__ == "__main__":
    from logic import CryptoConfig, build_crypto_weights
    from logic.core import cap_position_weights
    from tools.backtest_4h import load_4h, run_backtest, metrics

    sel = json.loads((HERE / "data" / "universe_selected.json").read_text())["selected"]
    panels = load_4h(sel)
    panels["universe_fixed"] = sel
    cfg = CryptoConfig()
    op = panels["open"]

    w_gate = cap_position_weights(build_crypto_weights(panels, cfg), 0.20)

    # pembanding tanpa governor, lewat simulasi yang sama (kontrol metodologi)
    ctrl = run_gov(op, w_gate, total_buy=cfg.total_buy, total_sell=cfg.total_sell,
                   capital=cfg.capital, start_dd=1e9, full_dd=1e18)
    print("kontrol (governor mati) :", {k: round(v, 4) for k, v in stats(ctrl).items()})
    r0 = run_backtest(panels, w_gate, cfg, cfg.capital)
    m0 = metrics(r0["equity"])
    print("run_backtest lama       :", {"cagr": round(m0["cagr"], 4), "mdd": round(m0["mdd"], 4),
                                        "calmar": round(m0["calmar"], 3)})

    for name, kw in [("gov 15/35 floor .25", {}),
                     ("gov 10/30 floor .30", dict(start_dd=0.10, full_dd=0.30, floor=0.30)),
                     ("gov 20/40 floor .40", dict(start_dd=0.20, full_dd=0.40, floor=0.40))]:
        d = run_gov(op, w_gate, total_buy=cfg.total_buy, total_sell=cfg.total_sell,
                    capital=cfg.capital, **kw)
        s = stats(d)
        h1 = stats(d.loc[:"2023-12-31"]); h2 = stats(d.loc["2024-01-01":])
        print(f"{name}: CAGR {s['cagr']:.2%} MDD {s['mdd']:.2%} Cal {s['calmar']:.3f} "
              f"gov {s['gov_mean']:.2f} expo {s['expo_mean']:.3f} | "
              f"H1 {h1['cagr']:.2%}/{h1['mdd']:.2%} H2 {h2['cagr']:.2%}/{h2['mdd']:.2%}")
        d.to_csv(HERE / "reports" / f"gov_{name.split()[1].replace('/', '_')}.csv")