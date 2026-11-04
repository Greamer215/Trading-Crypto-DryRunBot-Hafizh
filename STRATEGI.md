# Strategi Tertulis + Catatan Perubahan dari UTS

## Strategi (aturan lengkap; freeze efektif = commit adopsi 2026-11-04)

**Universe (10 pair, anti-survivorship):** BTC, ETH, BNB, DOGE, ADA, XRP, UNI,
DOT, TRX, LTC (pasangan IDR). Dipilih dari median turnover Rp per bar 4h pada
90 hari pertama backtest (2021-01..2021-04), BUKAN likuiditas hari ini. Beku
sejak seleksi, dipakai sama untuk backtest dan forward. Alat seleksi:
`tools/select_universe.py`, hasil: `data/universe_selected.json`.

**Sinyal masuk:** skor tren = OLS slope(log close, 60 bar 4h), **murni tanpa
pengali t-stat** (freeze 3, 2026-11-04). Sebelumnya `slope x max(0,tstat)`,
diubah karena terukur bermasalah: formulasi itu sama dengan `slope^2/se`
sehingga 50,7% observasi bernilai 0 persis, dan di 13,9% bar SEMUA pair
skor <= 0 sehingga `equal_weights` memilih lewat tie-break urutan kolom
(bot membeli BTC/ETH/BNB/DOGE/ADA 100% konsisten bukan karena sinyal).
Setelah perubahan: skor 0 = 0,00%, tie di top-5 = 0 bar, dan di 1.773 bar
"semua negatif" seleksi memilih yang paling tidak turun (nilai distinct 100%).
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

**Yang TIDAK berubah (core beku):** fungsi skor tren (`trend_reg_score` tetap
ada di `logic/core.py` sebagai referensi IDX, tidak dihapus), equal_weights,
time_exit overlay, soft_market_gate, scale_in_overlay, urutan pipeline.
`logic/core.py` = salinan verbatim dari `trading-desk-hafizh/logic/core.py`.

**Satu-satunya penyimpangan dari core:** `crypto_trend_score` di
`logic/pipeline.py` memakai slope murni. Fungsi core tidak diedit; varian crypto
ditulis sebagai wrapper terpisah supaya core tetap utuh dan perbedaannya
terlihat eksplisit.

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

### Freeze 3, skor tren = slope murni (2026-11-04)

CAGR 19,53%, MDD -42,58%, Calmar 0,46, Sharpe 0,76, PF 1,53, 772 trade,
WR 37,6%, fee 14,0% laba kotor, equity Rp100jt -> Rp283,5jt (5,8 tahun).
Split-half: H1 30,24% (Calmar 0,710) / H2 9,29% (Calmar 0,251).
Uji fase 10 offset: Calmar 0,400-0,483 (med 0,430, sd 0,026), H2 Calmar
0,156-0,263 (med 0,238). Benchmark buy-hold BTC: +238,5%.

Per tahun: 2021 +141,90% | 2022 -15,76% | 2023 +8,27% | 2024 +56,29% |
2025 -20,58% | 2026 +3,51%.

### Freeze 2, skor tren = slope x max(0,tstat) (pembanding)

CAGR 15,31%, MDD -48,59%, Calmar 0,32, Sharpe 0,64, PF 1,43, 777 trade,
WR 37,6%, fee 15,2% laba kotor, equity Rp100jt -> Rp229,8jt (5,8 tahun).
Benchmark buy-hold BTC: +238,5%.

Catatan protokol: freeze pertama `b0a6288` (gate BTC, cap 20%) terlambat 15
menit dari jadwal 12.00; gate ETH dan cap 12% diadopsi SETELAHnya atas
keputusan eksplisit user yang menerima konsekuensi pengurangan nilai. Freeze
efektif = commit adopsi ini.

## Diagnosis: mengapa performa di crypto lebih lemah

Tiga lapis, berurutan dari dampak terbesar. Semua diukur, bukan dugaan.

### 1. Edge-nya rezim, bukan parameter

Return per tahun (config beku):

| Tahun | Return | Biaya | Net | Expo | BTC |
|---|---|---|---|---|---|
| 2021 | +132,4% | 14,8% | +117,6% | 0,36 | +62,2% |
| 2022 | −16,8% | 10,0% | −26,8% | 0,22 | −61,5% |
| 2023 | −1,4% | 14,6% | −15,9% | 0,35 | +155,7% |
| 2024 | +53,5% | 13,3% | +40,2% | 0,30 | +130,8% |
| 2025 | −23,1% | 13,4% | −36,4% | 0,27 | −3,9% |
| 2026 | +2,1% | 8,9% | −6,7% | 0,28 | −5,7% |

Empat dari enam tahun negatif net. Dua tahun untung kebetulan tahun BTC naik
>60%. Tidak ada tahun di mana strategi untung saat BTC turun. IDX sebaliknya:
untung 2008 (+4,02%) saat krisis, konsisten 2013-2018, +227,98% di 2025.

Sebabnya struktural: IDX punya rotasi sektor, jadi ranking top-5 punya tempat
berlindung. Crypto korelasi antar pair 0,54, jadi saat BTC jatuh semuanya jatuh
serempak. Biaya juga tetap 9-15% per tahun termasuk tahun rugi.

### 2. Biaya memakan 51% laba kotor

| | Crypto | IDX |
|---|---|---|
| CAGR gross | 31,09% | 28,86% |
| CAGR net | 15,31% | 26,89% |
| Biaya memakan | 15,78 pp (51%) | 1,97 pp (7%) |
| Calmar gross | 0,85 | 0,85 |
| Calmar net | 0,32 | 0,75 |
| Turnover/tahun | 31,6x | 7,7x |
| Biaya round-trip | 0,81% | 0,40% |

Gross Calmar crypto 0,85 = IDX 0,85: sinyalnya sama bagusnya. Yang berbeda
gesekannya: turnover 4,1x, tarif 2,0x, drag 0,26/tahun vs 0,03/tahun (8,7x).
Uji level biaya: tanpa biaya CAGR 31,09%, biaya setara IDX 19,16%, biaya resmi
Indodax 15,31%. Jadi 11,8 pp hilang karena tarif, 3,9 pp karena churn.

### 3. Sinyal tipis dan berisik

IC cross-sectional (rank corr skor vs forward return):

| Horizon | IDX IC | Crypto IC |
|---|---|---|
| Pendek (10-21 bar) | +0,0162 | −0,0125 |
| Menengah (44 bar) | +0,0176 | +0,0037 |
| Panjang (88 bar) | - | +0,0247 |

Di horizon pendek crypto negatif: skor tren tidak informatif bahkan sedikit
berlawanan. sd IC crypto 0,36 vs IDX 0,10, noise 3,5x lebih besar.

## Logic yang works di IDX tapi TIDAK di crypto

Diuji langsung ke repo IDX (read-only), bukan dugaan.

| Logic | IDX | Crypto | Putusan |
|---|---|---|---|
| Market gate | rank corr +0,165; fwd 1 bulan saat gate tutup −2,11% vs buka +0,81% | rank corr +0,002 (ETH), −0,015 (BTC); saat BTC-gate tutup fwd malah +0,081% | IDX-only sebagai prediktor. Di crypto tetap dipakai karena terbukti menahan DD (gate mati -> H2 Calmar −0,134), tapi manfaatnya dari eksposur lebih rendah, bukan dari meramal. |
| Scale-in overlay | inert: 26,89% vs 26,89% saat dimatikan (0,00 pp), karena gate + max_entry_gap memblokir jalurnya | 20,49% -> 20,79% saat dimatikan: sedikit merugikan | Tidak berguna di keduanya. Klaim awal bahwa ini berguna di IDX salah, sudah dikoreksi dengan pengukuran. |
| Vol floor 5%/tahun | menyaring nama stagnan (vol saham 20-40%) | vol crypto 52-118%, filter lolos 100% bar: tidak pernah mengikat | IDX-only secara diam-diam. |
| Top-5 dari universe | 5 dari ~100 = 5% populasi | eligible 8,4 dari 10 pair, top-5 = 60% populasi; 25,3% bar semua 10 lolos | Kehilangan makna selektif. |
| Equal-weight 20% | 20% x vol 35% = risiko ~7%/nama | 20% x vol 90% = risiko ~18%/nama; 5 nama korelasi 0,54 -> vol portofolio ~40% | Tidak portabel, diganti cap 0,12. |
| Time exit 44 bar | 44 hari = 2 bulan | 44 bar 4h = 7,3 hari, padahal edge baru muncul di 88 bar | Satuan tidak portabel, dikalibrasi ke 88. |
| **Skor tren `slope x max(0,tstat)`** | ~100 nama, hampir selalu ada >=5 yang tren naik, jadi klip t-stat tidak pernah mengosongkan kandidat | 50,7% observasi skor = 0 persis; 13,9% bar semua skor <= 0 -> tie-break urutan kolom memilih BTC/ETH/BNB/DOGE/ADA 100% konsisten; 35,9% bar hanya 1-4 kandidat positif; total ~49,8% bar seleksi arbitrer | **IDX-only secara diam-diam.** Diganti slope murni (freeze 3): skor 0 jadi 0,00%, tie 0 bar, Calmar median 0,320 -> 0,430, H2 0,175 -> 0,238. |

## Kandidat yang diuji dan DITOLAK

Aturan adopsi: harus menang KEDUA paruh dan tahan uji fase (offset re-rank
digeser 0..every-1).

| Kandidat | Hasil | Putusan |
|---|---|---|
| Vol targeting (13 kombinasi, 2 implementasi) | PF 1,48 -> 1,07; CAGR ~0% | Ditolak. Vol tinggi crypto = fase tren naik, memotong eksposur saat vol naik = memotong pemenang. |
| DD governor (27 kombinasi + 4 varian peak) | full-sample Calmar 0,529 tapi H2 0,053; eksposur terkunci di lantai 0,25 setelah crash dalam | Ditolak. Menang H1 saja. Cacat: DD dari puncak sepanjang sejarah tidak bisa pulih. |
| Gate dimatikan (6 varian) | Calmar median 0,101-0,254 vs baseline 0,320; H2 Calmar negatif | Ditolak. Gate ETH justru yang menahan DD. |
| every 30/40/60 | kalah atau setara di uji fase; every=60 tampak juara (0,635) hanya di 1 dari 60 offset, rentang 0,066-0,547 | Ditolak, artefak fase. |
| time_exit 132/176/none | +0,3-0,7 pp, di dalam noise | Tidak diadopsi, tidak signifikan. |
| Universe 12 atau 18 pair | Calmar full-sample 0,388-0,399 naik, tapi H2 0,174/0,147 vs baseline 0,175; sd fase memburuk 3x | Ditolak. Pola sama: menang 2021-2023, kalah 2024-2026. |
| Filter korelasi 0,70/0,85 | 0,85 turunkan semua metrik; 0,70 CAGR negatif, PF 1,04-1,09 | Ditolak. |
| Cap 0,10 / 0,08 | Calmar naik tapi CAGR turun >2,5 pp per 0,05; 0,08 CAGR 10,3% | Ditolak, 0,12 dipilih. |
| Lookback 90 | full-sample 21,21% tapi H2 +0,3% / −3,0% | Ditolak, artefak bull 2021-23. |
| Varian skor: tanpa pick arbitrer (kas) | Calmar 0,483 tapi H2 0,025 | Ditolak, menang H1 saja. |
| Varian skor: slope x clip(tstat,0,2) | Calmar 0,352, H2 0,218 | Ditolak, kalah dari slope murni di semua sumbu. |
| Varian skor: skor jadi rank cross-sectional | **identik baseline sampai 4 desimal** | Ditolak, bukti ranking tidak terpengaruh konkavitas/konveksitas skor. |

Pola yang muncul di SEMUA kandidat parameter: menang full-sample, kalah di H2.
Itu tanda parameter tidak punya edge yang bisa ditambang lebih jauh, bukan tanda
tuning belum selesai.

**Pengecualian tunggal: skor tren slope murni.** Ini satu-satunya kandidat yang
menang di KEDUA paruh sekaligus (Calmar median 0,430 vs 0,320; H2 0,238 vs
0,175; H2-min 0,156 vs 0,097; turnover turun; sd fase setara). Alasannya karena
ia bukan tuning parameter, melainkan perbaikan cacat struktural: formulasi
`slope x max(0,tstat)` mengosongkan kandidat dan menyerahkan seleksi ke urutan
kolom file. Semua kandidat lain adalah tuning, dan semua tuning gagal.

Skrip pembukti (semua ada di repo): `tools/diag_where.py` (dekomposisi biaya +
IC), `tools/diag_churn.py` (turnover vs IDX), `tools/diag_feelevel.py` (uji level
biaya), `tools/diag_yearly.py` (per tahun), `tools/phase_test.py` dan
`tools/gateoff_phase.py` (uji fase), `tools/universe_wide.py`,
`tools/diag_score.py` (cacat skor), `tools/diag_tiebreak.py` (verifikasi
tie-break hilang), `tools/score_variants.py` (varian skor),
`tools/validate_slope.py` (validasi freeze 3).
