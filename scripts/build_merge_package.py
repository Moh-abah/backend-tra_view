#!/usr/bin/env python3
"""
build_merge_package.py — يحزم كل الملفات المعدلة والجديدة في ZIP بمسارات محفوظة
================================================================================
يقارن المشروع الحالي بالمشروع الأصلي (كما نُزل من Google Drive) ويولّد:
  1) MANIFEST_MERGE.md — بيان دقيق: معدل/جديد/محذوف + سبب التغيير لكل ملف
  2) trading-backend-merge-package.zip — للاستخراج فوق نظام المستخدم مباشرة
     (استبدال الملفات التالفة بالمعدلة + إضافة الجديدة كلها بنفس المسارات)

Usage: python scripts/build_merge_package.py [--original /tmp/uploaded_project/backend]
"""

import argparse
import hashlib
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]

# ما يُحزم (مسارات نسبية من جذر المشروع)
INCLUDE_DIRS = ["app", "strategies", "scripts", "reports", "tests", "examples"]
INCLUDE_FILES = ["requirements.txt", "README.md", ".env.example", ".env.production",
                 "Dockerfile", "docker-compose.yml", ".dockerignore", ".gitignore"]

EXCLUDE_DIR_PARTS = {"__pycache__", ".git", "venv", ".venv", "node_modules"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".log", ".db", ".sqlite3"}
EXCLUDE_PATTERNS = {"data/history/*.parquet"}  # 90MB — تُعاد بالجلب عبر السكربت

# ملفات جديدة بالكامل (لم تكن في الأصل) — تُكتشف آليًا أيضًا
KNOWN_NEW_DOCS = {"MANIFEST_MERGE.md"}


def should_skip(rel: str) -> bool:
    parts = set(rel.split(os.sep))
    if parts & EXCLUDE_DIR_PARTS:
        return True
    if any(rel.endswith(s) for s in EXCLUDE_SUFFIXES):
        return True
    for pat in EXCLUDE_PATTERNS:
        base = os.path.basename(rel)
        if pat.endswith("*.parquet") and base.endswith(".parquet") and rel.startswith("data/history"):
            return True
    return False


def sha16(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def collect(root: Path):
    files = {}
    for d in INCLUDE_DIRS:
        base = root / d
        if not base.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames if x not in EXCLUDE_DIR_PARTS]
            for fn in filenames:
                full = Path(dirpath) / fn
                rel = full.relative_to(root).as_posix()
                if should_skip(rel):
                    continue
                files[rel] = full
    for fn in INCLUDE_FILES:
        full = root / fn
        if full.exists():
            rel = fn
            if not should_skip(rel):
                files[rel] = full
    # data/history: فقط تقرير السلامة
    ig = root / "data" / "history" / "_integrity.json"
    if ig.exists():
        files["data/history/_integrity.json"] = ig
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--original", default="/tmp/uploaded_project/backend")
    args = ap.parse_args()

    orig_root = Path(args.original)
    cur = collect(PROJECT)
    orig = collect(orig_root) if orig_root.exists() else {}

    cur_hashes = {rel: sha16(p) for rel, p in cur.items()}
    orig_hashes = {rel: sha16(p) for rel, p in orig.items()}

    added = sorted(set(cur_hashes) - set(orig_hashes))
    removed = sorted(set(orig_hashes) - set(cur_hashes))
    modified = sorted(r for r in set(cur_hashes) & set(orig_hashes) if cur_hashes[r] != orig_hashes[r])
    unchanged = sorted(r for r in set(cur_hashes) & set(orig_hashes) if cur_hashes[r] == orig_hashes[r])

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # ---------------- MANIFEST ----------------
    L = []
    A = L.append
    A("# 📦 بيان حزمة الدمج (Merge Manifest)")
    A("")
    A(f"**تاريخ الحزم:** {now}  ")
    A(f"**مقارنة مع:** المشروع الأصلي المنزّل من Google Drive  ")
    A(f"**طريقة الدمج:** استخرج الـ ZIP فوق جذر مشروعك (نفس المسارات) — سيستبدل الملفات التالفة بالمعدلة ويضيف الجديدة.")
    A("")
    A("**قبل الدمج:** خذ نسخة احتياطية، وأوقف الخدمة (uvicorn/celery workers).")
    A("")
    A("**بعد الدمج:**")
    A("```bash")
    A("pip install -r requirements.txt        # بيئة نظيفة يُفضّل")
    A("python scripts/fetch_history.py        # (اختياري) جلب سنة بيانات BTC/ETH لكل الفريمات")
    A("uvicorn app.main:app --host 0.0.0.0 --port 8000")
    A("celery -A app.celery_app worker --loglevel=info   # للباك-تست غير المتزامن")
    A("```")
    A("")
    A("---")
    A("")
    A(f"## 🆕 ملفات جديدة ({len(added)})")
    A("")
    for r in added:
        size = cur[r].stat().st_size
        A(f"- `{r}` ({size/1024:.1f} KB)")
    A("")
    A(f"## ✏️ ملفات معدلة ({len(modified)})")
    A("")
    for r in modified:
        A(f"- `{r}`")
    A("")
    A(f"## ♻️ ملفات لم تتغير ({len(unchanged)}) — تُحزم أيضًا للاطمئنان")
    A("")
    for r in unchanged:
        A(f"- `{r}`")
    A("")
    A(f"## 🗑️ ملفات حذفناها من مشروعنا ({len(removed)}) — لن يزيلها الدمج، احذفها يدويًا إن وجدت (نسخ قديمة/مكررة)")
    A("")
    for r in removed:
        A(f"- `{r}`")
    A("")
    A("> ملاحظة: ملفات \"copy\" القديمة (engine_copy.py, core_copy.py, backtest1/, strategies1/, إلخ) ضمن المحذوفات — حذفها ضروري لتجنب تعارض الاستيرادات.")
    A("")
    A(f"## 📊 إحصائيات")
    A("")
    A(f"| البند | العدد |")
    A(f"|---|---:|")
    A(f"| ملفات في الحزمة | {len(cur)} |")
    A(f"| جديدة | {len(added)} |")
    A(f"| معدلة | {len(modified)} |")
    A(f"| غير متغيرة | {len(unchanged)} |")
    A(f"| محذوفة (احذفها يدويًا) | {len(removed)} |")
    A("")
    manifest_path = PROJECT / "MANIFEST_MERGE.md"
    manifest_path.write_text("\n".join(L), encoding="utf-8")
    print(f"WROTE {manifest_path}")

    # ---------------- ZIP ----------------
    zip_path = PROJECT / "trading-backend-merge-package.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel in sorted(cur):
            zf.write(cur[rel], arcname=rel)
        zf.write(manifest_path, arcname="MANIFEST_MERGE.md")
    size_mb = zip_path.stat().st_size / 1024 / 1024
    print(f"WROTE {zip_path} ({size_mb:.2f} MB, {len(cur)+1} files)")
    print(f"  added={len(added)} modified={len(modified)} unchanged={len(unchanged)} removed={len(removed)}")


if __name__ == "__main__":
    main()
