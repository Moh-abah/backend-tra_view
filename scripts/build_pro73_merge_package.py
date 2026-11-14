#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""بناء حزمة الدمج PRO73-MERGE-PACKAGE — الفرق الكامل بين pro73-workspace/src
و backend_PRO73.zip (المصدر الحرفي MD5 ad31b9a417aa7f7f26803fff752f50a8):
ملفات جديدة كاملة + فروقات المعدلة + خدمة التحكم + الأدلة + سكربت تحقق
الدمج + البيان + MD5 + تعليمات التثبيت."""
import difflib
import hashlib
import json
import os
import shutil
import zipfile

WS = "/home/z/my-project/pro73-workspace/src"
WS_ROOT = "/home/z/my-project/pro73-workspace"
ZIP = "/home/z/my-project/pro73-workspace/backend_PRO73.zip"
OUT = "/home/z/my-project/public/pro73-merge-package"
OUT_ZIP = "/home/z/my-project/public/pro73-merge-package.zip"
CONTROL = "/home/z/my-project/pro73-workspace/control-service"

# تقارير جذر مساحة العمل تُضمّ صراحةً (خارج شجرة src التي يمسحها السكربت)
ROOT_REPORTS = (
    "DELIVERY-REPORT-PRO73-FINAL-AR.md",
    "ADOPTION-REPORT-AR.md",
    "ENCYCLOPEDIA-SECTION14-PRO73-AR.md",
    "FRONTEND-AGENT-REPORT-PRO73-AR.md",
)

EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", "node_modules"}
EXCLUDE_FILES = {
    "service.log", "state.json", "dev.log", "dev.out.log", "server.log", "MD5SUMS.txt",
    # سقالات فارغة قديمة لا علاقة لها بـ PRO73 (0 بايت — موجودة في مساحة العمل فقط):
    "eth_historical_candles.json", "signals_stream.txt",
}
EXCLUDE_PREFIX = ("r73-evidence",)  # تُنسخ من مكانها الصحيح


def md5_file(p: str) -> str:
    h = hashlib.md5()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    # 1) خط الأساس من الـzip
    baseline: dict = {}
    with zipfile.ZipFile(ZIP) as z:
        for info in z.infolist():
            if info.is_dir():
                continue  # المجلدات فقط — ملفات 0 بايت تُحتسب من الأساس (كانت تُتجاهل فتُصنّف «جديدة» زورًا)
            baseline[info.filename] = z.read(info.filename)
    print(f"baseline files: {len(baseline)}")

    # 2) مسح مساحة العمل
    ws_files: dict = {}
    for root, dirs, files in os.walk(WS):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), WS)
            if fn in EXCLUDE_FILES:
                continue
            if any(rel.startswith(p) for p in EXCLUDE_PREFIX):
                continue
            if fn.endswith((".npz", ".zip", ".png", ".db")):
                continue
            ws_files[rel] = os.path.join(root, fn)

    new_files, modified = [], []
    for rel in sorted(ws_files):
        if rel not in baseline:
            new_files.append(rel)
        else:
            with open(ws_files[rel], "rb") as fh:
                if fh.read() != baseline[rel]:
                    modified.append(rel)
    removed = [rel for rel in baseline if rel not in ws_files and not rel.startswith(("evidence/", "verify_scripts/", "tests/"))]
    print(f"new: {len(new_files)} | modified: {len(modified)} | removed(non-historical): {len(removed)}")

    # 3) نسخ الملفات الجديدة/المعدلة كاملة
    for rel in new_files + modified:
        dst = os.path.join(OUT, "files", rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(ws_files[rel], dst)

    # 3b) تقارير جذر مساحة العمل (تسليم كامل) — تُحتسب ضمن الجديد
    for fn in ROOT_REPORTS:
        src = os.path.join(WS_ROOT, fn)
        if os.path.isfile(src):
            dst = os.path.join(OUT, "files", fn)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            if fn not in new_files:
                new_files.append(fn)

    # 4) فروقات المعدلة (diff موحد)
    for rel in modified:
        base_text = baseline[rel].decode("utf-8", errors="replace").splitlines(keepends=True)
        with open(ws_files[rel], encoding="utf-8", errors="replace") as fh:
            cur_text = fh.readlines()
        diff = list(difflib.unified_diff(base_text, cur_text, fromfile=f"a/{rel}", tofile=f"b/{rel}"))
        dst = os.path.join(OUT, "diffs", f"{rel}.diff")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "w", encoding="utf-8") as fh:
            fh.writelines(diff)

    # 5) خدمة التحكم (مكوّن إضافي اختياري — يُنشر بجانب الباك اند لا داخله)
    for fn in ("server.py", "watcher.py", "package.json"):
        src = os.path.join(CONTROL, fn)
        if os.path.isfile(src):
            dst = os.path.join(OUT, "control-service", fn)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)

    # 6) الأدلة (بطاريات + البطل)
    ev_src = os.path.join(WS, "tests-r73", "r73-evidence")
    if os.path.isdir(ev_src):
        for fn in os.listdir(ev_src):
            if fn.endswith(".json"):
                dst = os.path.join(OUT, "evidence", fn)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(os.path.join(ev_src, fn), dst)

    # 6b) وثائق الحزمة الثابتة (README + سكربت التحقق) من extras
    extras = os.path.join(WS, "scripts", "pro73_package_extras")
    for fn in ("README-INSTALL-AR.md",):
        src = os.path.join(extras, fn)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(OUT, fn))
    vsrc = os.path.join(extras, "verify_pro73_merge.py")
    if os.path.isfile(vsrc):
        os.makedirs(os.path.join(OUT, "verify"), exist_ok=True)
        shutil.copy2(vsrc, os.path.join(OUT, "verify", "verify_pro73_merge.py"))

    # 7) البيان (MANIFEST-MD5)
    manifest: dict = {
        "spec": "PRO73-MERGE-PACKAGE",
        "version": "1.0.0",
        "baseline_zip": "backend_PRO73.zip",
        "baseline_md5": "ad31b9a417aa7f7f26803fff752f50a8",
        "new_files": new_files,
        "modified_files": modified,
        "counts": {"new": len(new_files), "modified": len(modified)},
    }
    with open(os.path.join(OUT, "MANIFEST.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    lines = []
    for root, _dirs, files in os.walk(OUT):
        for fn in sorted(files):
            p = os.path.join(root, fn)
            lines.append(f"{md5_file(p)}  {os.path.relpath(p, OUT)}")
    with open(os.path.join(OUT, "MANIFEST-MD5.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    # 8) الضغط
    if os.path.isfile(OUT_ZIP):
        os.remove(OUT_ZIP)
    with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(OUT):
            for fn in sorted(files):
                p = os.path.join(root, fn)
                z.write(p, os.path.relpath(p, OUT))
    print(f"package → {OUT} ({len(new_files)} جديد + {len(modified)} معدل)")
    print(f"zip → {OUT_ZIP} ({os.path.getsize(OUT_ZIP) / 1024:.1f} KB)")
    print("new:", *new_files, sep="\n  + ")
    print("modified:", *modified, sep="\n  ~ ")


if __name__ == "__main__":
    main()
