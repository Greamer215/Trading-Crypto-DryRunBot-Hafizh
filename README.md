# UAS Bot Dry Run Indodax

Bot trading dry run Indodax di Vercel. Strategi: momentum cross-sectional beku
(commit `b0a6288`), timeframe 4 jam, modal virtual Rp100.000.000, long-only.

## Status
- FREEZE: commit `b0a6288` (2026-11-04 12.15 WIB, 15 menit setelah deadline; dicatat jujur)
- Fee kepatuhan soal: commit `11385d6` (taker buy 0,31% / sell 0,30%, halaman resmi lebih mahal dari api/pairs)
- Backtest 5,8 tahun (2021-01..2026-11, 12800 bar 4h): CAGR 9,71% (after fee resmi), MDD -72,26%, PF 1,38, 819 trade
- Sumber biaya: api/pairs `trade_fee_percent_taker` 0,20% (akses 2026-10-31) vs
  https://help.indodax.com/hc/en-us/articles/28673592088857-Details-of-Transaction-Fees-on-Indodax
  taker buy 0,31% / sell 0,30% (akses 2026-11-04) -> pakai yang lebih mahal sesuai soal

## Arsitektur (semua gratis, hanya Vercel + GitHub)
- **Vercel Hobby**: endpoint `/api/tick` (Python, 300s) + **Vercel Blob** untuk
  state, posisi, log JSONL (bawaan Vercel, free 1GB, diizinkan soal p.3)
- **GitHub Actions (free)**: cron `7 */4 * * *` memanggil endpoint; menit ke-7
  sesuai saran soal (jadwal menit-0 sering telat)
- **API publik Indodax**: candle, ticker, depth; tanpa API key

## Menjalankan
1. Push repo ke GitHub publik (bukti freeze dari riwayat commit)
2. Vercel: import repo -> Storage -> Create Database -> Blob (free); env
   `BLOB_READ_WRITE_TOKEN` otomatis. Tambah env `CRON_SECRET` (string acak)
   dan `VERCEL_URL` (opsional `KILL_SWITCH=1`)
3. GitHub secrets: `CRON_SECRET`, `VERCEL_URL`
4. GitHub Actions memanggil tiap 4 jam; uptime dicatat dari log panggilan

## Struktur
- `logic/core.py` = core strategy verbatim dari algo IDX (TIDAK diubah)
- `logic/config.py` = CryptoConfig beku (kalibrasi crypto terdokumentasi)
- `logic/pipeline.py` = adapter crypto (gate proxy BTC/IDR, tanpa lot/ARA)
- `bot/tick.py` = satu panggilan = satu candle: validasi data, sinyal, eksekusi
  simulasi ask/bid, risk check, log
- `api/tick.py` = endpoint Vercel (CRON_SECRET)
- `tools/backtest_4h.py` = backtest penuh (fungsi sinyal sama dengan bot)
- `tools/hitung_ulang.py` = reproduksi semua angka dashboard dari log mentah
- `tools/fetch_4h.py`, `tools/select_universe.py` = data + universe anti-survivorship

## Risk management (wajib soal)
- Batas posisi terbuka: 10; bobot maks 20% per pair
- Daily loss limit -5% equity harian (batas hari 00.00 WIB) -> stop entry
- Kill switch: env `KILL_SWITCH=1`, aktif tanpa redeploy, tercatat di log
- Idempotency: satu candle hanya diproses sekali
- Validasi data: candle basi >2x TF, harga/vol nol, order book kosong -> no entry + log
- Retry: terbatas (cron berikutnya); error dilog `log_errors`

## Backtest ulang jendela forward
Soal mensyaratkan backtest dijalan ulang pada jendela 10 hari forward dengan
candle sama (sinyal identik candle demi candle). Skrip: `tools/backtest_window.py`
(menggunakan `logic.build_crypto_weights` yang sama dengan bot).
