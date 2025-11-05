from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from amongus_reader.core.offsets import Offsets
from amongus_reader.service.data_service import AmongUsDataService


_SHIP_STATUS_TYPES = (
    "skeldshipstatus",
    "mirashipstatus",
    "polusshipstatus",
    "airshipstatus",
    "fungleshipstatus",
)

_SHIP_STATUS_LABELS: Dict[str, str] = {
    "skeldshipstatus": "SKELD",
    "mirashipstatus": "MIRA",
    "polusshipstatus": "POLUS",
    "airshipstatus": "AIRSHIP",
    "fungleshipstatus": "FUNGLE",
}

_LOBBY_UI_TYPES = (
    "creategameoptions",
    "gameoptionsmappicker",
    "gamesettingmenu",
)


@dataclass
class SessionSignals:
    lobby_ui_present: bool = False
    local_player_ptr: int = 0
    local_player_id: Optional[int] = None
    npi_count: int = 0
    any_pc: bool = False
    any_pc_pos: bool = False
    any_clientdata: bool = False
    hud_ptr: int = 0
    ship_status_hits: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    player_ids: List[int] = field(default_factory=list)
    client_slots: List[int] = field(default_factory=list)
    gamedata_first_int: Optional[int] = None
    gamedata_state_int: Optional[int] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "lobby_ui_present": self.lobby_ui_present,
            "local_player_ptr": hex(self.local_player_ptr) if self.local_player_ptr else 0,
            "local_player_id": self.local_player_id,
            "npi_count": self.npi_count,
            "any_pc": self.any_pc,
            "any_pc_pos": self.any_pc_pos,
            "any_clientdata": self.any_clientdata,
            "hud_ptr": hex(self.hud_ptr) if self.hud_ptr else 0,
            "ship_status_hits": list(self.ship_status_hits),
            "errors": list(self.errors),
            "player_ids": list(self.player_ids),
            "client_slots": list(self.client_slots),
            "gamedata_first_int": self.gamedata_first_int,
            "gamedata_state_int": self.gamedata_state_int,
        }


class SessionReader:
    """Derives coarse session state (LOBBY/MATCHING/SHIP) without Unity icalls."""

    _SCAN_TIME_BUDGET = 0.35

    def __init__(self, ds: AmongUsDataService) -> None:
        self._ds = ds

    # ---------------------------------------------------------------------
    # Public API
    def state(self) -> str:
        signals = self._collect_signals()
        return self._classify_state(signals)

    def map_name(self) -> str:
        state, signals = self.snapshot()
        if state != "SHIP":
            return state
        label = self._map_name_from_signals(signals)
        return label or state

    def snapshot(self) -> Tuple[str, SessionSignals]:
        signals = self._collect_signals()
        return self._classify_state(signals), signals

    # ------------------------------------------------------------------
    # Internals
    def _collect_signals(self) -> SessionSignals:
        if not self._ds.is_attached():
            self._ds.attach()

        signals = SessionSignals()
        time_budget_end = time.time() + self._SCAN_TIME_BUDGET

        self._check_lobby_ui(signals, time_budget_end)
        self._gather_player_signals(signals)
        gamedata_ints = self._read_gamedata_ints()
        if gamedata_ints:
            if len(gamedata_ints) > 0:
                signals.gamedata_first_int = gamedata_ints[0]
            if len(gamedata_ints) > 4:
                signals.gamedata_state_int = gamedata_ints[4]
        self._check_hud_and_ship_status(signals, time_budget_end)
        return signals

    def _check_lobby_ui(self, signals: SessionSignals, time_budget_end: float) -> None:
        for tname in _LOBBY_UI_TYPES:
            if time.time() > time_budget_end:
                break
            klass = self._get_class_from_dotnet(tname)
            if not klass:
                continue
            try:
                insts = self._ds._scan_heap_for_class_instances(klass, limit=1, time_budget_end=time_budget_end)
            except Exception:
                insts = []
            if insts:
                signals.lobby_ui_present = True
                break

    def _gather_player_signals(self, signals: SessionSignals) -> None:
        signals.player_ids.clear()
        signals.client_slots.clear()
        try:
            signals.local_player_ptr = self._ds._get_local_player_ptr()
        except Exception as exc:
            signals.errors.append(f"local_player_error:{exc}")
            signals.local_player_ptr = 0

        try:
            npi_objects = self._ds._get_all_npi_objects()
        except Exception as exc:
            signals.errors.append(f"npi_error:{exc}")
            npi_objects = []

        signals.npi_count = len(npi_objects)
        if not npi_objects:
            return

        for npi in npi_objects:
            try:
                pc_ptr = self._ds._get_player_control_from_npi(npi)
            except Exception:
                pc_ptr = 0
            if pc_ptr:
                signals.any_pc = True
                try:
                    pos = self._ds._get_player_position(pc_ptr)
                except Exception:
                    pos = None
                if pos:
                    x, y = float(pos[0]), float(pos[1])
                    if abs(x) > 1e-5 or abs(y) > 1e-5:
                        signals.any_pc_pos = True
            if not signals.any_clientdata:
                try:
                    if self._ds._npi_has_clientdata(npi):
                        signals.any_clientdata = True
                except Exception:
                    pass
            pid = None
            try:
                fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self._ds.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
                pid = self._ds.memory.read_u8(npi + fields_off + 0x8)
            except Exception:
                pid = None
            if pid is not None:
                signals.player_ids.append(int(pid))
                if pc_ptr and pc_ptr == signals.local_player_ptr:
                    signals.local_player_id = int(pid)
            client_slot = None
            try:
                fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self._ds.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
                client_slot = self._ds.memory.read_u32(npi + fields_off + 0x20)
            except Exception:
                client_slot = None
            if client_slot is not None:
                signals.client_slots.append(int(client_slot))
            if signals.any_pc_pos and signals.any_clientdata:
                break

    def _check_hud_and_ship_status(self, signals: SessionSignals, time_budget_end: float) -> None:
        try:
            signals.hud_ptr = self._ds._get_hudmanager_instance_ptr()
        except Exception as exc:
            signals.errors.append(f"hud_error:{exc}")
            signals.hud_ptr = 0

        hits: List[str] = []
        for tname in _SHIP_STATUS_TYPES:
            if time.time() > time_budget_end:
                break
            klass = self._get_class_from_dotnet(tname)
            if not klass:
                continue
            try:
                insts = self._ds._scan_heap_for_class_instances(klass, limit=1, time_budget_end=time_budget_end)
            except Exception:
                insts = []
            if insts:
                hits.append(tname)
                break
        signals.ship_status_hits = hits

    def _read_gamedata_ints(self, count: int = 8) -> Optional[List[int]]:
        try:
            inst = self._resolve_gamedata_instance()
            if not inst:
                return None
            fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self._ds.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
            blob = self._ds.memory.read_bytes(inst + fields_off, count * 4)
            ints = [int.from_bytes(blob[i : i + 4], "little", signed=False) for i in range(0, len(blob), 4)]
            return ints
        except Exception:
            return None

    def _resolve_gamedata_instance(self) -> int:
        gd_klass = self._ds._get_class_from_typeinfo(Offsets.GAMEDATA_TYPEINFO_RVA) or self._get_class_from_dotnet("gamedata")
        if not gd_klass:
            return 0
        candidates: List[int] = []
        try:
            ptr = self._ds.memory.read_ptr(gd_klass + Offsets.IL2CPPCLASS_STATIC_FIELDS_OFF)
            if ptr:
                candidates.append(ptr)
        except Exception:
            pass
        try:
            ptr2 = self._ds._get_static_fields_ptr(gd_klass)
            if ptr2 and ptr2 not in candidates:
                candidates.append(ptr2)
        except Exception:
            pass
        for cand in candidates:
            try:
                inst = self._ds.memory.read_ptr(cand)
                if inst:
                    return inst
            except Exception:
                continue
        return 0

    def _classify_state(self, signals: SessionSignals) -> str:
        if signals.lobby_ui_present:
            return "LOBBY"
        if signals.local_player_ptr == 0:
            return "LOBBY"

        joined_room = signals.any_pc or signals.npi_count > 1 or signals.any_clientdata
        game_first = signals.gamedata_first_int
        if game_first is not None:
            if game_first == 0:
                return "LOBBY"
            joined_room = True

        slot_counts = Counter(sl for sl in signals.client_slots if sl >= 0)
        unique_slots = sum(1 for count in slot_counts.values() if count >= 1)
        if unique_slots >= 2:
            joined_room = True
        elif game_first is None:
            return "LOBBY"

        valid_ids = [pid for pid in signals.player_ids if 0 <= pid < 255]
        id_counts = Counter(valid_ids)
        if id_counts:
            repeated = any(count > 1 for count in id_counts.values())
            if len(id_counts) == 1 and repeated and not signals.any_clientdata and unique_slots <= 1 and not (game_first and game_first != 0):
                return "LOBBY"
        elif game_first is None:
            return "LOBBY"

        if not joined_room:
            return "LOBBY"

        gamestate_started = bool(signals.gamedata_state_int)
        if gamestate_started and signals.any_pc_pos:
            return "SHIP"
        if signals.hud_ptr and signals.any_pc_pos:
            return "SHIP"
        if signals.ship_status_hits and signals.any_pc_pos:
            return "SHIP"
        return "MATCHING"

    def _map_name_from_signals(self, signals: SessionSignals) -> Optional[str]:
        for key in signals.ship_status_hits:
            label = _SHIP_STATUS_LABELS.get(key)
            if label:
                return label
        return None

    def _get_class_from_dotnet(self, name: str) -> int:
        try:
            return self._ds._get_class_from_dotnet(name)
        except Exception:
            return 0


__all__ = ["SessionReader", "SessionSignals"]

