"""Tick bot: satu panggilan = satu candle 4h. Idempotent, dilog penuh.

Urutan: baca state -> tarik candle -> validasi data -> hitung sinyal (fungsi
backtest yang sama) -> eksekusi simulasi ask/bid -> risk check -> simpan state
-> log JSONL. Aturan beku sejak commit b0a6288 + 11385d6 (fee).
"""
import json, math, sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.util import (Blob, TF, TF_SEC, WIB, indodax_candles, indodax_depth,
                      indodax_pairs, indodax_server_time, indodax_ticker_all,
                      last_closed_candle_id, now_iso, pair_key, round_qty,
                      round_to_tick, vwap_fill, wib_day)

HERE = Path(__file__).resolve().parent.parent
UNIVERSE = json.loads((HERE / "data" / "universe_selected.json").read_text())["selected"]
MIN_ORDER = 25_000.0
DAILY_LOSS_LIMIT = 0.05        # -5% equity harian -> stop entry s/d ganti hari WIB
MAX_POS = 10                   # batas posisi terbuka (risk management soal)
MAX_SPREAD = 0.02              # soal p.2: bid-ask > 2% -> no entry

# --- import logika backtest yang SAMA (persyaratan soal: kode sama) ---------
from logic import CryptoConfig, build_crypto_weights
from logic.core import cap_position_weights

CFG = CryptoConfig()  # config beku; satu-satunya sumber parameter
GATE_PAIR = CFG.gate_proxy  # ETHIDR, satu sumber dengan backtest
CAP_POSITION = CFG.position_weight_cap  # 0.12, satu sumber dengan backtest
BUY_FEE, SELL_FEE, SLIP = CFG.buy_fee, CFG.sell_fee, CFG.slippage


def fetch_close_series(r: Blob, symbol: str, upto: int, need: int):
    """Panel close 4h per pair dari candle terkunci cache Blob + API."""
    cache = r.get(f"candles:{symbol}", {"bars": {}})
    bars = dict(cache["bars"])
    frm = upto - need * TF_SEC
    fresh = indodax_candles(symbol, frm, upto + TF_SEC)
    server = None
    for b in fresh:
        t = int(b["Time"])
        if t <= upto:  # buang candle berjalan (Time > server_time equivalent)
            bars[str(t)] = [b["Open"], b["High"], b["Low"], b["Close"], float(b["Volume"])]
    r.set(f"candles:{symbol}", {"bars": bars})
    keys = sorted(int(k) for k in bars if int(k) <= upto)
    keys = keys[-need:]
    return {int(k): bars[str(k)] for k in keys}


def build_panels(r: Blob, upto: int, need: int = 400):
    closes, opens, vols = {}, {}, {}
    for sym in UNIVERSE + [GATE_PAIR]:
        ser = fetch_close_series(r, sym, upto, need + 200)
        closes[sym] = {t: v[3] for t, v in ser.items()}
        opens[sym] = {t: v[0] for t, v in ser.items()}
        vols[sym] = {t: v[4] for t, v in ser.items()}
    return closes, opens, vols


def compute_targets(closes, opens, vols) -> dict:
    """Panggil pipeline backtest (fungsi sama, panel pandas)."""
    import pandas as pd
    idx = sorted(set().union(*[set(c) for c in closes.values()]))
    def df_from(d):
        return pd.DataFrame({s: pd.Series(v).reindex(idx) for s, v in d.items()})
    panels = {"close": df_from(closes), "open": df_from(opens),
              "turnover": df_from({s: {t: closes[s][t] * vols[s][t] for t in closes[s]}
                                   for s in closes})}
    panels["universe_fixed"] = UNIVERSE
    w = build_crypto_weights(panels, CFG)
    w = cap_position_weights(w, CAP_POSITION)
    return w.iloc[-1].to_dict()


def validate_data(closes, opens, vols, upto) -> tuple[bool, str]:
    """Validasi data sesuai daftar soal p.2. Setiap kegagalan -> no entry + alasan.

    closes/opens/vols: {symbol: {ts: nilai}} (sudah diekstrak build_panels).
    """
    for sym in UNIVERSE:
        c_ser, v_ser = closes.get(sym, {}), vols.get(sym, {})
        if not c_ser:
            return False, f"{sym}: tidak ada candle"
        last_t = max(c_ser)
        # (a) candle terakhir lebih tua dari 2x timeframe
        if upto - last_t > 2 * TF_SEC:
            return False, f"{sym}: candle terakhir basi ({upto - last_t}s)"
        # (b) harga atau volume nol
        if not c_ser.get(last_t) or not v_ser.get(last_t):
            return False, f"{sym}: harga/volume nol"
        # (c) candle hilang di jendela indikator (deteksi gap)
        need = CFG.signal_lookback + 5
        keys = sorted(k for k in c_ser if k <= upto)
        if len(keys) < need:
            return False, f"{sym}: bar kurang ({len(keys)} < {need})"
        window = keys[-need:]
        expected = (window[-1] - window[0]) // TF_SEC + 1
        if len(window) != expected:
            return False, f"{sym}: candle hilang di jendela indikator ({len(window)}/{expected})"
    return True, "ok"


def validate_book(snap) -> tuple[bool, str]:
    """Validasi order book: kosong atau spread > 2% -> no entry (soal p.2)."""
    for sym in UNIVERSE:
        b = snap.get(sym) or {}
        bid, ask = b.get("bid") or 0.0, b.get("ask") or 0.0
        if bid <= 0 or ask <= 0:
            return False, f"{sym}: order book kosong (bid={bid}, ask={ask})"
        if ask < bid:
            return False, f"{sym}: book rusak (ask {ask} < bid {bid})"
        spread = (ask - bid) / bid
        if spread > MAX_SPREAD:
            return False, f"{sym}: spread {spread:.2%} > {MAX_SPREAD:.0%}"
    return True, "ok"


def tick(env) -> dict:
    r = Blob(env["BLOB_READ_WRITE_TOKEN"], store=env.get("BLOB_STORE_ID"))
    log = lambda k, v: r.rpush(k, v)  # noqa: E731
    now = int(datetime.now(timezone.utc).timestamp())
    try:
        server = indodax_server_time()
    except Exception as e:
        log("log_errors", {"t": now_iso(), "err": f"server_time: {e}"})
        return {"ok": False, "reason": "server_time gagal"}
    cid = last_closed_candle_id(now, server)
    state = r.get("state", {"processed": {}, "cash": 100_000_000.0,
                            "positions": {}, "equity_day": None, "equity_0d": None,
                            "kill": False, "halt": None})
    calls = r.get("log_calls", [])

    # kill switch manual (env var, tanpa redeploy kode)
    if env.get("KILL_SWITCH") == "1" and not state.get("kill"):
        state["kill"] = True
        log("log_events", {"t": now_iso(), "event": "kill_switch_on"})
    if state.get("kill"):
        log("log_calls", {"t": now_iso(), "candle": cid, "action": "killed"})
        r.set("state", state)
        return {"ok": True, "action": "killed"}

    # idempotency: candle yang sama tak diproses dua kali
    if str(cid) in state["processed"]:
        log("log_calls", {"t": now_iso(), "candle": cid, "action": "skip_dup"})
        r.set("state", state)
        return {"ok": True, "action": "skip_dup"}

    # snapshot order book (semua pair, tiap tick -> 6x/hari >= min 3x/hari)
    try:
        tickers = indodax_ticker_all()
        snap = {}
        for sym in UNIVERSE:
            t = tickers.get(pair_key(sym), {})
            snap[sym] = {"bid": float(t.get("buy", 0) or 0),
                         "ask": float(t.get("sell", 0) or 0),
                         "last": float(t.get("last", 0) or 0)}
        log("log_book", {"t": now_iso(), "candle": cid, "book": snap})
    except Exception as e:
        log("log_errors", {"t": now_iso(), "err": f"ticker_all: {e}"})
        snap = {}

    closes, opens, vols = build_panels(r, cid)
    ok, why = validate_data(closes, opens, vols, cid)
    targets = {}
    if ok:
        try:
            targets = compute_targets(closes, opens, vols)
        except Exception as e:
            log("log_errors", {"t": now_iso(), "err": f"sinyal: {e}"})
            ok, why = False, f"sinyal gagal: {e}"
    if not ok:
        state["processed"][str(cid)] = {"action": "no_entry", "why": why}
        # uptime: candle gagal diproses valid tepat waktu -> tidak dihitung terlaksana
        log("log_calls", {"t": now_iso(), "candle": cid, "action": "no_entry",
                          "why": why, "uptime": False})
        r.set("state", state)
        return {"ok": True, "action": "no_entry", "why": why}

    # validasi order book (kosong / spread > 2%) -> no entry, tapi ini bukan
    # kegagalan data candle: sinyal tetap tercatat, eksekusi ditahan
    book_ok, book_why = validate_book(snap)
    if not book_ok:
        state["processed"][str(cid)] = {"action": "no_entry", "why": book_why}
        log("log_calls", {"t": now_iso(), "candle": cid, "action": "no_entry",
                          "why": book_why, "uptime": True})
        r.set("state", state)
        return {"ok": True, "action": "no_entry", "why": book_why}

    # equity harian + daily loss limit (batas hari WIB 00.00)
    day = wib_day(now)
    prices = {s: (snap.get(s, {}).get("bid") or closes[s].get(cid)) for s in UNIVERSE}
    eq = state["cash"] + sum(p["qty"] * prices.get(s, p["entry"]) for s, p in state["positions"].items())
    if state["equity_day"] != day:
        state["equity_day"] = day
        state["equity_0d"] = eq
        log("log_equity", {"t": now_iso(), "day": day, "equity": eq})
    eq0 = state["equity_0d"] or eq
    entry_blocked = state.get("halt") == day or (eq0 and eq < eq0 * (1 - DAILY_LOSS_LIMIT))
    if state.get("halt") != day and eq0 and eq < eq0 * (1 - DAILY_LOSS_LIMIT):
        state["halt"] = day
        log("log_events", {"t": now_iso(), "event": "daily_loss_limit", "eq": eq, "eq0": eq0})

    # eksekusi simulasi: delta target vs posisi, beli di ask, jual di bid
    # Depth diambil per pair yang bertransaksi (VWAP multi-level, soal p.2).
    pairs_meta = {}
    try:
        pairs_meta = indodax_pairs()
    except Exception as e:
        log("log_errors", {"t": now_iso(), "err": f"pairs: {e}"})

    orders = []
    for sym in UNIVERSE:
        tgt_val = float(targets.get(sym, 0.0)) * 100_000_000.0
        cur = state["positions"].get(sym)
        cur_val = cur["qty"] * prices[sym] if cur else 0.0
        delta = tgt_val - cur_val
        if abs(delta) < MIN_ORDER:
            continue
        side = "buy" if delta > 0 else "sell"
        if side == "buy" and (entry_blocked or len(state["positions"]) >= MAX_POS):
            continue
        if side == "buy" and delta > state["cash"]:
            delta = max(state["cash"] - MIN_ORDER, 0.0)
            if delta < MIN_ORDER:
                continue

        # --- depth: habiskan level berikutnya, pakai harga rata-rata (soal p.2)
        meta = pairs_meta.get(sym.lower(), {}) or {}
        tick = float(meta.get("tick", 0) or 0)
        qty_step = float(meta.get("qty_step", 0) or 0)
        book_sym = snap.get(sym, {})
        best = book_sym.get("ask" if side == "buy" else "bid", 0)
        if not best:
            log("log_errors", {"t": now_iso(), "err": f"{sym}: best price kosong, order dilewati"})
            continue
        try:
            depth = indodax_depth(sym.lower())
            # depth Indodax: {'buy': [...bid terbaik dulu], 'sell': [...ask terbaik dulu]}
            raw = (depth.get("sell") or []) if side == "buy" else (depth.get("buy") or [])
            levels = [(lv[0], lv[1]) for lv in raw][:20]
        except Exception as e:
            log("log_errors", {"t": now_iso(), "err": f"{sym}: depth gagal ({e}), pakai best"})
            levels = [(best, 1e18)]

        avg_px, filled_qty = vwap_fill(levels, abs(delta))
        if not avg_px or filled_qty <= 0:
            log("log_errors", {"t": now_iso(), "err": f"{sym}: book tidak cukup, order dilewati"})
            continue
        avg_px = round_to_tick(avg_px, tick, side)
        levels_used = 1
        cum = 0.0
        for px, vol in levels:
            cum += float(px) * float(vol)
            if cum >= abs(delta):
                break
            levels_used += 1

        spread_at_fill = ((book_sym.get("ask", 0) - book_sym.get("bid", 0))
                          / max(book_sym.get("bid", 1), 1e-12))
        slip_vs_best = abs(avg_px - best) / best if best else 0.0

        fee = (BUY_FEE if side == "buy" else SELL_FEE) + SLIP
        if side == "buy":
            qty = round_qty(filled_qty, qty_step)
            if qty <= 0:
                continue
            cost = delta * (1 + fee)
            state["cash"] -= cost
            state["positions"][sym] = {"qty": (cur["qty"] if cur else 0) + qty,
                                       "entry": avg_px, "candle": cid}
            orders.append({"t": now_iso(), "candle": cid, "sym": sym, "side": side,
                           "qty": qty, "px": avg_px, "px_best": best,
                           "levels": levels_used, "slip_vs_best": slip_vs_best,
                           "spread": spread_at_fill,
                           "notional": delta, "fee": cost - delta,
                           "signal_px": closes[sym].get(cid)})
        else:
            qty = min(round_qty(cur["qty"], qty_step), round_qty(filled_qty, qty_step))
            if qty <= 0:
                continue
            gross = qty * avg_px
            net = gross * (1 - fee)
            state["cash"] += net
            rem = cur["qty"] - qty
            state["positions"][sym] = {"qty": rem, "entry": cur["entry"],
                                       "candle": cur["candle"]} if rem * avg_px >= MIN_ORDER else None
            if state["positions"][sym] is None:
                del state["positions"][sym]
            orders.append({"t": now_iso(), "candle": cid, "sym": sym, "side": side,
                           "qty": qty, "px": avg_px, "px_best": best,
                           "levels": levels_used, "slip_vs_best": slip_vs_best,
                           "spread": spread_at_fill,
                           "notional": gross, "fee": gross - net,
                           "signal_px": closes[sym].get(cid)})
    for o in orders:
        log("log_orders", o)
    state["processed"][str(cid)] = {"action": "executed", "n_orders": len(orders)}
    log("log_calls", {"t": now_iso(), "candle": cid, "action": "executed",
                      "n_orders": len(orders), "equity": eq, "uptime": True,
                      "processed_at": now_iso()})
    r.set("state", state)
    return {"ok": True, "action": "executed", "orders": len(orders), "equity": eq}


if __name__ == "__main__":
    import os
    env = {k: os.environ[k] for k in ("BLOB_READ_WRITE_TOKEN",) if k in os.environ}
    print(json.dumps(tick(env), indent=1))
