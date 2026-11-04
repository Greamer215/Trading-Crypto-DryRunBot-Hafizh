"""Config UAS bot crypto Indodax 4h.

CORE LOGIC BEKU dari algo IDX (logic/core.py disalin verbatim): trend_reg_score,
equal_weights, time_exit_overlay, soft_market_gate, scale_in_overlay, hold_every.
YANG DIKALIBRASI hanya lapisan parameter + adapter (keputusan user 2026-10-31):

  - lookback TIDAK diubah: signal_lookback 120, universe_lookback 40,
    time_exit_hold 44, min_gain 0.09  (tetap dalam satuan bar)
  - universe: top likuiditas diukur di AWAL backtest (anti-survivorship, soal UAS p.2)
    via trailing median turnover Rp, sama definisinya dgn IDX tapi pair crypto
  - market gate: proxy = ETH/IDR (pengganti IHSG; crypto 24/7 tidak punya indeks)
  - biaya: taker Indodax 0.20%/sisi (api/pairs 2026-10-31, trade_fee_percent_taker)
    vs halaman resmi (cek ulang sebelum freeze, pakai yang lebih mahal) + slip
  - kalender 24/7, bar 4 jam, tanpa lot, min order Rp25.000
"""
from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class CryptoConfig:
    # --- universe: likuiditas diukur dari data awal, bukan hari ini ---------
    universe_mode: str = "top_liquidity_at_start"   # fixed top-N, PIT-safe
    universe_top_n: int = 10                        # 3..10 pair (soal UAS)
    # KALIBRASI CRYPTO 2026-11-03 (opsi B): 40 -> 80 bar. Menang split-half
    # kedua paruh bersama sl=60/te=88 (lihat catatan signal_lookback).
    universe_lookback: int = 80                     # bar 4h = 13,3 hari
    min_turnover_idr: float = 5e7                   # Rp50jt median per bar 4h
    min_vol_ann: float = 0.05

    # --- signal: regularised trend factor (core beku dari IDX) -------------
    # KALIBRASI CRYPTO 2026-11-03 (PILIHAN USER, opsi B): 120 -> 60.
    # Grid 36 kombinasi (reports/grid_lookback.csv): 60/80/88 satu-satunya
    # kandidat yang menang split-half KEDUA paruh (H1 21-23 +19.6% / H2 24-26
    # +12.8%, Calmar 0.283/0.243) vs base 120/40/44 (+15.2%/+10.2%, 0.248/0.214).
    # Kandidat 90 ditolak: menang full-sample tapi H2 runtuh (90/40 +0.3%,
    # 90/80/22 -3.0%) = artefak rezim bull 2021-23, bukan edge.
    signal_lookback: int = 60                      # bar 4h = 10 hari
    n_top: int = 5
    every: int = 10                                 # re-rank tiap 10 bar = 40 jam

    # --- weighting: equal-weight (BEKU, v2) --------------------------------
    weighting: str = "eq"
    vol_window: int = 63

    # --- scale-in overlay (BEKU dari IDX) ----------------------------------
    z_window: int = 63
    entry_z: float = 1.5
    max_scale: float = 1.25
    max_entry_gap: float = 0.10

    # --- market gate: proxy ETH/IDR (adapter; IDX pakai IHSG) --------------
    # ADOPSI 2026-11-04 (keputusan user, opsi gate ETH): ETH lebih cepat
    # merespons rotasi alt daripada BTC. Backtest fee resmi: CAGR 20.49% /
    # Cal 0.29 / PF 1.48 vs BTC-gate 9.71%/0.13/1.38; menang split-half
    # KEDUA paruh (H1 34.60%/0.50, H2 7.66%/0.13 vs BTC 12.76%/0.18,
    # 6.83%/0.12). CATATAN PROTOKOL: freeze commit b0a6288 (12.15 WIB)
    # memuat gate BTC; gate ETH diadopsi SETELAH jadwal freeze 12.00 lewat
    # atas keputusan eksplisit user, konsekuensi pengurangan nilai telat
    # freeze diterima. Freeze efektif = commit adopsi ini.
    gate_proxy: str = "ETHIDR"                      # kolom pair gate di panels
    gate_k: float = 4000.0
    gate_b: float = 0.5
    gate_window: int = 120
    gate_floor: float = 0.0

    # --- time stop (core beku dari IDX; angka dikalibrasi) -----------------
    # KALIBRASI CRYPTO 2026-11-03 (opsi B): 44 -> 88 bar = 14,7 hari. Grid
    # opt2 (reports/grid_opt2.csv): te 132 konsisten +0.3-0.7pp vs 88, tapi
    # dipilih 88 (kurang agresif, satu langkah dari nilai IDX 44).
    time_exit_hold: int | None = 88
    time_exit_min_gain: float = 0.09

    # --- biaya Indodax (KEPATUHAN SOAL p.2: pakai yang lebih mahal) --------
    # api/pairs trade_fee_percent_taker = 0.20% (akses 2026-10-31)
    # HALAMAN RESMI lebih mahal -> dipakai (akses 2026-11-04):
    #   https://help.indodax.com/hc/en-us/articles/28673592088857-Details-of-
    #   Transaction-Fees-on-Indodax  : taker buy 0.31% / sell 0.30% (all-in)
    # Kepatuhan soal, bukan perubahan strategi; dicatat di commit terpisah.
    buy_fee: float = 0.0031
    sell_fee: float = 0.0030
    slippage: float = 0.001    # placeholder spread s/d snapshot terkumpul
    min_order_idr: float = 25_000.0                 # mode Pro (lebih ketat)

    # --- normalisasi risiko per nama (adapter crypto, BUKAN core) ----------
    # KALIBRASI CRYPTO 2026-11-04 (keputusan user): 0.20 -> 0.12.
    # Equal-weight 20% dirancang untuk vol saham 20-40%/thn. Pair crypto
    # 52-118%/thn, jadi 20% per nama = risiko 2-3x. Grid (reports/grid_dd.csv,
    # cand_equal.csv): cap adalah SATU-SATUNYA lever DD yang naik monoton di
    # KEDUA paruh, H2 Calmar 0.134 -> 0.157 -> 0.173 -> 0.185 (cap .20/.15/.12/.10)
    # dengan CAGR H2 hanya turun 7.66% -> 6.38%. Ditolak: vol targeting (PF
    # 1.48->1.07, memotong pemenang karena vol tinggi = fase tren naik) dan DD
    # governor (menang H1 saja; H2 Calmar 0.053, eksposur terkunci di lantai).
    position_weight_cap: float = 0.12

    # --- akun ---------------------------------------------------------------
    capital: float = 100_000_000.0                  # Rp100jt virtual (soal UAS)

    @property
    def total_buy(self) -> float:
        return self.buy_fee + self.slippage

    @property
    def total_sell(self) -> float:
        return self.sell_fee + self.slippage


def research_config(**overrides: object) -> CryptoConfig:
    return replace(CryptoConfig(), **overrides)
