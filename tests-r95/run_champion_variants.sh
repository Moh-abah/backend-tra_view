#!/usr/bin/env bash
# run_champion_variants.sh — تشغيل مصفوفة فريمات هيكل الخروج تسلسلياً (أمان الذاكرة)
set -u
cd /home/z/drive-download/backend_PRO95_extracted
HARNESS="tests-r95/champion_ab_harness.py"
NEWROOT="/home/z/drive-download/backend_PRO95_extracted"

run() {
  local res="$1"; local len="${2:-}"
  echo "=================================================="
  echo ">>> RUN zone_exit_resolution=$res zone_exit_length=${len:-default(226)}"
  echo "=================================================="
  if [ -n "$len" ]; then
    python3 "$HARNESS" "$NEWROOT" "$res" "$len" 2>&1 | tail -40
  else
    python3 "$HARNESS" "$NEWROOT" "$res" 2>&1 | tail -40
  fi
  echo ">>> DONE res=$res len=${len:-default} (exit=$?)"
}

run "60"
run "240"
run "1D"
run "60" "50"
run "240" "50"
run "1D" "50"
echo "ALL_VARIANTS_DONE"
