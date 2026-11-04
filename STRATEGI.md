# Strategi Tertulis + Catatan Perubahan dari UTS

## Strategi (aturan lengkap, beku sejak commit b0a6288)

**Universe (10 pair, anti-survivorship):** BTC, ETH, BNB, DOGE, ADA, XRP, UNI,
DOT, TRX, LTC (pasangan IDR). Dipilih dari median turnover Rp per bar 4h pada
90 hari pertama backtest (2021-01..2021-04), BUKAN likuiditas hari ini. Beku
sejak seleksi, dipakai sama untuk backtest dan forward. Alat seleksi:
`tools/select_universe.py`, hasil: `data/universe_selected.json`.

**Sinyal masuk:** skor tren = OLS slope(log close, 60 bar 4h) x max(0, t-stat).
Setiap 10 bar (40 jam), pilih 5 pair skor tertinggi yang lolos filter likuiditas
(trailing median turnover 80 bar > Rp50jt per bar, vol tahunan > 5%).

**Bobot:** equal-weight 1/5 per nama terpilih, maksimum 20% per pair.

**Overlay scale-in:** rata-rata turun pada z-score OU 63 bar (entry_z 1.5,
max_scale 1.25); posisi baru diblok bila gap open > 10% dari close sebelumnya.

**Gate pasar:** gross exposure x clip(0.5 + 4000 x slope120(log BTC/IDR), 0, 1).
Saat BTC downtrend, exposure menyusut otomatis (di backtest gate rata-rata 0.52,
tutup penuh 42,6% waktu).

**Keluar:** (1) keluar dari top-5 saat re-rank; (2) time stop: posisi dipegang
> 88 bar (14,7 hari) DAN return < +9% dibuang; (3) keduanya dari fungsi beku
IDX yang sama.

**Eksekusi:** beli di ask, jual di bid dari ticker live; fee taker all-in
beli 0,31% / jual 0,30% + slippage 10bps (placeholder s/d median spread
snapshot terkumpul); order minimum Rp25.000 (mode Pro).

**Risk management:** maks 10 posisi, maks 20% per pair, daily loss limit -5%
(batas hari 00.00 WIB), kill switch env, idempotency per candle, retry terbatas.

## Perubahan dari versi UTS (IDX saham) -> crypto

| Aspek | UTS (IDX harian) | UAS (crypto 4h) | Alasan |
|---|---|---|---|
| Universe | Kompas100 PIT + floor Rp5M/hari | 10 pair, likuiditas diukur 90 hari pertama | Syarat soal: anti-survivorship di awal backtest |
| Timeframe | Harian | 4 jam | Soal: 10 hari forward harian cuma 10 candle |
| signal_lookback | 120 | 60 | Split-half 2/2 paruh (grid 36 kombinasi) |
| universe_lookback | 40 | 80 | Idem |
| time_exit | 44 bar | 88 bar | Idem |
| Gate proxy | IHSG | BTC/IDR | Crypto 24/7, tak ada indeks |
| Bobot | equal-weight | equal-weight (tetap) | - |
| Biaya | IDX 0,1513%/0,2513% + lot + ARA/ARB | taker 0,31%/0,30% + slip, tanpa lot | Struktur pasar |
| Eksekusi | open next bar | ask/bid live saat tick | Soal: dilarang fill di mid/close |

**Yang TIDAK berubah (core beku):** fungsi skor tren, equal_weights, time_exit
overlay, soft_market_gate, scale_in_overlay, urutan pipeline. Verbatim dari
`trading-desk-hafizh/logic/core.py`.

## Jumlah kombinasi yang dicoba (transparansi)

- Grid kalibrasi biaya/universe/n_top: 36 kombinasi
- Grid lookback: 36 kombinasi
- Grid optimasi pos-cap/korelasi/te: 18 kombinasi
- Validasi: split-half H1 (2021-23) vs H2 (2024-26); adopsi hanya kandidat yang
  menang KEDUA paruh. Kandidat 90 ditolak (H2 runtuh), filter korelasi ditolak,
  pos cap 0.08 ditolak (CAGR hilang).

## Hasil backtest (fee resmi 0,31%/0,30% + slip 10bps)

CAGR 9,71%, MDD -72,26%, Calmar 0,13, PF 1,38, 819 trade, WR 37,9%,
fee 15,3% laba kotor, equity Rp100jt -> Rp171,8jt (5,8 tahun).
Split-half: H1 +19,6%/H2 +12,8% (pada fee lama 0,20%; re-run H1/H2 fee baru
menyusul di dashboard). Benchmark buy-hold BTC: +238,5%.
