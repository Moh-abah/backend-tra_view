# app/services/chart_storage.py
import os
import json
import tempfile
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional

STORAGE_DIR = Path("./chart_storage")
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

def _file_path(symbol: str, timeframe: str) -> Path:
    safe_symbol = symbol.replace("/", "_").upper()
    safe_tf = timeframe.replace("/", "_")
    return STORAGE_DIR / f"{safe_symbol}__{safe_tf}.json"

def _read_sync(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"indicators": []}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        # normalize shape
        if not isinstance(data, dict):
            return {"indicators": []}
        indicators = data.get("indicators") or []
        # ensure list of dicts
        normalized = []
        for ind in indicators:
            if isinstance(ind, list) and len(ind) > 0:
                ind = ind[0]
            if isinstance(ind, dict):
                normalized.append(ind)
        return {"indicators": normalized}
    except Exception:
        return {"indicators": []}

def _write_sync(path: Path, payload: Dict[str, Any]) -> None:
    # atomic write
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmpf:
            json.dump(payload, tmpf, ensure_ascii=False, indent=2)
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        raise

async def load_indicators(symbol: str, timeframe: str) -> List[Dict[str, Any]]:
    path = _file_path(symbol, timeframe)
    data = await asyncio.to_thread(_read_sync, path)
    return data.get("indicators", [])

async def save_indicator(symbol: str, timeframe: str, name: str, config: Dict[str, Any]) -> bool:
    """
    يحفظ/يحدّث مؤشر في الملف الخاص بالشارت+الفريم.
    - يطابق بالاسم ويستبدل إن وجد.
    - يعالج القوائم ويخزن دائماً dict
    """
    path = _file_path(symbol, timeframe)

    # Normalize incoming config: if it's a list, take first dict
    if isinstance(config, list):
        if len(config) == 0:
            return False
        config = config[0]
    if not isinstance(config, dict):
        return False

    # ensure name field
    if "name" not in config:
        config["name"] = name

    # read-modify-write atomically in thread
    def _sync():
        data = _read_sync(path)
        indicators = data.get("indicators", [])
        # remove existing same name
        indicators = [ind for ind in indicators if ind.get("name") != name]
        indicators.append(config)
        payload = {"indicators": indicators}
        _write_sync(path, payload)
        return True

    return await asyncio.to_thread(_sync)

async def remove_indicator(symbol: str, timeframe: str, name: str) -> bool:
    path = _file_path(symbol, timeframe)
    def _sync():
        data = _read_sync(path)
        indicators = data.get("indicators", [])
        new_inds = [ind for ind in indicators if ind.get("name") != name]
        if len(new_inds) == len(indicators):
            return False
        _write_sync(path, {"indicators": new_inds})
        return True
    return await asyncio.to_thread(_sync)

async def clear_indicators(symbol: str, timeframe: str) -> None:
    path = _file_path(symbol, timeframe)
    def _sync():
        if path.exists():
            _write_sync(path, {"indicators": []})
    await asyncio.to_thread(_sync)
