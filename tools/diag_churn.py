"""SeBab churn: dari mana trade crypto berasal (ranking vs time-stop) dan
berapa turnover tahunan dibanding IDX.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from logic import CryptoConfig, build_crypto_weights
from logic.core import cap_position_weights
from tools.backtest_4h import load_4h

sel = json.loads((HERE / "data" / "universe_selected.json").read_text())["selected"]
panels = load_4h(sel)
panels["universe_fixed"] = sel
cfg = CryptoConfig()
w = cap_position_weights(build_crypto_weights(panels, cfg), cfg.position_weight_cap)
wd = w.shift(1).fillna(0.0)

# klasifikasi entry/exit per pair
print(f"{'pair':8s} {'entry':>5s} {'exit':>5s} {'avg_hold':>8s} {'no%tional':>10s}")
tot_e = tot_x = 0
holds = []
for sym in wd.columns:
    h = (wd[sym] > 1e-9).to_numpy()
    edges = np.diff(np.concatenate([[0], h.astype(int), [0]]))
    entries = int((edges == 1).sum())
    exits = int((edges == -1).sum())
    lens = np.diff(np.flatnonzero(edges))[::2]
    holds.extend(lens.tolist())
    tot_e += entries
    tot_x += exits
    print(f"{sym:8s} {entries:5d} {exits:5d} {lens.mean():8.1f}")

holds = np.array(holds)
print(f"\ntotal entry {tot_e}, exit {tot_x}, avg hold {holds.mean():.1f} bar "
      f"= {holds.mean()/6:.1f} hari (time_exit = {cfg.time_exit_hold} bar)")

# berapa lama posisi hidup: distribusi
print("hold pct: p25 %.0f p50 %.0f p75 %.0f p90 %.0f max %d bar" % (
    np.percentile(holds, 25), np.percentile(holds, 50),
    np.percentile(holds, 75), np.percentile(holds, 90), holds.max()))

# turnover tahunan (satu sisi) crypto
yrs = (w.index[-1] - w.index[0]).days / 365.25
turn_all = wd.diff().abs().sum(axis=1).sum()
print(f"\ncrypto turnover {turn_all/yrs:.1f} x modal / tahun "
      f"(= total nilai ditransaksikan per tahun, dua sisi)")
print(f"crypto gross exposure rata2 {float(w.sum(axis=1).mean()):.2f}")
print(f"biaya round-trip crypto {cfg.total_buy + cfg.total_sell:.4f} = "
      f"{(cfg.total_buy + cfg.total_sell)*100:.2f}%")

# berapa entry per tahun vs slot yang tersedia
print(f"\nentry/tahun = {tot_e/yrs:.1f}; slot 5 pair -> tiap slot berputar "
      f"{tot_e/5/yrs:.2f}x per tahun (= tiap {365/(tot_e/5/yrs):.0f} hari)")

# --- pembanding IDX
IDXD = Path(r"C:\Users\Greamer\Downloads\trading-desk-hafizh")
sys.path.insert(0, str(IDXD))
for m in [m for m in list(sys.modules) if m.split(".")[0] in ("logic", "backtest", "data", "core")]:
    del sys.modules[m]
sys.path.remove(str(HERE))

from logic import ProductionConfig, build_target_weights
from backtest.engine import IDX_COST_T1
from data.loader_idx import build_panels_idx

icfg = ProductionConfig()
ip = build_panels_idx(membership_path=IDXD / "data" / "kompas100" / "pit" / "membership_pit_loader.csv")
iw = build_target_weights(ip, icfg).loc["2007-08-01":]
iwd = iw.shift(1).fillna(0.0)
iyrs = (iw.index[-1] - iw.index[0]).days / 365.25
iturn = iwd.diff().abs().sum(axis=1).sum()
ie = int(((iwd > 1e-9).astype(int).diff().fillna(0) == 1).sum().sum())
print(f"\nIDX turnover {iturn/iyrs:.1f} x modal/tahun, entry {ie/iyrs:.1f}/tahun, "
      f"exposure {float(iw.sum(axis=1).mean()):.2f}")
print(f"IDX biaya round-trip ~{IDX_COST_T1.buy + IDX_COST_T1.sell:.4f}")
print(f"\nRASIO crypto/IDX: turnover {turn_all/yrs/(iturn/iyrs):.1f}x, "
      f"biaya/roundtrip {(cfg.total_buy+cfg.total_sell)/(IDX_COST_T1.buy+IDX_COST_T1.sell):.1f}x")
print(f"-> drag biaya crypto relatif {(turn_all/yrs*(cfg.total_buy+cfg.total_sell)):.2f} "
      f"vs IDX {(iturn/iyrs*(IDX_COST_T1.buy+IDX_COST_T1.sell)):.2f} per tahun")