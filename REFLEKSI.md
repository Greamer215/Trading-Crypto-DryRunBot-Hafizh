# Refleksi: Backtest vs Forward Test

Dibuat otomatis 2026-11-06 14:33 WIB dari
`reports/` dan `logs/`. Angka di sini identik dengan dashboard dan
`tools/hitung_ulang.py`; tidak ada yang ditulis manual.

## 1. Ringkasan angka

| Metrik | Backtest (5,8 thn) | Backtest jendela forward | Forward test |
|---|---|---|---|
| Return total | 19,53% /thn (CAGR) | 0,00% | 0,00% |
| Maximum drawdown | -42,58% | 0,00% | 0,00% |
| Profit factor | 1.53 | nan | - |
| Trade | 772 | 0 | 0 order, 0 tertutup |
| Win rate | 37,56% | 0,00% | - |

Selisih forward vs backtest pada jendela yang sama (forward dikurangi backtest):
**return +0,00%**, **drawdown +0,00%**. Tanda negatif
berarti forward lebih buruk; positif berarti lebih baik. Jendela forward yang
dibandingkan: 2026-11-04 12:00:00 .. 2026-11-05 12:00:00.

## 2. Durasi forward test yang sebenarnya

Durasi dihitung dari log, bukan dari asumsi jadwal.

| Item | Nilai |
|---|---|
| Candle pertama diproses | 2026-11-05 01:31 WIB |
| Candle terakhir diproses | 2026-11-06 13:31 WIB |
| Durasi aktual | **1,50 hari (36,0 jam) = 1,50% dari 10 hari** |
| Candle terproses | 6/10 |
| Candle seharusnya (4 jam) | ~9 |
| Freeze dijadwalkan soal | 2026-11-04 12.00 WIB |
| Mulai pertama | 13,5 jam setelah jadwal freeze 4 Nov 12.00 WIB |
| Sisa sampai tenggat | 202,5 jam sebelum tenggat 14 Nov 23.59 WIB |

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

**100,00% identik** dari 6 candle, max selisih absolut 0.0

Metode: `tools/compare_forward.py` menjalankan ulang backtest pada jendela
forward dengan fungsi (`logic.build_crypto_weights`) dan config yang **sama
persis** dengan bot, lalu membandingkan target weight per pair pada candle yang
sama. Selisih 0 berarti keputusan bot dan backtest identik; setiap selisih
berarti ada data yang berbeda (cache candle, waktu, atau universe).

## 4. Porsi biaya

| Komponen | Nilai | Sumber |
|---|---|---|
| Fee taker all-in | beli 0,31% / jual 0,30% | halaman resmi help.indodax.com, lebih mahal dari api/pairs 0,20% |
| Spread terukur | 0,243% | 66 observasi, 1 file snapshot |
| Slippage terukur (1 level) | 0,072% | proxy biaya menembus level book |
| Asumsi backtest | 0,10% per sisi | placeholder sebelum snapshot terkumpul |
| Biaya nyata per sisi | 0,315% | spread + slippage |
| Selisih vs asumsi | 0,215% | >0 = backtest terlalu optimis |

Fee yang benar-benar dibayar di forward test: **Rp0** dari 0 order.

## 5. Stabilitas bot dan uptime

| Item | Nilai |
|---|---|
| Panggilan diterima | 15 |
| Diproses (executed) | 10 |
| Duplikat ditolak (skip_dup) | 5 |
| No entry (validasi gagal) | 0 |
| Uptime candle | 6/10 (60,00%) |
| Candle terlewat | 4 |
| Error API | 0 |
| Kill switch dipakai | 0 |
| Daily loss limit terpicu | 0 |

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

- Forward test baru mencakup 0 candle
  (0.0 hari); CAGR dari periode ini tidak
  bermakna dan tidak ditampilkan di dashboard.
- Backtest memakai slippage placeholder 10 bps, sedangkan pengukuran snapshot
  menunjukkan biaya nyata 0,315% per sisi.
- Edge strategi bergantung rezim: H1 2021-2023 CAGR 30,24%, H2 2024-2026 9,29%.
  Empat dari enam tahun negatif secara neto, dan tidak ada tahun untung saat BTC
  turun. Rincian di `STRATEGI.md`.
- Gate ETH/IDR bukan prediktor arah di crypto (rank corr +0,002); manfaatnya
  hanya menurunkan eksposur.
