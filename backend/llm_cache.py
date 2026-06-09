import hashlib
import threading
import time
from typing import Optional

_cache: dict[str, tuple[str, float]] = {}
_lock = threading.RLock()
TTL = int(__import__("os").getenv("LLM_CACHE_TTL", "3600"))


def _key(model: str, system_instruction: str, prompt: str) -> str:
    raw = f"{model}|{system_instruction}|{prompt}"
    return hashlib.sha256(raw.encode()).hexdigest()


def get(model: str, system_instruction: str, prompt: str) -> Optional[str]:
    k = _key(model, system_instruction, prompt)
    with _lock:
        if k in _cache:
            value, ts = _cache[k]
            if time.time() - ts < TTL:
                return value
            del _cache[k]
    return None


def set(model: str, system_instruction: str, prompt: str, response: str) -> None:
    k = _key(model, system_instruction, prompt)
    with _lock:
        _cache[k] = (response, time.time())
