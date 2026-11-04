"""Unduh candle 4h Indodax mundur dari sekarang (soal UAS p.2: history_v2 hanya
~650 bar/request; geser to mundur sampai capai tanggal awal). Max 3 req/detik,
tanpa paralel (bisa diblokir IP). Live mundur agar universe diukur di awal."""
import csv, json, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

BASE = "https://indodax.com/tradingview/history_v2"
OUT = Path(__file__).resolve().parent.parent / "data" / "indodax_4h"
OUT.mkdir(parents=True, exist_ok=True)
TF = 240  # menit = 4 jam; bar 4h = 6/hari


def fetch(symbol: str, frm: int, to: int):
    import urllib.request
    opener = urllib.request.build_opener()
    opener.addheaders = [("User-Agent", "Mozilla/5.0"), ("Referer", "https://indodax.com/")]
    url = f"{BASE}?symbol={symbol}&tf={TF}&from={frm}&to={to}"
    with opener.open(url, timeout=30) as r:
        data = r.read().decode()
    if data.startswith("<") or "invalid" in data.lower():
        raise RuntimeError(f"API menolak: {data[:80]}")
    return json.loads(data)


def download(symbol: str, start_ts: int, now_ts: int):
    rows = []
    to = now_ts
    frm = start_ts  # Indodax menolak from=0; pakai jendela dari tanggal awal
    while True:
        bars = fetch(symbol, frm, to)
        if not bars:
            break
        rows = bars + rows
        earliest = bars[0]["Time"]
        print(f"  {symbol}: +{len(bars)} bar, mundur ke {datetime.fromtimestamp(earliest, timezone.utc):%Y-%m-%d}", flush=True)
        if earliest <= start_ts + 1 or len(bars) < 500:
            break
        to = earliest - 1
        time.sleep(0.4)  # <=3 req/detik
    rows = [b for b in rows if b["Time"] >= start_ts]
    path = OUT / f"{symbol}.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "o", "h", "l", "c", "v"])
        for b in rows:
            ts = datetime.fromtimestamp(b["Time"], timezone.utc).strftime("%Y-%m-%d %H:%M")
            w.writerow([ts, b["Open"], b["High"], b["Low"], b["Close"], b["Volume"]])
    print(f"  {symbol}: simpan {len(rows)} bar -> {path.name}")
    return len(rows)


if __name__ == "__main__":
    # 20 pair kandidat teratas; diseleksi top-10 di AWAL backtest di tools/select_universe.py
    universe = sys.argv[1].split(",") if len(sys.argv) > 1 else (
        "BTCIDR ETHIDR XRPIDR BNBBIDR DOGEIDR SOLIDR TRXIDR LINKIDR ADAIDR "
        "LTCIDR BCHIDR ETCIDR XLMIDR HBARIDR DOTIDR UNIIDR NEARIDR ARBIDR AVAXIDR".split())
    now = int(datetime.now(timezone.utc).timestamp())
    start = int(datetime(2021, 1, 1, tzinfo=timezone.utc).timestamp())
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    (OUT / f"unduh_log_{stamp}.txt").write_text(
        f"sumber=https://indodax.com/tradingview/history_v2 tf=240 diakses={stamp}\n")
    for i, sym in enumerate(universe):
        try:
            download(sym, start, now)
        except Exception as e:
            print(f"  {sym}: GAGAL {e}")
        if i < len(universe) - 1:
            time.sleep(0.4)
    print("SELESAI")
