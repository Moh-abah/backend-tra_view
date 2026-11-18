#!/usr/bin/env bash
# run_all_sequential.sh — كل اختبارات r95 + بطارية r13 + مصفوفة الفريمات، تسلسلياً بحتاً
set -u
cd /home/z/drive-download/backend_PRO95_extracted
HARNESS="tests-r95/champion_ab_harness.py"
NEWROOT="/home/z/drive-download/backend_PRO95_extracted"

echo "########## 1) unit tests ##########"
python3 tests-r95/test_zone_exit_unit.py 2>&1 | tail -6
echo "########## 2) param flow ##########"
python3 tests-r95/test_param_flow.py 2>&1 | tail -3
echo "########## 3) timing causality ##########"
python3 tests-r95/verify_timing_causality.py 2>&1 | tail -3

run() {
  local res="$1"; local len="${2:-}"
  echo "########## RUN zx=$res len=${len:-default} ##########"
  if [ -n "$len" ]; then
    python3 "$HARNESS" "$NEWROOT" "$res" "$len" 2>&1 | grep -E '"total_trades"|"win_rate_pct"|"total_pnl_percent"|"final_capital"|"profit_factor"|"sharpe"|"max_drawdown_pct"|"avg_trade_duration_hours"|"trades_hash"|"zone_exit_resolution"|"zone_exit_length"|"execution_seconds"|Exit Signal' | head -16
  else
    python3 "$HARNESS" "$NEWROOT" "$res" 2>&1 | grep -E '"total_trades"|"win_rate_pct"|"total_pnl_percent"|"final_capital"|"profit_factor"|"sharpe"|"max_drawdown_pct"|"avg_trade_duration_hours"|"trades_hash"|"zone_exit_resolution"|"zone_exit_length"|"execution_seconds"|Exit Signal' | head -16
  fi
  sync; sleep 3
}

run "60"
run "240"
run "1D"
run "60" "50"
run "240" "50"
run "1D" "50"

echo "########## 4) r73 regression battery ##########"
python3 tests-r73/test_r73_battery.py 2>&1 | tail -25
echo "ALL_SEQUENTIAL_DONE"
