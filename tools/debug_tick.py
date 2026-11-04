"""Jalankan tick() dengan Blob palsu (in-memory) untuk mendapat traceback asli."""
import sys, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

class FakeBlob:
    def __init__(self): self.d = {}
    def get(self, k, default=None): return self.d.get(k, default)
    def set(self, k, v): self.d[k] = v
    def rpush(self, k, v):
        self.d.setdefault(k, []).append(v)

import bot.tick as T
T.Blob = lambda *a, **k: FakeBlob()      # type: ignore

try:
    out = T.tick({"BLOB_READ_WRITE_TOKEN": "x", "BLOB_STORE_ID": ""})
    print("HASIL:", out)
except Exception:
    traceback.print_exc()