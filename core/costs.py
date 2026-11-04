"""Transaction-cost models.

IDX (retail, Ajaib-published all-in 2025 schedule, after PPN 12%):
  buy  = 0.1513% of notional  (broker + levy + PPN)
  sell = 0.2513% of notional  (broker + levy + PPN + 0.10% PPh final)
  round-trip ~= 0.4026% of notional  -> use 0.004 as conservative default

Crypto (spot, typical tier-1 exchange retail taker):
  0.10% per side -> round-trip 0.20%. Pass explicit fees for your venue.

Slippage: model as half-spread estimate in bps, tiered by liquidity.
These are ASSUMPTIONS to be calibrated, not measurements — sensitivity-test them.
"""

IDX_BUY_RATE = 0.001513
IDX_SELL_RATE = 0.002513
IDX_ROUNDTRIP_RATE = IDX_BUY_RATE + IDX_SELL_RATE  # 0.004026

CRYPTO_TAKER_RATE = 0.001  # per side; adjust per venue

# Tiered slippage assumptions (one-way, fraction of notional)
SLIPPAGE = {
    "tier1": 0.0005,   # 5 bps  — mega-cap / BTC-USD
    "tier2": 0.0015,   # 15 bps — mid-cap / alts
    "tier3": 0.0050,   # 50 bps — illiquid, research only
    "index": 0.0,      # never traded
    "macro": 0.0,
    "fx": 0.0,
    "commodity": 0.0,
    "research": 0.0,
}


def idx_buy_cost(notional: float) -> float:
    return notional * IDX_BUY_RATE


def idx_sell_cost(notional: float) -> float:
    return notional * IDX_SELL_RATE


def idx_roundtrip_cost(buy_notional: float, sell_notional: float) -> float:
    return buy_notional * IDX_BUY_RATE + sell_notional * IDX_SELL_RATE


def roundtrip_drag_pct(asset_class: str = "idx_equity", tier: str = "tier1") -> float:
    """Total friction per round-trip as fraction: costs + 2x one-way slippage."""
    if asset_class == "idx_equity":
        base = IDX_ROUNDTRIP_RATE
    elif asset_class == "crypto":
        base = 2 * CRYPTO_TAKER_RATE
    else:
        base = 0.0
    return base + 2 * SLIPPAGE.get(tier, 0.0)


if __name__ == "__main__":
    # Self-check: numbers must match the memo's published schedule.
    assert abs(IDX_BUY_RATE - 0.001513) < 1e-9
    assert abs(IDX_SELL_RATE - 0.002513) < 1e-9
    assert abs(IDX_ROUNDTRIP_RATE - 0.004026) < 1e-9
    print(f"IDX round-trip drag tier1: {roundtrip_drag_pct('idx_equity','tier1'):.4%}")
    print(f"IDX round-trip drag tier2: {roundtrip_drag_pct('idx_equity','tier2'):.4%}")
    print(f"crypto round-trip drag tier1: {roundtrip_drag_pct('crypto','tier1'):.4%}")
    print("self-check OK")
