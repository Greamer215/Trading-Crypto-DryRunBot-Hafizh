"""Rutinitas refresh forward test: satu perintah, urutan yang benar.

Urutan penting: data candle dulu (fetch), baru log (export), baru angka
(hitung_ulang), baru pembanding sinyal, baru refleksi & dashboard. Kalau
compare_forward dijalankan sebelum fetch, candle terbaru akan dilaporkan
"data belum tersedia".

Pakai:
    python tools/refresh_semua.py            # semua langkah
    python tools/refresh_semua.py --no-fetch # lewati pengunduhan candle
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
PY = sys.executable


def run(label, args, timeout=900):
    t0 = time.time()
    print(f"\n=== {label} ===", flush=True)
    p = subprocess.run([PY] + args, cwd=str(HERE), capture_output=True, text=True,
                       timeout=timeout)
    out = (p.stdout or "").strip()
    if out:
        # tampilkan hanya baris penting supaya tidak banjir
        lines = out.splitlines()
        for ln in lines[-12:]:
            print("  " + ln)
    if p.returncode != 0:
        err = (p.stderr or "").strip().splitlines()
        print("  GAGAL:", " | ".join(err[-3:]) if err else f"exit {p.returncode}")
        return False
    print(f"  ok ({time.time()-t0:.1f}s)")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true", help="lewati fetch_4h (data sudah ada)")
    a = ap.parse_args()

    steps = []
    if not a.no_fetch:
        steps.append(("1/6 unduh candle 4h terbaru", ["tools/fetch_4h.py"], 1800))
    steps += [
        (f"{len(steps)+1}/6 ekspor log dari Vercel Blob", ["tools/export_logs.py"], 900),
        (f"{len(steps)+2}/6 hitung ulang angka dari log mentah", ["tools/hitung_ulang.py", "logs"], 600),
        (f"{len(steps)+3}/6 bandingkan sinyal bot vs backtest", ["tools/compare_forward.py"], 900),
        (f"{len(steps)+4}/6 tulis refleksi", ["tools/build_refleksi.py"], 300),
        (f"{len(steps)+5}/6 bangun dashboard offline", ["tools/build_dashboard.py"], 300),
    ]

    ok = True
    for label, args, to in steps:
        if not run(label, args, to):
            ok = False
            print("\nberhenti: langkah gagal. Perbaiki dulu sebelum lanjut.")
            break

    print("\n" + "=" * 60)
    if ok:
        print("SELESAI. Yang perlu di-commit: REFLEKSI.md, dashboard/index.html, logs/")
        print("  git add -A && git commit -m 'refresh forward test' && git push")
    else:
        print("ADA LANGKAH GAGAL, lihat output di atas.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())