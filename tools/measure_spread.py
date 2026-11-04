"""Hitung spread terukur dari snapshot untuk dipakai di backtest.

Soal p.2: backtest sebelum freeze memakai median spread & slippage dari
snapshot yang terkumpul. Skrip ini menghasilkan reports/spread_measured.json.

Slippage diestimasi dari kemiringan book: selisih harga level 2 vs level 1
relatif ke mid, sebagai proxy biaya menembus satu level.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from bot.util import indodax_depth

SNAP = HERE / "data" / "book_snapshots"
OUT = HERE / "reports" / "spread_measured.json"
WIB = timezone(timedelta(hours=7))


def from_snapshots():
    """Median spread per pair dari semua snapshot CSV yang ada."""
    files = sorted(SNAP.glob("*.csv"))
    if not files:
        return {}
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df = df[df["spread"].notna() & (df["spread"] > 0) & (df["spread"] < 0.2)]
    out = {}
    for pair, g in df.groupby("pair"):
        out[pair] = {
            "spread_median": float(g["spread"].median()),
            "spread_p90": float(g["spread"].quantile(0.90)),
            "n_snapshots": int(len(g)),
        }
    return out, df


def slippage_from_depth(symbols):
    """Proxy slippage: (harga level2 - level1)/level1 per sisi, median.

    Diukur live sekarang karena inilah kedalaman yang akan dihadapi backtest
    saat mengisi order tipikal (<= 12% modal per pair = Rp12jt).
    """
    out = {}
    for sym in symbols:
        try:
            d = indodax_depth(sym.lower())
            asks, bids = d.get("sell") or [], d.get("buy") or []
            if len(asks) < 2 or len(bids) < 2:
                continue
            a1, a2 = float(asks[0][0]), float(asks[1][0])
            b1, b2 = float(bids[0][0]), float(bids[1][0])
            out[sym] = {
                "slip_buy": (a2 - a1) / a1,       # biaya naik satu level ask
                "slip_sell": (b1 - b2) / b1,      # biaya turun satu level bid
                "ask_l1_idr": a1 * float(asks[0][1]),
                "bid_l1_idr": b1 * float(bids[0][1]),
            }
        except Exception as e:
            print(f"  {sym}: gagal {e}")
    return out


def main():
    sel = json.loads((HERE / "data" / "universe_selected.json").read_text())["selected"]
    res = from_snapshots()
    if not res:
        print("BELUM ADA snapshot. Jalankan tools/collect_book.py dulu.")
        return
    spread, df = res

    slip = slippage_from_depth(sel)

    merged = {}
    for sym in sel:
        s = spread.get(sym, {})
        l = slip.get(sym, {})
        if not s:
            continue
        merged[sym] = {
            **s,
            "slip_buy": l.get("slip_buy"),
            "slip_sell": l.get("slip_sell"),
        }

    all_spread = [v["spread_median"] for v in merged.values()]
    all_slip = [max(v["slip_buy"] or 0, v["slip_sell"] or 0) for v in merged.values()]
    summary = {
        "sumber": "snapshot /api/depth Indodax, dikumpulkan tools/collect_book.py",
        "n_files": len(list(SNAP.glob("*.csv"))),
        "n_observasi": int(len(df)),
        "periode": [str(df["iso_wib"].min()), str(df["iso_wib"].max())],
        "median_spread_semua_pair": float(np.median(all_spread)),
        "median_slippage_semua_pair": float(np.median(all_slip)),
        "per_pair": merged,
        "catatan": ("slippage di sini = biaya menembus 1 level book, proxy konservatif "
                    "untuk order <= 12% modal. Backtest memakai slippage konstan "
                    "config.slippage; angka ini dipakai untuk MEMVALIDASI apakah "
                    "asumsi itu terlalu optimis."),
    }
    OUT.write_text(json.dumps(summary, indent=1))

    print(f"snapshot: {summary['n_files']} file, {summary['n_observasi']} observasi")
    print(f"periode : {summary['periode'][0]} .. {summary['periode'][1]}")
    print(f"\n{'pair':10s} {'spread med':>11s} {'spread p90':>11s} {'slip buy':>9s} {'slip sell':>10s}")
    for sym, v in merged.items():
        print(f"{sym:10s} {v['spread_median']:>10.4%} {v['spread_p90']:>10.4%} "
              f"{(v['slip_buy'] or 0):>8.4%} {(v['slip_sell'] or 0):>9.4%}")
    print(f"\nmedian spread semua pair   : {summary['median_spread_semua_pair']:.4%}")
    print(f"median slippage 1 level    : {summary['median_slippage_semua_pair']:.4%}")
    print(f"asumsi backtest sekarang   : spread+slippage 0.10% per sisi")
    print(f"\nsimpan -> {OUT}")


if __name__ == "__main__":
    main()