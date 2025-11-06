from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple, Union
from collections import Counter

from ..cache.manager import CacheManager
from .data_service import AmongUsDataService, PlayerData, TaskData, ColorId
from ..readers.players import PlayersReader
from ..readers.tasks import TasksReader
from ..readers.hud import HudReader
from ..readers.session import SessionReader
from .task_lookup import TaskPanelEntry, format_task_entry


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
            "local_role": 0.3,
            "session": 0.3,
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
            elif typ == "local_role":
                result = self._ds.get_local_impostor_flag()
                self._cache.set("local_role", result, subkey="impostor")
            elif typ == "session":
                state = self._session.state()
                self._cache.set("session", state, subkey="state")
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

    # Roles / impostor
    def is_local_impostor(self) -> Tuple[Optional[bool], Dict[str, Any]]:
        cached = self._cache.get("local_role", subkey="impostor")
        if cached is not None:
            return cached
        result = self._ds.get_local_impostor_flag()
        self._cache.set("local_role", result, subkey="impostor")
        return result

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

    def get_player(self, color_id: Union[int, ColorId]) -> Optional[PlayerData]:
        return self.find_player_by_color(color_id)

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
    def get_tasks(self, color_id: Union[int, ColorId]) -> List[TaskData]:
        # Normalize ColorId
        cid = color_id.value if isinstance(color_id, ColorId) else int(color_id)
        cached = self._cache.get("tasks", subkey=cid)
        if cached is not None:
            return cached
        tasks = self._tasks.get_tasks(color_id)
        self._cache.set("tasks", tasks, subkey=cid)
        return tasks

    def get_task_panel(
        self,
        color_id: Optional[Union[int, ColorId]] = None,
        *,
        include_completed: bool = False,
    ) -> List[TaskPanelEntry]:
        if color_id is None:
            # Get local player's color_id
            local_player = self.get_local_player()
            if local_player is None:
                return []
            color_id = local_player.color_id
        tasks = self.get_tasks(color_id)
        if not tasks:
            return []
        totals = Counter(t.task_type_id for t in tasks)
        completed_counts = Counter(t.task_type_id for t in tasks if t.is_completed)
        panel: List[TaskPanelEntry] = []
        for task in tasks:
            if task.is_completed and not include_completed:
                continue
            entry = format_task_entry(task, totals, completed_counts)
            panel.append(entry)
        return panel

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
        state = self._session.state()
        self._cache.set("session", state, subkey="state")
        return state

    def get_session_snapshot(self) -> Tuple[str, Dict[str, Any]]:
        state, signals = self._session.snapshot()
        self._cache.set("session", state, subkey="state")
        return state, signals.to_dict()

    def get_current_map_name(self) -> str:
        state = self.get_session_state()
        if state == "SHIP":
            name = self._session.map_name()
            if name:
                return name
        return state

