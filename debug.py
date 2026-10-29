import requests
import json

def debug_endpoints():
    base_url = "http://localhost:8000"
    
    print("🔍 اختبار حالة النظام...")
    try:
        response = requests.get(f"{base_url}/api/v1/status", timeout=5)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {json.dumps(response.json(), indent=2)}\n")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    print("🔍 اختبار الرموز مع معالجة الأخطاء...")
    try:
        response = requests.get(
            f"{base_url}/api/v1/symbols", 
            params={"market": "crypto"},
            timeout=5
        )
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print(f"   Response: {json.dumps(response.json(), indent=2)}")
        else:
            print(f"   Error Response: {response.text}")
    except requests.exceptions.ConnectionError:
        print("   ❌ لا يمكن الاتصال بالخادم. تأكد من تشغيل uvicorn.")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    print("\n🔍 اختبار endpoint الجذر...")
    try:
        response = requests.get(f"{base_url}/", timeout=5)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text[:100]}...\n")
    except Exception as e:
        print(f"   ❌ Error: {e}")

if __name__ == "__main__":
    debug_endpoints()