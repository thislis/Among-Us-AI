from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple, Iterable


class CacheManager:
    def __init__(self, ttl_map: Optional[Dict[str, float]] = None) -> None:
        self._ttl: Dict[str, float] = dict(ttl_map or {})
        self._store: Dict[Tuple[str, Optional[Any]], Tuple[float, Any]] = {}

    def set_ttl(self, type_name: str, ttl_seconds: float) -> None:
        t = max(0.0, float(ttl_seconds))
        self._ttl[self._norm_type(type_name)] = t

    def get_ttl(self, type_name: str) -> float:
        return float(self._ttl.get(self._norm_type(type_name), 0.0))

    def get(self, type_name: str, subkey: Optional[Any] = None) -> Any:
        key = (self._norm_type(type_name), subkey)
        entry = self._store.get(key)
        if not entry:
            return None
        expires_at, value = entry
        ttl = self.get_ttl(type_name)
        if ttl > 0.0 and time.time() >= expires_at:
            try:
                del self._store[key]
            except KeyError:
                pass
            return None
        return value

    def set(self, type_name: str, value: Any, subkey: Optional[Any] = None) -> Any:
        t = self.get_ttl(type_name)
        expires_at = (time.time() + t) if t > 0.0 else 0.0
        key = (self._norm_type(type_name), subkey)
        self._store[key] = (expires_at, value)
        return value

    def invalidate(self, types: Optional[Iterable[str]] = None, subkey: Optional[Any] = None) -> None:
        if not types:
            self._store.clear()
            return
        types_norm = {self._norm_type(t) for t in types}
        to_delete = [k for k in self._store.keys() if (k[0] in types_norm and (subkey is None or k[1] == subkey))]
        for k in to_delete:
            try:
                del self._store[k]
            except KeyError:
                pass

    def snapshot(self, types: Optional[Iterable[str]] = None) -> Dict[str, Dict[Optional[Any], Any]]:
        now = time.time()
        res: Dict[str, Dict[Optional[Any], Any]] = {}
        types_norm = {self._norm_type(t) for t in types} if types else None
        for (typ, sub), (expires, val) in list(self._store.items()):
            if types_norm is not None and typ not in types_norm:
                continue
            ttl = self._ttl.get(typ, 0.0)
            if ttl > 0.0 and now >= expires:
                try:
                    del self._store[(typ, sub)]
                except KeyError:
                    pass
                continue
            res.setdefault(typ, {})[sub] = val
        return res

    def _norm_type(self, type_name: str) -> str:
        return str(type_name or "").strip().lower()
