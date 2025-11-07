import os
import sys
import math
import time
import pickle
import atexit
from typing import List, Tuple, Optional

import networkx as nx
import pyautogui

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from amongus_reader.service import AmongUsReader

_LOCAL_GRAPHS_DIR = os.path.join(os.path.dirname(__file__), "graphs")


class GraphManager:
    def __init__(self, local_dir: str):
        self.local_dir = local_dir
        self._cache = {}

    def _nx_path(self, base: str, map_name: str) -> str:
        return os.path.join(base, f"{map_name}_G.pkl")

    def _points_path(self, base: str, map_name: str) -> str:
        return os.path.join(base, f"{map_name}_graph.pkl")

    def load_local_nx(self, map_name: str) -> Optional[nx.Graph]:
        path = self._nx_path(self.local_dir, map_name)
        if not os.path.exists(path):
            return None
        with open(path, "rb") as f:
            return pickle.load(f)

    def get_graph(self, map_name: str) -> Optional[nx.Graph]:
        if map_name in self._cache:
            return self._cache[map_name]
        G = self.load_local_nx(map_name)
        self._cache[map_name] = G
        return G


_GRAPH_MANAGER = None
_CURRENT_MAP = "SHIP"
_MAP_ALIASES = {
    "the skeld": "SHIP",
    "skeld": "SHIP",
    "ship": "SHIP",
    "lobby": "LOBBY",
}
_READER: Optional[AmongUsReader] = None


def _get_reader() -> AmongUsReader:
    global _READER
    if _READER is None:
        _READER = AmongUsReader(process_name="Among Us.exe", debug=False)
    if not _READER.is_attached():
        _READER.attach()
    return _READER


def _cleanup_reader() -> None:
    global _READER
    if _READER is not None:
        try:
            _READER.detach()
        except Exception:
            pass
        _READER = None


atexit.register(_cleanup_reader)


def get_graph_manager() -> GraphManager:
    global _GRAPH_MANAGER
    if _GRAPH_MANAGER is None:
        _GRAPH_MANAGER = GraphManager(_LOCAL_GRAPHS_DIR)
    return _GRAPH_MANAGER


def set_current_map(map_name: str):
    global _CURRENT_MAP
    if map_name:
        key = _MAP_ALIASES.get(str(map_name).strip().lower(), map_name)
        _CURRENT_MAP = str(key)


def get_current_map() -> str:
    reader = _get_reader()
    try:
        name = reader.get_current_map_name()
        if name:
            set_current_map(name)
    except Exception:
        pass
    return _CURRENT_MAP


def load_map_graph(map_name: str) -> nx.Graph:
    return get_graph_manager().get_graph(map_name)


def _node_pos(G: nx.Graph, n) -> Tuple[float, float]:
    if isinstance(n, (tuple, list)) and len(n) == 2:
        return (float(n[0]), float(n[1]))
    try:
        p = G.nodes[n].get('pos')
    except Exception:
        p = None
    if p is None:
        raise KeyError("node has no position")
    return (float(p[0]), float(p[1]))


def _nearest_node(G: nx.Graph, pos: Tuple[float, float]) -> Tuple[float, float]:
    """Return the nearest node in G to a world position."""
    best, best_d = None, float("inf")
    for n in G.nodes:
        pn = _node_pos(G, n)
        d = math.dist(pn, pos)
        if d < best_d:
            best, best_d = n, d
    return best


def _shortest_path(G: nx.Graph, start_pos: Tuple[float, float], dest_pos: Tuple[float, float]) -> List[Tuple[float, float]]:
    """Plan a shortest path between nearest nodes to start and dest (inclusive)."""
    s = _nearest_node(G, start_pos)
    t = _nearest_node(G, dest_pos)
    if s is None or t is None:
        return []
    if s == t:
        return [_node_pos(G, s)]
    try:
        nodes = nx.shortest_path(G, s, t, weight="weight")
    except Exception:
        return []
    path_coords = []
    for n in nodes:
        try:
            path_coords.append(_node_pos(G, n))
        except Exception:
            continue
    return path_coords


def _stick_vector(src: Tuple[float, float], dst: Tuple[float, float]) -> Tuple[float, float]:
    """Compute a normalized movement vector from src to dst in world space."""
    dx = dst[0] - src[0]
    dy = dst[1] - src[1]
    l = math.hypot(dx, dy)
    if l == 0:
        return (0.0, 0.0)
    return (dx / l, dy / l)


def _get_player_position() -> Tuple[float, float]:
    """Player coordinates via AmongUsReader facade."""
    reader = _get_reader()
    try:
        local_player = reader.get_local_player()
        if local_player is None:
            return (0.0, 0.0)
        pos_map = reader.positions()
        pos = pos_map.get(local_player.color_id)
        if not pos:
            return (0.0, 0.0)
        return (float(pos[0]), float(pos[1]))
    except Exception:
        return (0.0, 0.0)


class MovementController:
    """High-level movement planner using archived nav graphs and live memory for position."""

    def __init__(self, map_name: Optional[str] = None):
        # TODO: Read current map id via a pointer. For now, default to "SHIP" if not provided.
        # Add a new pointer in `PSmanager.py` and import it here, e.g., service.get_value("map_id").
        resolved = map_name or get_current_map()
        alias = _MAP_ALIASES.get(str(resolved).strip().lower(), resolved)
        self.map_name = alias
        self.G = load_map_graph(self.map_name)
        if self.G is None and self.map_name != "SHIP":
            self.map_name = "SHIP"
            self.G = load_map_graph(self.map_name)

    def plan_path(self, dest: Tuple[float, float]) -> List[Tuple[float, float]]:
        """Return a path (list of waypoints) from current position to dest using nav graph."""
        cur = _get_player_position()
        if self.G is None or getattr(self.G, 'number_of_nodes', lambda: 0)() == 0:
            return [dest]
        waypoints: List[Tuple[float, float]] = []
        try:
            s = _nearest_node(self.G, cur)
            t = _nearest_node(self.G, dest)
        except Exception:
            return [dest]
        try:
            nodes = nx.shortest_path(self.G, s, t, weight="weight")
        except Exception:
            nodes = [s, t]
        try:
            s_pos = _node_pos(self.G, s)
            if not waypoints or waypoints[-1] != s_pos:
                waypoints.append(s_pos)
        except Exception:
            pass
        if nodes:
            for n in nodes[1:-1]:
                try:
                    p = _node_pos(self.G, n)
                    if not waypoints or waypoints[-1] != p:
                        waypoints.append(p)
                except Exception:
                    continue
        try:
            t_pos = _node_pos(self.G, t)
            if not waypoints or waypoints[-1] != t_pos:
                waypoints.append(t_pos)
        except Exception:
            pass
        if not waypoints:
            return [dest]
        if waypoints[-1] != dest:
            waypoints.append(dest)
        return waypoints

    def next_step(self, path: List[Tuple[float, float]], arrive_threshold: float = 0.2) -> Tuple[Tuple[float, float], List[Tuple[float, float]]]:
        """Compute the next stick vector given a path and live position.

        Returns (stick_vector, remaining_path). If already arrived, returns ((0,0), []).
        """
        if not path:
            return (0.0, 0.0), []
        pos = _get_player_position()
        # Adjust arrive threshold by speed if needed.
        waypoint = path[0]
        if math.dist(pos, waypoint) <= arrive_threshold:
            path = path[1:]
            if not path:
                return (0.0, 0.0), []
            waypoint = path[0]
        # print("pos:", pos, "waypoint:", waypoint)  #========== 디버그용 (주석 처리)
        vec = _stick_vector(pos, waypoint)
        return vec, path

    def move_blocking(self, dest: Tuple[float, float], tick_rate: float = 30.0, arrive_radius: float = 0.2):
        """Blocking loop that yields stick vectors until arrival.

        NOTE:
        - This function only computes vectors. Emitting inputs (keyboard/gamepad) should be implemented by caller.
        - TODO: Add pointers for meeting state, death state, sabotage, etc., if you want to auto-interrupt.
        """
        path = self.plan_path(dest)
        dt = 1.0 / tick_rate
        last_vec = (0.0, 0.0)
        while path:
            vec, path = self.next_step(path, arrive_threshold=arrive_radius)
            last_vec = vec
            # Caller can map vec -> input. For example: hold WASD or analog stick toward vec.
            # TODO: If you want auto-input, integrate a sender here and ensure proper focus + timing.
            time.sleep(dt)
        return last_vec


class KeyboardDriver:
    def __init__(self, deadzone: float = 0.2):
        self.deadzone = deadzone
        self._down = set()

    def _desired_keys(self, vec: Tuple[float, float]) -> set:
        dx, dy = vec
        want = set()
        if dy > self.deadzone:
            want.add('w')
        elif dy < -self.deadzone:
            want.add('s')
        if dx > self.deadzone:
            want.add('d')
        elif dx < -self.deadzone:
            want.add('a')
        return want

    def _apply_keys(self, want: set):
        for k in list(self._down):
            if k not in want:
                try:
                    pyautogui.keyUp(k)
                except Exception:
                    pass
                self._down.discard(k)
        for k in want:
            if k not in self._down:
                try:
                    pyautogui.keyDown(k)
                except Exception:
                    pass
                self._down.add(k)

    def release_all(self):
        for k in list(self._down):
            try:
                pyautogui.keyUp(k)
            except Exception:
                pass
        self._down.clear()

    def drive_path(self, ctrl: 'MovementController', path: List[Tuple[float, float]], tick_rate: float = 30.0, arrive_radius: float = 0.2):
        dt = 1.0 / tick_rate
        try:
            while path:
                vec, path = ctrl.next_step(path, arrive_threshold=arrive_radius)
                want = self._desired_keys(vec)
                self._apply_keys(want)
                time.sleep(dt)
        finally:
            self.release_all()


def move_to_with_keyboard(ctrl: 'MovementController', dest: Tuple[float, float], tick_rate: float = 30.0, arrive_radius: float = 0.2, deadzone: float = 0.2):
    kd = KeyboardDriver(deadzone=deadzone)
    path = ctrl.plan_path(dest)
    kd.drive_path(ctrl, path, tick_rate=tick_rate, arrive_radius=arrive_radius)

def move_player_to(
    dest: Tuple[float, float],
    map_name: Optional[str] = None,
    tick_rate: float = 30.0,
    arrive_radius: float = 0.2,
    deadzone: float = 0.2,
    timeout: float = 3.0,
) -> bool:
    ctrl = MovementController(map_name=map_name or get_current_map())
    path = ctrl.plan_path(dest)
    if not path:
        return False
    kd = KeyboardDriver(deadzone=deadzone)
    dt = 1.0 / tick_rate
    success = False
    try:
        last_pos = _get_player_position()
        last_progress_time = time.time()
        while path:
            vec, path = ctrl.next_step(path, arrive_threshold=arrive_radius)
            want = kd._desired_keys(vec)
            kd._apply_keys(want)
            time.sleep(dt)
            cur_pos = _get_player_position()
            if math.dist(cur_pos, dest) <= arrive_radius:
                success = True
                path = []
                break
            if math.dist(cur_pos, last_pos) >= arrive_radius * 0.1:
                last_pos = cur_pos
                last_progress_time = time.time()
            elif time.time() - last_progress_time > timeout:
                break
        if not path and not success:
            cur_pos = _get_player_position()
            success = math.dist(cur_pos, dest) <= arrive_radius
    finally:
        kd.release_all()
    return success


# Minimal example for dry-run (no actual input emission)
if __name__ == "__main__":
    # TODO: Replace with a pointer-derived target or pass via CLI.
    target = (0.0, 0.0)
    ctrl = MovementController(map_name="SHIP")  # TODO: replace with map pointer later
    path = ctrl.plan_path(target)
    print(f"Planned waypoints: {len(path)}")
    # Print a few steps worth of vectors without emitting input
    for _ in range(10):
        vec, path = ctrl.next_step(path)
        print("vector:", vec, "remaining waypoints:", len(path))
        if not path:
            break
        time.sleep(0.033)