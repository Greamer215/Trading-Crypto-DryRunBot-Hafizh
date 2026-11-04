"""Seleksi universe top-10: likuiditas diukur di AWAL periode backtest (soal UAS p.2,
anti-survivorship). Median turnover Rp/bar 4h pada 90 hari pertama data, rank, ambil
top-10. Pair terpilih dibekukan untuk seluruh backtest + forward test."""
import json, sys
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent.parent
DATA = HERE / "data" / "indodax_4h"
OUT = HERE / "data" / "universe_selected.json"

START = "2021-01-01"
WARMUP_DAYS = 90
TOP_N = 10


def main():
    frames = {}
    for p in sorted(DATA.glob("*.csv")):
        df = pd.read_csv(p, parse_dates=["t"])
        df = df.set_index("t").sort_index()
        df = df[df["c"].notna() & (df["c"] > 0)]
        if len(df) < 3000:  # minimal ~8 bulan bar 4h
            continue
        frames[p.stem] = df
    print(f"kandidat: {len(frames)} pair")

    rp = {}
    for sym, df in frames.items():
        df = df.loc[START:]
        if len(df) < 3000:
            print(f"  {sym}: data < 3000 bar sejak {START}, skip")
            continue
        to = (df["c"] * df["v"]).loc[: pd.Timestamp(START) + pd.Timedelta(days=WARMUP_DAYS)]
        med = float(to.median())
        if pd.isna(med) or med <= 0:
            continue  # belum listing pada window 90 hari pertama
        rp[sym] = med
    rank = sorted(rp.items(), key=lambda kv: -kv[1])
    top = [s for s, _ in rank[:TOP_N]]
    print("top-10 di awal backtest (median Rp/bar 4h, 90 hari pertama):")
    for s, v in rank[:TOP_N]:
        print(f"  {s:10s} Rp{v:>16,.0f}")
    OUT.write_text(json.dumps({
        "method": "median turnover Rp per bar 4h, 90 hari pertama sejak 2021-01-01",
        "selected": top,
        "all_measured": {s: round(v) for s, v in rank},
    }, indent=1))
    print(f"simpan {OUT}")


if __name__ == "__main__":
    main()
