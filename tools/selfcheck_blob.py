"""Self-check Vercel Blob: get/set/rpush/rpush-2x ke store private."""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

# baca .env.local tanpa dependensi
env = {}
for line in (HERE / ".env.local").read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"')

tok = env.get("BLOB_READ_WRITE_TOKEN")
assert tok, "BLOB_READ_WRITE_TOKEN tidak ada di .env.local"

from bot.util import Blob

b = Blob(tok, store=env.get("BLOB_STORE_ID"))
import time as _t
key = f"selftest/blob-{int(_t.time())}.json"
k2 = f"selftest/log-{int(_t.time())}.json"

print("1. get key yang belum ada -> default")
print("   ", b.get(key, {"absent": True}))

print("2. set lalu get")
b.set(key, {"v": 1, "iso": "test"})
got = b.get(key)
print("   ", got)
assert got == {"v": 1, "iso": "test"}, got

print("3. overwrite (x-add-random-suffix 0 + allow-overwrite)")
b.set(key, {"v": 2})
got = b.get(key)
print("   ", got)
assert got["v"] == 2, got

print("4. rpush dua kali")
b.set(k2, [])
b.rpush(k2, {"n": 1})
b.rpush(k2, {"n": 2})
log = b.get(k2)
print("   ", log)
assert len(log) == 2 and log[1]["n"] == 2, log

print("\nBLOB OK")