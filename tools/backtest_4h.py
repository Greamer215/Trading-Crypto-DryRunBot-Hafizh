"""Backtest penuh UAS: algo frozen (lookback BEKU) di 10 pair universe 4h.

Biaya: taker 0.31%/0.30% all-in (halaman resmi Indodax, lebih mahal dari
api/pairs 0.20%; akses 2026-11-04) + slip 10bps placeholder.
REALISTIS crypto: eksekusi open next bar, tanpa lot, min order Rp25rb.
Gate proxy: ETHIDR (adapter crypto 24/7, bukan IHSG). Cap posisi: config.
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from logic import CryptoConfig, build_crypto_weights
from logic.core import cap_position_weights


def load_4h(symbols):
    frames = {}
    for sym in symbols:
        p = HERE / "data" / "indodax_4h" / f"{sym}.csv"
        df = pd.read_csv(p, parse_dates=["t"])
        df = df.set_index("t").sort_index()
        df = df[~df.index.duplicated(keep="first")]
        df = df[df["c"].notna() & (df["c"] > 0)]
        df = df.rename(columns={"o": "Open", "h": "High", "l": "Low",
                                "c": "Close", "v": "Volume"})
        df["turnover_idr"] = df["Close"] * df["Volume"]
        frames[sym] = df
    idx = None
    for df in frames.values():
        idx = df.index if idx is None else idx.union(df.index)
    def stack(col):
        return pd.DataFrame({s: df[col].reindex(idx) for s, df in frames.items()})
    panels = {"open": stack("Open"), "high": stack("High"), "low": stack("Low"),
              "close": stack("Close"), "volume": stack("Volume"),
              "turnover": stack("turnover_idr")}
    keep = panels["close"].notna().sum(axis=1) >= 3
    for k in panels:
        panels[k] = panels[k].loc[keep]
    return panels


def run_backtest(panels, w, cfg: CryptoConfig, capital: float, start=None):
    open_px = panels["open"].sort_index()
    w = w.reindex(index=open_px.index, columns=open_px.columns).fillna(0.0)
    if start:
        open_px = open_px.loc[start:]; w = w.loc[start:]
    ret = open_px.pct_change().shift(-1).fillna(0.0)
    held = w.shift(1).fillna(0.0)
    gross = (held * ret).sum(axis=1)
    dw = held.diff().fillna(held.iloc[0])
    cost = (dw.clip(lower=0.0) * cfg.total_buy).sum(axis=1) + \
           ((-dw).clip(lower=0.0) * cfg.total_sell).sum(axis=1)
    net = gross - cost
    equity = capital * (1.0 + net).cumprod()
    return {"equity": equity, "net": net, "gross": gross, "cost": cost,
            "turnover": dw.abs().sum(axis=1), "held": held}


def trade_stats(panels, w, cfg: CryptoConfig):
    """Trade tertutup: run posisi per pair; fee per ubah posisi; min Rp25rb."""
    open_px = panels["open"]
    held = w.shift(1).fillna(0.0)
    trades = []
    for sym in open_px.columns:
        h, px = held[sym].values, open_px[sym].values
        pos = False; eqty = enot = ecost = 0.0; ev = ed = None
        for i in range(len(h)):
            now = h[i] > 1e-9
            if now and not pos:
                if h[i] * 100_000_000 < cfg.min_order_idr:
                    continue
                pos = True; ev, ed = px[i], i
                eqty = (h[i] * 100_000_000) / px[i]
                enot = eqty * px[i]; ecost = enot * cfg.total_buy
            elif not now and pos:
                xnot = eqty * px[i]
                fee = ecost + xnot * cfg.total_sell
                trades.append({"sym": sym, "entry": ed, "exit": i,
                               "pnl": xnot - enot - fee, "fee": fee,
                               "ret": xnot / enot - 1})
                pos = False
        if pos and np.isfinite(px[-1]):
            xnot = eqty * px[-1]
            fee = ecost + xnot * cfg.total_sell
            trades.append({"sym": sym, "entry": ed, "exit": len(h) - 1,
                           "pnl": xnot - enot - fee, "fee": fee,
                           "ret": xnot / enot - 1, "open": True})
    df = pd.DataFrame(trades)
    if "open" in df:
        cl = df[~df["open"].fillna(False).astype(bool)]
    else:
        cl = df
    win = cl[cl["pnl"] > 0]; loss = cl[cl["pnl"] <= 0]
    gp, gl = win["pnl"].sum(), -loss["pnl"].sum()
    return {"n_trades": len(cl), "n_open": int(df.get("open", pd.Series(False)).sum()),
            "win_rate": len(win) / max(len(cl), 1),
            "profit_factor": gp / gl if gl > 0 else float("nan"),
            "avg_win": win["pnl"].mean() if len(win) else 0.0,
            "avg_loss": loss["pnl"].mean() if len(loss) else 0.0,
            "net_pnl": cl["pnl"].sum(), "fee": cl["fee"].sum(),
            "cost_share": cl["fee"].sum() / gp if gp > 0 else float("nan"),
            "by_sym": df.groupby("sym")["pnl"].sum().to_dict()}


def metrics(eq: pd.Series):
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1
    mdd = float((eq / eq.cummax() - 1).min())
    n = eq.pct_change().dropna()
    per = len(eq) / yrs  # bar per tahun (4h = 2190)
    return {"cagr": cagr, "mdd": mdd, "calmar": cagr / abs(mdd),
            "sharpe": float(n.mean() / n.std() * np.sqrt(per)) if n.std() > 0 else 0.0,
            "years": yrs, "final": float(eq.iloc[-1])}


def main():
    sel = json.loads((HERE / "data" / "universe_selected.json").read_text())["selected"]
    print(f"universe: {sel}")
    cfg = CryptoConfig()
    panels = load_4h(sel)
    panels["universe_fixed"] = sel
    print(f"range: {panels['close'].index[0]} .. {panels['close'].index[-1]}, bar: {len(panels['close'])}")
    w = build_crypto_weights(panels, cfg)
    w = cap_position_weights(w, cfg.position_weight_cap)
    res = run_backtest(panels, w, cfg, cfg.capital)
    m = metrics(res["equity"])
    ts = trade_stats(panels, w, cfg)
    btc = panels["close"]["BTCIDR"]
    btc_ret = float(btc.iloc[-1] / btc.loc[btc.first_valid_index()] - 1)
    print(f"\nSTRATEGI 4h frozen: CAGR {m['cagr']:.2%} MDD {m['mdd']:.2%} Cal {m['calmar']:.2f} Sharpe {m['sharpe']:.2f}")
    print(f"  equity Rp{cfg.capital:,.0f} -> Rp{m['final']:,.0f} ({m['years']:.1f} thn)")
    print(f"  trade {ts['n_trades']} (+{ts['n_open']} terbuka) WR {ts['win_rate']:.1%} PF {ts['profit_factor']:.2f}")
    print(f"  avg win Rp{ts['avg_win']:,.0f} avg loss Rp{ts['avg_loss']:,.0f}")
    print(f"  fee Rp{ts['fee']:,.0f} = {ts['cost_share']:.1%} laba kotor")
    print(f"  BENCH buy-hold BTC: {btc_ret:.2%}")
    print(f"  PnL per pair: " + ", ".join(f"{k} {v/1e6:+.1f}jt" for k, v in sorted(ts['by_sym'].items(), key=lambda kv: -kv[1])))
    outdir = HERE / "reports"
    outdir.mkdir(exist_ok=True)
    res["equity"].to_csv(outdir / "equity_4h.csv", header=["equity"])
    (outdir / "summary_4h.json").write_text(json.dumps({**m, **{k: v for k, v in ts.items() if k != "by_sym"}, "bench_btc": btc_ret}, indent=1, default=str))
    print("\nsaved reports/equity_4h.csv summary_4h.json")


if __name__ == "__main__":
    main()
