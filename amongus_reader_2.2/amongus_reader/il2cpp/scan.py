from __future__ import annotations

import time
from typing import List, Optional, Tuple

from ..core.memory import MemoryClient
from .meta import MetaIndex


class Il2CppScanner:
    def __init__(self, memory: MemoryClient, meta: MetaIndex, debug: bool = False) -> None:
        self.memory = memory
        self.meta = meta
        self.debug = bool(debug)

    def _is_asm_ptr(self, ptr: int) -> bool:
        try:
            if not ptr:
                return False
            b = self.memory.base
            return b <= ptr < (b + 0x08000000)
        except Exception:
            return False

    def get_class_from_typeinfo(self, rva: int) -> int:
        try:
            return self.memory.read_ptr(self.memory.base + int(rva)) if rva else 0
        except Exception:
            return 0

    def get_class_from_dotnet(self, name_substr: str) -> int:
        rva = self.meta.get_typeinfo_rva_by_name(name_substr)
        return self.get_class_from_typeinfo(rva) if rva else 0

    def get_static_fields_ptr(self, klass: int) -> int:
        if not klass:
            return 0
        candidates = [0xB8, 0xB0, 0xD8, 0xD0, 0x5C]
        for off in candidates:
            try:
                p = self.memory.read_ptr(klass + off)
                if p:
                    return p
            except Exception:
                continue
        return 0

    def scan_fields_for_class(self, fields_base: int, span_bytes: int, target_klass: int) -> int:
        step = 8 if self.memory.is_64 else 4
        end = fields_base + span_bytes
        for cur in range(fields_base, end, step):
            try:
                ptr = self.memory.read_ptr(cur)
                if ptr:
                    k = self.memory.read_ptr(ptr)
                    if k == target_klass:
                        return ptr
            except Exception:
                continue
        return 0

    def scan_fields_for_ptr_value(self, fields_base: int, span_bytes: int, target_ptr: int) -> int:
        step = 8 if self.memory.is_64 else 4
        end = fields_base + span_bytes
        for cur in range(fields_base, end, step):
            try:
                ptr = self.memory.read_ptr(cur)
                if ptr == target_ptr:
                    return cur
            except Exception:
                continue
        return 0

    def scan_heap_for_class_instances(
        self,
        target_klass: int,
        regions: Optional[List[Tuple[int, int]]] = None,
        limit: int = 16,
        time_budget_end: Optional[float] = None,
    ) -> List[int]:
        if not target_klass:
            return []
        found: List[int] = []
        step = 8 if self.memory.is_64 else 4
        try:
            if regions is None:
                b = self.memory.base
                regions = [
                    (b + 0x01000000, 0x01000000),
                    (b + 0x02000000, 0x01000000),
                    (b + 0x03000000, 0x01000000),
                    (b + 0x04000000, 0x01000000),
                ]
            for start, size in regions:
                if time_budget_end and time.time() > time_budget_end:
                    break
                end = start + size
                cur = start
                while cur < end and len(found) < limit:
                    if time_budget_end and time.time() > time_budget_end:
                        break
                    try:
                        obj = self.memory.read_ptr(cur)
                        if obj == target_klass:
                            found.append(cur)
                        cur += step
                    except Exception:
                        cur += step
                        continue
                if len(found) >= limit:
                    break
        except Exception:
            return found
        return found

    def object_fields_contains_ptr(self, obj_ptr: int, target_ptr: int, span: int = 0x200) -> bool:
        try:
            fields_off = 0x10 if self.memory.is_64 else 0x8
            base = obj_ptr + fields_off
            step = 8 if self.memory.is_64 else 4
            end = base + max(0x40, span)
            for cur in range(base, end, step):
                try:
                    p = self.memory.read_ptr(cur)
                    if p == target_ptr:
                        return True
                except Exception:
                    continue
        except Exception:
            return False
        return False

    def scan_object_field_ptrs(self, obj_ptr: int, span: int = 0x800) -> List[int]:
        out: List[int] = []
        try:
            fields_off = 0x10 if self.memory.is_64 else 0x8
            base = obj_ptr + fields_off
            step = 8 if self.memory.is_64 else 4
            end = base + max(0x100, span)
            for cur in range(base, end, step):
                try:
                    p = self.memory.read_ptr(cur)
                    if p:
                        out.append(p)
                        if len(out) >= 512:
                            break
                except Exception:
                    continue
        except Exception:
            return out
        return out

    def class_has_methods(self, klass: int, methods: List[int]) -> bool:
        if not klass or not methods:
            return False
        step = 8 if self.memory.is_64 else 4
        scan_span = 0x10000
        try:
            hits = 0
            for addr in range(klass, klass + scan_span, step):
                try:
                    p = self.memory.read_ptr(addr)
                    if p in methods:
                        hits += 1
                        if hits >= min(2, len(methods)):
                            return True
                except Exception:
                    continue
        except Exception:
            return False
        return False

    def find_object_by_method_signature(self, methods: List[int], time_budget_end: Optional[float]) -> int:
        if not methods:
            return 0
        b = self.memory.base
        try:
            hi = max(methods)
        except Exception:
            hi = b + 0x05000000
        asm_max = max(b + 0x05000000, hi + 0x00100000)
        regions = list(self.memory.iter_heap_regions(max_regions=4096))
        step = 8 if self.memory.is_64 else 4
        scan_span = 0x10000
        for start, size in regions:
            if time_budget_end and time.time() > time_budget_end:
                break
            end = start + size
            cur = start
            while cur < end:
                if time_budget_end and time.time() > time_budget_end:
                    break
                try:
                    obj = cur
                    klass = self.memory.read_ptr(obj)
                    if klass and (b <= klass < asm_max):
                        hits = 0
                        for addr in range(klass, klass + scan_span, step):
                            try:
                                p = self.memory.read_ptr(addr)
                                if p in methods:
                                    hits += 1
                                    if hits >= min(2, len(methods)):
                                        return obj
                            except Exception:
                                continue
                    cur += step
                except Exception:
                    cur += step
                    continue
        return 0

    def find_button_by_string_xref(self, str_va: int, btn_klasses: List[int], time_budget_end: Optional[float]) -> int:
        if not str_va:
            return 0
        b = self.memory.base
        regions = [
            (b + 0x01000000, 0x01000000),
            (b + 0x02000000, 0x01000000),
            (b + 0x03000000, 0x01000000),
            (b + 0x04000000, 0x01000000),
        ]
        step = 8 if self.memory.is_64 else 4
        fields_off = 0x10 if self.memory.is_64 else 0x8
        for start, size in regions:
            if time_budget_end and time.time() > time_budget_end:
                break
            end = start + size
            cur = start
            while cur < end:
                if time_budget_end and time.time() > time_budget_end:
                    break
                try:
                    val = self.memory.read_ptr(cur)
                    if val == str_va:
                        for foff in (0x20, 0x28, 0x30, 0x38, 0x40, 0x48, 0x50, 0x60, 0x70, 0x80):
                            obj_base = cur - foff - fields_off
                            if obj_base <= 0:
                                continue
                            try:
                                k = self.memory.read_ptr(obj_base)
                                if k and (k in btn_klasses):
                                    return obj_base
                            except Exception:
                                continue
                    cur += step
                except Exception:
                    cur += step
                    continue
        return 0
