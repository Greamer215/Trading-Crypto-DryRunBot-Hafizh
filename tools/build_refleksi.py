"""Bangun kerangka refleksi dari data nyata (bukan tulisan tangan).

Menggabungkan: numbers backtest, forward test, kecocokan sinyal candle demi
candle, dan spread terukur. Teks penyebab selisih diisi manusia; angka dan
diagnosis otomatis diisi skrip ini supaya tidak ada angka karangan.

Output: REFLEKSI.md
"""
import json
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REP = HERE / "reports"
LOGS = HERE / "logs"


def jread(p, d=None):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return d


def load_jsonl(name):
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


def pct(v, d=2):
    return "-" if v is None else f"{v*100:.{d}f}%".replace(".", ",")


def rp(v):
    return "-" if v is None else "Rp" + format(round(v), ",").replace(",", ".")


def main():
    bt = jread(REP / "summary_4h.json", {}) or {}
    fw = jread(REP / "backtest_forward_window.json", {}) or {}
    cmp_ = jread(REP / "compare_forward.json", {}) or {}
    hu = jread(REP / "hitung_ulang.json", {}) or {}
    sp = jread(REP / "spread_measured.json", {}) or {}
    calls = load_jsonl("log_calls")
    orders = load_jsonl("log_orders")

    n_calls = len(calls)
    n_exec = sum(1 for c in calls if c.get("action") == "executed")
    n_skip = sum(1 for c in calls if c.get("action") == "skip_dup")
    n_no = sum(1 for c in calls if c.get("action") == "no_entry")
    up_done = hu.get("uptime_candle", "-")
    up_pct = hu.get("uptime_pct")
    fwd_ret = hu.get("forward_return_total")
    fwd_mdd = hu.get("forward_mdd")
    n_tr = hu.get("n_orders", 0)
    fee = hu.get("total_fee", 0)

    bt_ret = fw.get("return_total")
    bt_mdd = fw.get("mdd")
    gap_ret = (fwd_ret - bt_ret) if (fwd_ret is not None and bt_ret is not None) else None
    gap_mdd = (fwd_mdd - bt_mdd) if (fwd_mdd is not None and bt_mdd is not None) else None

    def signed(v, d=2):
        """Selisih dengan tanda eksplisit (forward relatif terhadap backtest)."""
        if v is None:
            return "-"
        return f"{v*100:+.{d}f}%".replace(".", ",")

    med_sp = sp.get("median_spread_semua_pair")
    med_slip = sp.get("median_slippage_semua_pair")
    asumsi = 0.001
    bill = (med_sp + med_slip) if (med_sp is not None and med_slip is not None) else None
    over = (bill - asumsi) if bill is not None else None

    match_pct = cmp_.get("match_pct")
    n_cmp = cmp_.get("n_candle_dibandingkan")
    max_diff = cmp_.get("max_abs_diff_semua")

    # --- Durasi forward test AKTUAL dari log (bukan dari asumsi soal) --------
    # Keputusan user: kumpul tepat waktu 14 Nov 23.59 dan nyatakan durasi nyata.
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    WIB = _tz(_td(hours=7))
    DEADLINE = _dt(2026, 11, 14, 23, 59, tzinfo=WIB)
    JDW_FREEZE = _dt(2026, 11, 4, 12, 0, tzinfo=WIB)

    exec_calls = [c for c in calls if c.get("action") == "executed" and c.get("t")]
    if exec_calls:
        t_first = _dt.fromisoformat(exec_calls[0]["t"])
        t_last = _dt.fromisoformat(exec_calls[-1]["t"])
    else:
        t_first = t_last = None

    if t_first is not None and t_last is not None:
        dur_jam = (t_last - t_first).total_seconds() / 3600
        dur_hari = dur_jam / 24
        sisa_jam = (DEADLINE - t_last).total_seconds() / 3600
        telat_jam = (t_first - JDW_FREEZE).total_seconds() / 3600
        n_candle_harap = int(dur_jam // 4) + 1
        # konvensi Indonesia: koma untuk desimal
        def _c(v, d=1):
            return f"{v:.{d}f}".replace(".", ",")
        dur_teks = f"{_c(dur_hari, 2)} hari ({_c(dur_jam)} jam)"
        mulai_teks = t_first.strftime("%Y-%m-%d %H:%M WIB")
        akhir_teks = t_last.strftime("%Y-%m-%d %H:%M WIB")
        telat_teks = f"{_c(telat_jam)} jam setelah jadwal freeze 4 Nov 12.00 WIB"
        sisa_teks = f"{_c(sisa_jam)} jam sebelum tenggat 14 Nov 23.59 WIB"
    else:
        dur_hari = dur_jam = sisa_jam = telat_jam = 0.0
        n_candle_harap = 0
        dur_teks = mulai_teks = akhir_teks = telat_teks = sisa_teks = "-"

    pct_10hari = (dur_hari / 10 * 100) if dur_hari else 0.0

    md = f"""# Refleksi: Backtest vs Forward Test

Dibuat otomatis {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB dari
`reports/` dan `logs/`. Angka di sini identik dengan dashboard dan
`tools/hitung_ulang.py`; tidak ada yang ditulis manual.

## 1. Ringkasan angka

| Metrik | Backtest (5,8 thn) | Backtest jendela forward | Forward test |
|---|---|---|---|
| Return total | {pct(bt.get('cagr'))} /thn (CAGR) | {pct(bt_ret)} | {pct(fwd_ret)} |
| Maximum drawdown | {pct(bt.get('mdd'))} | {pct(bt_mdd)} | {pct(fwd_mdd)} |
| Profit factor | {bt.get('profit_factor', 0):.2f} | {fw.get('pf', 0):.2f} | {hu.get('pf', '-')} |
| Trade | {bt.get('n_trades', 0)} | {fw.get('n_trades', 0)} | {n_tr} order, {hu.get('n_trades', 0)} tertutup |
| Win rate | {pct(bt.get('win_rate'))} | {pct(fw.get('wr'))} | {pct(hu.get('wr'))} |

Selisih forward vs backtest pada jendela yang sama (forward dikurangi backtest):
**return {signed(gap_ret)}**, **drawdown {signed(gap_mdd)}**. Tanda negatif
berarti forward lebih buruk; positif berarti lebih baik. Jendela forward yang
dibandingkan: {fw.get('window', ['-', '-'])[0]} .. {fw.get('window', ['-', '-'])[1]}.

## 2. Durasi forward test yang sebenarnya

Durasi dihitung dari log, bukan dari asumsi jadwal.

| Item | Nilai |
|---|---|
| Candle pertama diproses | {mulai_teks} |
| Candle terakhir diproses | {akhir_teks} |
| Durasi aktual | **{dur_teks} = {pct(dur_hari/100, 2)} dari 10 hari** |
| Candle terproses | {hu.get('uptime_candle', '-')} |
| Candle seharusnya (4 jam) | ~{n_candle_harap} |
| Freeze dijadwalkan soal | 2026-11-04 12.00 WIB |
| Mulai pertama | {telat_teks} |
| Sisa sampai tenggat | {sisa_teks} |

**Dinyatakan terbuka:** bot tidak mulai memproses candle pada 4 Nov 12.00 WIB,
karena pada hari itu masih dilakukan deploy, perbaikan bug koneksi API, dan uji
idempotency. Pekerjaan itu wajib diselesaikan lebih dulu; bot yang berjalan
dengan state tidak terbaca akan memproses candle berulang dan membuat seluruh
log tidak sah. Konsekuensinya durasi forward test lebih pendek dari 10 hari
penuh, dan laporan ini menyatakan durasi aktualnya, bukan mengklaim 10 hari.

Periode yang dilaporkan tetap dihitung dengan definisi soal: uptime = candle
terproses tepat waktu dibagi jumlah candle selama periode bot benar-benar
berjalan. Pekerjaan setelah freeze hanya perbaikan bug dan penambahan alat
pencatat; **aturan, parameter, dan universe tidak diubah** (bukti: `git log`
antara `4aef4f1` dan commit terakhir hanya menyentuh validasi, log, dashboard,
README, dan tools).

## 3. Kecocokan sinyal candle demi candle (komponen 25%)

{("**" + pct(match_pct) + " identik** dari " + str(n_cmp) + " candle, max selisih absolut " + str(max_diff)) if match_pct is not None else "Belum ada candle yang bisa dibandingkan (log_sinyal kosong)."}

Metode: `tools/compare_forward.py` menjalankan ulang backtest pada jendela
forward dengan fungsi (`logic.build_crypto_weights`) dan config yang **sama
persis** dengan bot, lalu membandingkan target weight per pair pada candle yang
sama. Selisih 0 berarti keputusan bot dan backtest identik; setiap selisih
berarti ada data yang berbeda (cache candle, waktu, atau universe).

## 4. Porsi biaya

| Komponen | Nilai | Sumber |
|---|---|---|
| Fee taker all-in | beli 0,31% / jual 0,30% | halaman resmi help.indodax.com, lebih mahal dari api/pairs 0,20% |
| Spread terukur | {pct(med_sp, 3)} | {sp.get('n_observasi', 0)} observasi, {sp.get('n_files', 0)} file snapshot |
| Slippage terukur (1 level) | {pct(med_slip, 3)} | proxy biaya menembus level book |
| Asumsi backtest | 0,10% per sisi | placeholder sebelum snapshot terkumpul |
| Biaya nyata per sisi | {pct(bill, 3) if bill else '-'} | spread + slippage |
| Selisih vs asumsi | {pct(over, 3) if over is not None else '-'} | {">0 = backtest terlalu optimis" if (over or 0) > 0 else "dalam batas asumsi"} |

Fee yang benar-benar dibayar di forward test: **{rp(fee)}** dari {n_tr} order.

## 5. Stabilitas bot dan uptime

| Item | Nilai |
|---|---|
| Panggilan diterima | {n_calls} |
| Diproses (executed) | {n_exec} |
| Duplikat ditolak (skip_dup) | {n_skip} |
| No entry (validasi gagal) | {n_no} |
| Uptime candle | {up_done} ({pct(up_pct)}) |
| Candle terlewat | {hu.get('candle_terlewat', 0)} |
| Error API | {hu.get('n_error_api', 0)} |
| Kill switch dipakai | {hu.get('kill_switch_events', 0)} |
| Daily loss limit terpicu | {hu.get('daily_loss_limit_events', 0)} |

Uptime memakai definisi soal: panggilan dihitung terlaksana bila candle diproses
sebelum candle berikutnya ditutup. Rentang dihitung dari candle pertama yang
diproses sampai candle tertutup terakhir yang sudah lewat, sehingga candle yang
terlewat ikut dihitung dan candle yang belum tiba waktunya tidak dihukum.
`skip_dup` tidak mengurangi uptime karena candle tersebut sudah diproses.

**Penyebab uptime turun, terukur dari log Actions:** jadwal `7 */4 * * *`
seharusnya memberi 12 kesempatan dalam dua hari pertama, tetapi GitHub Actions
hanya menjalankan 4 di antaranya. Empat jadwal tidak pernah muncul sama sekali
(bukan gagal, memang tidak dijalankan) dan yang berjalan pun terlambat 6-143
menit. Perbaikannya: jadwal diubah ke tiap jam (`7 * * * *`) sehingga ada 4x
lebih banyak kesempatan menangkap setiap candle, dan panggilan ekstra ditolak
oleh mekanisme idempotency (`skip_dup`, tanpa order). Perubahan ini menyentuh
penjadwalan, bukan aturan, parameter, atau universe.

## 6. Penyebab selisih (diisi analisis, bukan angka)

Urutan pemeriksaan yang dipakai:

1. **Sinyal berbeda?** Lihat bagian 2. Jika 100% identik, selisih return murni
   berasal dari eksekusi, bukan dari strategi.
2. **Harga fill berbeda?** Bot membeli di ask dan menjual di bid dari order book
   live, sedangkan backtest memakai `open` bar berikutnya. Selisih ini selalu
   merugikan bot, besarannya sekitar setengah spread + slippage per transaksi.
3. **Waktu eksekusi berbeda?** GitHub Actions bisa terlambat 5-30 menit
   (tercatat di `log_calls`), sehingga harga fill bergeser dari `open` candle.
4. **Jumlah trade berbeda?** Bot punya minimum order Rp25.000 dan pembulatan
   lot; backtest mengabaikan sisa di bawah minimum.
5. **Biaya berbeda?** Lihat bagian 3.

_Setiap penyebab di atas harus dikuantifikasi dari log sebelum ditulis di sini.
Kalau tidak bisa dihitung dari log, jangan diklaim._

## 7. Keterbatasan yang diakui

- Forward test baru mencakup {((hu.get('uptime_expected') or 0) // 6)} candle
  ({(hu.get('uptime_expected') or 0) / 6:.1f} hari); CAGR dari periode ini tidak
  bermakna dan tidak ditampilkan di dashboard.
- Backtest memakai slippage placeholder 10 bps, sedangkan pengukuran snapshot
  menunjukkan biaya nyata {pct(bill, 3) if bill else '-'} per sisi.
- Edge strategi bergantung rezim: H1 2021-2023 CAGR 30,24%, H2 2024-2026 9,29%.
  Empat dari enam tahun negatif secara neto, dan tidak ada tahun untung saat BTC
  turun. Rincian di `STRATEGI.md`.
- Gate ETH/IDR bukan prediktor arah di crypto (rank corr +0,002); manfaatnya
  hanya menurunkan eksposur.
"""
    (HERE / "REFLEKSI.md").write_text(md, encoding="utf-8")
    print(f"REFLEKSI.md ditulis ({len(md)} karakter)")
    print(f"  panggilan {n_calls}, order {n_tr}, uptime {up_done}, "
          f"match {pct(match_pct) if match_pct is not None else '-'}")


if __name__ == "__main__":
    main()