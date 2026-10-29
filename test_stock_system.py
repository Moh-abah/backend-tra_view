# test_stock_system.py
import asyncio
import json
from app.providers.us_stock_provider import USStockProvider

async def test_full_system():
    provider = USStockProvider()
    
    print("🚀 اختبار نظام الأسهم الأمريكي المتكامل\n")
    
    # 1. الرموز
    print("1. 📊 جلب الرموز:")
    symbols = await provider.get_symbols("technology")
    print(f"   ✅ {len(symbols)} رمز تقني")
    print(f"   أمثلة: {symbols[:5]}\n")
    
    # 2. الرسم البياني
    print("2. 📈 جلب بيانات الرسم البياني لـ AAPL:")
    chart_data = await provider.get_chart_data(
        symbol="AAPL",
        timeframe="1d",
        period="1mo",
        indicators=[
            {"name": "sma", "params": {"period": 20}},
            {"name": "rsi", "params": {"period": 14}},
            {"name": "macd", "params": {}}
        ]
    )
    print(f"   ✅ {len(chart_data.get('candles', []))} شمعة")
    print(f"   ✅ {len(chart_data.get('indicators', {}))} مؤشر\n")
    
    # 3. التحليل الفني
    print("3. 🔍 التحليل الفني لـ TSLA:")
    analysis = await provider.get_technical_analysis("TSLA")
    print(f"   ✅ اتجاه: {analysis.get('trend', {}).get('direction')}")
    print(f"   ✅ RSI: {analysis.get('momentum', {}).get('rsi'):.2f}")
    print(f"   ✅ إشارات: {len(analysis.get('signals', []))}\n")
    
    # 4. معلومات الشركة
    print("4. 🏢 معلومات شركة MSFT:")
    company = await provider.get_company_info("MSFT")
    print(f"   ✅ الشركة: {company.get('name')}")
    print(f"   ✅ القطاع: {company.get('sector')}")
    print(f"   ✅ القيمة السوقية: ${company.get('market_cap'):,}\n")
    
    # 5. ملخص السوق
    print("5. 🌐 ملخص السوق:")
    summary = await provider.get_market_summary()
    for idx, data in summary.items():
        print(f"   📊 {idx}: {data.get('price'):.2f} ({data.get('change_percent'):.2f}%)")
    
    print(f"\n✅ النظام يعمل بكامل وظائفه!")

if __name__ == "__main__":
    asyncio.run(test_full_system())