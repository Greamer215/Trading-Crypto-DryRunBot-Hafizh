"""Bangun ZIP pengumpulan UAS: source + logs + reports + dashboard + .git UTUH.

Syarat soal: bukti freeze wajib bisa dicek dari riwayat commit. Karena itu
folder .git disertakan utuh (atau repo publik). ZIP ini memuat keduanya.

Yang SENGAJA tidak dimasukkan: .env, .env.local, .env*.local, file cache.
.env.example tetap disertakan (template tanpa rahasia).

Pakai: python tools/build_submission.py
Output: ~/Downloads/UAS_Algoritma_Trading_<NIM>_<Nama>.zip
"""
import os
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
OUT_DEFAULT = Path.home() / "Downloads" / "UAS_Algoritma_Trading_25110200032_Hafizh_Muhammad_Zhafran.zip"

# pola yang HARAM ikut (rahasia / sampah)
BLOCK_FILES = {".env", ".env.local", ".env.production", ".env.development"}
BLOCK_SUFFIX = (".pyc", ".pyo")
BLOCK_DIRS = {"__pycache__", ".vercel", ".pytest_cache", ".mypy_cache", "node_modules"}
# .git ikut UTUH (bukti freeze), kecuali lock/index yang bisa besar/tidak perlu
GIT_SKIP = {"index"}


def should_skip(rel: Path) -> bool:
    parts = set(rel.parts)
    if parts & BLOCK_DIRS:
        return True
    if rel.name in BLOCK_FILES:
        return True
    if rel.name.startswith(".env") and not rel.name.endswith(".example"):
        return True
    if rel.suffix in BLOCK_SUFFIX:
        return True
    return False


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT_DEFAULT
    # pastikan status commit bersih supaya bukti freeze konsisten
    st = subprocess.run(["git", "status", "--porcelain"], cwd=str(HERE),
                        capture_output=True, text=True).stdout.strip()
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(HERE),
                          capture_output=True, text=True).stdout.strip()

    files, total = 0, 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(HERE.rglob("*")):
            if p.is_dir():
                continue
            rel = p.relative_to(HERE)
            if should_skip(rel):
                continue
            if rel.parts and rel.parts[0] == ".git" and rel.name in GIT_SKIP:
                continue
            z.write(p, rel.as_posix())
            files += 1
            total += p.stat().st_size

    size = out.stat().st_size
    print(f"ZIP   : {out}")
    print(f"file  : {files} ({total/1e6:.1f} MB sebelum kompres, {size/1e6:.1f} MB ZIP)")
    print(f"commit: {head} | working tree {'BERSIH' if not st else 'KOTOR: ' + st[:120]}")

    # verifikasi: .git ikut, dan tidak ada rahasia
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        has_git = any(n.startswith(".git/") for n in names)
        has_env_example = any(n.endswith(".env.example") for n in names)
        leaked = [n for n in names
                  if Path(n).name in BLOCK_FILES
                  or (Path(n).name.startswith(".env") and not n.endswith(".example"))]
        n_commits = sum(1 for n in names if n.startswith(".git/"))
    print(f"cek   : .git {'ADA' if has_git else 'TIDAK ADA'} ({n_commits} entri), "
          f".env.example {'ada' if has_env_example else 'TIDAK ADA'}, "
          f"rahasia bocor: {leaked if leaked else 'tidak ada'}")
    if not has_git or leaked or not has_env_example:
        print("PERINGATAN: periksa hasil di atas sebelum submit")
        return 1
    print("OK: siap dikumpulkan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
