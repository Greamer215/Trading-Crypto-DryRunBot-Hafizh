"""Ekspor log forward test dari Vercel Blob -> logs/*.jsonl (format yang dibaca
tools/hitung_ulang.py dan dashboard).

Log di Blob disimpan append-only satu blob per entri (prefix/{ts}-{rand}.json),
karena get-append-set tidak atomic. Skrip ini mengumpulkannya jadi JSONL.

Pakai:  python tools/export_logs.py            # tulis ke logs/
        python tools/export_logs.py --out dir
Env:    BLOB_READ_WRITE_TOKEN, BLOB_STORE_ID  (dari .env.local atau environment)
"""
import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from bot.util import Blob

PREFIXES = ["log_calls", "log_orders", "log_equity", "log_book",
            "log_errors", "log_events", "log_sinyal"]


def load_env():
    env = {}
    p = HERE / ".env.local"
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"')
    for k in ("BLOB_READ_WRITE_TOKEN", "BLOB_STORE_ID"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "logs"))
    a = ap.parse_args()

    env = load_env()
    assert env.get("BLOB_READ_WRITE_TOKEN"), "BLOB_READ_WRITE_TOKEN tidak ada"
    b = Blob(env["BLOB_READ_WRITE_TOKEN"], store=env.get("BLOB_STORE_ID"))

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    total = 0
    for pre in PREFIXES:
        items = b.read_log(pre, limit=5000)
        path = out / f"{pre}.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
        print(f"{pre:12s} {len(items):5d} entri -> {path.name}")
        total += len(items)

    st = b.get("state") or {}
    (out / "state.json").write_text(json.dumps(st, indent=1, ensure_ascii=False))
    print(f"{'state':12s} {len(st.get('processed', {})):5d} candle diproses -> state.json")
    print(f"\ntotal {total} entri log")


if __name__ == "__main__":
    main()