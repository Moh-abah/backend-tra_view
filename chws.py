# test_client.py
import asyncio
import json
import time
import websockets
from datetime import datetime

WS_URL = "ws://localhost:8000/ws/chart/BTCUSDT"
OUTPUT_FILE = "chart_ws_test_results.json"

results = {
    "meta": {
        "ws_url": WS_URL,
        "started_at": datetime.utcnow().isoformat(),
    },
    "init": {},
    "events": [],
    "stats": {
        "messages_received": 0,
        "avg_latency": None
    }
}

latencies = []


async def log_event(event_type, payload, latency=None):
    results["events"].append({
        "type": event_type,
        "timestamp": datetime.utcnow().isoformat(),
        "latency": latency,
        "payload": payload
    })


async def run():
    async with websockets.connect(WS_URL) as ws:
        # ===== INIT =====
        init_payload = {"timeframe": "1m", "market": "crypto"}
        await ws.send(json.dumps(init_payload))

        start = time.perf_counter()
        init_msg = await ws.recv()
        latency = time.perf_counter() - start

        results["init"] = {
            "request": init_payload,
            "response": json.loads(init_msg),
            "latency": latency
        }
        latencies.append(latency)

        # ===== ADD INDICATOR =====
        add_msg = {
            "action": "add_indicator",
            "indicator_config": {"name": "rsi", "params": {"period": 14}}
        }

        await ws.send(json.dumps(add_msg))
        resp = json.loads(await ws.recv())
        await log_event("indicator_added", resp)

        # ===== LISTEN STREAM (10s) =====
        end_time = time.time() + 10
        while time.time() < end_time:
            start = time.perf_counter()
            msg = json.loads(await ws.recv())
            latency = time.perf_counter() - start

            latencies.append(latency)
            await log_event(msg.get("type", "unknown"), msg, latency)

            results["stats"]["messages_received"] += 1

        # ===== PING =====
        await ws.send(json.dumps({"action": "ping"}))
        start = time.perf_counter()
        pong = json.loads(await ws.recv())
        latency = time.perf_counter() - start

        latencies.append(latency)
        await log_event("pong", pong, latency)

    # ===== FINAL STATS =====
    if latencies:
        results["stats"]["avg_latency"] = sum(latencies) / len(latencies)

    results["meta"]["ended_at"] = datetime.utcnow().isoformat()

    # ===== WRITE FILE =====
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"✔ Test completed — results saved to {OUTPUT_FILE}")


asyncio.run(run())
