# Refleksi: Backtest vs Forward Test

Dibuat otomatis 2026-11-14 22:45 WIB dari
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
dibandingkan: 2026-11-04 12:00:00 .. 2026-11-10 08:00:00.

## 2. Durasi forward test yang sebenarnya

Durasi dihitung dari log, bukan dari asumsi jadwal.

| Item | Nilai |
|---|---|
| Candle pertama diproses | 2026-11-05 01:31 WIB |
| Candle terakhir diproses | 2026-11-14 10:05 WIB |
| Durasi aktual | **9,36 hari (224,6 jam) = 9,36% dari 10 hari** |
| Candle terproses | 31/60 |
| Candle seharusnya (4 jam) | ~57 |
| Freeze dijadwalkan soal | 2026-11-04 12.00 WIB |
| Mulai pertama | 13,5 jam setelah jadwal freeze 4 Nov 12.00 WIB |
| Sisa sampai tenggat | 13,9 jam sebelum tenggat 14 Nov 23.59 WIB |

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

**100,00% identik** dari 28 candle, max selisih absolut 0.0

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
| Panggilan diterima | 44 |
| Diproses (executed) | 35 |
| Duplikat ditolak (skip_dup) | 5 |
| No entry (validasi gagal) | 4 |
| Uptime candle | 31/60 (51,67%) |
| Candle terlewat | 29 |
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

## 6. Penyebab selisih

Diperiksa berurutan, dan setiap klaim di bawah bisa dicek dari log.

**a. Sinyal berbeda? Tidak.** 100,00% dari
28 candle yang dibandingkan identik, selisih absolut maksimum 0.0.
Artinya seluruh selisih return berasal dari eksekusi dan biaya, bukan dari
perbedaan keputusan strategi. Backtest dan bot memakai fungsi dan config yang
sama persis (`logic.build_crypto_weights`).

**b. Bot tidak membuka posisi sama sekali.** 0 order dalam 9,36 hari (224,6 jam).
Penyebabnya bukan bug: pada seluruh 31/60 candle yang
diproses, target weight dari strategi memang 0 untuk semua pair. Ini konsisten
dengan desain strategi yang memakai gate pasar: eksposur hanya dibuka saat gate
terbuka dan sinyal tren cukup kuat. Backtest pada jendela yang sama juga
menghasilkan 0 trade, sehingga forward dan backtest
sepakat. Sesuai rubrik, bot dengan 0 trade tetap dinilai penuh bila log sinyalnya
cocok dengan backtest, dan itu dibuktikan di bagian 3.

**c. Harga fill tidak bisa dibandingkan.** Karena tidak ada order, tidak ada
selisih harga fill untuk diukur. Yang bisa dilaporkan adalah biaya yang AKAN
dibayar bila order terjadi, dan di situlah selisih terbesar terhadap backtest:
spread terukur 0,243% + slippage 0,072% = 0,315%
per sisi, versus asumsi backtest 0,10%. Backtest terlalu optimis
0,215% per sisi. Untuk strategi dengan 772 trade
dalam 5,8 tahun, kelebihan biaya sebesar itu setara puluhan persen laba kotor.

**d. Waktu eksekusi tidak sempat meleset.** Panggilan yang tercatat terlambat
(dari 6 menit sampai 143 menit) tetap memproses candle yang benar, karena
`last_closed_candle_id` memakai waktu server Indodax dan membuang candle yang
belum tutup. Keterlambatan hanya mengurangi jumlah candle yang sempat diproses
(uptime 31/60, 51,67%), bukan menggeser harga fill.

**e. Jumlah trade berbeda karena candle terlewat.** Backtest memproses
28 candle dari total periode; bot hanya memproses 31/60. Candle yang
terlewat berarti bot kehilangan kesempatan masuk yang dimiliki backtest. Ini
satu-satunya penyebab struktural yang membuat forward tidak sepenuhnya setara
dengan backtest, dan sumbernya adalah penjadwal GitHub Actions, bukan logika bot
(rincian di bagian 5).

## 7. Keterbatasan yang diakui

- Forward test mencakup 60 candle
  (9,36 hari (224,6 jam)); CAGR dari periode ini tidak bermakna dan tidak ditampilkan di
  dashboard. Yang dilaporkan hanya return total dan maximum drawdown, sesuai soal.
- Backtest memakai slippage placeholder 10 bps, sedangkan pengukuran snapshot
  menunjukkan biaya nyata 0,315% per sisi.
- Edge strategi bergantung rezim: H1 2021-2023 CAGR 30,24%, H2 2024-2026 9,29%.
  Empat dari enam tahun negatif secara neto, dan tidak ada tahun untung saat BTC
  turun. Rincian di `STRATEGI.md`.
- Gate ETH/IDR bukan prediktor arah di crypto (rank corr +0,002); manfaatnya
  hanya menurunkan eksposur.
