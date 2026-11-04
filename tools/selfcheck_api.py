"""Self-check bot tanpa storage: validasi API, tick size, VWAP depth, validasi data.

Tidak menulis apa pun ke Blob. Memakai API publik Indodax sungguhan.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.util import (indodax_candles, indodax_depth, indodax_pairs,
                      indodax_server_time, indodax_ticker_all,
                      last_closed_candle_id, pair_key, round_qty, round_to_tick,
                      vwap_fill)
from bot.tick import UNIVERSE, GATE_PAIR, TF_SEC, validate_book, validate_data

fails = []


def check(name, cond, detail=""):
    print(("OK   " if cond else "FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


print("=== 1. metadata pasangan (tick size + qty step) ===")
meta = indodax_pairs()
check("pairs terisi", len(meta) > 100, f"n={len(meta)}")
for sym in UNIVERSE[:3]:
    m = meta.get(sym.lower(), {})
    check(f"{sym} punya tick", m.get("tick", 0) > 0, f"tick={m.get('tick')} step={m.get('qty_step')}")

print("\n=== 2. pembulatan tick & qty ===")
check("beli dibulatkan ke atas", round_to_tick(1000.4, 5, "buy") >= 1000.4,
      str(round_to_tick(1000.4, 5, "buy")))
check("jual dibulatkan ke bawah", round_to_tick(1000.4, 5, "sell") <= 1000.4,
      str(round_to_tick(1000.4, 5, "sell")))
check("qty dibulatkan ke bawah", round_qty(1.23456, 1e-08) <= 1.23456)

print("\n=== 3. VWAP multi-level ===")
levels = [(100.0, 1.0), (101.0, 1.0), (102.0, 3.0)]
avg, qty = vwap_fill(levels, 250.0)   # habiskan level 1 (100) + 1 (101) + sisa
check("avg di antara level 1-3", 100.0 < avg < 102.0, f"avg={avg:.4f} qty={qty:.6f}")
avg1, qty1 = vwap_fill([(100.0, 100.0)], 50.0)
check("order kecil fill di level terbaik", abs(avg1 - 100.0) < 1e-9, f"avg={avg1}")
avg2, qty2 = vwap_fill([(100.0, 0.1)], 1000.0)
check("book kurang -> partial fill", qty2 < 10.0, f"qty={qty2:.4f}")

print("\n=== 4. depth live per pair ===")
for sym in UNIVERSE[:3]:
    d = indodax_depth(sym.lower())
    asks = (d.get("sell") or [])[:3]
    bids = (d.get("buy") or [])[:3]
    check(f"{sym} depth punya ask+bid", len(asks) > 0 and len(bids) > 0,
          f"ask0={asks[0] if asks else None} bid0={bids[0] if bids else None}")
    if asks and bids:
        ask0, bid0 = float(asks[0][0]), float(bids[0][0])
        spread = (ask0 - bid0) / bid0
        check(f"{sym} spread < 2%", spread < 0.02, f"spread={spread:.4%}")
        check(f"{sym} ask > bid", ask0 > bid0, f"ask={ask0} bid={bid0}")

print("\n=== 5. candle live + validasi data ===")
server = indodax_server_time()
import time
cid = last_closed_candle_id(int(time.time()), server)
print(f"  server_time={server} candle_tertutup={cid}")
closes, opens, vols = {}, {}, {}
for sym in UNIVERSE + [GATE_PAIR]:
    frm = cid - 400 * TF_SEC
    bars = indodax_candles(sym, frm, cid + TF_SEC)
    ser = {}
    for b in bars:
        t = int(b["Time"])
        if t <= cid:
            ser[t] = [b["Open"], b["High"], b["Low"], b["Close"], float(b["Volume"])]
    closes[sym] = {t: v[3] for t, v in ser.items()}
    opens[sym] = {t: v[0] for t, v in ser.items()}
    vols[sym] = {t: v[4] for t, v in ser.items()}
    check(f"{sym} candle terunduh", len(ser) >= 300, f"n={len(ser)}")

ok, why = validate_data(closes, opens, vols, cid)
print(f"  validate_data -> {ok} ({why})")
check("validasi data lolos di kondisi normal", ok, why)

print("\n=== 6. validate_book ===")
tk = indodax_ticker_all()
snap = {s: {"bid": float(tk.get(pair_key(s), {}).get("buy", 0) or 0),
            "ask": float(tk.get(pair_key(s), {}).get("sell", 0) or 0)} for s in UNIVERSE}
okb, whyb = validate_book(snap)
check("book normal lolos", okb, whyb)
bad = dict(snap)
bad[UNIVERSE[0]] = {"bid": 0, "ask": 0}
check("book kosong ditolak", validate_book(bad)[0] is False, validate_book(bad)[1])
wide = dict(snap)
p = dict(snap[UNIVERSE[0]])
p["ask"] = p["bid"] * 1.05
wide[UNIVERSE[0]] = p
check("spread > 2% ditolak", validate_book(wide)[0] is False, validate_book(wide)[1])

print("\n=== HASIL ===")
if fails:
    print(f"GAGAL {len(fails)}: {fails}")
    sys.exit(1)
print("SEMUA CEK LOLOS")