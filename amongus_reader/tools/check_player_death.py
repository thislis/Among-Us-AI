"""
다른 플레이어의 사망 여부를 읽는 예제 코드

이 스크립트는 AmongUsReader를 사용하여 모든 플레이어의 사망 여부를 확인합니다.
color_id 기반으로 플레이어를 찾고, 여러 방법을 시도하여 사망 여부를 읽습니다.

사용 예제:
    # 한 번만 확인
    python tools/check_player_death.py --once
    
    # 주기적으로 모니터링
    python tools/check_player_death.py
    
    # 특정 color_id의 플레이어만 확인
    python tools/check_player_death.py --once --color-id 0

코드에서 사용하는 방법:
    from tools.check_player_death import get_player_death_status
    from amongus_reader.service import AmongUsReader
    
    reader = AmongUsReader()
    reader.attach()
    try:
        is_dead, diag = get_player_death_status(reader._ds, color_id=0)
        if is_dead is True:
            print("플레이어가 사망했습니다")
        elif is_dead is False:
            print("플레이어가 생존했습니다")
        else:
            print(f"읽기 실패: {diag.get('error')}")
    finally:
        reader.detach()
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from amongus_reader.service import AmongUsReader
from amongus_reader.service.data_service import AmongUsDataService, PlayerData
from amongus_reader.core import Offsets


# Role type metadata (extracted from Il2Cpp enum definitions)
ROLE_TYPE_NAMES: Dict[int, str] = {
    0x0000: "Crewmate",
    0x0001: "Impostor",
    0x0002: "Scientist",
    0x0003: "Engineer",
    0x0004: "GuardianAngel",
    0x0005: "Shapeshifter",
    0x0006: "CrewmateGhost",
    0x0007: "ImpostorGhost",
    0x0008: "Noisemaker",
    0x0009: "Phantom",
    0x000A: "Tracker",
    0x000C: "Detective",
    0x0012: "Viper",
}

# Known value ranges for role types (allow room for newer roles)
ROLE_TYPE_KNOWN_VALUES = set(ROLE_TYPE_NAMES.keys()) | set(range(0, 0x20))
ROLE_TYPE_DEAD_VALUES = {0x0004, 0x0006, 0x0007}
ROLE_TYPE_IMPOSTOR_VALUES = {0x0001, 0x0005, 0x0007}

# Offset caches (per architecture) to avoid repeated scans
_ROLE_OFFSET_CACHE: Dict[bool, Optional[int]] = {}


def _read_u16(ds: AmongUsDataService, addr: int) -> int:
    """MemoryClient helper: 읽기 전용 16비트 값."""
    lo = ds.memory.read_u8(addr)
    hi = ds.memory.read_u8(addr + 1)
    return lo | (hi << 8)


def _detect_role_offset(
    ds: AmongUsDataService,
    npi_map: Dict[int, int],
    fields_off: int,
) -> Optional[int]:
    """NetworkedPlayerInfo RoleType 필드 오프셋을 동적으로 식별합니다."""
    if not npi_map:
        return None
    key = bool(ds.memory.is_64)
    cached = _ROLE_OFFSET_CACHE.get(key)
    if cached is not None:
        return cached

    def validate_candidate(offset: int) -> bool:
        try:
            values = []
            for npi in npi_map.values():
                val = _read_u16(ds, npi + fields_off + offset)
                if val not in ROLE_TYPE_KNOWN_VALUES:
                    return False
                values.append(val)
        except Exception:
            return False

        if len(values) < 2:
            return False

        unique_vals = set(values)
        if len(unique_vals) <= 1:
            return False

        return True

    # 64비트에서는 구조가 비교적 안정적이며 0x30이 RoleType이다.
    preferred_offsets = [0x30] if key else [0x24]
    for offset in preferred_offsets:
        if validate_candidate(offset):
            _ROLE_OFFSET_CACHE[key] = offset
            return offset

    # RoleType은 2바이트 enum. 0x24~0x80 구간을 추가 검사.
    search_range = range(0x24, 0x80, 2)

    for offset in search_range:
        if offset in preferred_offsets:
            continue
        if validate_candidate(offset):
            _ROLE_OFFSET_CACHE[key] = offset
            return offset

    _ROLE_OFFSET_CACHE[key] = None
    return None


def get_player_death_status(
    ds: AmongUsDataService,
    color_id: int,
) -> Tuple[Optional[bool], Dict[str, any]]:
    """주어진 color_id 플레이어의 사망 여부를 추론합니다."""

    diag: Dict[str, any] = {}

    try:
        if not ds.is_attached() and not ds.attach():
            diag["error"] = "not attached"
            return (None, diag)

        if not ds.memory:
            diag["error"] = "memory unavailable"
            return (None, diag)

        player = ds.get_player_by_color(color_id)
        if not player:
            diag["error"] = f"player with color_id {color_id} not found"
            return (None, diag)

        diag["color_id"] = color_id
        diag["color_name"] = player.color_name
        diag["player_id"] = player.player_id

        npi = ds._get_npi_by_color_id(color_id)
        if not npi:
            diag["error"] = "NPI not found"
            return (None, diag)

        diag["npi_ptr"] = npi

        pc_ptr = ds._get_player_control_from_npi(npi)
        diag["pc_ptr"] = pc_ptr or 0

        is64 = bool(ds.memory.is_64)
        fields_off = Offsets.OBJ_FIELDS_OFF_X64 if is64 else Offsets.OBJ_FIELDS_OFF_X86
        ptr_sz = 8 if is64 else 4

        # 1) CachedPlayerData 접근 시도 (로컬 플레이어 전용)
        cached_ptr = 0
        if pc_ptr:
            try:
                cached_ptr = ds._get_cached_playerdata_ptr(pc_ptr)
            except Exception:
                cached_ptr = 0

        if cached_ptr:
            try:
                base = cached_ptr + fields_off
                is_dead_offset = ptr_sz * 2 + 2
                raw = ds.memory.read_u8(base + is_dead_offset)
                if raw in (0, 1):
                    diag.update(
                        {
                            "method": "CachedPlayerData",
                            "cached_playerdata_ptr": cached_ptr,
                            "is_dead_offset": is_dead_offset,
                            "is_dead_raw": int(raw),
                        }
                    )
                    return (bool(raw), diag)
            except Exception:
                diag["cached_playerdata_error"] = "read_failed"

        # 2) RoleType 기반 추론 (NetworkedPlayerInfo)
        #    모든 플레이어의 NPI를 수집하여 RoleType 필드를 동적으로 찾는다.
        npi_map: Dict[int, int] = {}
        try:
            for p in ds.get_all_players() or []:
                npi_ptr = ds._get_npi_by_color_id(p.color_id)
                if npi_ptr:
                    npi_map[p.color_id] = npi_ptr
        except Exception:
            # fallback: 최소한 타겟만이라도 포함
            npi_map[color_id] = npi

        if color_id not in npi_map:
            npi_map[color_id] = npi

        role_offset = _detect_role_offset(ds, npi_map, fields_off)

        role_types: Dict[int, int] = {}
        if role_offset is not None:
            for cid, npi_ptr in npi_map.items():
                try:
                    role_types[cid] = _read_u16(ds, npi_ptr + fields_off + role_offset)
                except Exception:
                    continue

        if role_types:
            diag["role_offset"] = role_offset
            role_value = role_types.get(color_id)
            if role_value is not None:
                role_label = ROLE_TYPE_NAMES.get(role_value, f"Unknown({role_value})")
                diag["role_type"] = int(role_value)
                diag["role_type_label"] = role_label

                dead_set = {cid for cid, v in role_types.items() if v in ROLE_TYPE_DEAD_VALUES}
                impostor_set = {
                    cid
                    for cid, v in role_types.items()
                    if (v in ROLE_TYPE_IMPOSTOR_VALUES) and (v not in ROLE_TYPE_DEAD_VALUES)
                }

                diag["dead_role_colors"] = sorted(dead_set)
                diag["impostor_role_colors"] = sorted(impostor_set)
                diag["role_snapshot"] = {
                    cid: ROLE_TYPE_NAMES.get(v, str(v)) for cid, v in role_types.items()
                }

                is_dead_via_role = role_value in ROLE_TYPE_DEAD_VALUES
                diag["method"] = "RoleType_inference"

                # 참고용: RoleType과 bool 플래그가 불일치할 경우 경고를 남긴다.
                try:
                    # 후보 bool 필드 하나를 빠르게 검사 (주요 후보 0xE8)
                    quick_flag = ds.memory.read_u8(npi + fields_off + 0xE8)
                    if quick_flag in (0, 1):
                        diag["flag_0xE8"] = int(quick_flag)
                        if bool(quick_flag) != is_dead_via_role:
                            diag.setdefault("warnings", []).append(
                                "flag_0xE8 mismatch"
                            )
                except Exception:
                    pass

                return (is_dead_via_role, diag)

        # 3) RoleType을 찾지 못한 경우: NPI bool heuristic (최후의 수단)
        candidate_offsets = [
            0x34,
            0x4C,
            0xE8,
            0xF0,
        ]
        npi_fields = npi + fields_off
        for offset in candidate_offsets:
            try:
                val = ds.memory.read_u8(npi_fields + offset)
                if val in (0, 1):
                    diag["method"] = "NPI_bool_fallback"
                    diag["npi_offset"] = offset
                    diag["is_dead_raw"] = int(val)
                    diag["note"] = "heuristic fallback - verify manually"
                    return (bool(val), diag)
            except Exception:
                continue

        diag["error"] = "could not determine death status"
        return (None, diag)

    except Exception as exc:
        diag["error"] = str(exc)
        return (None, diag)


def main():
    """모든 플레이어의 사망 여부를 주기적으로 출력합니다."""
    reader = AmongUsReader(process_name="Among Us.exe", debug=False)
    
    if not reader.attach():
        print("❌ Among Us 프로세스에 연결 실패")
        print("게임이 실행 중인지 확인하세요.")
        return
    
    print("✅ 프로세스 연결 성공\n")
    print("플레이어 사망 여부 모니터링 시작 (Ctrl+C로 종료)\n")
    
    try:
        while True:
            players = reader.list_players()
            if not players:
                print("플레이어를 찾을 수 없습니다...")
                time.sleep(1.0)
                continue
            
            print(f"\n[{time.strftime('%H:%M:%S')}] 플레이어 사망 여부 ({len(players)}명)")
            print("-" * 60)
            print(f"{'ColorID':<8} | {'PlayerID':<8} | {'Color Name':<12} | {'Status':<10} | {'Local'}")
            print("-" * 60)
            
            for player in players:
                is_dead, diag = get_player_death_status(reader._ds, player.color_id)
                
                color_id_str = str(player.color_id)
                player_id_str = str(player.player_id)
                color_name = player.color_name
                local_flag = "Yes" if player.is_local_player else "No"
                
                if is_dead is None:
                    status = f"Unknown ({diag.get('error', 'N/A')})"
                elif is_dead:
                    status = "💀 DEAD"
                else:
                    status = "❤️ ALIVE"
                
                print(f"{color_id_str:<8} | {player_id_str:<8} | {color_name:<12} | {status:<10} | {local_flag}")
            
            time.sleep(1.0)
            
    except KeyboardInterrupt:
        print("\n\n모니터링 종료")
    finally:
        reader.detach()
        print("프로세스 연결 해제 완료")


def example_single_player():
    """특정 플레이어의 사망 여부를 한 번만 확인하는 예제"""
    reader = AmongUsReader(process_name="Among Us.exe", debug=False)
    
    if not reader.attach():
        print("❌ Among Us 프로세스에 연결 실패")
        return
    
    try:
        # 모든 플레이어 목록 가져오기
        players = reader.list_players()
        if not players:
            print("플레이어를 찾을 수 없습니다.")
            return
        
        print("플레이어 목록:")
        for i, p in enumerate(players):
            print(f"  {i+1}. {p.color_name} (color_id: {p.color_id}, player_id: {p.player_id})")
        
        # 모든 플레이어의 사망 여부 확인
        print(f"\n모든 플레이어의 사망 여부:")
        print("-" * 60)
        print(f"{'ColorID':<8} | {'PlayerID':<8} | {'Color Name':<12} | {'Status':<10}")
        print("-" * 60)
        
        for player in players:
            is_dead, diag = get_player_death_status(reader._ds, player.color_id)
            
            color_id_str = str(player.color_id)
            player_id_str = str(player.player_id)
            color_name = player.color_name
            
            if is_dead is None:
                status = f"Unknown ({diag.get('error', 'N/A')[:20]})"
            elif is_dead:
                status = "💀 DEAD"
            else:
                status = "❤️ ALIVE"
            
            print(f"{color_id_str:<8} | {player_id_str:<8} | {color_name:<12} | {status}")
        
        # 첫 번째 플레이어의 상세 진단 정보 출력
        if players:
            target_player = players[0]
            print(f"\n{target_player.color_name} (color_id: {target_player.color_id})의 상세 진단 정보:")
            is_dead, diag = get_player_death_status(reader._ds, target_player.color_id)
            
            if diag:
                for key, value in diag.items():
                    if key != "error":
                        print(f"  {key}: {value}")
        
    finally:
        reader.detach()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="플레이어 사망 여부 확인 도구")
    parser.add_argument(
        "--once",
        action="store_true",
        help="한 번만 확인하고 종료 (기본값: 주기적으로 모니터링)"
    )
    parser.add_argument(
        "--color-id",
        type=int,
        help="특정 color_id의 플레이어만 확인"
    )
    
    args = parser.parse_args()
    
    if args.once:
        if args.color_id is not None:
            # 특정 color_id만 확인
            reader = AmongUsReader(process_name="Among Us.exe", debug=False)
            if reader.attach():
                try:
                    is_dead, diag = get_player_death_status(reader._ds, args.color_id)
                    player = reader.get_player(args.color_id)
                    if player:
                        print(f"{player.color_name} (color_id: {args.color_id}): ", end="")
                    if is_dead is None:
                        print(f"Unknown - {diag.get('error', 'N/A')}")
                    elif is_dead:
                        print("💀 DEAD")
                    else:
                        print("❤️ ALIVE")
                finally:
                    reader.detach()
        else:
            example_single_player()
    else:
        main()

