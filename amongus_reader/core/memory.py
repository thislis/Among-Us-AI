from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Iterator, List, Tuple

import pymem
import pymem.process


class MemoryClient:
    def __init__(self, process_name: str = "Among Us.exe") -> None:
        self.pm = pymem.Pymem(process_name)
        self.base = self._get_module_base("GameAssembly.dll")
        self.is_64 = self._detect_architecture()

    def _get_module_base(self, name: str) -> int:
        mod = pymem.process.module_from_name(self.pm.process_handle, name)
        return mod.lpBaseOfDll

    def _detect_architecture(self) -> bool:
        try:
            return pymem.process.is_64_bit(self.pm.process_handle)
        except Exception:
            return ctypes.sizeof(ctypes.c_void_p) == 8

    def close(self) -> None:
        try:
            self.pm.close_process()
        except Exception:
            pass

    # primitives
    def read_ptr(self, addr: int) -> int:
        if self.is_64:
            return self.pm.read_ulonglong(addr)
        else:
            return self.pm.read_uint(addr)

    def read_u32(self, addr: int) -> int:
        return self.pm.read_uint(addr)

    def read_u8(self, addr: int) -> int:
        return self.pm.read_bytes(addr, 1)[0]

    def read_f32(self, addr: int) -> float:
        return self.pm.read_float(addr)

    def read_int(self, addr: int) -> int:
        return self.pm.read_int(addr)

    # region enumeration
    def iter_committed_readable_regions(self, max_regions: int = 4096) -> Iterator[Tuple[int, int]]:
        kernel32 = ctypes.windll.kernel32
        PROCESS = self.pm.process_handle

        class MEMORY_BASIC_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BaseAddress", ctypes.c_void_p),
                ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wintypes.DWORD),
                ("RegionSize", ctypes.c_size_t),
                ("State", wintypes.DWORD),
                ("Protect", wintypes.DWORD),
                ("Type", wintypes.DWORD),
            ]

        PAGE_NOACCESS = 0x01
        PAGE_GUARD = 0x100
        MEM_COMMIT = 0x1000
        readable = {0x02, 0x04, 0x08, 0x20, 0x40, 0x80}

        mbi = MEMORY_BASIC_INFORMATION()
        addr = 0
        count = 0
        max_address = 0x7FFFFFFFFFFF if self.is_64 else 0x7FFFFFFF
        while addr < max_address and count < max_regions:
            res = kernel32.VirtualQueryEx(PROCESS, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi))
            if not res:
                addr += 0x10000
                continue
            size = int(mbi.RegionSize)
            base = int(ctypes.cast(mbi.BaseAddress, ctypes.c_void_p).value or 0)
            prot = int(mbi.Protect)
            state = int(mbi.State)
            if state == MEM_COMMIT and prot in readable and prot != PAGE_NOACCESS and (prot & PAGE_GUARD) == 0:
                yield (base, size)
                count += 1
            addr = base + size

    def iter_heap_regions(self, max_regions: int = 4096) -> Iterator[Tuple[int, int]]:
        kernel32 = ctypes.windll.kernel32
        PROCESS = self.pm.process_handle

        class MEMORY_BASIC_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BaseAddress", ctypes.c_void_p),
                ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wintypes.DWORD),
                ("RegionSize", ctypes.c_size_t),
                ("State", wintypes.DWORD),
                ("Protect", wintypes.DWORD),
                ("Type", wintypes.DWORD),
            ]

        MEM_COMMIT = 0x1000
        RW_PROTS = {0x04, 0x08, 0x40, 0x80}

        mbi = MEMORY_BASIC_INFORMATION()
        addr = 0
        count = 0
        max_address = 0x7FFFFFFFFFFF if self.is_64 else 0x7FFFFFFF
        while addr < max_address and count < max_regions:
            res = kernel32.VirtualQueryEx(PROCESS, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi))
            if not res:
                addr += 0x10000
                continue
            size = int(mbi.RegionSize)
            base = int(ctypes.cast(mbi.BaseAddress, ctypes.c_void_p).value or 0)
            prot = int(mbi.Protect)
            state = int(mbi.State)
            if state == MEM_COMMIT and prot in RW_PROTS:
                yield (base, size)
                count += 1
            addr = base + size
