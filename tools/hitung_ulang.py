"""Skrip hitung_ulang: reproduksi SEMUA angka dashboard dari log mentah (Blob dump).

Pemakaian: python tools/hitung_ulang.py logs/  (folder berisi log_calls.jsonl,
log_orders.jsonl, log_equity.jsonl, log_book.jsonl, log_errors.jsonl, log_events.jsonl,
state.json, candles/  -> dump dari tools/dump_logs.py)
Output: reports/hitung_ulang.json (bandingkan dengan dashboard -> harus sama persis).
"""
import json, sys
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent.parent
LOGS = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "logs"
CAPITAL = 100_000_000.0
BUY_FEE, SELL_FEE, SLIP = 0.0031, 0.0030, 0.001


def load(name):
    """Baca JSONL. Toleran terhadap baris berisi array (format lama rpush)."""
    p = LOGS / f"{name}.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        v = json.loads(line)
        if isinstance(v, list):
            out.extend(v)          # baris berisi array entri
        else:
            out.append(v)
    return out


def main():
    orders = load("log_orders")
    equity = load("log_equity")
    calls = load("log_calls")
    errors = load("log_errors")
    events = load("log_events")
    books = load("log_book")

    # equity harian: harga fill order + best bid snapshot terakhir per hari
    df = pd.DataFrame(orders)
    if len(df):
        df["dt"] = pd.to_datetime(df["t"])
        df["day"] = df["dt"].dt.strftime("%Y-%m-%d")
    # forward return: dari log_equity (panggilan pertama setelah 00.00 WIB)
    eq = pd.DataFrame([{"t": e["t"], "equity": e["equity"]} for e in equity])
    out = {
        "n_panggilan_terjadwal": len(calls),
        "n_panggilan_executed": sum(1 for c in calls if c.get("action") == "executed"),
        "n_skip_dup": sum(1 for c in calls if c.get("action") == "skip_dup"),
        "n_no_entry": sum(1 for c in calls if c.get("action") == "no_entry"),
        "n_error_api": len(errors),
        "kill_switch_events": sum(1 for e in events if e.get("event") == "kill_switch_on"),
        "daily_loss_limit_events": sum(1 for e in events if e.get("event") == "daily_loss_limit"),
        "n_orders": len(orders),
        "total_fee": round(sum(o.get("fee", 0) for o in orders), 2),
        "n_book_snapshots": len(books),
    }
    if len(df):
        buys = float(df[df["side"] == "buy"]["notional"].sum())
        sells = float(df[df["side"] == "sell"]["notional"].sum())
        out["notional_beli"] = round(buys, 2)
        out["notional_jual"] = round(sells, 2)
    if len(eq):
        e0 = float(eq["equity"].iloc[0])
        e1 = float(eq["equity"].iloc[-1])
        out["equity_awal"] = e0
        out["equity_akhir"] = e1
        out["forward_return_total"] = round(e1 / e0 - 1, 6)
        s = eq["equity"]
        out["forward_mdd"] = round(float((s / s.cummax() - 1).min()), 6)
        # UPTIME (definisi soal): candle terproses tepat waktu / jumlah candle
        # selama forward test. Dasar = rentang dari candle PERTAMA yang diproses
        # sampai candle TERTUTUP TERAKHIR yang sudah lewat (bukan sekadar candle
        # terakhir yang sempat diproses) -> candle yang terlewat ikut dihitung,
        # sedangkan candle yang belum tiba waktunya tidak dihukum.
        import time as _time
        executed = [c for c in calls if c.get("action") == "executed"]
        done = sorted({c["candle"] for c in executed if "candle" in c})
        if done:
            c_first = done[0]
            now = int(_time.time())
            last_closed = (now // 14400) * 14400 - 14400
            c_last = max(last_closed, done[-1])
            n_expected = (c_last - c_first) // 14400 + 1
            n_done = len(done)
            missed = [c_first + i * 14400 for i in range(n_expected)
                      if (c_first + i * 14400) not in set(done)]
            out["uptime_candle"] = f"{n_done}/{n_expected}"
            out["uptime_pct"] = round(n_done / max(n_expected, 1), 4)
            out["candle_terlewat"] = len(missed)
            out["candle_terlewat_list"] = missed[:40]
            out["candle_pertama"] = c_first
            out["candle_tertutup_terakhir"] = c_last
        else:
            out["uptime_candle"] = "0/0"
            out["uptime_pct"] = 0.0
            out["candle_terlewat"] = 0
    # median spread dari snapshot book
    if books:
        sp = []
        for b in books:
            for sym, v in b["book"].items():
                if v["bid"] and v["ask"]:
                    sp.append((v["ask"] - v["bid"]) / ((v["ask"] + v["bid"]) / 2))
        out["spread_median_terukur"] = round(float(pd.Series(sp).median()), 6) if sp else None
        out["n_spread_obs"] = len(sp)
    (HERE / "reports" / "hitung_ulang.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
