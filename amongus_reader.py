"""
Among Us 데이터 서비스 API
"""

from __future__ import print_function, unicode_literals
import pymem
import pymem.process
import ctypes
import time
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum


class ColorId(Enum):
    """Among Us 색상 ID 상수"""
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
        """ID를 색상 이름으로 변환""" # 모니터링 용
        color_map = {
            0: "Red", 1: "Blue", 2: "Green", 3: "Pink",
            4: "Orange", 5: "Yellow", 6: "Black", 7: "White",
            8: "Purple", 9: "Brown", 10: "Cyan", 11: "Lime",
            12: "Maroon", 13: "Rose", 14: "Banana", 15: "Gray",
            16: "Tan", 17: "Sunset", 18: "Coral"
        }
        return color_map.get(color_id, f"Unknown({color_id})")

@dataclass
class PlayerData:
    """플레이어 데이터 구조체"""
    player_id: int
    color_id: int
    color_name: str
    position: Tuple[float, float]
    is_local_player: bool = False
    last_update: float = 0.0

@dataclass
class TaskData:
    """태스크 데이터 구조체"""
    task_id: int
    task_type_id: int
    is_completed: bool

class Offsets:
    """메모리 오프셋 상수"""
    # TypeInfo RVA
    PC_TYPEINFO_RVA = 0x29861fc
    NPI_TYPEINFO_RVA = 0x29B7DD8
    GAMEDATA_TYPEINFO_RVA = 0x29933B0
    LIST_NPI_TYPEINFO_RVA = 0x298ECBC
    LIST_TASKINFO_TYPEINFO_RVA = 0x2994A70
    
    # 기본 오프셋
    IL2CPPCLASS_STATIC_FIELDS_OFF = 0x5c
    OBJ_FIELDS_OFF_X86 = 0x8
    OBJ_FIELDS_OFF_X64 = 0x10
    IL2CPP_ARRAY_VECTOR_OFF_X86 = 0x10
    IL2CPP_ARRAY_VECTOR_OFF_X64 = 0x20
    
    # PlayerControl
    PC_STATIC_LOCALPLAYER_OFF = 0x0
    PC_FIELDS_NetTransform = 0x90
    
    # CustomNetworkTransform
    CNT_FIELDS_lastPosition = 0x3c
    CNT_FIELDS_lastPosSent = 0x44

class MemoryReader:
    """저수준 메모리 읽기 유틸리티"""
    
    def __init__(self, process_name: str = "Among Us.exe"):
        self.pm = pymem.Pymem(process_name)
        self.base = self._get_module_base("GameAssembly.dll")
        self.is_64 = self._detect_architecture()
    
    def _get_module_base(self, name: str) -> int:
        """모듈 기본 주소 가져오기"""
        mod = pymem.process.module_from_name(self.pm.process_handle, name)
        return mod.lpBaseOfDll
    
    def _detect_architecture(self) -> bool:
        """아키텍처 감지"""
        try:
            return pymem.process.is_64_bit(self.pm.process_handle)
        except Exception:
            return ctypes.sizeof(ctypes.c_void_p) == 8
    
    def read_ptr(self, addr: int) -> int:
        """포인터 읽기"""
        if self.is_64:
            return self.pm.read_ulonglong(addr)
        else:
            return self.pm.read_uint(addr)
    
    def read_u32(self, addr: int) -> int:
        """32비트 정수 읽기"""
        return self.pm.read_uint(addr)
    
    def read_u8(self, addr: int) -> int:
        """8비트 정수 읽기"""
        return self.pm.read_bytes(addr, 1)[0]
    
    def read_f32(self, addr: int) -> float:
        """32비트 실수 읽기"""
        return self.pm.read_float(addr)
    
    def read_int(self, addr: int) -> int:
        """정수 읽기"""
        return self.pm.read_int(addr)
    
    def close(self):
        """프로세스 핸들 닫기"""
        try:
            self.pm.close_process()
        except Exception:
            pass

class AmongUsDataService:
    """Among Us 데이터 서비스"""
    
    def __init__(self, process_name: str = "Among Us.exe", scan_interval: float = 0.1, debug: bool = False):
        self._class_cache = {}
        self._last_scan_time = 0.0
        self._scan_interval = max(0.01, float(scan_interval))  # 최소 10ms
        self._cached_players = []
        self._cached_local_player = None
        self._debug = bool(debug)
        self._process_name = process_name
        self.memory = None
        self.attach(process_name)
    
    def enable_debug(self, enabled: bool = True):
        """디버그 로그 활성화"""
        self._debug = enabled
    
    def set_scan_interval(self, seconds: float):
        """스캔 주기 설정(초 단위)"""
        try:
            self._scan_interval = max(0.01, float(seconds))
        except Exception:
            pass
    
    def is_attached(self) -> bool:
        """프로세스 연결 여부"""
        return self.memory is not None
    
    def attach(self, process_name: Optional[str] = None) -> bool:
        """프로세스에 연결 시도"""
        if process_name:
            self._process_name = process_name
        try:
            self.memory = MemoryReader(self._process_name)
            self._class_cache.clear()
            return True
        except Exception as e:
            self.memory = None
            self._debug_log(f"프로세스 연결 실패: {e}")
            return False
    
    def detach(self):
        """프로세스 연결 해제"""
        try:
            if self.memory:
                self.memory.close()
        finally:
            self.memory = None
    
    def _debug_log(self, message: str):
        """디버그 로그 출력"""
        if self._debug:
            print(f"[디버그] {message}")
    
    def _get_class_from_typeinfo(self, rva: int) -> int:
        """TypeInfo RVA로 클래스 포인터 가져오기 (캐시 사용)"""
        if rva in self._class_cache:
            return self._class_cache[rva]
        
        klass = self.memory.read_ptr(self.memory.base + rva)
        self._class_cache[rva] = klass
        return klass
    
    def _scan_fields_for_class(self, fields_base: int, span_bytes: int, target_klass: int) -> int:
        """필드 영역에서 특정 클래스 포인터 스캔"""
        step = 8 if self.memory.is_64 else 4
        end = fields_base + span_bytes
        
        for cur in range(fields_base, end, step):
            try:
                ptr = self.memory.read_ptr(cur)
                if ptr:
                    klass = self.memory.read_ptr(ptr)
                    if klass == target_klass:
                        return ptr
            except Exception:
                continue
        return 0
    
    def _scan_fields_for_ptr_value(self, fields_base: int, span_bytes: int, target_ptr: int) -> int:
        """필드 영역에서 특정 포인터 값 스캔"""
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
    
    def _get_local_player_ptr(self) -> int:
        """로컬 플레이어 포인터 가져오기"""
        try:
            typeinfo = self._get_class_from_typeinfo(Offsets.PC_TYPEINFO_RVA)
            if not typeinfo:
                return 0
            
            static_fields = self.memory.read_ptr(typeinfo + Offsets.IL2CPPCLASS_STATIC_FIELDS_OFF)
            if not static_fields:
                return 0
            
            return self.memory.read_ptr(static_fields + Offsets.PC_STATIC_LOCALPLAYER_OFF)
        except Exception:
            return 0
    
    def _get_player_position(self, player_control_ptr: int) -> Optional[Tuple[float, float]]:
        """플레이어 위치 가져오기"""
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
            
            # 위치가 (0,0)이면 lastPosSent를 사용
            if x == 0.0 and y == 0.0:
                x = self.memory.read_f32(cnt_fields + Offsets.CNT_FIELDS_lastPosSent + 0x0)
                y = self.memory.read_f32(cnt_fields + Offsets.CNT_FIELDS_lastPosSent + 0x4)
            
            return (x, y)
        except Exception:
            return None
    
    def _get_default_outfit_from_dict(self, dict_ptr: int) -> int:
        """딕셔너리에서 기본 아웃핏 가져오기"""
        if not dict_ptr:
            return 0
        
        try:
            fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
            dict_fields = dict_ptr + fields_off
            
            # Dictionary 필드: _entries, _count
            entries_arr = self.memory.read_ptr(dict_fields + (0x8 if self.memory.is_64 else 0x4))
            count = self.memory.read_int(dict_fields + (0x10 if self.memory.is_64 else 0x8))
            
            if not entries_arr or count <= 0:
                return 0
            
            # Il2Cpp 배열 벡터 오프셋
            vec_off = Offsets.IL2CPP_ARRAY_VECTOR_OFF_X64 if self.memory.is_64 else Offsets.IL2CPP_ARRAY_VECTOR_OFF_X86
            entries_base = entries_arr + vec_off
            entry_size = 0x18 if self.memory.is_64 else 0x10
            
            # 엔트리 스캔
            for i in range(min(count, 16)):
                entry_offset = entries_base + i * entry_size
                try:
                    hash_code = self.memory.read_u32(entry_offset + 0x0)
                    if ctypes.c_int(hash_code).value < 0:  # 빈 슬롯
                        continue
                    
                    key = self.memory.read_u32(entry_offset + 0x8)
                    if key == 0:  # Default outfit
                        return self.memory.read_ptr(entry_offset + (0x10 if self.memory.is_64 else 0x0C))
                except Exception:
                    continue
            
            return 0
        except Exception:
            return 0
    
    def _get_color_id_from_outfit(self, outfit_ptr: int) -> int:
        """아웃핏에서 ColorId 가져오기"""
        if not outfit_ptr:
            return -1
        
        try:
            fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
            outfit_fields = outfit_ptr + fields_off
            return self.memory.read_u32(outfit_fields + 0x0)
        except Exception:
            return -1
    
    def _get_player_color_id(self, npi_ptr: int) -> int:
        """NetworkedPlayerInfo에서 ColorId 가져오기 (안정적 방식)"""
        if not npi_ptr:
            return -1
        
        try:
            fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
            npi_fields = npi_ptr + fields_off
            
            # Outfits 딕셔너리 탐색 (실제 빌드에서는 +0x38 등에 위치)
            for offset in [0x38, 0x3C, 0x40, 0x44, 0x48] + list(range(0x30, 0x80, 8 if self.memory.is_64 else 4)):
                try:
                    outfits_dict = self.memory.read_ptr(npi_fields + offset)
                    if not outfits_dict:
                        continue
                    
                    # 딕셔너리 유효성 검증
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
        """모든 NetworkedPlayerInfo 객체 가져오기"""
        try:
            gd_klass = self._get_class_from_typeinfo(Offsets.GAMEDATA_TYPEINFO_RVA)
            if not gd_klass:
                return []
            
            gd_static = self.memory.read_ptr(gd_klass + Offsets.IL2CPPCLASS_STATIC_FIELDS_OFF)
            if not gd_static:
                return []
            
            gd = self.memory.read_ptr(gd_static + 0x0)  # GameData.Instance
            if not gd:
                return []
            
            gd_fields = gd + (Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86)
            list_npi_klass = self._get_class_from_typeinfo(Offsets.LIST_NPI_TYPEINFO_RVA)
            
            all_players_list = self._scan_fields_for_class(gd_fields, 0x400, list_npi_klass)
            if not all_players_list:
                return []
            
            # List<NetworkedPlayerInfo> 파싱
            list_fields = all_players_list + (Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86)
            items = self.memory.read_ptr(list_fields + 0x0)
            size = self.memory.read_int(list_fields + (0x8 if self.memory.is_64 else 0x4))
            
            if not items or size <= 0 or size > 32:
                return []
            
            vec_off = Offsets.IL2CPP_ARRAY_VECTOR_OFF_X64 if self.memory.is_64 else Offsets.IL2CPP_ARRAY_VECTOR_OFF_X86
            ptr_sz = 8 if self.memory.is_64 else 4
            
            players = []
            for i in range(size):
                npi = self.memory.read_ptr(items + vec_off + i * ptr_sz)
                if npi:
                    players.append(npi)
            
            return players
        except Exception:
            return []
    
    def _get_player_control_from_npi(self, npi_ptr: int) -> int:
        """NetworkedPlayerInfo에서 PlayerControl 가져오기"""
        if not npi_ptr:
            return 0
        
        try:
            fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
            npi_fields = npi_ptr + fields_off
            pc_klass = self._get_class_from_typeinfo(Offsets.PC_TYPEINFO_RVA)
            
            # _object 필드 스캔 (일반적으로 +0x50 근처)
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

    def _get_npi_by_player_id(self, player_id: int) -> int:
        """player_id로 NPI 포인터 찾기"""
        try:
            for npi in self._get_all_npi_objects():
                try:
                    fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
                    npi_fields = npi + fields_off
                    pid = self.memory.read_u8(npi_fields + 0x8)
                    if pid == player_id:
                        return npi
                except Exception:
                    continue
        except Exception:
            pass
        return 0

    def _get_tasks_list_from_npi(self, npi_ptr: int) -> int:
        """NPI에서 List<TaskInfo> 포인터 찾기"""
        if not npi_ptr:
            return 0
        try:
            list_taskinfo_klass = self._get_class_from_typeinfo(Offsets.LIST_TASKINFO_TYPEINFO_RVA)
            fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
            npi_fields = npi_ptr + fields_off
            return self._scan_fields_for_class(npi_fields, 0x400, list_taskinfo_klass)
        except Exception:
            return 0

    def _parse_tasks_from_list(self, list_ptr: int) -> List[TaskData]:
        """List<TaskInfo>를 파싱하여 TaskData 목록으로 변환"""
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
                    # 추정 레이아웃: u32 id @+0x0, u32 type @+0x4, bool completed @+{0x8,0xC,0x10}
                    tid = self.memory.read_u32(task_fields + 0x0)
                    ttype = self.memory.read_u32(task_fields + 0x4)
                    completed = None
                    for boff in (0x8, 0xC, 0x10):
                        try:
                            val = self.memory.read_u8(task_fields + boff)
                            if val in (0, 1):
                                completed = bool(val)
                                break
                        except Exception:
                            continue
                    if completed is None:
                        # 기본값으로 미완료 처리
                        completed = False
                    # 간단한 유효성 검사
                    if 0 <= tid < 1024 and 0 <= ttype < 1024:
                        tasks.append(TaskData(task_id=int(tid), task_type_id=int(ttype), is_completed=completed))
                except Exception:
                    continue
        except Exception:
            pass
        return tasks
    
    def _refresh_cache(self, force: bool = False):
        """캐시 새로고침 (주기적 호출)"""
        current_time = time.time()
        if not force and current_time - self._last_scan_time < self._scan_interval:
            return
        
        self._last_scan_time = current_time
        self._cached_players = []
        self._cached_local_player = None
        
        try:
            if not self.is_attached() and not self.attach():
                return
            # 로컬 플레이어 가져오기
            local_player_ptr = self._get_local_player_ptr()
            
            # 모든 플레이어 가져오기
            all_npi = self._get_all_npi_objects()
            
            for npi in all_npi:
                try:
                    # PlayerControl 가져오기
                    player_control = self._get_player_control_from_npi(npi)
                    if not player_control:
                        continue
                    
                    # 위치 가져오기
                    position = self._get_player_position(player_control)
                    if not position:
                        continue
                    
                    # ColorId 가져오기
                    color_id = self._get_player_color_id(npi)
                    if color_id < 0:
                        continue
                    
                    # PlayerId 가져오기
                    fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
                    npi_fields = npi + fields_off
                    player_id = self.memory.read_u8(npi_fields + 0x8)
                    
                    # 로컬 플레이어 확인
                    is_local = (player_control == local_player_ptr)
                    if is_local:
                        self._cached_local_player = player_id
                    
                    player_data = PlayerData(
                        player_id=player_id,
                        color_id=color_id,
                        color_name=ColorId.get_name(color_id),
                        position=position,
                        is_local_player=is_local,
                        last_update=current_time
                    )
                    
                    self._cached_players.append(player_data)
                    
                except Exception:
                    continue
            
            self._debug_log(f"캐시 새로고침: {len(self._cached_players)}명 플레이어")
            
        except Exception as e:
            self._debug_log(f"캐시 새로고침 실패: {e}")
    
    # 캐시 제어 (명시적 호출 전용)
    def rebuild_cache(self):
        """캐시 재구성 (명시적으로 호출)"""
        self._refresh_cache(force=True)

    def clear_cache(self):
        """캐시 비우기 (명시적으로 호출)"""
        self._cached_players.clear()
        self._cached_local_player = None
        self._last_scan_time = 0.0
    
    def get_tasks_for_player(self, player_id: int) -> List[TaskData]:
        """특정 플레이어의 태스크 목록 가져오기"""
        try:
            if not self.is_attached() and not self.attach():
                return []
            npi = self._get_npi_by_player_id(player_id)
            if not npi:
                return []
            tasks_list = self._get_tasks_list_from_npi(npi)
            if not tasks_list:
                return []
            return self._parse_tasks_from_list(tasks_list)
        except Exception as e:
            self._debug_log(f"태스크 조회 실패: {e}")
            return []
    
    def cleanup(self):
        """리소스 정리"""
        try:
            self._class_cache.clear()
            self._cached_players.clear()
            self._cached_local_player = None
            self.detach()
        except Exception:
            pass
    
    def __enter__(self):
        """컨텍스트 매니저 진입"""
        return self
    
    def __exit__(self, exc_type, exc, tb):
        """컨텍스트 매니저 종료"""
        self.cleanup()
    
    def __del__(self):
        """소멸자"""
        self.cleanup()


    # 조회 메서드 (자동 캐시 갱신)
    def get_player_by_id(self, player_id: int) -> Optional[PlayerData]:
        """ID로 플레이어 데이터 가져오기"""
        self._refresh_cache()
        for player in self._cached_players:
            if player.player_id == player_id:
                return player
        return None

    def get_player_by_color(self, color_id: Union[int, ColorId]) -> Optional[PlayerData]:
        """색상으로 플레이어 데이터 가져오기"""
        if isinstance(color_id, ColorId):
            color_id = color_id.value
        self._refresh_cache()
        for player in self._cached_players:
            if player.color_id == color_id:
                return player
        return None

    def get_local_player(self) -> Optional[PlayerData]:
        """로컬 플레이어 데이터 가져오기"""
        self._refresh_cache()
        for player in self._cached_players:
            if player.is_local_player:
                return player
        return None

    def get_local_player_id(self) -> Optional[int]:
        """로컬 플레이어 ID 가져오기"""
        self._refresh_cache()
        return self._cached_local_player

    def get_all_players(self) -> List[PlayerData]:
        """모든 플레이어 데이터 가져오기"""
        self._refresh_cache()
        return self._cached_players.copy()

    def get_players_by_color_name(self, color_name: str) -> List[PlayerData]:
        """색상 이름으로 플레이어 목록 가져오기"""
        self._refresh_cache()
        return [p for p in self._cached_players if p.color_name.lower() == color_name.lower()]

    def get_player_positions(self) -> Dict[int, Tuple[float, float]]:
        """모든 플레이어 위치 가져오기 (고성능)"""
        self._refresh_cache()
        return {p.player_id: p.position for p in self._cached_players}

    def get_color_mapping(self) -> Dict[int, str]:
        """플레이어 ID-색상 매핑 가져오기"""
        self._refresh_cache()
        return {p.player_id: p.color_name for p in self._cached_players}

    def get_player_count(self) -> int:
        """현재 플레이어 수 가져오기"""
        self._refresh_cache()
        return len(self._cached_players)

    def refresh(self, force: bool = False):
        """캐시를 즉시 새로고침"""
        self._refresh_cache(force=force)

    def get_snapshot(self) -> Tuple[float, List[PlayerData]]:
        """현재 스냅샷 가져오기 (타임스탬프, 플레이어 목록)"""
        self._refresh_cache()
        return (self._last_scan_time, self._cached_players.copy())


# 전역 서비스 인스턴스
_service_instance = None


def get_data_service() -> AmongUsDataService:
    """전역 데이터 서비스 인스턴스 가져오기 (싱글톤)"""
    global _service_instance
    if _service_instance is None:
        _service_instance = AmongUsDataService()
    return _service_instance

def reset_data_service():
    """전역 데이터 서비스 리셋"""
    global _service_instance
    if _service_instance is not None:
        _service_instance.cleanup()
        _service_instance = None


# --------------------- API 편의 함수 ---------------------------
# 로컬 플레이어
def get_local_player() -> Optional[PlayerData]:
    """로컬 플레이어 가져오기"""
    return get_data_service().get_local_player()


def get_local_player_id() -> Optional[int]:
    """로컬 플레이어 ID 가져오기"""
    return get_data_service().get_local_player_id()


def get_local_player_position() -> Optional[Tuple[float, float]]:
    """로컬 플레이어 위치 가져오기"""
    me = get_data_service().get_local_player()
    return me.position if me else None


# 모든 플레이어
def get_all_players() -> List[PlayerData]:
    """모든 플레이어 가져오기"""
    return get_data_service().get_all_players()


def get_player_by_id(player_id: int) -> Optional[PlayerData]:
    """ID로 플레이어 가져오기"""
    return get_data_service().get_player_by_id(player_id)


def get_player_by_color(color_id: Union[int, ColorId]) -> Optional[PlayerData]:
    """색상으로 플레이어 가져오기"""
    return get_data_service().get_player_by_color(color_id)


def get_all_player_positions() -> Dict[int, Tuple[float, float]]:
    """모든 플레이어 위치 가져오기 (고성능 편의 함수)"""
    return get_data_service().get_player_positions()
