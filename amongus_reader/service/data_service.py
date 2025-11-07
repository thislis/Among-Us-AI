from __future__ import annotations

import ctypes
from ctypes import wintypes
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union

from ..core.memory import MemoryClient
from ..core.offsets import Offsets
from ..il2cpp.meta import MetaIndex
from ..il2cpp.scan import Il2CppScanner
from .task_lookup import system_type_to_name


class ColorId(Enum):
    RED = 0
    BLUE = 1
    GREEN = 2
    PINK = 3
    ORANGE = 4
    YELLOW = 5
    BLACK = 6
    WHITE = 7
    PURPLE = 8
    BROWN = 9
    CYAN = 10
    LIME = 11
    MAROON = 12
    ROSE = 13
    BANANA = 14
    GRAY = 15
    TAN = 16
    SUNSET = 17
    CORAL = 18

    @classmethod
    def get_name(cls, color_id: int) -> str:
        color_map = {
            0: "Red", 1: "Blue", 2: "Green", 3: "Pink",
            4: "Orange", 5: "Yellow", 6: "Black", 7: "White",
            8: "Purple", 9: "Brown", 10: "Cyan", 11: "Lime",
            12: "Maroon", 13: "Rose", 14: "Banana", 15: "Gray",
            16: "Tan", 17: "Sunset", 18: "Coral",
        }
        return color_map.get(int(color_id), f"Unknown({color_id})")


@dataclass
class PlayerData:
    player_id: int
    color_id: int
    color_name: str
    position: Tuple[float, float]
    is_local_player: bool = False
    last_update: float = 0.0


@dataclass
class TaskData:
    task_id: int
    task_type_id: int
    is_completed: bool
    step: Optional[int] = None
    max_step: Optional[int] = None
    start_system: Optional[int] = None
    location: Optional[str] = None
    destination: Optional[str] = None
    step: Optional[int] = None
    max_step: Optional[int] = None


class AmongUsDataService:
    def __init__(self, process_name: str = "Among Us.exe", scan_interval: float = 0.1, debug: bool = False) -> None:
        self._class_cache: Dict[int, int] = {}
        self._typeinfo_cache: Dict[str, int] = {}
        self._stringlit_cache: Dict[str, int] = {}
        self._meta_loaded = False
        self._last_scan_time = 0.0
        self._scan_interval = max(0.01, float(scan_interval))
        self._cached_players: List[PlayerData] = []
        self._cached_local_player: Optional[int] = None
        self._debug = bool(debug)
        self._process_name = process_name
        self.memory: Optional[MemoryClient] = None
        self._meta_index: Optional[MetaIndex] = None
        self._scanner: Optional[Il2CppScanner] = None
        # HUD/report scan control
        self._hud_ptr_cache: int = 0
        self._report_ptr_cache: int = 0
        self._report_bool_off_cache: Optional[int] = None
        self._report_scan_last: float = 0.0
        self._report_scan_min_interval: float = 1.5
        self._report_scan_time_budget: float = 0.10
        # CachedPlayerData helpers
        self._cached_playerdata_ptr_off: Dict[bool, Optional[int]] = {}
        self._cached_playerdata_class: Optional[int] = None
        self.attach(process_name)

    # Session / debug
    def enable_debug(self, enabled: bool = True) -> None:
        self._debug = bool(enabled)

    def _debug_log(self, msg: str) -> None:
        if self._debug:
            print(f"[디버그] {msg}")

    def is_attached(self) -> bool:
        return self.memory is not None

    def attach(self, process_name: Optional[str] = None) -> bool:
        if process_name:
            self._process_name = process_name
        try:
            self.memory = MemoryClient(self._process_name)
            self._class_cache.clear()
            try:
                self._meta_index = MetaIndex(self.memory)
                self._meta_index.load()
            except Exception:
                self._meta_index = None
            try:
                self._scanner = Il2CppScanner(self.memory, self._meta_index or MetaIndex(self.memory), debug=self._debug)
            except Exception:
                self._scanner = None
            return True
        except Exception as e:
            self.memory = None
            self._debug_log(f"프로세스 연결 실패: {e}")
            return False

    def detach(self) -> None:
        try:
            if self.memory:
                self.memory.close()
        finally:
            self.memory = None
            self._meta_index = None
            self._scanner = None
            self._cached_playerdata_class = None
            self._cached_playerdata_ptr_off.clear()

    def set_scan_interval(self, seconds: float) -> None:
        try:
            self._scan_interval = max(0.01, float(seconds))
        except Exception:
            pass

    def set_report_scan_budget(self, seconds: float) -> None:
        try:
            s = float(seconds)
            self._report_scan_time_budget = max(0.05, min(s, 10.0))
            self._debug_log(f"Report 스캔 타임버짓: {self._report_scan_time_budget:.2f}s")
        except Exception:
            pass

    # Meta helpers
    def _ensure_metadata_loaded(self) -> None:
        if self._meta_loaded:
            return
        try:
            if self._meta_index is None:
                self._meta_index = MetaIndex(self.memory)
            ok = self._meta_index.load()
            self._meta_loaded = bool(ok)
            self._debug_log("metadata.json 로드 완료" if ok else "metadata.json 로드 실패")
        except Exception as e:
            self._meta_loaded = False
            self._debug_log(f"metadata.json 로드 실패: {e}")

    def _get_typeinfo_rva_by_name(self, name_substr: str) -> int:
        self._ensure_metadata_loaded()
        key = (name_substr or "").lower()
        if key in self._typeinfo_cache:
            return self._typeinfo_cache[key]
        try:
            if self._meta_index:
                rva = self._meta_index.get_typeinfo_rva_by_name(name_substr)
                if rva:
                    self._typeinfo_cache[key] = rva
                    self._debug_log(f"typeinfo 매칭: {name_substr} -> rva=0x{rva:x}")
                return rva
        except Exception:
            pass
        return 0

    def _find_typeinfo_rva_by_substrings(self, subs: List[str]) -> int:
        self._ensure_metadata_loaded()
        key = "|".join(sorted([str(s or "").lower() for s in subs]))
        if key in self._typeinfo_cache:
            return self._typeinfo_cache[key]
        try:
            if self._meta_index:
                rva = self._meta_index.get_typeinfo_rva_by_substrings(subs)
                if rva:
                    self._typeinfo_cache[key] = rva
                    self._debug_log(f"typeinfo 매칭(복합): {subs} -> rva=0x{rva:x}")
                return rva
        except Exception:
            pass
        return 0

    def _get_string_va(self, needle: str) -> int:
        self._ensure_metadata_loaded()
        k = (needle or "").lower()
        if k in self._stringlit_cache:
            return self._stringlit_cache[k]
        try:
            if self._meta_index:
                va = self._meta_index.get_string_va(needle)
                if va:
                    self._stringlit_cache[k] = va
                return va
        except Exception:
            pass
        return 0

    # Class helpers
    def _get_class_from_typeinfo(self, rva: int) -> int:
        if rva in self._class_cache:
            return self._class_cache[rva]
        klass = self.memory.read_ptr(self.memory.base + rva)
        self._class_cache[rva] = klass
        return klass

    def _get_class_from_dotnet(self, name_substr: str) -> int:
        rva = self._get_typeinfo_rva_by_name(name_substr)
        if not rva:
            self._debug_log(f"typeinfo 미발견: {name_substr}")
            return 0
        return self._get_class_from_typeinfo(rva)

    def _get_static_fields_ptr(self, klass: int) -> int:
        if not klass:
            return 0
        if self._scanner:
            try:
                p = self._scanner.get_static_fields_ptr(klass)
                if p:
                    return p
            except Exception:
                pass
        for off in (0xB8, 0xB0, 0xD8, 0xD0, Offsets.IL2CPPCLASS_STATIC_FIELDS_OFF):
            try:
                ptr = self.memory.read_ptr(klass + off)
                if ptr:
                    return ptr
            except Exception:
                continue
        return 0

    # Scanning helpers
    def _scan_fields_for_class(self, fields_base: int, span_bytes: int, target_klass: int) -> int:
        if self._scanner:
            try:
                return self._scanner.scan_fields_for_class(fields_base, span_bytes, target_klass)
            except Exception:
                pass
        step = 8 if self.memory.is_64 else 4
        end = fields_base + span_bytes
        for cur in range(fields_base, end, step):
            try:
                ptr = self.memory.read_ptr(cur)
                if ptr and self.memory.read_ptr(ptr) == target_klass:
                    return ptr
            except Exception:
                continue
        return 0

    def _scan_fields_for_ptr_value(self, fields_base: int, span_bytes: int, target_ptr: int) -> int:
        if self._scanner:
            try:
                return self._scanner.scan_fields_for_ptr_value(fields_base, span_bytes, target_ptr)
            except Exception:
                pass
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

    def _scan_heap_for_class_instances(self, target_klass: int, regions: Optional[List[Tuple[int,int]]] = None, limit: int = 16, time_budget_end: Optional[float] = None) -> List[int]:
        if not target_klass:
            return []
        if self._scanner:
            try:
                return self._scanner.scan_heap_for_class_instances(target_klass, regions, limit, time_budget_end)
            except Exception:
                pass
        found: List[int] = []
        step = 8 if self.memory.is_64 else 4
        try:
            if regions is None:
                b = self.memory.base
                regions = [(b + 0x01000000, 0x01000000), (b + 0x02000000, 0x01000000), (b + 0x03000000, 0x01000000), (b + 0x04000000, 0x01000000)]
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

    def _object_fields_contains_ptr(self, obj_ptr: int, target_ptr: int, span: int = 0x200) -> bool:
        if self._scanner:
            try:
                return self._scanner.object_fields_contains_ptr(obj_ptr, target_ptr, span)
            except Exception:
                pass
        try:
            fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
            base = obj_ptr + fields_off
            step = 8 if self.memory.is_64 else 4
            end = base + max(0x40, span)
            for cur in range(base, end, step):
                try:
                    if self.memory.read_ptr(cur) == target_ptr:
                        return True
                except Exception:
                    continue
        except Exception:
            return False
        return False

    def _class_has_methods(self, klass: int, methods: List[int]) -> bool:
        if self._scanner:
            try:
                return self._scanner.class_has_methods(klass, methods)
            except Exception:
                pass
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

    def _scan_object_field_ptrs(self, obj_ptr: int, span: int = 0x800) -> List[int]:
        if self._scanner:
            try:
                return self._scanner.scan_object_field_ptrs(obj_ptr, span)
            except Exception:
                pass
        out: List[int] = []
        try:
            fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
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

    def _find_object_by_method_signature(self, methods: List[int], time_budget_end: Optional[float]) -> int:
        if self._scanner:
            try:
                return self._scanner.find_object_by_method_signature(methods, time_budget_end)
            except Exception:
                pass
        return 0

    def _find_button_by_string_xref(self, time_budget_end: Optional[float] = None) -> int:
        str_va = self._get_string_va("report")
        if not str_va:
            return 0
        try:
            if self._scanner:
                btn_klasses = [self._get_class_from_dotnet(n) for n in ("reportbutton", "actionbutton", "passivebutton")]
                btn_klasses = [k for k in btn_klasses if k]
                if btn_klasses:
                    obj = self._scanner.find_button_by_string_xref(str_va, btn_klasses, time_budget_end)
                    if obj:
                        return obj
        except Exception:
            pass
        return 0

    # HUD / Report helpers
    def _find_report_button_by_label(self, time_budget_end: Optional[float] = None) -> int:
        str_va = self._get_string_va("report")
        if not str_va:
            return 0
        if self._scanner:
            try:
                btn_klasses: List[int] = []
                for tname in ("reportbutton", "actionbutton", "passivebutton"):
                    k = self._get_class_from_dotnet(tname)
                    if k:
                        btn_klasses.append(k)
                if btn_klasses:
                    obj = self._scanner.find_button_by_string_xref(str_va, btn_klasses, time_budget_end)
                    if obj:
                        return obj
            except Exception:
                pass
        for tname in ("reportbutton", "actionbutton", "passivebutton"):
            klass = self._get_class_from_dotnet(tname)
            if not klass:
                continue
            insts = self._scan_heap_for_class_instances(klass, limit=64, time_budget_end=time_budget_end)
            if not insts:
                continue
            for inst in insts:
                if time_budget_end and time.time() > time_budget_end:
                    return 0
                if self._object_fields_contains_ptr(inst, str_va, span=0x400):
                    return inst
        return 0

    def _get_hudmanager_instance_ptr(self) -> int:
        try:
            hud_klass = self._get_class_from_dotnet("hudmanager")
            if not hud_klass:
                return 0
            if self._hud_ptr_cache:
                try:
                    k = self.memory.read_ptr(self._hud_ptr_cache)
                    if k == hud_klass:
                        return self._hud_ptr_cache
                except Exception:
                    pass
            ds_rva = self._find_typeinfo_rva_by_substrings(["destroyablesingleton", "hudmanager"])
            if ds_rva:
                ds_klass = self._get_class_from_typeinfo(ds_rva)
                if ds_klass:
                    ds_static = self._get_static_fields_ptr(ds_klass)
                    if ds_static:
                        inst = self._scan_fields_for_class(ds_static, 0x400, hud_klass)
                        if inst:
                            self._hud_ptr_cache = inst
                            return inst
            static_fields = self._get_static_fields_ptr(hud_klass)
            if not static_fields:
                endt = time.time() + self._report_scan_time_budget
                insts = self._scan_heap_for_class_instances(hud_klass, limit=4, time_budget_end=endt)
                if insts:
                    self._hud_ptr_cache = insts[0]
                    return self._hud_ptr_cache
                return 0
            inst = self._scan_fields_for_class(static_fields, 0x2000, hud_klass)
            if inst:
                self._hud_ptr_cache = inst
                return self._hud_ptr_cache
            endt = time.time() + self._report_scan_time_budget
            insts = self._scan_heap_for_class_instances(hud_klass, limit=4, time_budget_end=endt)
            if insts:
                self._hud_ptr_cache = insts[0]
                return self._hud_ptr_cache
            return 0
        except Exception:
            return 0

    def _get_report_button_ptr(self) -> int:
        try:
            if self._report_ptr_cache:
                try:
                    klass = self.memory.read_ptr(self._report_ptr_cache)
                    for tname in ("reportbutton", "actionbutton", "passivebutton"):
                        k = self._get_class_from_dotnet(tname)
                        if k and klass == k:
                            return self._report_ptr_cache
                except Exception:
                    pass
            hud = self._get_hudmanager_instance_ptr()
            if hud:
                fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
                hud_fields = hud + fields_off
                for tname in ("reportbutton", "actionbutton", "passivebutton"):
                    klass = self._get_class_from_dotnet(tname)
                    if not klass:
                        continue
                    ptr = self._scan_fields_for_class(hud_fields, 0x4000, klass)
                    if ptr:
                        self._report_ptr_cache = ptr
                        return self._report_ptr_cache
            now = time.time()
            if now - self._report_scan_last < self._report_scan_min_interval:
                return 0
            self._report_scan_last = now
            endt = now + self._report_scan_time_budget
            for tname in ("reportbutton", "actionbutton", "passivebutton"):
                klass = self._get_class_from_dotnet(tname)
                if not klass:
                    continue
                insts = self._scan_heap_for_class_instances(klass, limit=8, time_budget_end=endt)
                if insts:
                    self._report_ptr_cache = insts[0]
                    return self._report_ptr_cache
            by_label = self._find_report_button_by_label(time_budget_end=endt)
            if by_label:
                self._report_ptr_cache = by_label
                return self._report_ptr_cache
            str_va = self._get_string_va("report")
            if str_va:
                obj = self._find_button_by_string_xref(time_budget_end=endt)
                if obj:
                    self._report_ptr_cache = obj
                    return self._report_ptr_cache
            try:
                methods_abs: List[int] = []
                for rva_hex in ("0x105007C0", "0x10500870"):
                    rva = int(rva_hex, 16)
                    methods_abs.append(self.memory.base + rva)
                if methods_abs:
                    obj = self._find_object_by_method_signature(methods_abs, time_budget_end=endt)
                    if obj:
                        self._report_ptr_cache = obj
                        return self._report_ptr_cache
            except Exception:
                pass
            try:
                seeds: List[int] = []
                for rva_hex in ("0x10503820", "0x105002F0", "0x10503C70", "0x10500E50"):
                    obj = self._find_object_by_method_signature([self.memory.base + int(rva_hex, 16)], time_budget_end=endt)
                    if obj:
                        seeds.append(obj)
                report_methods = [self.memory.base + int(x, 16) for x in ("0x105007C0", "0x10500870")]
                for seed in seeds:
                    if time.time() > endt:
                        break
                    refs = self._scan_object_field_ptrs(seed, span=0x1200)
                    for ref in refs:
                        if time.time() > endt:
                            break
                        try:
                            k = self.memory.read_ptr(ref)
                            if k and (self.memory.base <= k < self.memory.base + 0x05000000):
                                if self._class_has_methods(k, report_methods):
                                    self._report_ptr_cache = ref
                                    return self._report_ptr_cache
                        except Exception:
                            continue
            except Exception:
                pass
            return 0
        except Exception:
            return 0

    def _read_bool_candidates(self, obj_ptr: int) -> Dict[int, int]:
        res: Dict[int, int] = {}
        try:
            fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
            base = obj_ptr + fields_off
            for off in range(0x20, 0x200, 4):
                try:
                    val = self.memory.read_u8(base + off)
                    if val in (0, 1):
                        res[off] = val
                except Exception:
                    continue
        except Exception:
            pass
        return res

    def is_report_button_active(self) -> Tuple[Optional[bool], Dict[str, Union[int, str, Dict[int, int]]]]:
        diag: Dict[str, Union[int, str, Dict[int, int]]] = {}
        try:
            rb = self._report_ptr_cache or self._get_report_button_ptr()
            if not rb:
                diag["error"] = "ReportButton 포인터를 찾지 못함"
                return (None, diag)
            diag["report_button_ptr"] = rb
            if self._report_bool_off_cache is not None:
                fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
                try:
                    val = self.memory.read_u8(rb + fields_off + self._report_bool_off_cache)
                    diag["chosen_offset"] = self._report_bool_off_cache
                    return (bool(val), diag)
                except Exception:
                    self._report_bool_off_cache = None
            cands = self._read_bool_candidates(rb)
            diag["bool_candidates"] = cands
            if not cands:
                return (None, diag)
            best_off = sorted(cands.keys())[0]
            self._report_bool_off_cache = best_off
            active = bool(cands[best_off])
            diag["chosen_offset"] = best_off
            return (active, diag)
        except Exception as e:
            diag["error"] = str(e)
            return (None, diag)

    # Player scanning
    def _get_local_player_ptr(self) -> int:
        try:
            pc_klass = self._get_class_from_typeinfo(Offsets.PC_TYPEINFO_RVA) or self._get_class_from_dotnet("playercontrol")
            if not pc_klass:
                return 0
            candidates: List[int] = []
            try:
                sf = self.memory.read_ptr(pc_klass + Offsets.IL2CPPCLASS_STATIC_FIELDS_OFF)
                if sf:
                    candidates.append(sf)
            except Exception:
                pass
            try:
                sf2 = self._get_static_fields_ptr(pc_klass)
                if sf2 and sf2 not in candidates:
                    candidates.append(sf2)
            except Exception:
                pass
            for sf in candidates:
                try:
                    lp = self.memory.read_ptr(sf + Offsets.PC_STATIC_LOCALPLAYER_OFF)
                    if lp:
                        return lp
                except Exception:
                    continue
            return 0
        except Exception:
            return 0

    def _get_player_position(self, player_control_ptr: int) -> Optional[Tuple[float, float]]:
        if not player_control_ptr:
            return None
        try:
            fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
            pc_fields = player_control_ptr + fields_off
            net_transform = self.memory.read_ptr(pc_fields + Offsets.PC_FIELDS_NetTransform)
            if not net_transform:
                return None
            cnt_fields = net_transform + fields_off
            x = self.memory.read_f32(cnt_fields + Offsets.CNT_FIELDS_lastPosition + 0x0)
            y = self.memory.read_f32(cnt_fields + Offsets.CNT_FIELDS_lastPosition + 0x4)
            if x == 0.0 and y == 0.0:
                x = self.memory.read_f32(cnt_fields + Offsets.CNT_FIELDS_lastPosSent + 0x0)
                y = self.memory.read_f32(cnt_fields + Offsets.CNT_FIELDS_lastPosSent + 0x4)
            return (x, y)
        except Exception:
            return None

    def _get_default_outfit_from_dict(self, dict_ptr: int) -> int:
        if not dict_ptr:
            return 0
        try:
            fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
            dict_fields = dict_ptr + fields_off
            entries_arr = self.memory.read_ptr(dict_fields + (0x8 if self.memory.is_64 else 0x4))
            count = self.memory.read_int(dict_fields + (0x10 if self.memory.is_64 else 0x8))
            if not entries_arr or count <= 0:
                return 0
            vec_off = Offsets.IL2CPP_ARRAY_VECTOR_OFF_X64 if self.memory.is_64 else Offsets.IL2CPP_ARRAY_VECTOR_OFF_X86
            entries_base = entries_arr + vec_off
            entry_size = 0x18 if self.memory.is_64 else 0x10
            for i in range(min(count, 16)):
                entry_offset = entries_base + i * entry_size
                try:
                    hash_code = self.memory.read_u32(entry_offset + 0x0)
                    if ctypes.c_int(hash_code).value < 0:
                        continue
                    key = self.memory.read_u32(entry_offset + 0x8)
                    if key == 0:
                        return self.memory.read_ptr(entry_offset + (0x10 if self.memory.is_64 else 0x0C))
                except Exception:
                    continue
            return 0
        except Exception:
            return 0

    def _get_color_id_from_outfit(self, outfit_ptr: int) -> int:
        if not outfit_ptr:
            return -1
        try:
            fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
            outfit_fields = outfit_ptr + fields_off
            return self.memory.read_u32(outfit_fields + 0x0)
        except Exception:
            return -1

    def _get_player_color_id(self, npi_ptr: int) -> int:
        if not npi_ptr:
            return -1
        try:
            fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
            npi_fields = npi_ptr + fields_off
            for offset in [0x38, 0x3C, 0x40, 0x44, 0x48] + list(range(0x30, 0x80, 8 if self.memory.is_64 else 4)):
                try:
                    outfits_dict = self.memory.read_ptr(npi_fields + offset)
                    if not outfits_dict:
                        continue
                    dict_fields = outfits_dict + fields_off
                    entries_arr = self.memory.read_ptr(dict_fields + (0x8 if self.memory.is_64 else 0x4))
                    count = self.memory.read_int(dict_fields + (0x10 if self.memory.is_64 else 0x8))
                    if entries_arr and 0 < count <= 16:
                        outfit = self._get_default_outfit_from_dict(outfits_dict)
                        if outfit:
                            color_id = self._get_color_id_from_outfit(outfit)
                            if 0 <= color_id <= 18:
                                return color_id
                except Exception:
                    continue
            return -1
        except Exception:
            return -1

    def _get_all_npi_objects(self) -> List[int]:
        try:
            gd_klass = self._get_class_from_typeinfo(Offsets.GAMEDATA_TYPEINFO_RVA) or self._get_class_from_dotnet("gamedata")
            if not gd_klass:
                return []
            candidates: List[int] = []
            try:
                sf = self.memory.read_ptr(gd_klass + Offsets.IL2CPPCLASS_STATIC_FIELDS_OFF)
                if sf:
                    candidates.append(sf)
            except Exception:
                pass
            try:
                sf2 = self._get_static_fields_ptr(gd_klass)
                if sf2 and sf2 not in candidates:
                    candidates.append(sf2)
            except Exception:
                pass
            gd = 0
            for sf in candidates:
                try:
                    inst = self.memory.read_ptr(sf + 0x0)
                    if inst:
                        gd = inst
                        break
                except Exception:
                    continue
            if not gd:
                return []
            gd_fields = gd + (Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86)
            list_npi_klass = self._get_class_from_typeinfo(Offsets.LIST_NPI_TYPEINFO_RVA) or self._get_class_from_dotnet("list_1_networkedplayerinfo_")
            all_players_list = self._scan_fields_for_class(gd_fields, 0x400, list_npi_klass)
            if not all_players_list:
                return []
            list_fields = all_players_list + (Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86)
            items = self.memory.read_ptr(list_fields + 0x0)
            size = self.memory.read_int(list_fields + (0x8 if self.memory.is_64 else 0x4))
            if not items or size <= 0 or size > 32:
                return []
            vec_off = Offsets.IL2CPP_ARRAY_VECTOR_OFF_X64 if self.memory.is_64 else Offsets.IL2CPP_ARRAY_VECTOR_OFF_X86
            ptr_sz = 8 if self.memory.is_64 else 4
            players: List[int] = []
            for i in range(size):
                npi = self.memory.read_ptr(items + vec_off + i * ptr_sz)
                if npi:
                    players.append(npi)
            return players
        except Exception:
            return []

    def _get_player_control_from_npi(self, npi_ptr: int) -> int:
        if not npi_ptr:
            return 0
        try:
            fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
            npi_fields = npi_ptr + fields_off
            pc_klass = self._get_class_from_typeinfo(Offsets.PC_TYPEINFO_RVA) or self._get_class_from_dotnet("playercontrol")
            for offset in [0x48, 0x4C, 0x50, 0x54, 0x58, 0x5C]:
                try:
                    candidate_pc = self.memory.read_ptr(npi_fields + offset)
                    if candidate_pc:
                        candidate_klass = self.memory.read_ptr(candidate_pc)
                        if candidate_klass == pc_klass:
                            return candidate_pc
                except Exception:
                    continue
            return 0
        except Exception:
            return 0

    # Role helpers
    def _get_cached_playerdata_class(self) -> int:
        if not self.memory:
            return 0
        if self._cached_playerdata_class:
            return self._cached_playerdata_class
        klass = 0
        try:
            klass = self._get_class_from_typeinfo(Offsets.CACHED_PLAYERDATA_TYPEINFO_RVA)
        except Exception:
            klass = 0
        if not klass:
            try:
                klass = self._get_class_from_dotnet("cachedplayerdata")
            except Exception:
                klass = 0
        if klass:
            self._cached_playerdata_class = klass
        return klass

    def _get_cached_playerdata_ptr(self, pc_ptr: int) -> int:
        if not pc_ptr or not self.memory:
            return 0
        klass = self._get_cached_playerdata_class()
        if not klass:
            return 0
        is64 = bool(self.memory.is_64)
        cached_off = self._cached_playerdata_ptr_off.get(is64)
        fields_off = Offsets.OBJ_FIELDS_OFF_X64 if is64 else Offsets.OBJ_FIELDS_OFF_X86
        pc_fields = pc_ptr + fields_off
        ptr_sz = 8 if is64 else 4

        def check_at(offset: int) -> int:
            try:
                cand = self.memory.read_ptr(pc_fields + offset)
            except Exception:
                return 0
            if not cand:
                return 0
            try:
                cand_klass = self.memory.read_ptr(cand)
            except Exception:
                return 0
            if cand_klass == klass:
                self._cached_playerdata_ptr_off[is64] = offset
                return cand
            return 0

        if cached_off is not None:
            ptr = check_at(cached_off)
            if ptr:
                return ptr
            self._cached_playerdata_ptr_off.pop(is64, None)

        max_span = 0x200 if is64 else 0x100
        for off in range(0, max_span, ptr_sz):
            ptr = check_at(off)
            if ptr:
                return ptr
        return 0

    def get_local_impostor_flag(self) -> Tuple[Optional[bool], Dict[str, Union[int, str]]]:
        diag: Dict[str, Union[int, str]] = {}
        try:
            if not self.is_attached() and not self.attach():
                diag["error"] = "not attached"
                return (None, diag)
            if not self.memory:
                diag["error"] = "memory unavailable"
                return (None, diag)
            is64 = bool(self.memory.is_64)
            diag["is64"] = 1 if is64 else 0
            pc_ptr = self._get_local_player_ptr()
            diag["local_pc"] = pc_ptr or 0
            if not pc_ptr:
                diag["error"] = "local player not found"
                return (None, diag)
            cached_ptr = self._get_cached_playerdata_ptr(pc_ptr)
            diag["cached_playerdata_ptr"] = cached_ptr or 0
            ptr_off = self._cached_playerdata_ptr_off.get(is64)
            diag["cached_ptr_offset"] = int(ptr_off) if ptr_off is not None else -1
            if not cached_ptr:
                diag["error"] = "CachedPlayerData not found"
                return (None, diag)
            fields_off = Offsets.OBJ_FIELDS_OFF_X64 if is64 else Offsets.OBJ_FIELDS_OFF_X86
            ptr_sz = 8 if is64 else 4
            base = cached_ptr + fields_off
            offsets = {
                "is_you": ptr_sz * 2,
                "is_impostor": ptr_sz * 2 + 1,
                "is_dead": ptr_sz * 2 + 2,
            }
            diag["fields_offset"] = fields_off
            diag["is_you_offset"] = offsets["is_you"]
            diag["is_impostor_offset"] = offsets["is_impostor"]
            try:
                is_you_raw = self.memory.read_u8(base + offsets["is_you"])
                diag["is_you_raw"] = int(is_you_raw)
            except Exception:
                diag["is_you_raw"] = -1
            try:
                is_dead_raw = self.memory.read_u8(base + offsets["is_dead"])
                diag["is_dead_raw"] = int(is_dead_raw)
            except Exception:
                diag["is_dead_raw"] = -1
            try:
                raw = self.memory.read_u8(base + offsets["is_impostor"])
            except Exception as exc:
                diag["error"] = str(exc)
                return (None, diag)
            diag["impostor_raw"] = int(raw)
            if raw not in (0, 1):
                diag["error"] = "unexpected raw value"
                return (None, diag)
            return (bool(raw), diag)
        except Exception as e:
            diag["error"] = str(e)
            return (None, diag)

    def _npi_has_clientdata(self, npi_ptr: int) -> bool:
        if not npi_ptr:
            return False
        try:
            fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
            npi_fields = npi_ptr + fields_off
            cd_klass = self._get_class_from_typeinfo(Offsets.CLIENTDATA_TYPEINFO_RVA) or self._get_class_from_dotnet("clientdata")
            if not cd_klass:
                return False
            step = 8 if self.memory.is_64 else 4
            for offset in list(range(0x30, 0x100, step)) + [0x10, 0x14, 0x18, 0x1C]:
                try:
                    candidate_ptr = self.memory.read_ptr(npi_fields + offset)
                    if candidate_ptr:
                        candidate_klass = self.memory.read_ptr(candidate_ptr)
                        if candidate_klass == cd_klass:
                            return True
                except Exception:
                    continue
            return False
        except Exception:
            return False

    # Tasks helpers
    def _get_npi_by_player_id(self, player_id: int) -> int:
        try:
            for npi in self._get_all_npi_objects():
                try:
                    # Prefer robust correlation via PlayerControl pointer
                    pc = self._get_player_control_from_npi(npi)
                    if pc:
                        lp = self._get_local_player_ptr()
                        if lp and pc == lp and self._cached_local_player is not None and int(player_id) == int(self._cached_local_player):
                            return npi
                    # Fallback: best-effort read of PlayerId (field layout may vary)
                    fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
                    npi_fields = npi + fields_off
                    for off in (0x8, 0x10, 0x18, 0x20, 0x24, 0x28):
                        try:
                            pid = self.memory.read_u8(npi_fields + off)
                            if pid == player_id:
                                return npi
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception:
            pass
        return 0

    def _get_npi_by_color_id(self, color_id: int) -> int:
        try:
            cid = int(color_id)
            if not (0 <= cid <= 18):
                return 0
            for npi in self._get_all_npi_objects():
                try:
                    npi_color_id = self._get_player_color_id(npi)
                    if npi_color_id == cid:
                        return npi
                except Exception:
                    continue
        except Exception:
            pass
        return 0

    def _get_tasks_list_from_npi(self, npi_ptr: int) -> int:
        if not npi_ptr:
            return 0
        try:
            list_taskinfo_klass = self._get_class_from_typeinfo(Offsets.LIST_TASKINFO_TYPEINFO_RVA) or self._get_class_from_dotnet("list_1_networkedplayerinfo_taskinfo_")
            fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
            npi_fields = npi_ptr + fields_off
            return self._scan_fields_for_class(npi_fields, 0x400, list_taskinfo_klass)
        except Exception:
            return 0

    def _parse_tasks_from_list(self, list_ptr: int) -> List[TaskData]:
        tasks: List[TaskData] = []
        if not list_ptr:
            return tasks
        try:
            fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
            list_fields = list_ptr + fields_off
            items = self.memory.read_ptr(list_fields + 0x0)
            size = self.memory.read_int(list_fields + (0x8 if self.memory.is_64 else 0x4))
            if not items or size <= 0 or size > 64:
                return tasks
            vec_off = Offsets.IL2CPP_ARRAY_VECTOR_OFF_X64 if self.memory.is_64 else Offsets.IL2CPP_ARRAY_VECTOR_OFF_X86
            ptr_sz = 8 if self.memory.is_64 else 4
            for i in range(size):
                try:
                    task_ptr = self.memory.read_ptr(items + vec_off + i * ptr_sz)
                    if not task_ptr:
                        continue
                    task_fields = task_ptr + fields_off
                    tid = self.memory.read_u32(task_fields + 0x0)
                    ttype = self.memory.read_u8(task_fields + 0x4)
                    completed = bool(self.memory.read_u8(task_fields + 0x5))
                    if 0 <= tid < 1024 and 0 <= ttype < 1024:
                        tasks.append(TaskData(task_id=int(tid), task_type_id=int(ttype), is_completed=completed))
                except Exception:
                    continue
        except Exception:
            pass
        return tasks

    # ----- myTasks step probing (heuristic, local only) -----
    def _find_myTasks_list_by_owner(self, pc_ptr: int) -> int:
        if not pc_ptr:
            return 0
        try:
            fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
            base = pc_ptr + fields_off
            step = 8 if self.memory.is_64 else 4
            vec_off = Offsets.IL2CPP_ARRAY_VECTOR_OFF_X64 if self.memory.is_64 else Offsets.IL2CPP_ARRAY_VECTOR_OFF_X86
            ptr_sz = 8 if self.memory.is_64 else 4
            for cur in range(base, base + 0x1400, step):
                try:
                    lst = self.memory.read_ptr(cur)
                except Exception:
                    lst = 0
                if not lst:
                    continue
                try:
                    list_fields = lst + fields_off
                    items = self.memory.read_ptr(list_fields + 0x0)
                    size = self.memory.read_int(list_fields + (0x8 if self.memory.is_64 else 0x4))
                    if not items or size <= 0 or size > 64:
                        continue
                    total = min(size, 6)
                    if total <= 0:
                        continue
                    ok = 0
                    for i in range(total):
                        try:
                            obj = self.memory.read_ptr(items + vec_off + i * ptr_sz)
                            if not obj:
                                continue
                            if self._object_fields_contains_ptr(obj, pc_ptr, span=0x120):
                                ok += 1
                        except Exception:
                            continue
                    if ok >= max(2, total // 2):
                        return lst
                except Exception:
                    continue
        except Exception:
            return 0
        return 0

    def _read_list_items(self, list_ptr: int) -> List[int]:
        out: List[int] = []
        if not list_ptr:
            return out
        try:
            fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
            list_fields = list_ptr + fields_off
            items = self.memory.read_ptr(list_fields + 0x0)
            size = self.memory.read_int(list_fields + (0x8 if self.memory.is_64 else 0x4))
            if not items or size <= 0 or size > 64:
                return out
            vec_off = Offsets.IL2CPP_ARRAY_VECTOR_OFF_X64 if self.memory.is_64 else Offsets.IL2CPP_ARRAY_VECTOR_OFF_X86
            ptr_sz = 8 if self.memory.is_64 else 4
            for i in range(size):
                try:
                    obj = self.memory.read_ptr(items + vec_off + i * ptr_sz)
                    if obj:
                        out.append(obj)
                except Exception:
                    continue
        except Exception:
            return out
        return out

    def _read_step_info_heuristic(self, obj_ptr: int, completed_hint: Optional[bool]) -> Tuple[Optional[int], Optional[int]]:
        try:
            fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
            base = obj_ptr + fields_off
            best = None
            for off in range(0x10, 0x200, 4):
                try:
                    a = self.memory.read_int(base + off)
                    b = self.memory.read_int(base + off + 4)
                except Exception:
                    continue
                if 0 <= a <= 16 and 1 <= b <= 16 and a <= b:
                    score = 0
                    if b <= 7:
                        score += 2
                    if a <= 3:
                        score += 1
                    if completed_hint is True and a == b:
                        score += 2
                    if completed_hint is False and a < b:
                        score += 1
                    if best is None or score > best[0]:
                        best = (score, a, b)
            if best:
                return best[1], best[2]
        except Exception:
            return (None, None)
        return (None, None)

    def _read_tasktype_from_playertask(self, obj_ptr: int, pc_ptr: int) -> Tuple[Optional[int], Optional[int], Optional[int]]:
        try:
            fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
            base = obj_ptr + fields_off
            ptr_sz = 8 if self.memory.is_64 else 4
            owner_off = None
            for off in range(0x0, 0x80, ptr_sz):
                try:
                    p = self.memory.read_ptr(base + off)
                    if p == pc_ptr:
                        try:
                            maybe_id = self.memory.read_u32(base + off - 4)
                        except Exception:
                            maybe_id = None
                        owner_off = off
                        break
                except Exception:
                    continue
            if owner_off is not None:
                start_at = None
                try:
                    start_at = self.memory.read_int(base + owner_off + ptr_sz)
                except Exception:
                    start_at = None
                try:
                    ttype_off = owner_off + ptr_sz + 0x4
                    ttype = self.memory.read_int(base + ttype_off)
                except Exception:
                    ttype = None
                try:
                    tid_val = self.memory.read_u32(base + owner_off - 4)
                except Exception:
                    tid_val = None
                return ttype, tid_val, start_at
        except Exception:
            return (None, None, None)
        return (None, None, None)

    def _system_type_to_name(self, system_id: Optional[int]) -> Optional[str]:
        if system_id is None:
            return None
        return system_type_to_name.get(int(system_id))

    # Cache and public API
    def _refresh_cache(self, force: bool = False) -> None:
        current_time = time.time()
        if not force and current_time - self._last_scan_time < self._scan_interval:
            return
        self._last_scan_time = current_time
        self._cached_players = []
        self._cached_local_player = None
        try:
            if not self.is_attached() and not self.attach():
                return
            local_player_ptr = self._get_local_player_ptr()
            all_npi = self._get_all_npi_objects()
            for idx, npi in enumerate(all_npi):
                try:
                    player_control = self._get_player_control_from_npi(npi)
                    if not player_control:
                        continue
                    position = self._get_player_position(player_control)
                    if not position:
                        continue
                    color_id = self._get_player_color_id(npi)
                    if color_id < 0:
                        continue
                    fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
                    npi_fields = npi + fields_off
                    pc_fields = player_control + fields_off
                    
                    # Try to read player_id from multiple locations
                    # First try NPI fields (common offsets)
                    player_id = None
                    for offset in (0x8, 0x10, 0x18, 0x20, 0x24, 0x28, 0x2C, 0x30, 0x34, 0x38):
                        try:
                            candidate_id = self.memory.read_u8(npi_fields + offset)
                            # Check if it's a reasonable player_id (0-15 is typical for Among Us)
                            if 0 <= candidate_id < 16:
                                # Verify it's not just a common value by checking uniqueness
                                player_id = candidate_id
                                break
                        except Exception:
                            continue
                    
                    # If not found in NPI, try PlayerControl fields
                    if player_id is None:
                        for offset in (0x8, 0x10, 0x18, 0x20, 0x24, 0x28, 0x2C, 0x30, 0x34, 0x38):
                            try:
                                candidate_id = self.memory.read_u8(pc_fields + offset)
                                if 0 <= candidate_id < 16:
                                    player_id = candidate_id
                                    break
                            except Exception:
                                continue
                    
                    # If still not found, use index-based ID to ensure uniqueness
                    # Use the index in the NPI list as a fallback
                    if player_id is None:
                        player_id = idx
                    else:
                        # Check if this player_id is already used, if so use index
                        existing_ids = {p.player_id for p in self._cached_players}
                        if player_id in existing_ids:
                            # Use sequential ID starting from max existing + 1
                            max_id = max(existing_ids) if existing_ids else -1
                            player_id = max_id + 1
                    is_local = (player_control == local_player_ptr)
                    if is_local:
                        self._cached_local_player = player_id
                    self._cached_players.append(
                        PlayerData(
                            player_id=player_id,
                            color_id=color_id,
                            color_name=ColorId.get_name(color_id),
                            position=position,
                            is_local_player=is_local,
                            last_update=current_time,
                        )
                    )
                except Exception:
                    continue
        except Exception as e:
            self._debug_log(f"캐시 새로고침 실패: {e}")

    def refresh(self, force: bool = False) -> None:
        self._refresh_cache(force=force)

    def get_player_by_id(self, player_id: int) -> Optional[PlayerData]:
        self._refresh_cache()
        for p in self._cached_players:
            if p.player_id == player_id:
                return p
        return None

    def get_player_by_color(self, color_id: Union[int, ColorId]) -> Optional[PlayerData]:
        self._refresh_cache()
        cid = color_id.value if isinstance(color_id, ColorId) else int(color_id)
        for p in self._cached_players:
            if p.color_id == cid:
                return p
        return None

    def get_local_player(self) -> Optional[PlayerData]:
        self._refresh_cache()
        for p in self._cached_players:
            if p.is_local_player:
                return p
        return None

    def get_local_player_id(self) -> Optional[int]:
        self._refresh_cache()
        return self._cached_local_player

    def get_all_players(self) -> List[PlayerData]:
        self._refresh_cache()
        return self._cached_players.copy()

    def get_player_positions(self) -> Dict[int, Tuple[float, float]]:
        self._refresh_cache()
        return {p.player_id: p.position for p in self._cached_players}

    def get_player_positions_by_color(self) -> Dict[int, Tuple[float, float]]:
        self._refresh_cache()
        return {p.color_id: p.position for p in self._cached_players}

    def get_color_mapping(self) -> Dict[int, str]:
        self._refresh_cache()
        return {p.player_id: p.color_name for p in self._cached_players}

    def get_color_mapping_by_color_id(self) -> Dict[int, str]:
        self._refresh_cache()
        return {p.color_id: p.color_name for p in self._cached_players}

    def get_player_count(self) -> int:
        self._refresh_cache()
        return len(self._cached_players)

    def get_tasks_for_player(self, player_id: int) -> List[TaskData]:
        try:
            if not self.is_attached() and not self.attach():
                return []
            # For local player, resolve NPI by PlayerControl correlation to avoid PlayerId offset mismatches
            npi = 0
            if self._cached_local_player is not None and int(player_id) == int(self._cached_local_player):
                for cand in self._get_all_npi_objects():
                    try:
                        pc = self._get_player_control_from_npi(cand)
                        if pc and pc == self._get_local_player_ptr():
                            npi = cand
                            break
                    except Exception:
                        continue
            if not npi:
                npi = self._get_npi_by_player_id(player_id)
            if not npi:
                return []
            tasks_list = self._get_tasks_list_from_npi(npi)
            if not tasks_list:
                return []
            tasks = self._parse_tasks_from_list(tasks_list)
            task_by_id: Dict[int, TaskData] = {int(t.task_id): t for t in tasks}
            # Enrich with step info for local player's myTasks when available
            pc = self._get_player_control_from_npi(npi)
            if pc and tasks:
                lst = self._find_myTasks_list_by_owner(pc)
                objs = self._read_list_items(lst) if lst else []
                if objs:
                    for obj in objs:
                        ttype, tid_guess, start_at = self._read_tasktype_from_playertask(obj, pc)
                        if tid_guess is None:
                            continue
                        tid = int(tid_guess)
                        td = task_by_id.get(tid)
                        if td is None:
                            td = TaskData(task_id=tid, task_type_id=int(ttype or -1), is_completed=False)
                            task_by_id[tid] = td
                            tasks.append(td)
                        if ttype is not None:
                            td.task_type_id = int(ttype)
                        if start_at is not None:
                            td.start_system = int(start_at)
                            td.location = system_type_to_name(start_at)
                        s, m = self._read_step_info_heuristic(obj, td.is_completed)
                        td.step, td.max_step = s, m
                        if m is not None and s is not None and m > 0 and s >= m:
                            td.is_completed = True
            return tasks
        except Exception:
            return []

    def get_tasks_for_player_by_color(self, color_id: Union[int, ColorId]) -> List[TaskData]:
        try:
            if not self.is_attached() and not self.attach():
                return []
            cid = color_id.value if isinstance(color_id, ColorId) else int(color_id)
            npi = self._get_npi_by_color_id(cid)
            if not npi:
                return []
            tasks_list = self._get_tasks_list_from_npi(npi)
            if not tasks_list:
                return []
            tasks = self._parse_tasks_from_list(tasks_list)
            task_by_id: Dict[int, TaskData] = {int(t.task_id): t for t in tasks}
            # Enrich with step info for local player's myTasks when available
            pc = self._get_player_control_from_npi(npi)
            if pc and tasks:
                lst = self._find_myTasks_list_by_owner(pc)
                objs = self._read_list_items(lst) if lst else []
                if objs:
                    for obj in objs:
                        ttype, tid_guess, start_at = self._read_tasktype_from_playertask(obj, pc)
                        if tid_guess is None:
                            continue
                        tid = int(tid_guess)
                        td = task_by_id.get(tid)
                        if td is None:
                            td = TaskData(task_id=tid, task_type_id=int(ttype or -1), is_completed=False)
                            task_by_id[tid] = td
                            tasks.append(td)
                        if ttype is not None:
                            td.task_type_id = int(ttype)
                        if start_at is not None:
                            td.start_system = int(start_at)
                            td.location = system_type_to_name(start_at)
                        s, m = self._read_step_info_heuristic(obj, td.is_completed)
                        td.step, td.max_step = s, m
                        if m is not None and s is not None and m > 0 and s >= m:
                            td.is_completed = True
            return tasks
        except Exception:
            return []

    # Lifecycle helpers
    def cleanup(self) -> None:
        try:
            self._class_cache.clear()
            self._cached_players.clear()
            self._cached_local_player = None
            self._cached_playerdata_ptr_off.clear()
            self._cached_playerdata_class = None
            self.detach()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.cleanup()

    def __del__(self):
        self.cleanup()
