from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Iterator, List, Tuple, Optional

import pymem
import pymem.process


class MemoryClient:
    def __init__(self, process_name: str = "Among Us.exe") -> None:
        self.pm = pymem.Pymem(process_name)
        self.base = self._get_module_base("GameAssembly.dll")
        self._kernel32 = ctypes.windll.kernel32
        self.is_64 = self._detect_architecture()

    def _get_module_base(self, name: str) -> int:
        mod = pymem.process.module_from_name(self.pm.process_handle, name)
        return mod.lpBaseOfDll

    def _detect_architecture(self) -> bool:
        try:
            is_64 = pymem.process.is_64_bit(self.pm.process_handle)
        except Exception:
            is_64 = ctypes.sizeof(ctypes.c_void_p) == 8

        if not is_64:
            try:
                is_wow64 = wintypes.BOOL()
                if self._kernel32.IsWow64Process(self.pm.process_handle, ctypes.byref(is_wow64)):
                    if not is_wow64.value and ctypes.sizeof(ctypes.c_void_p) == 8:
                        is_64 = True
            except Exception:
                pass

        if not is_64:
            try:
                test_addr = self.base + 0x10
                high = self.pm.read_uint(test_addr + 4)
                if high:
                    is_64 = True
            except Exception:
                pass

        return is_64

    def close(self) -> None:
        try:
            self.pm.close_process()
        except Exception:
            pass

    def _virtual_query(self, addr: int) -> Optional[ctypes.Structure]:
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

        mbi = MEMORY_BASIC_INFORMATION()
        res = self._kernel32.VirtualQueryEx(self.pm.process_handle, ctypes.c_void_p(int(addr)), ctypes.byref(mbi), ctypes.sizeof(mbi))
        if res == 0:
            return None
        return mbi

    def is_address_committed(self, addr: int) -> bool:
        try:
            info = self._virtual_query(addr)
        except Exception:
            return False
        if not info:
            return False
        MEM_COMMIT = 0x1000
        PAGE_GUARD = 0x100
        PAGE_NOACCESS = 0x01
        state = int(info.State)
        prot = int(info.Protect)
        if state != MEM_COMMIT:
            return False
        if prot == PAGE_NOACCESS or (prot & PAGE_GUARD):
            return False
        return True

    # primitives
    def read_ptr(self, addr: int) -> int:
        if not self.is_address_committed(addr):
            raise pymem.exception.MemoryReadError(addr, 8 if self.is_64 else 4, 299)
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

    def read_bytes(self, addr: int, size: int) -> bytes:
        return bytes(self.pm.read_bytes(addr, size))

    def write_bytes(self, addr: int, data: bytes) -> None:
        self.pm.write_bytes(addr, data, len(data))

    # remote memory management / threads
    def alloc(self, size: int, protect: int = 0x40) -> int:
        # default protect: PAGE_EXECUTE_READWRITE = 0x40
        MEM_COMMIT = 0x1000
        MEM_RESERVE = 0x2000
        addr = self._kernel32.VirtualAllocEx(self.pm.process_handle, None, size, MEM_COMMIT | MEM_RESERVE, protect)
        return int(ctypes.c_void_p(addr).value or 0)

    def free(self, addr: int, size: int = 0) -> bool:
        MEM_RELEASE = 0x8000
        return bool(self._kernel32.VirtualFreeEx(self.pm.process_handle, ctypes.c_void_p(addr), size, MEM_RELEASE))

    def create_remote_thread(self, start_addr: int, param: int = 0) -> int:
        hThread = self._kernel32.CreateRemoteThread(self.pm.process_handle, None, 0, ctypes.c_void_p(start_addr), ctypes.c_void_p(param), 0, None)
        return int(ctypes.c_void_p(hThread).value or 0)

    def wait_thread(self, thread_handle: int, timeout_ms: int = 5000) -> Optional[int]:
        WAIT_OBJECT_0 = 0x00000000
        INFINITE = 0xFFFFFFFF
        to = timeout_ms if timeout_ms >= 0 else INFINITE
        res = self._kernel32.WaitForSingleObject(ctypes.c_void_p(thread_handle), to)
        if res != WAIT_OBJECT_0:
            return None
        exit_code = wintypes.DWORD()
        if not self._kernel32.GetExitCodeThread(ctypes.c_void_p(thread_handle), ctypes.byref(exit_code)):
            return None
        return int(exit_code.value)

    # Export resolver for remote module (reads remote PE export directory)
    def get_export_address(self, module_base: int, export_name: str) -> int:
        try:
            base = module_base
            # IMAGE_DOS_HEADER
            dos = self.read_bytes(base, 0x40)
            if len(dos) < 0x40 or dos[:2] != b"MZ":
                return 0
            e_lfanew = int.from_bytes(dos[0x3C:0x40], "little")
            # IMAGE_NT_HEADERS (read generously)
            nt = self.read_bytes(base + e_lfanew, 0x200)
            if len(nt) < 0x90 or nt[:4] != b"PE\x00\x00":
                return 0
            # FileHeader is 0x18 bytes after signature; OptionalHeader follows
            opt = nt[0x18:]
            if len(opt) < 0x70:
                return 0
            magic = int.from_bytes(opt[0:2], "little")
            if magic == 0x20B:  # PE32+
                data_dir_off = 0x70
            elif magic == 0x10B:  # PE32
                data_dir_off = 0x60
            else:
                return 0
            # IMAGE_DIRECTORY_ENTRY_EXPORT = 0
            if len(opt) < data_dir_off + 8:
                return 0
            export_rva = int.from_bytes(opt[data_dir_off:data_dir_off+4], "little")
            export_size = int.from_bytes(opt[data_dir_off+4:data_dir_off+8], "little")
            if export_rva == 0:
                return 0
            # IMAGE_EXPORT_DIRECTORY (size >= 0x28)
            exp = self.read_bytes(base + export_rva, 0x28)
            if len(exp) < 0x28:
                return 0
            NumberOfFunctions = int.from_bytes(exp[0x14:0x18], "little")
            NumberOfNames = int.from_bytes(exp[0x18:0x1C], "little")
            AddressOfFunctions = int.from_bytes(exp[0x1C:0x20], "little")
            AddressOfNames = int.from_bytes(exp[0x20:0x24], "little")
            AddressOfNameOrdinals = int.from_bytes(exp[0x24:0x28], "little")
            names_rva = base + AddressOfNames
            ords_rva = base + AddressOfNameOrdinals
            funcs_rva = base + AddressOfFunctions
            for i in range(NumberOfNames):
                name_rva = int.from_bytes(self.read_bytes(names_rva + i*4, 4), "little")
                if not name_rva:
                    continue
                # read C-string at base + name_rva
                saddr = base + name_rva
                name_bytes = bytearray()
                for _ in range(256):
                    b = self.read_bytes(saddr + len(name_bytes), 1)
                    if not b or b[0] == 0:
                        break
                    name_bytes.append(b[0])
                name = name_bytes.decode(errors="ignore")
                if name == export_name:
                    ord_index = int.from_bytes(self.read_bytes(ords_rva + i*2, 2), "little")
                    func_rva = int.from_bytes(self.read_bytes(funcs_rva + ord_index*4, 4), "little")
                    return base + func_rva
            return 0
        except Exception:
            return 0

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
