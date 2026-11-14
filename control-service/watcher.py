#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""مراقب إعادة التشغيل التلقائي لخدمة التحكم PRO73 (يشغّل server.py ويعيد
تشغيله عند أي تعديل على ملفات *.py في مجلد الخدمة أو نواة الباك اند)."""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "server.py")
WATCH_BACKEND = "/home/z/my-project/pro73-workspace/src/app/services/indicators"


def _snapshot():
    stamps = {}
    for root in (HERE, WATCH_BACKEND):
        if not os.path.isdir(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            if "__pycache__" in dirpath:
                continue
            for fn in filenames:
                if fn.endswith(".py"):
                    p = os.path.join(dirpath, fn)
                    try:
                        stamps[p] = os.path.getmtime(p)
                    except OSError:
                        pass
    return stamps


def main():
    snap = _snapshot()
    proc = subprocess.Popen([sys.executable, TARGET])
    print(f"[watcher] started pid={proc.pid} — watching {len(snap)} py files", flush=True)
    try:
        while True:
            time.sleep(2.0)
            if proc.poll() is not None:
                print(f"[watcher] server exited rc={proc.returncode} — restarting in 1s", flush=True)
                time.sleep(1.0)
                proc = subprocess.Popen([sys.executable, TARGET])
                snap = _snapshot()
                print(f"[watcher] restarted pid={proc.pid}", flush=True)
                continue
            new = _snapshot()
            changed = [p for p, m in new.items() if snap.get(p) != m]
            if changed:
                for p in changed[:5]:
                    print(f"[watcher] change: {p}", flush=True)
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                proc = subprocess.Popen([sys.executable, TARGET])
                snap = new
                print(f"[watcher] restarted pid={proc.pid}", flush=True)
    except KeyboardInterrupt:
        proc.terminate()
        print("[watcher] bye", flush=True)


if __name__ == "__main__":
    main()
