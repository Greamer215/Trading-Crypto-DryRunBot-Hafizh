"""Config UAS bot crypto Indodax 4h.

CORE LOGIC BEKU dari algo IDX (logic/core.py disalin verbatim): trend_reg_score,
equal_weights, time_exit_overlay, soft_market_gate, scale_in_overlay, hold_every.
YANG DIKALIBRASI hanya lapisan parameter + adapter (keputusan user 2026-10-31):

  - lookback TIDAK diubah: signal_lookback 120, universe_lookback 40,
    time_exit_hold 44, min_gain 0.09  (tetap dalam satuan bar)
  - universe: top likuiditas diukur di AWAL backtest (anti-survivorship, soal UAS p.2)
    via trailing median turnover Rp, sama definisinya dgn IDX tapi pair crypto
  - market gate: proxy = BTC/IDR (pengganti IHSG; crypto 24/7 tidak punya indeks)
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

    # --- market gate: proxy BTC/IDR (adapter; IDX pakai IHSG) --------------
    gate_proxy: str = "BTCIDR"                      # kolom pair gate di panels
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

    # --- biaya Indodax (terukur 2026-10-31; cek ulang sebelum freeze) ------
    # trade_fee_percent_taker=0.20 (api/pairs); halaman resmi bila beda -> pakai
    # yang lebih mahal (soal UAS p.2). Slippage 10 bps placeholder s/d snapshot.
    taker_fee: float = 0.002
    slippage: float = 0.001
    min_order_idr: float = 25_000.0                 # mode Pro (lebih ketat)

    # --- akun ---------------------------------------------------------------
    capital: float = 100_000_000.0                  # Rp100jt virtual (soal UAS)

    @property
    def total_buy(self) -> float:
        return self.taker_fee + self.slippage

    @property
    def total_sell(self) -> float:
        return self.taker_fee + self.slippage


def research_config(**overrides: object) -> CryptoConfig:
    return replace(CryptoConfig(), **overrides)
