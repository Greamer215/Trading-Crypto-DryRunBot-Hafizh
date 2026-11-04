# Strategi Tertulis + Catatan Perubahan dari UTS

## Strategi (aturan lengkap; freeze efektif = commit adopsi 2026-11-04)

**Universe (10 pair, anti-survivorship):** BTC, ETH, BNB, DOGE, ADA, XRP, UNI,
DOT, TRX, LTC (pasangan IDR). Dipilih dari median turnover Rp per bar 4h pada
90 hari pertama backtest (2021-01..2021-04), BUKAN likuiditas hari ini. Beku
sejak seleksi, dipakai sama untuk backtest dan forward. Alat seleksi:
`tools/select_universe.py`, hasil: `data/universe_selected.json`.

**Sinyal masuk:** skor tren = OLS slope(log close, 60 bar 4h) x max(0, t-stat).
Setiap 10 bar (40 jam), pilih 5 pair skor tertinggi yang lolos filter likuiditas
(trailing median turnover 80 bar > Rp50jt per bar, vol tahunan > 5%).

**Bobot:** equal-weight 1/5 per nama terpilih, maksimum 12% per pair.

**Overlay scale-in:** rata-rata turun pada z-score OU 63 bar (entry_z 1.5,
max_scale 1.25); posisi baru diblok bila gap open > 10% dari close sebelumnya.

**Gate pasar:** gross exposure x clip(0.5 + 4000 x slope120(log ETH/IDR), 0, 1).
Diadopsi 2026-11-04 setelah jadwal freeze 12.00 (keputusan user, penalti telat
diterima): menang split-half kedua paruh vs BTC-gate (H1 34,6%/0,50, H2
7,7%/0,13 vs 12,8%/0,18 dan 6,8%/0,12). Catatan jujur: daya prediksi gate itu
sendiri di crypto ~nol (rank corr +0,002 vs +0,17 di IDX); manfaatnya datang
dari menutup sedikit lebih sering (45,5% vs 42,6% waktu) sehingga eksposur
turun. Di refleksi ini dibedakan dari klaim prediktif.

**Keluar:** (1) keluar dari top-5 saat re-rank; (2) time stop: posisi dipegang
> 88 bar (14,7 hari) DAN return < +9% dibuang; (3) keduanya dari fungsi beku
IDX yang sama.

**Eksekusi:** beli di ask, jual di bid dari ticker live; fee taker all-in
beli 0,31% / jual 0,30% + slippage 10bps (placeholder s/d median spread
snapshot terkumpul); order minimum Rp25.000 (mode Pro).

**Risk management:** maks 10 posisi, maks 12% per pair, daily loss limit -5%
(batas hari 00.00 WIB), kill switch env, idempotency per candle, retry terbatas.

## Perubahan dari versi UTS (IDX saham) -> crypto

| Aspek | UTS (IDX harian) | UAS (crypto 4h) | Alasan |
|---|---|---|---|
| Universe | Kompas100 PIT + floor Rp5M/hari | 10 pair, likuiditas diukur 90 hari pertama | Syarat soal: anti-survivorship di awal backtest |
| Timeframe | Harian | 4 jam | Soal: 10 hari forward harian cuma 10 candle |
| signal_lookback | 120 | 60 | Split-half 2/2 paruh (grid 36 kombinasi) |
| universe_lookback | 40 | 80 | Idem |
| time_exit | 44 bar | 88 bar | Idem |
| Gate proxy | IHSG | ETH/IDR | Adopsi post-freeze 2026-11-04, keputusan user |
| Bobot | equal-weight | equal-weight + cap 12% | Normalisasi risiko: vol crypto 2-3x saham |
| Biaya | IDX 0,1513%/0,2513% + lot + ARA/ARB | taker 0,31%/0,30% + slip, tanpa lot | Struktur pasar |
| Eksekusi | open next bar | ask/bid live saat tick | Soal: dilarang fill di mid/close |

**Yang TIDAK berubah (core beku):** fungsi skor tren, equal_weights, time_exit
overlay, soft_market_gate, scale_in_overlay, urutan pipeline. Verbatim dari
`trading-desk-hafizh/logic/core.py`.

## Jumlah kombinasi yang dicoba (transparansi)

- Grid kalibrasi biaya/universe/n_top: 36 kombinasi
- Grid lookback: 36 kombinasi
- Grid optimasi pos-cap/korelasi/te: 18 kombinasi
- Grid DD (pos cap x gross cap x gate x scale): 12 kombinasi (`grid_dd.csv`)
- Vol targeting: 13 kombinasi, 2 implementasi (tiap-bar + step-10) -> DITOLAK
  (PF 1,48 -> 1,07; vol tinggi crypto = fase tren naik, memotong eksposur
  saat vol naik = memotong pemenang)
- DD governor: 27 kombinasi + 4 varian peak (all/365/180/90 hari) -> DITOLAK
  (menang H1 saja: H2 Calmar 0,053 vs baseline 0,134; peak sepanjang sejarah
  mengunci eksposur di lantai setelah crash dalam)
- Uji silang daya prediksi gate: rank corr gate vs fwd return: IDX +0,165,
  crypto ETH +0,002, BTC -0,015 -> gate crypto = penurun eksposur, bukan prediktor
- Validasi: split-half H1 (2021-23) vs H2 (2024-26); adopsi hanya kandidat yang
  menang KEDUA paruh. Ditolak: lookback 90 (artefak bull 2021-23), filter
  korelasi (CAGR negatif), pos cap 0.08 (CAGR hilang), vol targeting, governor.

## Hasil backtest (fee resmi 0,31%/0,30% + slip 10bps, cap 12%)

CAGR 15,31%, MDD -48,59%, Calmar 0,32, Sharpe 0,64, PF 1,43, 777 trade,
WR 37,6%, fee 15,2% laba kotor, equity Rp100jt -> Rp229,8jt (5,8 tahun).
Benchmark buy-hold BTC: +238,5%.

Catatan protokol: freeze pertama `b0a6288` (gate BTC, cap 20%) terlambat 15
menit dari jadwal 12.00; gate ETH dan cap 12% diadopsi SETELAHnya atas
keputusan eksplisit user yang menerima konsekuensi pengurangan nilai. Freeze
efektif = commit adopsi ini.
