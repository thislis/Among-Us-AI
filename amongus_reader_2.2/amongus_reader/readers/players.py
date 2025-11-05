from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Union
import time

from amongus_reader.service.data_service import AmongUsDataService, PlayerData, ColorId
from amongus_reader.core import Offsets


class PlayersReader:
    def __init__(self, ds: AmongUsDataService) -> None:
        self._ds = ds
        # Cached mapping of player_id -> PlayerControl pointer for fast per-call positions
        self._pc_by_pid: Dict[int, int] = {}
        self._last_pc_map_ts: float = 0.0
        self._pc_map_ttl: float = 1.0  # seconds
        self._pc_klass: Optional[int] = None
        self._last_known_count: int = 0

    def list_players(self) -> List[PlayerData]:
        return self._ds.get_all_players()

    def get_local_player(self) -> Optional[PlayerData]:
        return self._ds.get_local_player()

    def get_local_player_id(self) -> Optional[int]:
        return self._ds.get_local_player_id()

    def get_by_id(self, player_id: int) -> Optional[PlayerData]:
        return self._ds.get_player_by_id(player_id)

    def find_by_color(self, color_id: Union[int, ColorId]) -> Optional[PlayerData]:
        cid = color_id.value if isinstance(color_id, ColorId) else int(color_id)
        return self._ds.get_player_by_color(cid)

    def positions(self) -> Dict[int, Tuple[float, float]]:
        # Per-call fast path: reuse PlayerControl pointers and only read positions
        self._ensure_pc_map()
        out: Dict[int, Tuple[float, float]] = {}
        if not self._pc_by_pid:
            return out
        removed = 0
        for pid, pc_ptr in list(self._pc_by_pid.items()):
            try:
                if not self._verify_pc_ptr(pc_ptr):
                    self._pc_by_pid.pop(pid, None)
                    removed += 1
                    continue
                pos = self._ds._get_player_position(pc_ptr)
                if pos is not None:
                    out[pid] = pos
            except Exception:
                # If reading fails, drop this entry; it will be rebuilt on next map refresh
                self._pc_by_pid.pop(pid, None)
                removed += 1
        # Heuristics: if too many removed or count dropped significantly, rebuild immediately
        if removed >= 2 or (self._last_known_count and len(out) < max(1, self._last_known_count // 2)):
            self._rebuild_pc_map(force=True)
            # Try one more quick read if map rebuilt
            out.clear()
            for pid, pc_ptr in list(self._pc_by_pid.items()):
                try:
                    if not self._verify_pc_ptr(pc_ptr):
                        continue
                    pos = self._ds._get_player_position(pc_ptr)
                    if pos is not None:
                        out[pid] = pos
                except Exception:
                    continue
        self._last_known_count = len(out)
        return out

    def colors(self) -> Dict[int, str]:
        return self._ds.get_color_mapping()

    def count(self) -> int:
        return self._ds.get_player_count()

    # Internal helpers
    def _ensure_pc_map(self) -> None:
        now = time.time()
        if (now - self._last_pc_map_ts) < self._pc_map_ttl and self._pc_by_pid:
            return
        self._rebuild_pc_map(force=False)

    def _rebuild_pc_map(self, force: bool) -> None:
        now = time.time()
        try:
            if not self._ds.is_attached():
                self._ds.attach()
            fields_off = Offsets.OBJ_FIELDS_OFF_X64 if self._ds.memory and self._ds.memory.is_64 else Offsets.OBJ_FIELDS_OFF_X86
            new_map: Dict[int, int] = {}
            for npi in self._ds._get_all_npi_objects():
                try:
                    npi_fields = npi + fields_off
                    pid = self._ds.memory.read_u8(npi_fields + 0x8)
                    pc = self._ds._get_player_control_from_npi(npi)
                    if pid is not None and pc:
                        new_map[int(pid)] = int(pc)
                except Exception:
                    continue
            if new_map:
                self._pc_by_pid = new_map
                self._last_pc_map_ts = now
                # refresh klass cache lazily
                self._pc_klass = None
        except Exception:
            # leave old map if any
            pass

    def _verify_pc_ptr(self, pc_ptr: int) -> bool:
        try:
            if not pc_ptr or not self._ds.memory:
                return False
            if self._pc_klass is None:
                self._pc_klass = self._ds._get_class_from_typeinfo(Offsets.PC_TYPEINFO_RVA)
            k = self._ds.memory.read_ptr(pc_ptr)
            return bool(k and self._pc_klass and k == self._pc_klass)
        except Exception:
            return False

    # External controls
    def invalidate_pc_map(self) -> None:
        self._pc_by_pid.clear()
        self._last_pc_map_ts = 0.0
        self._pc_klass = None
        self._last_known_count = 0

    def configure(self, pc_map_ttl: Optional[float] = None) -> None:
        if pc_map_ttl is not None:
            try:
                self._pc_map_ttl = max(0.1, float(pc_map_ttl))
            except Exception:
                pass
