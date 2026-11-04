"""Util bot: Vercel Blob (REST) + Indodax publik + waktu WIB. Stdlib only.

Storage = Vercel Blob (bawaan Vercel Hobby free, diizinkan soal p.3):
BLOB_READ_WRITE_TOKEN di-set Vercel otomatis saat Blob di-enable di project.
"""
import json, math, os, random, string, time, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))
TF = 240  # 4 jam (menit)
TF_SEC = TF * 60
UA = [("User-Agent", "Mozilla/5.0"), ("Referer", "https://indodax.com/")]


def _headers(extra=None):
    return dict(UA + (extra or []))


def _get(url: str, timeout: int = 25, headers=None, retries: int = 3):
    """GET JSON dengan retry terbatas (soal p.3: retry terbatas, bukan tanpa batas).

    3 percobaan, backoff 0.5/1.0 detik. Kegagalan akhir dilempar ke pemanggil
    supaya tercatat sebagai error di log, bukan didiamkan.
    """
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=_headers(headers))
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # jaringan/HTTP/timeout/JSON rusak
            last = e
            if attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))
    raise last if last is not None else RuntimeError("GET gagal tanpa error")


def indodax_candles(symbol: str, frm: int, to: int, tf: int = TF):
    d = _get(f"https://indodax.com/tradingview/history_v2"
             f"?symbol={symbol}&tf={tf}&from={frm}&to={to}")
    return d if isinstance(d, list) else []


def pair_key(symbol: str) -> str:
    """BTCIDR -> btc_idr (format yang dipakai /api/ticker_all, terverifikasi)."""
    s = symbol.lower()
    return s[:-3] + "_" + s[-3:] if s.endswith("idr") else s


def indodax_ticker_all():
    return _get("https://indodax.com/api/ticker_all")["tickers"]


def indodax_depth(pair: str):  # pair lowercase tanpa underscore, mis. "btcidr"
    """Order book: {'buy': [[px, qty], ...], 'sell': [...]}.

    Terverifikasi 2026-11-04: level = list [harga_str, qty_str], harga DESC
    untuk buy (bid terbaik di depan) dan ASC untuk sell (ask terbaik di depan).
    """
    return _get(f"https://indodax.com/api/depth/{pair}")


def indodax_server_time() -> int:
    """Waktu server Indodax dalam DETIK (API mengirim milidetik).

    Terverifikasi 2026-11-04: /api/server_time -> {"server_time": 1793814014066}
    """
    raw = int(_get("https://indodax.com/api/server_time")["server_time"])
    return raw // 1000 if raw > 10_000_000_000 else raw


def indodax_pairs():
    """Metadata pasangan (list) + price_increments (dict terpisah).

    Struktur terverifikasi 2026-11-04:
      /api/pairs            -> list of dict, kunci 'id' = "btcidr"
      /api/price_increments -> {"increments": {"btc_idr": "1000", ...}}
    Return dict keyed by id huruf kecil, masing-masing punya 'tick' dan 'min_base'.
    """
    out = {}
    try:
        rows = _get("https://indodax.com/api/pairs")
        if isinstance(rows, list):
            for r in rows:
                pid = str(r.get("id", "")).lower()
                if pid:
                    out[pid] = {
                        "tick": 0.0,
                        "min_base": float(r.get("trade_min_base_currency", 0) or 0),
                        "qty_step": float(r.get("quantity_increment", 0) or 0),
                        "fee_taker": float(r.get("trade_fee_percent_taker", 0) or 0),
                    }
    except Exception:
        pass
    try:
        inc = _get("https://indodax.com/api/price_increments")
        inc = inc.get("increments", {}) if isinstance(inc, dict) else {}
        for k, v in inc.items():
            pid = str(k).replace("_", "").lower()  # btc_idr -> btcidr
            if pid in out:
                out[pid]["tick"] = float(v or 0)
    except Exception:
        pass
    return out


def round_to_tick(px: float, tick: float, side: str) -> float:
    """Bulatkan harga ke kenaikan harga pasangan (soal p.2: patuhi price_increments).

    Beli dibulatkan KE ATAS, jual KE BAWAH: pembulatan tidak boleh membuat fill
    lebih baik dari pasar.
    """
    if not tick or tick <= 0:
        return px
    n = px / tick
    k = math.ceil(n - 1e-9) if side == "buy" else math.floor(n + 1e-9)
    return round(k * tick, 12)


def round_qty(qty: float, step: float) -> float:
    """Bulatkan kuantitas ke kelipatan step (pembulatan ke bawah, jangan lebih)."""
    if not step or step <= 0:
        return qty
    return math.floor(qty / step + 1e-9) * step


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

    Store mode PRIVATE (default aman). Kontrak terverifikasi 2026-11-04:
      - PUT  : x-api-version: 4 + x-vercel-blob-access: private (wajib, kalau
               tidak -> 400 "Cannot use public access on a private store")
      - GET  : host privat {store}.private.blob.vercel-storage.com + Bearer
    rpush = get -> append -> set (volume kecil, 6 tick/hari, aman).
    """

    def __init__(self, token: str, store: str | None = None):
        self.token = token
        self.store = store or os.environ.get("BLOB_STORE_ID", "")

    def _base(self) -> str:
        """Host PUBLIK untuk menulis (PUT). Membaca memakai host privat."""
        return "https://blob.vercel-storage.com/"

    def _url(self, key: str) -> str:
        return self._base() + urllib.parse.quote(key)

    def _read_url(self, key: str) -> str:
        """Store private: baca lewat {store}.private.blob.vercel-storage.com."""
        if self.store:
            return (f"https://{self.store}.private.blob.vercel-storage.com/"
                    f"{urllib.parse.quote(key)}")
        return self._url(key)

    def _headers(self, extra=None):
        h = [("Authorization", f"Bearer {self.token}"),
             ("x-api-version", "4"),
             ("x-vercel-blob-access", "private")]
        return _headers(h + (extra or []))

    def get(self, key: str, default=None, retries: int = 3):
        """Baca blob. Retry singkat: propagasi CDN setelah overwrite tidak instan."""
        for attempt in range(retries):
            try:
                # cache-buster: CDN Blob bisa menyajikan versi lama
                url = f"{self._read_url(key)}?ts={int(time.time() * 1000)}"
                req = urllib.request.Request(
                    url, headers=self._headers([("Cache-Control", "no-cache")]))
                with urllib.request.urlopen(req, timeout=25) as r:
                    raw = r.read().decode()
                try:
                    return json.loads(raw)
                except Exception:
                    return raw
            except Exception:
                if attempt < retries - 1:
                    time.sleep(0.6 * (attempt + 1))
        return default

    def set(self, key: str, val) -> None:
        data = json.dumps(val).encode()
        req = urllib.request.Request(
            self._url(key), data=data, method="PUT",
            headers=self._headers([("Content-Type", "application/json"),
                                   ("x-add-random-suffix", "0"),
                                   ("allow-overwrite", "1")]))
        with urllib.request.urlopen(req, timeout=25) as r:
            r.read()

    def list(self, prefix: str, limit: int = 1000):
        """Daftar blob dengan prefix (untuk membaca log append-only)."""
        out, cursor = [], None
        while True:
            u = (f"https://blob.vercel-storage.com/?prefix={urllib.parse.quote(prefix)}"
                 f"&limit={min(limit, 1000)}")
            if cursor:
                u += f"&cursor={urllib.parse.quote(cursor)}"
            req = urllib.request.Request(u, headers=self._headers())
            with urllib.request.urlopen(req, timeout=25) as r:
                d = json.loads(r.read().decode())
            out.extend(d.get("blobs", []))
            cursor = d.get("cursor")
            if not d.get("hasMore") or not cursor or len(out) >= limit:
                break
        return out

    def append(self, prefix: str, val) -> str:
        """Tambah satu entri log sebagai blob terpisah (append-only, tanpa race).

        Key: {prefix}/{ts_ms}-{rand}.json. Dipakai untuk semua log supaya dua
        panggilan bersamaan tidak saling menimpa (get-append-set tidak atomic).
        """
        key = (f"{prefix}/{int(time.time() * 1000)}-"
               f"{''.join(random.choices(string.ascii_lowercase + string.digits, k=6))}.json")
        self.set(key, val)
        return key

    def read_log(self, prefix: str, limit: int = 2000):
        """Baca semua entri log berprefix, urut waktu naik."""
        items = []
        for b in self.list(prefix, limit=limit):
            v = self.get(b["pathname"])
            if v is not None:
                items.append(v)
        items.sort(key=lambda d: d.get("t", "") if isinstance(d, dict) else "")
        return items

    def rpush(self, key: str, val) -> None:
        """Kompatibilitas lama: tulis ke blob per-entri di bawah key/."""
        self.append(key, val)
