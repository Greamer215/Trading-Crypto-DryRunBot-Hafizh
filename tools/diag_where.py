"""Diagnosis: DI MANA return hilang. Dekomposisi gross vs net, kualitas sinyal,
dan kualitas exit. Crypto vs IDX dengan metrik yang sama.

Pertanyaan yang dijawab:
 1. Gross CAGR (tanpa biaya) vs net CAGR -> berapa pp dimakan biaya?
 2. Kualitas sinyal: IC (rank corr skor vs forward return) di horizon re-rank
    dan horizon time-exit, crypto vs IDX.
 3. Kualitas exit: berapa trade keluar karena time-stop vs karena turun ranking,
    dan mana yang merugi.
 4. Beban biaya per trade vs edge gross per trade -> rasio break-even.
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
from logic.core import cap_position_weights, trend_reg_score
from tools.backtest_4h import load_4h


def eq_metrics(eq: pd.Series):
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1
    mdd = float((eq / eq.cummax() - 1).min())
    return cagr, mdd, cagr / abs(mdd), yrs


def trades_detail(open_px, w, total_buy, total_sell, min_order, capital):
    """Per-trade: gross return (harga saja), biaya, net, holding bars."""
    wd = w.shift(1).fillna(0.0)
    out = []
    for sym in open_px.columns:
        h = wd[sym].to_numpy(float)
        px = open_px[sym].to_numpy(float)
        pos, entry_px, entry_i, notional = False, 0.0, 0, 0.0
        for i in range(len(h)):
            now = h[i] > 1e-9
            if now and not pos and np.isfinite(px[i]) and px[i] > 0:
                notional = h[i] * capital
                if notional < min_order:
                    continue
                pos, entry_px, entry_i = True, px[i], i
            elif not now and pos:
                gross = px[i] / entry_px - 1.0
                fee = total_buy + (1 + gross) * total_sell
                out.append({"sym": sym, "bars": i - entry_i, "gross": gross,
                            "fee": fee, "net": gross - fee})
                pos = False
        if pos:
            gross = px[-1] / entry_px - 1.0
            fee = total_buy + (1 + gross) * total_sell
            out.append({"sym": sym, "bars": len(h) - 1 - entry_i, "gross": gross,
                        "fee": fee, "net": gross - fee, "open": True})
    return pd.DataFrame(out)


def ic_report(close, score, mask, horizons):
    """IC = rank corr cross-sectional antara skor di t dan forward return."""
    lp = np.log(close.where(close > 0))
    res = {}
    for hz in horizons:
        fwd = lp.shift(-hz) - lp
        ics = []
        for t in score.index:
            s = score.loc[t][mask.loc[t]].dropna()
            f = fwd.loc[t][mask.loc[t]].dropna()
            common = s.index.intersection(f.index)
            if len(common) < 4:
                continue
            ics.append(s[common].rank().corr(f[common].rank()))
        res[hz] = (float(np.nanmean(ics)), float(np.nanstd(ics)), len(ics))
    return res


# ---------------------------------------------------------------- CRYPTO
sel = json.loads((HERE / "data" / "universe_selected.json").read_text())["selected"]
panels = load_4h(sel)
panels["universe_fixed"] = sel
cfg = CryptoConfig()
op = panels["open"]
w = cap_position_weights(build_crypto_weights(panels, cfg), cfg.position_weight_cap)

# gross (tanpa biaya) vs net
net = trades_detail(op, w, cfg.total_buy, cfg.total_sell, cfg.min_order_idr, cfg.capital)


def sim_equity(open_px, w, tb, ts_, capital):
    wd = w.shift(1).fillna(0.0)
    ret = open_px.pct_change().shift(-1).fillna(0.0)
    W, R = wd.to_numpy(float), ret.to_numpy(float)
    eq = capital
    out = np.empty(len(W))
    held = np.zeros(W.shape[1])
    for i in range(len(W)):
        tgt = W[i]
        dw = tgt - held
        cost = dw[dw > 0].sum() * tb + (-dw[dw < 0]).sum() * ts_
        eq = eq * (1.0 + float(tgt @ R[i]) - cost)
        held = tgt
        out[i] = eq
    return pd.Series(out, index=open_px.index)


gross_eq = sim_equity(op, w, 0.0, 0.0, cfg.capital)
net_eq = sim_equity(op, w, cfg.total_buy, cfg.total_sell, cfg.capital)
gc, gm, gcal, yrs = eq_metrics(gross_eq)
nc, nm, ncal, _ = eq_metrics(net_eq)

print("=" * 74)
print("CRYPTO (10 pair 4h, 2021-01..2026-11, cap 0.12)")
print(f"  GROSS (tanpa biaya) CAGR {gc:7.2%}  MDD {gm:7.2%}  Cal {gcal:5.2f}")
print(f"  NET   (fee resmi)   CAGR {nc:7.2%}  MDD {nm:7.2%}  Cal {ncal:5.2f}")
print(f"  --> biaya memakan {gc - nc:.2f} pp CAGR ({abs((gc-nc)/gc)*100:.0f}% dari gross)")

closed = net[~net.get("open", pd.Series(False, index=net.index)).fillna(False).astype(bool)]
tr_per_yr = len(closed) / yrs
avg_gross = closed["gross"].mean()
avg_fee = closed["fee"].mean()
print(f"\n  trade/6thn {len(closed)} = {tr_per_yr:.1f}/thn | avg gross/trade {avg_gross:+.2%} "
      f"| avg biaya {avg_fee:.2%} | edge bersih {avg_gross - avg_fee:+.2%}")
print(f"  rasio biaya/gross = {avg_fee/abs(avg_gross):.2f}x" if avg_gross != 0 else "")
print(f"  WR gross {float((closed['gross']>0).mean()):.1%}  WR net {float((closed['net']>0).mean()):.1%}")
print(f"  avg hold {closed['bars'].mean():.1f} bar = {closed['bars'].mean()/6:.1f} hari")
print(f"  sum gross {closed['gross'].sum():+.2f} | sum fee {closed['fee'].sum():.2f} "
      f"| sum net {closed['net'].sum():+.2f}")

# IC sinyal crypto
score = trend_reg_score(panels["close"], cfg.signal_lookback)
mask = w.notna() & (panels["close"].notna())
ic = ic_report(panels["close"], score, mask, [10, 44, 88])
print("\n  IC skor tren (cross-sectional, 10 pair):")
for hz, (m, s, n) in ic.items():
    print(f"    horizon {hz:3d} bar ({hz/6:4.1f} hari): IC {m:+.4f} (sd {s:.3f}, n {n})")

print("=" * 74)

# ---------------------------------------------------------------- IDX
IDXD = Path(r"C:\Users\Greamer\Downloads\trading-desk-hafizh")
sys.path.insert(0, str(IDXD))
import importlib

for mod in [m for m in list(sys.modules) if m.split(".")[0] in ("logic", "backtest", "data", "core")]:
    del sys.modules[mod]
sys.path.remove(str(HERE))

from logic import ProductionConfig, build_target_weights
from logic.core import trend_reg_score as idx_score
from backtest.engine import IDX_COST_T1
from data.loader_idx import build_panels_idx

idx_cfg = ProductionConfig()
idx_panels = build_panels_idx(
    membership_path=IDXD / "data" / "kompas100" / "pit" / "membership_pit_loader.csv")
idx_w = build_target_weights(idx_panels, idx_cfg)
idx_open = idx_panels["open"].loc["2007-08-01":]
idx_w = idx_w.reindex(idx_open.index).fillna(0.0)

zero = replace(IDX_COST_T1, buy=0.0, sell=0.0) if hasattr(IDX_COST_T1, "buy") else None
from backtest import engine as idx_engine

idx_gross = idx_engine.run_backtest(idx_open, idx_w, zero, capital=idx_cfg.capital,
                                    start="2007-08-01").equity
idx_net = idx_engine.run_backtest(idx_open, idx_w, IDX_COST_T1, capital=idx_cfg.capital,
                                  start="2007-08-01").equity
ig, igm, igcal, iyrs = eq_metrics(idx_gross)
in_, inm, incal, _ = eq_metrics(idx_net)
print(f"IDX (Kompas100 harian, 2007-2026)")
print(f"  GROSS CAGR {ig:7.2%}  MDD {igm:7.2%}  Cal {igcal:5.2f}")
print(f"  NET   CAGR {in_:7.2%}  MDD {inm:7.2%}  Cal {incal:5.2f}")
print(f"  --> biaya memakan {ig - in_:.2f} pp CAGR ({abs((ig-in_)/ig)*100:.0f}% dari gross)")

i_score = idx_score(idx_panels["close"], idx_cfg.signal_lookback)
i_mask = idx_w.notna() & idx_panels["close"].notna()
i_ic = ic_report(idx_panels["close"], i_score, i_mask, [21, idx_cfg.time_exit_hold])
print("\n  IC skor tren (cross-sectional, ~100 nama):")
for hz, (m, s, n) in i_ic.items():
    print(f"    horizon {hz:3d} bar ({hz:3d} hari): IC {m:+.4f} (sd {s:.3f}, n {n})")
print("=" * 74)