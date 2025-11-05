from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from ..core.memory import MemoryClient


class MetaIndex:
    def __init__(self, memory: Optional[MemoryClient] = None) -> None:
        self._loaded = False
        self._meta: Dict[str, any] = {}
        self._typeinfo_cache: Dict[str, int] = {}
        self._stringlit_cache: Dict[str, int] = {}
        self._memory = memory

    def load(self, base_dir: Optional[str] = None) -> bool:
        if self._loaded:
            return True
        try:
            base = base_dir or os.path.dirname(__file__)
            pkg_root = os.path.dirname(base)
            # Preferred: package-local Il2cpp_result
            candidate1 = os.path.join(pkg_root, "Il2cpp_result", "metadata.json")
            # Fallback: repo-root Il2cpp_result (one dir above package root)
            repo_root = os.path.dirname(pkg_root)
            candidate2 = os.path.join(repo_root, "Il2cpp_result", "metadata.json")
            meta_path = candidate1 if os.path.isfile(candidate1) else candidate2
            with open(meta_path, "r", encoding="utf-8") as f:
                self._meta = json.load(f)
            self._loaded = True
            return True
        except Exception:
            self._meta = {}
            self._loaded = False
            return False

    def get_typeinfo_rva_by_name(self, name_substr: str) -> int:
        self.load()
        key = (name_substr or "").lower()
        if key in self._typeinfo_cache:
            return self._typeinfo_cache[key]
        try:
            tips = (self._meta.get("typeInfoPointers") if self._meta else [])
            for item in tips:
                dn = (item.get("dotNetType") or "").lower()
                if dn == key or dn.endswith("." + key) or dn.endswith("/" + key):
                    rva = int(item.get("virtualAddress"), 16)
                    self._typeinfo_cache[key] = rva
                    return rva
            for item in tips:
                nm = (item.get("name") or "").lower()
                if key in nm:
                    rva = int(item.get("virtualAddress"), 16)
                    self._typeinfo_cache[key] = rva
                    return rva
        except Exception:
            pass
        return 0

    def get_typeinfo_rva_by_substrings(self, subs: List[str]) -> int:
        self.load()
        key = "|".join(sorted([str(s or "").lower() for s in subs]))
        if key in self._typeinfo_cache:
            return self._typeinfo_cache[key]
        try:
            tips = (self._meta.get("typeInfoPointers") if self._meta else [])
            for item in tips:
                dn = (item.get("dotNetType") or "").lower()
                nm = (item.get("name") or "").lower()
                ty = (item.get("type") or "").lower()
                blob = f"{dn} {nm} {ty}"
                ok = True
                for s in subs:
                    s = str(s or "").lower()
                    if s not in blob:
                        ok = False
                        break
                if ok:
                    rva = int(item.get("virtualAddress"), 16)
                    self._typeinfo_cache[key] = rva
                    return rva
        except Exception:
            pass
        return 0

    def get_string_va(self, needle: str) -> int:
        self.load()
        k = (needle or "").lower()
        if k in self._stringlit_cache:
            return self._stringlit_cache[k]
        try:
            lits = (self._meta.get("stringLiterals") if self._meta else [])
            for it in lits:
                s = (it.get("string") or "").lower()
                if s == k:
                    rva = int(it.get("virtualAddress"), 16)
                    va = (self._memory.base + rva) if self._memory else rva
                    self._stringlit_cache[k] = va
                    return va
        except Exception:
            pass
        return 0
