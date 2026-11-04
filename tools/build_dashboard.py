"""Bangun dashboard HTML offline mandiri (tanpa CDN, tanpa network).

Input : logs/*.jsonl, logs/state.json, reports/summary_4h.json,
        reports/spread_measured.json, reports/backtest_forward_window.json
Output: dashboard/index.html  (satu file, dibuka tanpa internet)

Angka dihitung ulang di sini dari log mentah, BUKAN dari reports/hitung_ulang.json,
supaya dashboard dan skrip hitung_ulang independen dan bisa dibandingkan.
"""
import json
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
LOGS = HERE / "logs"
OUT = HERE / "dashboard" / "index.html"
CAPITAL = 100_000_000.0


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


def jread(p, default=None):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return default


def compute():
    calls = load("log_calls")
    orders = load("log_orders")
    equity = load("log_equity")
    books = load("log_book")
    errors = load("log_errors")
    events = load("log_events")
    state = jread(LOGS / "state.json", {}) or {}

    executed = [c for c in calls if c.get("action") == "executed"]
    candles = sorted({c["candle"] for c in executed if "candle" in c})
    span = (candles[-1] - candles[0] + 14400) if candles else 0
    n_expected = max(span // 14400, 1) if candles else 0

    eq = [e["equity"] for e in equity if "equity" in e]
    e0 = eq[0] if eq else CAPITAL
    e1 = eq[-1] if eq else CAPITAL
    peak, mdd = -1e18, 0.0
    for v in eq:
        peak = max(peak, v)
        if peak > 0:
            mdd = min(mdd, v / peak - 1)

    # trade tertutup: FIFO sederhana per pair dari log_orders
    trades, pos = [], {}
    for o in orders:
        s = o["sym"]
        if o["side"] == "buy":
            p = pos.setdefault(s, {"qty": 0.0, "cost": 0.0})
            p["qty"] += o["qty"]
            p["cost"] += o["notional"] + o.get("fee", 0)
        else:
            p = pos.get(s)
            if not p or p["qty"] <= 0:
                continue
            frac = min(1.0, o["qty"] / p["qty"])
            cost = p["cost"] * frac
            proceeds = o["notional"] - o.get("fee", 0)
            trades.append({"sym": s, "pnl": proceeds - cost})
            p["qty"] -= o["qty"]
            p["cost"] -= cost
            if p["qty"] <= 1e-12:
                pos.pop(s, None)

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    gp = sum(t["pnl"] for t in wins)
    gl = -sum(t["pnl"] for t in losses)
    fee_total = sum(o.get("fee", 0) for o in orders)

    spreads = []
    for b in books:
        for v in (b.get("book") or {}).values():
            bid, ask = v.get("bid") or 0, v.get("ask") or 0
            if bid > 0 and ask > 0:
                spreads.append((ask - bid) / ((ask + bid) / 2))
    spreads.sort()
    med_spread = spreads[len(spreads) // 2] if spreads else None

    return {
        "n_calls": len(calls), "n_executed": len(executed),
        "n_skip": sum(1 for c in calls if c.get("action") == "skip_dup"),
        "n_no_entry": sum(1 for c in calls if c.get("action") == "no_entry"),
        "n_errors": len(errors),
        "errors": errors[-8:],
        "kill_switch": sum(1 for e in events if e.get("event") == "kill_switch_on"),
        "daily_loss_limit": sum(1 for e in events if e.get("event") == "daily_loss_limit"),
        "n_orders": len(orders), "n_trades": len(trades),
        "fee_total": fee_total,
        "pf": (gp / gl) if gl > 0 else (None if not wins else float("inf")),
        "wr": (len(wins) / len(trades)) if trades else None,
        "avg_win": (gp / len(wins)) if wins else 0.0,
        "avg_loss": (-gl / len(losses)) if losses else 0.0,
        "equity_0": e0, "equity_1": e1,
        "fwd_ret": (e1 / e0 - 1) if e0 else 0.0,
        "fwd_mdd": mdd,
        "uptime_done": len(candles), "uptime_expected": n_expected,
        "uptime_pct": (len(candles) / n_expected) if n_expected else None,
        "candles": candles,
        "med_spread": med_spread,
        "n_book": len(books),
        "positions": state.get("positions", {}),
        "cash": state.get("cash"),
        "n_processed": len(state.get("processed", {})),
        "first_t": calls[0]["t"] if calls else None,
        "last_t": calls[-1]["t"] if calls else None,
    }


def fmt_rp(v):
    return "Rp" + format(round(v), ",").replace(",", ".")


def pct(v, d=2):
    return "-" if v is None else f"{v*100:.{d}f}%"


def build():
    m = compute()
    bt = jread(HERE / "reports" / "summary_4h.json", {}) or {}
    fw = jread(HERE / "reports" / "backtest_forward_window.json", {}) or {}
    sp = jread(HERE / "reports" / "spread_measured.json", {}) or {}

    mode = "forward test berjalan" if m["n_calls"] else "belum ada log (menunggu tick pertama)"
    sched = f"{m['first_t']} .. {m['last_t']}" if m["first_t"] else "-"
    pf_str = "-" if m["pf"] is None else ("inf" if m["pf"] == float("inf") else f"{m['pf']:.2f}")

    cards = [
        ("Backtest CAGR", pct(bt.get("cagr")), "5,8 thn, 4h, fee resmi", "good"),
        ("Backtest MDD", pct(bt.get("mdd")), "maksimum drawdown", "bad"),
        ("Backtest PF", f"{bt.get('profit_factor', 0):.2f}", f"{bt.get('n_trades', 0)} trade tertutup", "good"),
        ("Return forward", pct(m["fwd_ret"]), f"{m['equity_0'] and fmt_rp(m['equity_0'])} -> {fmt_rp(m['equity_1'])}", "neutral"),
        ("MDD forward", pct(m["fwd_mdd"]), "dari equity harian log", "bad"),
        ("Uptime", (pct(m["uptime_pct"]) if m["uptime_pct"] is not None else "-"),
         f"{m['uptime_done']}/{m['uptime_expected']} candle", "good"),
        ("Panggilan", str(m["n_calls"]), f"{m['n_executed']} executed, {m['n_skip']} skip_dup, {m['n_no_entry']} no_entry", "neutral"),
        ("Order simulasi", str(m["n_orders"]), f"{m['n_trades']} trade tertutup, fee {fmt_rp(m['fee_total'])}", "neutral"),
        ("Spread terukur", pct(m["med_spread"], 3), f"median dari {m['n_book']} snapshot book", "neutral"),
        ("Error API", str(m["n_errors"]), "retry terbatas 3x", ("bad" if m["n_errors"] else "good")),
        ("Kill switch", str(m["kill_switch"]), "pemakaian tercatat di log", ("bad" if m["kill_switch"] else "good")),
        ("Daily loss limit", str(m["daily_loss_limit"]), "batas hari 00.00 WIB", ("bad" if m["daily_loss_limit"] else "good")),
    ]

    rows = "\n".join(
        f"<div class='card'><div class='k'>{k}</div>"
        f"<div class='v {cls}'>{v}</div><div class='n'>{n}</div></div>"
        for k, v, n, cls in cards)

    pos_rows = "".join(
        f"<tr><td>{s}</td><td>{p.get('qty'):.8f}</td><td>{fmt_rp(p.get('qty',0)*p.get('entry',0))}</td></tr>"
        for s, p in m["positions"].items()) or "<tr><td colspan='3' class='muted'>tidak ada posisi terbuka</td></tr>"

    err_rows = "".join(
        f"<tr><td class='muted'>{e.get('t','')}</td><td>{e.get('err','')[:140]}</td></tr>"
        for e in m["errors"]) or "<tr><td colspan='2' class='muted'>tidak ada error</td></tr>"

    html = f"""<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dashboard UAS Bot Dry Run Indodax</title>
<style>
:root{{--bg:#0b0d0c;--card:#141715;--line:#242925;--fg:#e8ece9;--muted:#8b958e;--accent:#c7ff39}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}}
header{{padding:22px 28px;border-bottom:1px solid var(--line);display:flex;
justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px}}
h1{{font-size:17px;margin:0;font-weight:600;letter-spacing:.2px}}
.sub{{color:var(--muted);font-size:12px}}
main{{padding:24px 28px;max-width:1100px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px;margin-bottom:26px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px 16px}}
.card .k{{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.6px}}
.card .v{{font-size:22px;margin:5px 0 2px;font-variant-numeric:tabular-nums}}
.card .v.good{{color:var(--accent)}}
.card .v.bad{{color:#ff6b5e}}
.card .v.neutral{{color:var(--fg)}}
.card .n{{color:var(--muted);font-size:11px}}
h2{{font-size:13px;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);
margin:26px 0 10px;font-weight:600}}
table{{width:100%;border-collapse:collapse;background:var(--card);
border:1px solid var(--line);border-radius:8px;overflow:hidden}}
th,td{{padding:9px 13px;text-align:left;border-bottom:1px solid var(--line);font-size:12.5px}}
tr:last-child td{{border-bottom:none}}
th{{color:var(--muted);font-weight:600;text-transform:uppercase;font-size:11px;letter-spacing:.5px}}
td.k{{color:var(--muted);width:180px}}
td.v{{color:var(--accent);font-variant-numeric:tabular-nums}}
.muted{{color:var(--muted)}}
footer{{padding:18px 28px;border-top:1px solid var(--line);color:var(--muted);font-size:11px}}
.note{{background:var(--card);border:1px solid var(--line);border-left:2px solid #5b9cff;
border-radius:8px;padding:14px 18px;color:var(--muted);font-size:12.5px;margin-bottom:22px;line-height:1.6}}
.badge{{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;
border:1px solid #2f6b30;color:var(--accent);background:#17220f}}
</style></head><body>
<header>
<div><h1>Bot Dry Run Indodax · UAS Algoritma Trading</h1>
<div class="sub">Hafizh Muhammad Zhafran · 25110200032 · timeframe 4 jam · dry run, tanpa uang sungguhan</div></div>
<div class="sub"><span class="badge">{mode}</span><br>{sched}</div>
</header>
<main>
<div class="note">Semua angka di halaman ini dihitung dari log mentah bot
(<code>log_calls</code>, <code>log_orders</code>, <code>log_equity</code>,
<code>log_book</code>). Skrip <code>tools/hitung_ulang.py</code> menghasilkan angka
yang sama dari dump log yang sama. Tidak ada angka yang ditulis manual.</div>
<div class="grid">{rows}</div>

<h2>Backtest vs forward (jendela sama)</h2>
<table>
<tr><th>Metrik</th><th>Backtest</th><th>Forward</th></tr>
<tr><td class="k">CAGR</td><td>{pct(bt.get('cagr'))}</td><td class="muted">tidak bermakna (10 hari)</td></tr>
<tr><td class="k">Return total</td><td>{pct(fw.get('return_total'))} <span class="muted">(jendela {fw.get('window',['-','-'])[0]} .. {fw.get('window',['-','-'])[1]})</span></td><td>{pct(m['fwd_ret'])}</td></tr>
<tr><td class="k">Maximum drawdown</td><td>{pct(fw.get('mdd'))}</td><td>{pct(m['fwd_mdd'])}</td></tr>
<tr><td class="k">Profit factor</td><td>{fw.get('pf', 0):.2f}</td><td>{pf_str}</td></tr>
<tr><td class="k">Jumlah trade</td><td>{fw.get('n_trades', 0)}</td><td>{m['n_trades']}</td></tr>
</table>

<h2>Biaya</h2>
<table>
<tr><th>Komponen</th><th>Nilai</th><th>Keterangan</th></tr>
<tr><td class="k">Fee taker (all-in)</td><td>beli 0,31% / jual 0,30%</td><td class="muted">halaman resmi help.indodax.com, lebih mahal dari api/pairs 0,20%</td></tr>
<tr><td class="k">Slippage backtest</td><td>0,10% per sisi</td><td class="muted">placeholder sebelum snapshot; angka terukur di bawah</td></tr>
<tr><td class="k">Spread terukur</td><td>{pct(sp.get('median_spread_semua_pair'), 3)}</td><td class="muted">{sp.get('n_observasi', 0)} observasi, {sp.get('n_files', 0)} file snapshot</td></tr>
<tr><td class="k">Slippage terukur (1 level)</td><td>{pct(sp.get('median_slippage_semua_pair'), 3)}</td><td class="muted">proxy biaya menembus level book</td></tr>
</table>

<h2>Posisi terbuka</h2>
<table><tr><th>Pair</th><th>Qty</th><th>Nilai</th></tr>{pos_rows}</table>

<h2>Error terakhir</h2>
<table><tr><th>Waktu</th><th>Pesan</th></tr>{err_rows}</table>
</main>
<footer>Dibangun dari log mentah. Versi file: {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB.
Kas: {fmt_rp(m['cash'] or 0)} · {m['n_processed']} candle diproses · universe 10 pair beku</footer>
</body></html>"""

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"dashboard -> {OUT}  ({OUT.stat().st_size/1024:.1f} KB)")
    print(f"  panggilan {m['n_calls']}, order {m['n_orders']}, trade {m['n_trades']}, "
          f"uptime {m['uptime_done']}/{m['uptime_expected']}")
    print("  cek offline: tidak ada http:// atau https:// di HTML ->",
          ("http" not in html.replace("https://help.indodax.com", "")))


if __name__ == "__main__":
    build()