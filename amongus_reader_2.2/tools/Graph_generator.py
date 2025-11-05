import os
import time
import math
import json
import pickle
import shutil
from datetime import datetime
from typing import List, Tuple, Optional, Set

import networkx as nx
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

import sys
import atexit
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from amongus_reader.service import AmongUsReader

BASE_DIR = os.path.dirname(__file__)
GENERATED_ROOT = os.path.join(BASE_DIR, "graphs_generated")
PUBLISHED_DIR = os.path.join(BASE_DIR, "graphs")

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


def _get_map_name(default: str) -> str:
    reader = _get_reader()
    try:
        name = reader.get_current_map_name()
        if name:
            return name
    except Exception:
        pass
    return default


def _get_player_position() -> Optional[Tuple[float, float]]:
    reader = _get_reader()
    try:
        local_id = reader.get_local_player_id()
        if local_id is None:
            return None
        pos_map = reader.positions()
        pos = pos_map.get(local_id)
        if not pos:
            return None
        return (float(pos[0]), float(pos[1]))
    except Exception:
        return None


class GraphRecorder:
    def __init__(
        self,
        map_name: str,
        interval: float = 0.1,
        node_spacing: float = 0.75,
        connect_threshold: Optional[float] = None,
        merge_radius: float = 0.5,
        visualize: bool = True,
        viz_scale: float = 0.2,
    ):
        self.map_name = map_name or _get_map_name("SHIP")
        self.interval = max(0.02, float(interval))
        self.node_spacing = float(node_spacing)
        self.connect_threshold = float(connect_threshold) if connect_threshold is not None else float(node_spacing)
        self.merge_radius = float(merge_radius)
        self.visualize = bool(visualize)
        self.viz_scale = float(viz_scale)

        self.nodes: List[Tuple[float, float]] = []
        self.edges: Set[Tuple[int, int]] = set()

        self._anchor_idx: Optional[int] = None
        self._last_pos: Optional[Tuple[float, float]] = None
        self._stopped = False
        self._save_on_exit = True

        self._fig = None
        self._ax = None
        self._sc_nodes = None
        self._sc_player = None
        self._lc_edges = None

    # --------- Visualization helpers ---------
    def _init_plot(self):
        if not self.visualize:
            return
        self._fig, self._ax = plt.subplots()
        self._ax.set_title(f"Recording graph for {self.map_name} (q=save+quit, x=quit-no-save, p=publish)")
        self._ax.set_aspect('equal', adjustable='datalim')
        self._sc_nodes = self._ax.scatter([], [], s=15, c='tab:blue')
        self._sc_player = self._ax.scatter([], [], s=30, c='tab:red')
        self._lc_edges = LineCollection([], colors='tab:gray', linewidths=1.0, alpha=0.7)
        self._ax.add_collection(self._lc_edges)
        self._fig.canvas.mpl_connect('key_press_event', self._on_key)
        plt.ion()
        plt.show(block=False)

    def _on_key(self, event):
        if event.key == 'q':
            self._stopped = True
        elif event.key == 'x':
            self._save_on_exit = False
            self._stopped = True
        elif event.key == 'p':
            try:
                session_dir = self.save_session()
                publish_graph(self.map_name, session_dir)
                print(f"Published to {os.path.join(PUBLISHED_DIR, f'{self.map_name}_G.pkl')}")
            except Exception as e:
                print(f"Publish failed: {e}")

    def _update_plot(self, player_pos: Optional[Tuple[float, float]]):
        if not self.visualize:
            return
        s = self.viz_scale
        xs = [p[0] * s for p in self.nodes]
        ys = [p[1] * s for p in self.nodes]
        self._sc_nodes.set_offsets(list(zip(xs, ys)) if xs else [])
        sp = None
        if player_pos is not None:
            sp = (player_pos[0] * s, player_pos[1] * s)
            self._sc_player.set_offsets([sp])
        # edges
        segments = []
        for a, b in self.edges:
            pa = self.nodes[a]
            pb = self.nodes[b]
            segments.append([(pa[0] * s, pa[1] * s), (pb[0] * s, pb[1] * s)])
        self._lc_edges.set_segments(segments)
        # optional auto-limits: keep current if many points
        if sp is not None and len(self.nodes) < 50:
            r = 5 * s
            self._ax.set_xlim(sp[0] - r, sp[0] + r)
            self._ax.set_ylim(sp[1] - r, sp[1] + r)
        self._fig.canvas.draw_idle()
        plt.pause(0.001)

    # --------- Graph building logic ---------
    def _find_nearby_node(self, pos: Tuple[float, float], radius: float) -> Optional[int]:
        r2 = radius * radius
        best_idx = None
        best_d2 = None
        for i, p in enumerate(self.nodes):
            dx = p[0] - pos[0]
            dy = p[1] - pos[1]
            d2 = dx * dx + dy * dy
            if d2 <= r2 and (best_d2 is None or d2 < best_d2):
                best_idx, best_d2 = i, d2
        return best_idx

    def _add_node(self, pos: Tuple[float, float]) -> int:
        self.nodes.append(pos)
        return len(self.nodes) - 1

    def _connect(self, i: int, j: int):
        if i == j:
            return
        a, b = (i, j) if i < j else (j, i)
        self.edges.add((a, b))

    def _connect_nearby(self, idx: int, radius: float):
        p = self.nodes[idx]
        for j, q in enumerate(self.nodes):
            if j == idx:
                continue
            if math.dist(p, q) <= radius:
                self._connect(idx, j)

    def _maybe_create_node(self, pos: Tuple[float, float]):
        # If no anchor, create first node immediately
        if self._anchor_idx is None:
            self._anchor_idx = self._add_node(pos)
            return
        anchor_pos = self.nodes[self._anchor_idx]
        if math.dist(pos, anchor_pos) < self.node_spacing:
            return
        # merge to nearby node if any
        idx = self._find_nearby_node(pos, self.merge_radius)
        if idx is None:
            idx = self._add_node(pos)
        # always connect from previous anchor
        self._connect(self._anchor_idx, idx)
        # connect to other nodes within threshold
        self._connect_nearby(idx, self.connect_threshold)
        # update anchor
        self._anchor_idx = idx

    # --------- Session control ---------
    def run(self, max_seconds: Optional[float] = None) -> str:
        self._init_plot()
        start = time.time()
        try:
            while not self._stopped:
                pos = _get_player_position()
                if pos is not None:
                    self._maybe_create_node(pos)
                self._update_plot(pos)
                if max_seconds is not None and (time.time() - start) >= max_seconds:
                    break
                time.sleep(self.interval)
        finally:
            if self.visualize and self._fig is not None:
                plt.ioff()
                try:
                    plt.close(self._fig)
                except Exception:
                    pass
        session_dir = ""
        if self._save_on_exit:
            session_dir = self.save_session()
        else:
            print("Session discarded (not saved).")
        return session_dir

    def save_session(self) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = os.path.join(GENERATED_ROOT, self.map_name, ts)
        os.makedirs(session_dir, exist_ok=True)

        # Build NetworkX graph
        G = nx.Graph()
        for i, p in enumerate(self.nodes):
            G.add_node(i, pos=(float(p[0]), float(p[1])))
        for a, b in self.edges:
            pa = self.nodes[a]
            pb = self.nodes[b]
            G.add_edge(a, b, weight=round(math.dist(pa, pb), 4))

        with open(os.path.join(session_dir, 'G.pkl'), 'wb') as f:
            pickle.dump(G, f)

        meta = {
            'map': self.map_name,
            'interval': self.interval,
            'node_spacing': self.node_spacing,
            'connect_threshold': self.connect_threshold,
            'merge_radius': self.merge_radius,
            'nodes': len(self.nodes),
            'edges': len(self.edges),
        }
        with open(os.path.join(session_dir, 'meta.json'), 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        print(f"Session saved to: {session_dir}")
        return session_dir


def publish_graph(map_name: str, session_dir: str) -> str:
    """Copy session G.pkl to graphs/<MAP>_G.pkl for consumption by move.py"""
    src = os.path.join(session_dir, 'G.pkl')
    if not os.path.exists(src):
        raise FileNotFoundError(f"G.pkl not found in {session_dir}")
    os.makedirs(PUBLISHED_DIR, exist_ok=True)
    dst = os.path.join(PUBLISHED_DIR, f"{map_name}_G.pkl")
    shutil.copy2(src, dst)
    return dst


def record_session(
    map_name: str,
    interval: float = 0.1,
    node_spacing: float = 0.75,
    connect_threshold: Optional[float] = None,
    merge_radius: float = 0.5,
    visualize: bool = True,
    max_seconds: Optional[float] = None,
    publish: bool = True,
    viz_scale: float = 0.2,
) -> str:
    rec = GraphRecorder(
        map_name=map_name,
        interval=interval,
        node_spacing=node_spacing,
        connect_threshold=connect_threshold,
        merge_radius=merge_radius,
        visualize=visualize,
        viz_scale=viz_scale,
    )
    session_dir = rec.run(max_seconds=max_seconds)
    if publish and session_dir:
        publish_graph(map_name, session_dir)
    return session_dir


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Among Us map graph recorder')
    parser.add_argument('--map', dest='map_name', type=str, required=True, help='Map name (e.g., SHIP)')
    parser.add_argument('--interval', type=float, default=0.1, help='Sampling interval seconds')
    parser.add_argument('--node-spacing', type=float, default=0.75, help='Distance to create a new node from last anchor')
    parser.add_argument('--connect-threshold', type=float, default=None, help='Connect to nodes within this radius (default: node-spacing)')
    parser.add_argument('--merge-radius', type=float, default=0.5, help='Reuse nearby node instead of creating a new one')
    parser.add_argument('--no-viz', dest='visualize', action='store_false', help='Disable live visualization')
    parser.add_argument('--viz-scale', type=float, default=0.2, help='Visualization scale factor (e.g., 0.2 shows 1/5 size)')
    parser.add_argument('--max-seconds', type=float, default=None, help='Stop after this many seconds')
    parser.add_argument('--no-publish', dest='publish', action='store_false', help='Do not publish to graphs/<MAP>_G.pkl')

    args = parser.parse_args()

    session = record_session(
        map_name=args.map_name,
        interval=args.interval,
        node_spacing=args.node_spacing,
        connect_threshold=args.connect_threshold,
        merge_radius=args.merge_radius,
        visualize=args.visualize,
        max_seconds=args.max_seconds,
        publish=args.publish,
        viz_scale=args.viz_scale,
    )
    print('Recording finished:', session)
