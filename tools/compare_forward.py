"""Bandingkan sinyal forward test vs backtest, CANDLE DEMI CANDLE.

Rubrik (25%): backtest dijalankan ulang pada jendela forward dengan candle yang
sama; sinyal masuk/keluar harus identik candle demi candle karena kodenya sama.
Skrip ini membuktikan/mengukur klaim itu.

Input : logs/log_sinyal.jsonl  (target weight yang DIPUTUSKAN bot per candle)
        logs/log_orders.jsonl  (order simulasi aktual)
        candles backtest 4h dari data/indodax_4h
        reports/book_snapshots (spread terukur)

Output: reports/compare_forward.json + ringkasan layar.

Pakai: python tools/compare_forward.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from logic import CryptoConfig, build_crypto_weights
from logic.core import cap_position_weights
from tools.backtest_4h import load_4h

LOGS = HERE / "logs"
OUT = HERE / "reports" / "compare_forward.json"
TOL = 1e-6


def load(name):
    p = LOGS / f"{name}.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        v = json.loads(line)
        out.extend(v if isinstance(v, list) else [v])
    return out


def main():
    sel = json.loads((HERE / "data" / "universe_selected.json").read_text())["selected"]
    cfg = CryptoConfig()
    sig = [s for s in load("log_sinyal") if s.get("targets")]
    if not sig:
        print("BELUM ADA log_sinyal. Bot harus berjalan minimal satu candle dulu.")
        return

    candles = sorted({int(s["candle"]) for s in sig})
    t0 = pd.Timestamp(candles[0], unit="s", tz="UTC")
    t1 = pd.Timestamp(candles[-1], unit="s", tz="UTC")

    # backtest pada jendela yang sama, dengan fungsi & config yang sama
    panels = load_4h(sel)
    panels["universe_fixed"] = sel
    w = cap_position_weights(build_crypto_weights(panels, cfg), cfg.position_weight_cap)
    w.index = pd.to_datetime(w.index, utc=True)
    tz0 = pd.Timestamp(candles[0], unit="s", tz="UTC")

    diffs, per_candle = [], []
    for s in sig:
        c = int(s["candle"])
        ts = pd.Timestamp(c, unit="s", tz="UTC")
        if ts not in w.index:
            per_candle.append({"candle": c, "status": "candle_tidak_ada_di_data"})
            continue
        bt_row = w.loc[ts]
        bt = {k: float(bt_row.get(k, 0.0)) for k in sel}
        fw = {k: float(s["targets"].get(k, 0.0)) for k in sel}
        max_abs = max(abs(bt[k] - fw[k]) for k in sel)
        set_bt = {k for k in sel if bt[k] > TOL}
        set_fw = {k for k in sel if fw[k] > TOL}
        diffs.append(max_abs)
        per_candle.append({
            "candle": c, "iso_utc": ts.isoformat(),
            "max_abs_diff": round(max_abs, 10),
            "identik": bool(max_abs <= TOL),
            "pair_bot": sorted(set_fw), "pair_backtest": sorted(set_bt),
            "hanya_bot": sorted(set_fw - set_bt), "hanya_backtest": sorted(set_bt - set_fw),
            "exposure_bot": round(sum(fw.values()), 6),
            "exposure_backtest": round(sum(bt.values()), 6),
        })

    ok = [p for p in per_candle if p.get("identik")]
    res = {
        "jendela_utc": [tz0.isoformat(), pd.Timestamp(candles[-1], unit="s",
                                                      tz="UTC").isoformat()],
        "n_candle_dibandingkan": len(per_candle),
        "n_identik": len(ok),
        "match_pct": round(len(ok) / max(len(per_candle), 1), 4),
        "max_abs_diff_semua": round(max(diffs), 10) if diffs else None,
        "toleransi": TOL,
        "detail": per_candle,
    }
    OUT.write_text(json.dumps(res, indent=1))

    print(f"jendela      : {res['jendela_utc'][0]} .. {res['jendela_utc'][1]}")
    print(f"candle       : {len(per_candle)} dibandingkan, {len(ok)} identik "
          f"({res['match_pct']:.1%})")
    print(f"max abs diff : {res['max_abs_diff_semua']}")
    for p in per_candle[:12]:
        if p.get("status"):
            print(f"  {p['candle']}: {p['status']}")
            continue
        flag = "OK " if p["identik"] else "DIFF"
        print(f"  {flag} {p['iso_utc']}  bot={p['exposure_bot']:.3f} "
              f"bt={p['exposure_backtest']:.3f}  {p['pair_bot'] or '-'}")
    print(f"\nsimpan -> {OUT}")


if __name__ == "__main__":
    main()