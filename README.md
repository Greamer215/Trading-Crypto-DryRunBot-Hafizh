# UAS Bot Dry Run Indodax

Bot trading dry run Indodax di Vercel. Strategi momentum cross-sectional,
timeframe 4 jam, modal virtual Rp100.000.000, long-only, tanpa API key.

- **Repo**: https://github.com/Greamer215/Trading-Crypto-DryRunBot-Hafizh
- **Bot live**: https://trading-crypto-dryrunbot-hafizh.vercel.app
- **Dashboard**: https://trading-crypto-dryrunbot-hafizh.vercel.app/dashboard/index.html
  (juga tersedia offline di `dashboard/index.html`)

## Bukti freeze (riwayat commit)

| Commit | Waktu WIB | Isi |
|---|---|---|
| `b0a6288` | 2026-11-04 12:15 | Freeze pertama: config crypto K5 (sl=60/ul=80/te=88), universe top-10, taker 0,20% |
| `11385d6` | 2026-11-04 | Kepatuhan fee soal: taker 0,31%/0,30% (halaman resmi, lebih mahal dari api/pairs) |
| `fe21513` | 2026-11-04 22:54 | Freeze 2: gate ETH/IDR + position cap 0,12 |
| `4aef4f1` | 2026-11-05 00:00 | **Freeze efektif**: skor tren = slope murni (perbaikan cacat struktural) |

**Catatan protokol yang dinyatakan terbuka:** jadwal freeze di soal adalah
2026-11-04 12.00 WIB. Commit pertama `b0a6288` dibuat 12.15 (telat 15 menit).
Gate ETH dan skor slope murni diadopsi SETELAH jadwal tersebut atas keputusan
eksplisit pemilik tugas, yang menerima konsekuensi pengurangan nilai.
Riwayat commit **tidak** ditulis ulang (tanpa force-push). Perubahan setelah
`4aef4f1` hanya perbaikan bug dan penambahan alat, **tidak** mengubah aturan,
parameter, maupun universe; semuanya tercatat di pesan commit.

## Backtest (data asli Indodax, 5,8 tahun)

Periode 2021-01-01 .. 2026-11-04, 12.800 bar 4 jam, 10 pair IDR.

| Metrik | Nilai |
|---|---|
| CAGR | 19,53% |
| Maximum drawdown | −42,58% |
| Calmar | 0,46 |
| Sharpe | 0,76 |
| Profit factor | 1,53 |
| Trade tertutup | 772, win rate 37,6% |
| Modal | Rp100.000.000 -> Rp283.472.836 |
| Benchmark buy-hold BTC | +238,48% |

Split-half: H1 2021-2023 CAGR 30,24% (Calmar 0,710), H2 2024-2026 CAGR 9,29%
(Calmar 0,251). Uji fase 10 offset re-rank: Calmar 0,400-0,483 (median 0,430).

### Sumber biaya (dua sumber, pakai yang lebih mahal)

| Sumber | Nilai | Akses |
|---|---|---|
| `/api/pairs` -> `trade_fee_percent_taker` | 0,20% | 2026-10-31 |
| Halaman resmi help.indodax.com (Details of Transaction Fees) | taker buy 0,31% / sell 0,30% (all-in) | 2026-11-04 |

Dipakai **0,31% beli / 0,30% jual** sesuai instruksi soal.
Minimum order: `/api/pairs` -> `trade_min_base_currency` Rp10.000; mode Pro
Rp25.000 -> dipakai **Rp25.000** (yang lebih ketat).

## Arsitektur (gratis, hanya Vercel + GitHub)

- **Vercel Hobby**: endpoint `/api/tick` (Python, timeout 300 s) + **Vercel Blob**
  (store private) untuk state, posisi, dan semua log
- **GitHub Actions**: cron `7 */4 * * *` (menit ke-7, sesuai saran soal) memanggil
  endpoint dengan `Authorization: Bearer $CRON_SECRET`
- **API publik Indodax**: candle `history_v2`, `ticker_all`, `depth`, `pairs`,
  `price_increments`, `server_time`. Tanpa API key.

## Menjalankan

1. Clone repo, `python -m venv .venv`, `pip install -r requirements.txt`
2. Vercel: import repo -> Storage -> Blob -> env `BLOB_READ_WRITE_TOKEN` otomatis;
   tambah `CRON_SECRET` (string acak) dan opsional `BLOB_STORE_ID`, `KILL_SWITCH`
3. GitHub: Settings -> Secrets -> Actions: `CRON_SECRET`, `VERCEL_URL`
4. Cron GitHub memanggil bot tiap 4 jam. Uptime dihitung dari `log_calls`

## Struktur

| File | Isi |
|---|---|
| `logic/core.py` | core strategy verbatim dari algo IDX (tidak diubah) |
| `logic/config.py` | `CryptoConfig` beku, semua parameter + alasan kalibrasi |
| `logic/pipeline.py` | adapter crypto: `crypto_trend_score` (slope murni) + urutan pipeline |
| `bot/tick.py` | satu panggilan = satu candle: validasi, sinyal, eksekusi, risk, log |
| `bot/util.py` | Indodax API + Vercel Blob (append-only log) + util WIB/tick size |
| `api/tick.py` | endpoint Vercel, dilindungi `CRON_SECRET` |
| `dashboard/index.html` | dashboard offline mandiri (tanpa CDN, tanpa network) |
| `tools/backtest_4h.py` | backtest penuh, fungsi sinyal sama dengan bot |
| `tools/backtest_window.py` | backtest jendela forward (sinyal identik candle demi candle) |
| `tools/hitung_ulang.py` | reproduksi semua angka dashboard dari log mentah |
| `tools/export_logs.py` | Blob -> `logs/*.jsonl` |
| `tools/collect_book.py` | pengumpul snapshot order book (spread & slippage terukur) |
| `tools/measure_spread.py` | median spread terukur -> `reports/spread_measured.json` |
| `tools/selfcheck_api.py` | uji API Indodax: tick size, VWAP, validasi, book |
| `tools/selfcheck_blob.py` | uji Vercel Blob: get/set/overwrite/append/list |
| `tools/fetch_4h.py`, `tools/select_universe.py` | data + universe anti-survivorship |
| `STRATEGI.md` | strategi tertulis, catatan perubahan dari UTS, diagnosis, kandidat yang ditolak |

## Risk management (wajib soal)

- Batas posisi terbuka 10; bobot maksimum 12% per pair
- **Daily loss limit** −5% equity harian, batas hari 00.00 WIB (17.00 UTC);
  stop membuka posisi baru sampai hari berikutnya, tercatat di `log_events`
- **Kill switch** env `KILL_SWITCH=1`, aktif tanpa redeploy, tercatat di log
- **Idempotency**: satu candle hanya diproses sekali (`state.processed`);
  panggilan kedua -> `skip_dup` (diverifikasi: 3 panggilan berurutan = 3x skip_dup)
- **Validasi data**: candle basi > 2x TF, harga/volume nol, candle hilang di
  jendela indikator, order book kosong, spread bid-ask > 2% -> no entry + alasan di log
- **Retry terbatas**: 3 percobaan dengan backoff untuk setiap GET API

## Eksekusi (sesuai soal p.2)

- Beli di **ask**, jual di **bid** dari `ticker_all`; fill tidak pernah di mid/close
- Order lebih besar dari level terbaik menghabiskan level berikutnya lewat
  `/api/depth` dan memakai **harga rata-rata** (`vwap_fill`)
- Harga dibulatkan ke `price_increments` (beli ke atas, jual ke bawah);
  kuantitas dibulatkan ke `quantity_increment`
- Equity menilai posisi pada **best bid**; equity harian diambil pada panggilan
  pertama setelah 00.00 WIB
- Setiap order dicatat: waktu, pair, sisi, qty, best bid/ask, harga fill rata-rata,
  jumlah level terpakai, slippage vs best, spread saat fill, fee, harga sinyal

## Dashboard & hitung ulang

```bash
python tools/export_logs.py          # Blob -> logs/*.jsonl + state.json
python tools/hitung_ulang.py logs    # log mentah -> reports/hitung_ulang.json
python tools/build_dashboard.py      # log mentah -> dashboard/index.html
```

Dashboard dan `hitung_ulang.py` membaca log yang sama dan menghasilkan angka yang
sama (diverifikasi: jumlah panggilan, order, uptime, return forward identik).
Dashboard tidak memuat URL eksternal apa pun; bisa dibuka tanpa internet.
