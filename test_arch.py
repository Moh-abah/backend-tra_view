import requests
import json
import time

# إعدادات السيرفر
BASE_URL = "http://localhost:8000/api/v1"

# تحميل ملف التكوين
with open('test_strategy_config.json', 'r') as f:
    STRATEGY_CONFIG = json.load(f)

print("=" * 50)
print("🚀 بدء اختبار معمارية التداول الجديدة")
print("=" * 50)

# ==========================================
# 1. اختبار طبقة القرار (Decision Layer)
# ==========================================
print("\n[1️⃣] اختبار /strategies/run (Black Box Decision)...")

query_params = {
    "symbol": "ETHUSDT",
    "timeframe": "1m",
    "market": "crypto",
    "days": 50
}


decision_payload = STRATEGY_CONFIG 

try:
    response = requests.post(
        f"{BASE_URL}/strategies1/run",
        params=query_params,  # << query parameters
        json=decision_payload      # << request body
    )
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ النجاح: تم الحصول على {data['total_bars_processed']} شمعة بيانات.")
        print(f"   ✅ النجاح: تم العثور على {data['active_decisions_count']} قرار نشط (BUY/SELL).")
        
        if data['active_decisions_count'] > 0:
            print(f"   📌 مثال قرار: {data['active_decisions'][0]}")
        else:
            print("   ⚠️ ملاحظة: لم تصدر الاستراتيجية قرارات شراء/بيع في هذه الفترة (طبيعي جداً).")
    else:
        print(f"   ❌ فشل: {response.status_code} - {response.text}")
except Exception as e:
    print(f"   ❌ خطأ في الاتصال: {e}")

# ==========================================
# 2. اختبار طبقة التنفيذ (Execution Layer - Backtest)
# ==========================================
print("\n[2️⃣] اختبار /backtest/run (Execution Engine)...")

# تجهيز تكوين الباك-تيست
backtest_config = {
    "name": "Test New Arch Backtest",
    "start_date": "2025-05-01T00:00:00",
    "end_date": "2025-12-31T00:00:00",
    "initial_capital": 10000.0,
    "commission_rate": 0.001,
    "slippage_percent": 0.001,
    "position_size_percent": 0.1,
    "stop_loss_percent": 5.0,
    "take_profit_percent": 10.0,
    "symbols": ["BTCUSDT"],
    "timeframe": "1h",
    "market": "crypto",
    "strategy_config": STRATEGY_CONFIG # تمرير نفس الاستراتيجية الجديدة
}

try:
    start_time = time.time()
    response = requests.post(f"{BASE_URL}/backtest1/run", json=backtest_config)
    duration = time.time() - start_time
    
    if response.status_code == 200:
        result = response.json()
        summary = result['summary']
        
        print(f"   ✅ النجاح: تم الانتهاء من الباك-تيست في {duration:.2f} ثانية.")
        print(f"   💰 رأس المال النهائي: ${summary['final_capital']:.2f}")
        print(f"   📈 إجمالي الربح/الخسارة: {summary['total_pnl_percent']:.2f}%")
        print(f"   📊 عدد الصفقات: {summary['total_trades']}")
        print(f"   🎯 نسبة الفوز: {summary['win_rate']:.2f}%")
        print(f"   ⚖️ Sharpe Ratio: {summary['sharpe_ratio']:.2f}")
        print(f"   🏗️  الوضع المعماري: {summary['architecture_mode']}")
        
        if summary['total_trades'] > 0:
            print("\n   🎉 الاكتشاف الكبير: ")
            print("   محرك الاستراتيجية (الذي لا يعرف شيئاً عن الصفقات) أصدر قرارات،")
            print("   ومحرك الباك-تيست ترجمها إلى صفقات وحقق نتائج حقيقية!")
    else:
        print(f"   ❌ فشل: {response.status_code} - {response.text}")

except Exception as e:
    print(f"   ❌ خطأ في الاتصال: {e}")

print("\n" + "=" * 50)
print("✅ انتهى الاختبار")
print("=" * 50)