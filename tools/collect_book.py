"""Pengumpul snapshot order book -> data terukur untuk spread & slippage backtest.

Soal p.2: simpan snapshot tiap pasangan sesering mungkin (idealnya tiap jam,
minimal 3x sehari) sejak hari pertama persiapan; semua snapshot mentah
dikumpulkan. Dijalankan di laptop, bukan di fungsi Vercel.

Output append-only: data/book_snapshots/YYYY-MM-DD.csv (WIB)

Pakai:  python tools/collect_book.py                  # sekali
        python tools/collect_book.py --loop 3600      # tiap jam
"""
import argparse
import csv
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from bot.util import indodax_depth, indodax_server_time

WIB = timezone(timedelta(hours=7))
OUT = HERE / "data" / "book_snapshots"
FIELDS = ["ts_utc", "iso_wib", "pair", "bid", "ask", "spread", "mid",
          "ask_depth6_idr", "bid_depth6_idr", "n_ask_levels", "n_bid_levels"]


def universe():
    sel = json.loads((HERE / "data" / "universe_selected.json").read_text())["selected"]
    return sel + ["ETHIDR"]


def one_round() -> int:
    try:
        server = indodax_server_time()
    except Exception as e:
        print(f"server_time gagal: {e}")
        return 0
    dt = datetime.fromtimestamp(server, WIB)
    path = OUT / f"{dt:%Y-%m-%d}.csv"
    new = not path.exists()
    OUT.mkdir(parents=True, exist_ok=True)

    rows = []
    for sym in universe():
        try:
            d = indodax_depth(sym.lower())
            asks, bids = d.get("sell") or [], d.get("buy") or []
            if not asks or not bids:
                continue
            a0, b0 = float(asks[0][0]), float(bids[0][0])
            if b0 <= 0 or a0 <= 0 or a0 < b0:
                continue
            rows.append({
                "ts_utc": server,
                "iso_wib": dt.isoformat(timespec="seconds"),
                "pair": sym,
                "bid": b0,
                "ask": a0,
                "spread": round((a0 - b0) / b0, 8),
                "mid": (a0 + b0) / 2,
                "ask_depth6_idr": round(sum(float(p) * float(q) for p, q in asks[:6]), 2),
                "bid_depth6_idr": round(sum(float(p) * float(q) for p, q in bids[:6]), 2),
                "n_ask_levels": len(asks),
                "n_bid_levels": len(bids),
            })
        except Exception as e:
            print(f"  {sym}: gagal {e}")
        time.sleep(0.25)  # <= 3 request/detik (soal p.2)

    if not rows:
        return 0
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerows(rows)
    med = sorted(r["spread"] for r in rows)[len(rows) // 2]
    print(f"{dt:%Y-%m-%d %H:%M} WIB: {len(rows)} pair -> {path.name} "
          f"(median spread {med:.4%})")
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=int, default=0, help="interval detik; 0 = sekali")
    a = ap.parse_args()
    if not a.loop:
        one_round()
        return
    print(f"loop tiap {a.loop}s, Ctrl-C untuk stop")
    try:
        while True:
            one_round()
            time.sleep(a.loop)
    except KeyboardInterrupt:
        print("stop")


if __name__ == "__main__":
    main()