from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from ..cache.manager import CacheManager
from .data_service import AmongUsDataService, PlayerData, TaskData, ColorId
from ..readers.players import PlayersReader
from ..readers.tasks import TasksReader
from ..readers.hud import HudReader
from ..readers.session import SessionReader


class AmongUsReader:
    def __init__(
        self,
        process_name: str = "Among Us.exe",
        debug: bool = False,
        cache_ttl_overrides: Optional[Dict[str, float]] = None,
        hud_min_interval: float = 1.5,
        hud_time_budget: float = 0.10,
        players_pc_map_ttl: float = 1.0,
    ) -> None:
        self._ds = AmongUsDataService(process_name=process_name, debug=debug)
        self._players = PlayersReader(self._ds)
        self._players.configure(pc_map_ttl=players_pc_map_ttl)
        self._tasks = TasksReader(self._ds)
        self._hud = HudReader(self._ds, min_interval=hud_min_interval, time_budget=hud_time_budget)
        self._session = SessionReader(self._ds)
        ttl_defaults: Dict[str, float] = {
            "players": 0.15,
            "colors": 1.0,
            "tasks": 3.0,
            "hud": 1.5,
            "session": 0.5,
        }
        if cache_ttl_overrides:
            ttl_defaults.update({str(k).strip().lower(): float(v) for k, v in cache_ttl_overrides.items()})
        self._cache = CacheManager(ttl_defaults)

    # Session
    def attach(self, process_name: Optional[str] = None) -> bool:
        return self._ds.attach(process_name)

    def detach(self) -> None:
        self._ds.detach()

    def is_attached(self) -> bool:
        return self._ds.is_attached()

    def enable_debug(self, enabled: bool = True) -> None:
        self._ds.enable_debug(enabled)

    # Cache
    def refresh(self, types: Optional[Iterable[str]] = None, force: bool = False) -> None:
        if not types:
            self._cache.invalidate(None)
            self._ds.refresh(force=force)
            return
        # Refresh only requested types; rely on DS to have latest when needed.
        for t in types:
            typ = str(t or "").strip().lower()
            if typ == "players":
                players = self._players.list_players()
                self._cache.set("players", players)
            elif typ == "colors":
                colors = self._players.colors()
                self._cache.set("colors", colors)
            elif typ == "hud":
                status = self._hud.is_report_active()
                self._cache.set("hud", status, subkey="report")
            elif typ == "tasks":
                # tasks are keyed per player; cannot bulk refresh safely
                self._cache.invalidate(["tasks"])  # fall back to lazy fetch
            else:
                pass
        if force:
            self._ds.refresh(force=True)

    def invalidate(self, types: Optional[Iterable[str]] = None) -> None:
        self._cache.invalidate(types)

    def snapshot(self, types: Optional[Iterable[str]] = None) -> Dict[str, Dict[Optional[Any], Any]]:
        return self._cache.snapshot(types)

    # Configuration helpers
    def configure_hud(self, min_interval: Optional[float] = None, time_budget: Optional[float] = None) -> None:
        self._hud.configure(min_interval=min_interval, time_budget=time_budget)

    def configure_players(self, pc_map_ttl: Optional[float] = None) -> None:
        self._players.configure(pc_map_ttl=pc_map_ttl)

    def invalidate_players_pc_map(self) -> None:
        self._players.invalidate_pc_map()

    # Players
    def list_players(self) -> List[PlayerData]:
        cached = self._cache.get("players")
        if cached is not None:
            return cached
        players = self._players.list_players()
        self._cache.set("players", players)
        return players

    def get_local_player(self) -> Optional[PlayerData]:
        players = self._cache.get("players")
        if players is None:
            # Avoid forcing a full list refresh; use DS direct path
            return self._players.get_local_player()
        for p in players:
            if getattr(p, "is_local_player", False):
                return p
        return None

    def get_local_player_id(self) -> Optional[int]:
        # Use DS fast path; avoids requiring list refresh
        return self._players.get_local_player_id()

    def get_player(self, player_id: int) -> Optional[PlayerData]:
        players = self._cache.get("players")
        if players is not None:
            for p in players:
                if p.player_id == player_id:
                    return p
        return self._players.get_by_id(player_id)

    def find_player_by_color(self, color_id: Union[int, ColorId]) -> Optional[PlayerData]:
        # Normalize ColorId
        cid = color_id.value if isinstance(color_id, ColorId) else int(color_id)
        players = self._cache.get("players")
        if players is not None:
            for p in players:
                if p.color_id == cid:
                    return p
        return self._players.find_by_color(cid)

    def positions(self) -> Dict[int, Tuple[float, float]]:
        return self._players.positions()

    def colors(self) -> Dict[int, str]:
        cached = self._cache.get("colors")
        if cached is not None:
            return cached
        colors = self._players.colors()
        self._cache.set("colors", colors)
        return colors

    def count(self) -> int:
        players = self._cache.get("players")
        if players is not None:
            return len(players)
        return self._players.count()

    # Tasks
    def get_tasks(self, player_id: int) -> List[TaskData]:
        cached = self._cache.get("tasks", subkey=player_id)
        if cached is not None:
            return cached
        tasks = self._tasks.get_tasks(player_id)
        self._cache.set("tasks", tasks, subkey=player_id)
        return tasks

    # HUD / Report
    def is_report_active(self) -> Tuple[Optional[bool], Dict[str, Any]]:
        cached = self._cache.get("hud", subkey="report")
        if cached is not None:
            return cached
        status = self._hud.is_report_active()
        self._cache.set("hud", status, subkey="report")
        return status

    # Session / Map state
    def get_session_state(self) -> str:
        cached = self._cache.get("session", subkey="state")
        if cached is not None:
            return str(cached)
        s = self._session.state()
        self._cache.set("session", s, subkey="state")
        return s

    def get_current_map_name(self) -> str:
        s = self.get_session_state()
        if s == "SHIP":
            return "SHIP"
        return s
