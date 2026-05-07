import os
import urllib.parse
import asyncio
import time
from typing import Any, Dict, Optional

from utils.http_client import get_http_client


LOSTARK_API_BASE = "https://developer-lostark.game.onstove.com"
_CACHE_TTL_SEC = float(os.getenv("LOSTARK_CHAR_CACHE_TTL_SEC", "15"))
_CACHE_MAX_SIZE = int(os.getenv("LOSTARK_CHAR_CACHE_MAX", "1024"))
_char_cache: dict[str, tuple[float, Optional[Dict[str, Any]]]] = {}
_inflight: dict[str, asyncio.Task[Optional[Dict[str, Any]]]] = {}
_cache_lock = asyncio.Lock()


def _parse_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return default


async def _fetch_lostark_character(char_name: str) -> Optional[Dict[str, Any]]:
    try:
        api_key = os.getenv("LOSTARK_API_KEY", "").strip()

        if not api_key:
            print("[LostArk API] LOSTARK_API_KEY is empty")
            return None

        # 혹시 Railway 변수에 실수로 bearer까지 넣었을 경우 방어
        if api_key.lower().startswith("bearer "):
            api_key = api_key.split(" ", 1)[1].strip()

        encoded_name = urllib.parse.quote(char_name, safe="")
        url = f"{LOSTARK_API_BASE}/armories/characters/{encoded_name}/profiles"

        client = await get_http_client()
        response = await client.get(
            url,
            headers={
                "accept": "application/json",
                "authorization": f"bearer {api_key}",
            },
            timeout=15.0,
        )

        if response.status_code != 200:
            print(
                f"[LostArk API] character profile failed | "
                f"name={char_name} | status={response.status_code} | body={response.text[:300]}"
            )
            return None

        data = response.json()

        return {
            "char_name": data.get("CharacterName", char_name),
            "class_name": data.get("CharacterClassName", ""),
            "server_name": data.get("ServerName", ""),
            "guild_name": data.get("GuildName", ""),
            "char_image": data.get("CharacterImage", ""),
            "item_lvl": _parse_float(data.get("ItemAvgLevel")),
            "combat_power": _parse_float(data.get("CombatPower")),
        }
    except Exception as e:
        print(f"[LostArk API] character profile exception | name={char_name} | error={e}")
        return None


def _prune_cache(now_mono: float) -> None:
    expired = [k for k, (exp, _) in _char_cache.items() if exp <= now_mono]
    for k in expired:
        _char_cache.pop(k, None)

    if len(_char_cache) <= _CACHE_MAX_SIZE:
        return

    overflow = len(_char_cache) - _CACHE_MAX_SIZE
    for k, _ in sorted(_char_cache.items(), key=lambda kv: kv[1][0])[:overflow]:
        _char_cache.pop(k, None)


async def search_lostark_character(char_name: str) -> Optional[Dict[str, Any]]:
    key = (char_name or "").strip().lower()
    if not key:
        return None

    now_mono = time.monotonic()
    async with _cache_lock:
        _prune_cache(now_mono)
        cached = _char_cache.get(key)
        if cached and cached[0] > now_mono:
            data = cached[1]
            return dict(data) if isinstance(data, dict) else data

        inflight = _inflight.get(key)
        if inflight is None:
            inflight = asyncio.create_task(_fetch_lostark_character(char_name))
            _inflight[key] = inflight

    try:
        result = await inflight
    finally:
        async with _cache_lock:
            if _inflight.get(key) is inflight:
                _inflight.pop(key, None)

    async with _cache_lock:
        _char_cache[key] = (time.monotonic() + _CACHE_TTL_SEC, result)
        _prune_cache(time.monotonic())

    return dict(result) if isinstance(result, dict) else result
