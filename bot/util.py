"""Util bot: Vercel Blob (REST) + Indodax publik + waktu WIB. Stdlib only.

Storage = Vercel Blob (bawaan Vercel Hobby free, diizinkan soal p.3):
BLOB_READ_WRITE_TOKEN di-set Vercel otomatis saat Blob di-enable di project.
"""
import json, time, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))
TF = 240  # 4 jam (menit)
TF_SEC = TF * 60
UA = [("User-Agent", "Mozilla/5.0"), ("Referer", "https://indodax.com/")]


def _headers(extra=None):
    return dict(UA + (extra or []))


def _get(url: str, timeout: int = 25, headers=None):
    req = urllib.request.Request(url, headers=_headers(headers))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def indodax_candles(symbol: str, frm: int, to: int, tf: int = TF):
    d = _get(f"https://indodax.com/tradingview/history_v2"
             f"?symbol={symbol}&tf={tf}&from={frm}&to={to}")
    return d if isinstance(d, list) else []


def indodax_ticker_all():
    return _get("https://indodax.com/api/ticker_all")["tickers"]


def indodax_depth(pair: str):  # pair lowercase, mis. "btcidr"
    return _get(f"https://indodax.com/api/depth/{pair}")


def indodax_server_time() -> int:
    return int(_get("https://indodax.com/api/server_time")["server_time"])


def last_closed_candle_id(now_utc: int, server_time: int) -> int:
    """Bar 4h tertutup terakhir: boundary <= min(now, server_time) - TF."""
    ref = min(now_utc, server_time)
    return (ref // TF_SEC) * TF_SEC - TF_SEC


def vwap_fill(levels, side_notional: float):
    """Konsumsi level order book sampai notional terisi. Return (avg_px, filled)."""
    remain, cost, qty = side_notional, 0.0, 0.0
    for px, vol in levels:
        px, vol = float(px), float(vol)
        if remain <= 0:
            break
        lvl_qty = remain / px
        take = min(lvl_qty, vol)
        cost += take * px
        qty += take
        remain -= take * px
    if qty <= 0:
        return None, 0.0
    return cost / qty, qty


def wib_day(ts_utc: int) -> str:
    return datetime.fromtimestamp(ts_utc, WIB).strftime("%Y-%m-%d")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone(WIB).isoformat(timespec="seconds")


class Blob:
    """State + log di Vercel Blob via REST. Interface get/set/rpush.

    GET publik per blob URL; PUT butuh Bearer BLOB_READ_WRITE_TOKEN.
    rpush = get -> append -> set (volume kecil, 6 tick/hari, aman).
    """

    def __init__(self, token: str):
        self.token = token

    def _url(self, key: str) -> str:
        return f"https://blob.vercel-storage.com/{urllib.parse.quote(key)}"

    def get(self, key: str, default=None):
        try:
            req = urllib.request.Request(self._url(key))
            with urllib.request.urlopen(req, timeout=25) as r:
                raw = r.read().decode()
        except Exception:
            return default
        try:
            return json.loads(raw)
        except Exception:
            return raw

    def set(self, key: str, val) -> None:
        data = json.dumps(val).encode()
        req = urllib.request.Request(
            self._url(key), data=data, method="PUT",
            headers=_headers([("Authorization", f"Bearer {self.token}"),
                              ("x-api-version", "4"),
                              ("Content-Type", "application/json")]))
        with urllib.request.urlopen(req, timeout=25) as r:
            r.read()

    def rpush(self, key: str, val) -> None:
        cur = self.get(key, [])
        if not isinstance(cur, list):
            cur = []
        cur.append(val)
        self.set(key, cur)
