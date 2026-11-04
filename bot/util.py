"""Util bot: Upstash Redis REST + Indodax publik + waktu WIB. Stdlib only."""
import json, time, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))
TF = 240  # 4 jam (menit)
TF_SEC = TF * 60
UA = [("User-Agent", "Mozilla/5.0"), ("Referer", "https://indodax.com/")]


def _get(url: str, timeout: int = 25):
    op = urllib.request.build_opener()
    op.addheaders = UA
    with op.open(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _post(url: str, data: str, token: str, timeout: int = 25):
    req = urllib.request.Request(url, data=data.encode(), method="POST",
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "text/plain"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


class Redis:
    """Upstash Redis REST: get/set/rpush. Sambil hemat command (free tier)."""

    def __init__(self, url: str, token: str):
        self.url, self.token = url.rstrip("/"), token

    def get(self, key: str, default=None):
        try:
            r = _post(f"{self.url}/get/{key}", "", self.token)
        except Exception:
            return default
        v = r.get("result")
        if v is None:
            return default
        try:
            return json.loads(v)
        except Exception:
            return v

    def set(self, key: str, val) -> None:
        _post(f"{self.url}/set/{key}", json.dumps(val), self.token)

    def rpush(self, key: str, val) -> None:
        _post(f"{self.url}/rpush/{key}", json.dumps(val), self.token)


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
