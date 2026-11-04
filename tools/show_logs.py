"""Verifikasi log forward test: flatten array format lama, tampilkan ringkas."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
LOGS = HERE / "logs"


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


calls = load("log_calls")
print(f"log_calls: {len(calls)} entri")
for r in calls:
    print(f"  {r.get('t')} | {r.get('action'):9s} | candle {r.get('candle')} | uptime {r.get('uptime')}")

orders = load("log_orders")
print(f"\nlog_orders: {len(orders)}")
equity = load("log_equity")
print(f"log_equity: {len(equity)} -> {[e.get('equity') for e in equity]}")
books = load("log_book")
print(f"log_book: {len(books)} snapshot")
errs = load("log_errors")
print(f"log_errors: {len(errs)}")
for e in errs[-3:]:
    print("  ", str(e)[:160])

state = json.loads((LOGS / "state.json").read_text())
print(f"\nstate: {len(state.get('processed', {}))} candle, cash {state.get('cash')}, "
      f"posisi {len(state.get('positions', {}))}")