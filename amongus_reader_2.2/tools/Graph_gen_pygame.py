import os
import time
import math
import json
import pickle
import shutil
from datetime import datetime
from typing import List, Tuple, Optional, Set

import networkx as nx
import pygame
import keyboard

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
        delete_radius: Optional[float] = None,
        translation_speed: float = 0.05,
        visualize: bool = True,
        viz_scale: float = 3.0,
        load_from: Optional[str] = None,
        bg_paths: Optional[List[str]] = None,
        export_dir: Optional[str] = None,
    ):
        self.map_name = map_name or _get_map_name("SHIP")
        self.interval = max(0.02, float(interval))
        self.node_spacing = float(node_spacing)
        self.connect_threshold = float(connect_threshold) if connect_threshold is not None else float(node_spacing)
        self.merge_radius = float(merge_radius)
        self.delete_radius = float(delete_radius) if delete_radius is not None else float(merge_radius) * 1.5
        self.translation_speed = float(translation_speed)
        self.visualize = bool(visualize)
        self.viz_scale = float(viz_scale)

        self.nodes: List[Tuple[float, float]] = []
        self.edges: Set[Tuple[int, int]] = set()

        self.bg_graphs = [] 
        if bg_paths:
            # 구분하기 쉽도록 미리 정의된 색상 테마들
            themes = [((100, 100, 100), (60, 60, 60)),   # 테마1: 회색 노드, 어두운 엣지
                      ((0, 100, 0), (0, 60, 0)),         # 테마2: 녹색 노드, 어두운 엣지
                      ((100, 0, 100), (60, 0, 60))]      # 테마3: 보라색 노드
            for i, path in enumerate(bg_paths):
                theme = themes[i % len(themes)]
                self._load_bg_graph(path, theme)

        if load_from:
            self._load_graph(load_from)
        
        self._anchor_idx: Optional[int] = None
        self._stopped = False
        self._save_on_exit = True
        self._mode = 'PAUSED'  # REPLACE self._is_recording
        self._translation_offset = [0.0, 0.0]

        # Pygame 관련 변수
        self._screen = None
        self._clock = None

        self._export_dir = export_dir
    
    def _load_bg_graph(self, session_dir: str, theme):
        # 배경 그래프를 읽어서 메모리에 로드 (수정 불가)
        pkl = os.path.join(session_dir, 'G.pkl')
        if not os.path.exists(pkl):
            print(f"[ERROR] BG Graph not found at: {pkl}")
            return
        try:
            with open(pkl, 'rb') as f: G = pickle.load(f)

            if isinstance(G, list):
                bg_nodes = G
                bg_edges = []
            else:
                print("shit!!!")
                bg_nodes = []
                node_map = {}
                for i, (n, d) in enumerate(sorted(G.nodes(data=True))):
                    if 'pos' in d:
                        bg_nodes.append(d['pos'])
                        node_map[n] = i
                    elif isinstance(n, tuple) and len(n) == 2:
                        bg_nodes.append(n)
                        node_map[n] = i
                    else:
                        print(f"Unknown node format: {n}")
                bg_edges = []
                for u, v in G.edges():
                    if u in node_map and v in node_map:
                        bg_edges.append((node_map[u], node_map[v]))

            self.bg_graphs.append((bg_nodes, bg_edges, theme))
            print(f"Background graph loaded: {session_dir} ({len(bg_nodes)} nodes)")
        except Exception as e:
            print(G)
            print(f"Failed to load BG {session_dir}: {e}")

    def _load_graph(self, session_dir: str):
        pkl_path = os.path.join(session_dir, 'G.pkl')
        if not os.path.exists(pkl_path):
            print(f"Error: Cannot find {pkl_path}")
            return

        try:
            with open(pkl_path, 'rb') as f:
                G = pickle.load(f)
            
            # NetworkX 그래프를 내부 구조로 변환
            # 노드 인덱스가 0부터 순차적이라고 가정합니다.
            node_map = {} # 기존 ID -> 새 리스트 인덱스 매핑

            for i, (n, data) in enumerate(sorted(G.nodes(data=True))):
                if 'pos' in data:
                    self.nodes.append(data['pos'])
                    node_map[n] = i
                elif isinstance(n, tuple) and len(n) == 2:
                    self.nodes.append(n)
                    node_map[n] = i
                else:
                    print(f"Unknown node format: {n}")

            for u, v in G.edges():
                if u in node_map and v in node_map:
                    self.edges.add(tuple(sorted((node_map[u], node_map[v]))))

            print(f"Loaded graph from {session_dir}: {len(self.nodes)} nodes, {len(self.edges)} edges")
        except Exception as e:
            print(f"Failed to load graph: {e}")

    def _init_viz(self):
        if not self.visualize:
            return
        pygame.init()
        os.environ['SDL_VIDEO_WINDOW_POS'] = '0,0'
        self._screen = pygame.display.set_mode((800, 600))
        pygame.display.set_caption(f"Recording {self.map_name} (r:REC/PAUSE, q:SAVE&QUIT, x:QUIT)")
        self._clock = pygame.time.Clock()

    def _setup_global_hooks(self):
        keyboard.on_press_key('r', self._set_mode_record, suppress=False)
        keyboard.on_press_key('t', self._set_mode_pause, suppress=False)
        keyboard.on_press_key('z', self._set_mode_delete, suppress=False)
        
        # 종료 및 내보내기 키는 유지
        keyboard.on_press_key('q', lambda e: self._stop(True), suppress=False)
        keyboard.on_press_key('x', lambda e: self._stop(False), suppress=False)
        keyboard.on_press_key('e', lambda e: self._export_graph(), suppress=False)
        
        keyboard.on_press_key('i', lambda e: self._apply_translation(0, self.translation_speed), suppress=False)
        keyboard.on_press_key('k', lambda e: self._apply_translation(0, -self.translation_speed), suppress=False)
        keyboard.on_press_key('j', lambda e: self._apply_translation(-self.translation_speed, 0), suppress=False)
        keyboard.on_press_key('l', lambda e: self._apply_translation(self.translation_speed, 0), suppress=False)
        
        print("Global hotkeys registered: [R] Record, [T] Pause, [Z] Delete, [IJKL] Translate, [Q] Save&Quit, [X] Quit, [E] Export")

    def _set_mode_record(self, event=None):
        if self._mode != 'RECORDING':
            self._mode = 'RECORDING'
            print("\n>>> [GLOBAL] Mode changed to RECORDING <<<")

    def _set_mode_pause(self, event=None):
        if self._mode != 'PAUSED':
            self._anchor_idx = None # 앵커 초기화
            self._mode = 'PAUSED'
            print("\n>>> [GLOBAL] Mode changed to PAUSED <<<")

    def _set_mode_delete(self, event=None):
        if self._mode != 'DELETING':
            self._anchor_idx = None # 앵커 초기화
            self._mode = 'DELETING'
            print("\n>>> [GLOBAL] Mode changed to DELETING <<<")

    def _stop(self, save: bool):
        self._save_on_exit = save
        self._stopped = True
        print(f"\n>>> [GLOBAL] Stopping (Save={save}) <<<")

    def _to_screen(self, pos: Tuple[float, float], camera_center: Tuple[float, float]) -> Tuple[int, int]:
        x = (pos[0] - camera_center[0]) * self.viz_scale + 400
        y = -(pos[1] - camera_center[1]) * self.viz_scale + 300 # y축 반전
        return (int(x), int(y))

    def _draw(self, player_pos: Optional[Tuple[float, float]]):
        if not self.visualize or not self._screen: return
        pygame.event.pump()
        self._screen.fill((30, 30, 30))
        if player_pos: self._last_pos = player_pos
        cam = self._last_pos if self._last_pos else (0,0)

        for bg_nodes, bg_edges, (node_color, edge_color) in self.bg_graphs:
            for a, b in bg_edges:
                p1, p2 = self._to_screen(bg_nodes[a], cam), self._to_screen(bg_nodes[b], cam)
                pygame.draw.line(self._screen, edge_color, p1, p2, 1)
            for node in bg_nodes:
                sp = self._to_screen(node, cam)
                if -10 <= sp[0] <= 810 and -10 <= sp[1] <= 610:
                    pygame.draw.circle(self._screen, node_color, sp, 2)

        for a, b in self.edges:
            p1, p2 = self._to_screen(self.nodes[a], cam), self._to_screen(self.nodes[b], cam)
            pygame.draw.line(self._screen, (150, 150, 150), p1, p2, 2)
        for node in self.nodes:
            sp = self._to_screen(node, cam)
            if -10 <= sp[0] <= 810 and -10 <= sp[1] <= 610:
                 pygame.draw.circle(self._screen, (0, 120, 255), sp, 4)

        if player_pos:
            if self._mode == 'RECORDING':
                c = (50, 255, 50)
            elif self._mode == 'DELETING':
                c = (255, 50, 50)
            else: # PAUSED
                c = (255, 255, 0)
            pygame.draw.circle(self._screen, c, (400, 300), 5)

            if self._mode == 'DELETING':
                pixel_radius = int(self.delete_radius * self.viz_scale)
                pygame.draw.circle(self._screen, (255, 50, 50), (400, 300), pixel_radius, 1)

        try:
            font = pygame.font.SysFont("arial", 24, bold=True)
            # MODIFY status text logic
            st = self._mode.upper() # This now shows RECORDING, PAUSED, or DELETING
            # 플레이어 좌표 정보 추가 (소수점 4자리까지)
            pos_str = f"({player_pos[0]:.4f}, {player_pos[1]:.4f})" if player_pos else "(N/A, N/A)"
            info = f"{st} | Pos: {pos_str} | Main: {len(self.nodes)} | BG: {len(self.bg_graphs)}"
            offset_str = f"Offset: ({self._translation_offset[0]:.2f}, {self._translation_offset[1]:.2f})"
            self._screen.blit(font.render(info, True, (255,255,255)), (10, 10))
            self._screen.blit(font.render(offset_str, True, (255,255,255)), (10, 40))
        except: pass
        pygame.display.flip()

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

    def _find_nearby_nodes(self, pos: Tuple[float, float], radius: float) -> List[int]:
        r2 = radius * radius
        nearby_indices = []
        for i, p in enumerate(self.nodes):
            dx = p[0] - pos[0]
            dy = p[1] - pos[1]
            d2 = dx * dx + dy * dy
            if d2 <= r2:
                nearby_indices.append(i)
        return nearby_indices

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

    def _maybe_delete_node(self, pos: Tuple[float, float]):
        """
        Finds and deletes all nodes within self.delete_radius of the player.
        This function safely rebuilds the node list and edge set to maintain valid indices.
        """
        nodes_to_delete_set = set(self._find_nearby_nodes(pos, self.delete_radius))
        if not nodes_to_delete_set:
            return

        new_nodes = []
        old_to_new_idx = {} # Maps old index to new index
        
        # Create the new node list and the index mapping
        for i, node in enumerate(self.nodes):
            if i not in nodes_to_delete_set:
                new_idx = len(new_nodes)
                new_nodes.append(node)
                old_to_new_idx[i] = new_idx
        
        # Rebuild the edge set using the new indices
        new_edges = set()
        for u, v in self.edges:
            # If both nodes of an edge still exist, add the edge with new indices
            if u in old_to_new_idx and v in old_to_new_idx:
                new_u = old_to_new_idx[u]
                new_v = old_to_new_idx[v]
                new_edges.add(tuple(sorted((new_u, new_v))))
        
        # Only update if something actually changed
        if len(new_nodes) != len(self.nodes):
            deleted_count = len(self.nodes) - len(new_nodes)
            print(f"Deleted {deleted_count} nodes.")
            
            self.nodes = new_nodes
            self.edges = new_edges
            self._anchor_idx = None

    def _maybe_create_node(self, pos: Tuple[float, float]):
        # If no anchor, create first node immediately
        if self._anchor_idx is None:
            self._anchor_idx = self._find_nearby_node(pos, self.node_spacing * 2)
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

    def _export_graph(self):
        if self._export_dir is None:
            print("No export directory specified, skipping export.")
            return

        G = nx.Graph()
        for p in self.nodes:
            G.add_node((float(p[0]), float(p[1])))
        for a, b in self.edges:
            pa = self.nodes[a]
            pb = self.nodes[b]
            G.add_edge((float(pa[0]), float(pa[1])), (float(pb[0]), float(pb[1])), weight=round(math.dist(pa, pb), 4))

        os.makedirs(self._export_dir, exist_ok=True)
        with open(os.path.join(self._export_dir, f'{self.map_name}_G.pkl'), 'wb') as f:
            pickle.dump(G, f)
        with open(os.path.join(self._export_dir, f'{self.map_name}_graph.pkl'), 'wb') as f:
            pickle.dump(self.nodes, f)

        print(f"Graph exported to: {os.path.join(self._export_dir, f'{self.map_name}_G.pkl')}")

    def _apply_translation(self, dx: float, dy: float):
        """ 
        활성 그래프(self.nodes)의 모든 노드 좌표를 실제로 변경하고,
        총 이동량을 기록합니다.
        """
        # 1. 총 이동량 업데이트
        self._translation_offset[0] += dx
        self._translation_offset[1] += dy
        
        # 2. self.nodes 리스트의 모든 좌표를 실제로 이동 (데이터 수정)
        #    (배경 그래프는 self.bg_graphs에 있으므로 영향을 받지 않음)
        self.nodes = [(x + dx, y + dy) for (x, y) in self.nodes]
        
        # 3. (선택적) 콘솔에 현재 이동량 피드백
        print(f"Graph translated. Total Offset: ({self._translation_offset[0]:.2f}, {self._translation_offset[1]:.2f})", end="\r")

    # --------- Session control ---------
    def run(self, max_seconds: Optional[float] = None) -> str:
        self._init_viz()
        self._setup_global_hooks()

        start_time = time.time()
        try:
            while not self._stopped:
                # 1. 입력 처리 (가장 중요)
                if self.visualize:
                    pygame.event.pump()

                # 2. 로직 업데이트
                pos = _get_player_position()
                if pos is not None:
                    if self._mode == 'RECORDING':
                        self._maybe_create_node(pos)
                    elif self._mode == 'DELETING':
                        self._maybe_delete_node(pos)

                # 3. 화면 그리기
                if self.visualize:
                    self._draw(pos)
                    self._clock.tick(30) # 최대 30 FPS로 제한하여 CPU 사용량 조절
                else:
                    time.sleep(self.interval)

                if max_seconds and (time.time() - start_time) >= max_seconds:
                    break
                    
        except KeyboardInterrupt:
            pass
        finally:
            keyboard.unhook_all()
            if self.visualize:
                pygame.quit()

        # (저장 로직 동일)
        if self._save_on_exit:
            return self.save_session()
        return ""

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


# def publish_graph(map_name, session_dir):
#     src = os.path.join(session_dir, 'G.pkl')
#     if os.path.exists(src):
#         dst = os.path.join(PUBLISHED_DIR, f"{map_name}_G.pkl")
#         shutil.copy2(src, dst)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Among Us map graph recorder')
    parser.add_argument('--map', dest='map_name', type=str, required=True, help='Map name (e.g., SHIP)')
    parser.add_argument('--interval', type=float, default=0.1, help='Sampling interval seconds')
    parser.add_argument('--node-spacing', type=float, default=0.75, help='Distance to create a new node from last anchor')
    parser.add_argument('--connect-threshold', type=float, default=None, help='Connect to nodes within this radius (default: node-spacing)')
    parser.add_argument('--merge-radius', type=float, default=0.5, help='Reuse nearby node instead of creating a new one')
    parser.add_argument('--delete-radius', type=float, default=None, help='Radius to delete nodes in "Z" mode (default: merge-radius * 1.5)')
    parser.add_argument('--translate-speed', type=float, default=0.05, help='Translation speed using arrow keys')
    parser.add_argument('--no-viz', dest='visualize', action='store_false', help='Disable live visualization')
    parser.add_argument('--viz-scale', type=float, default=40.0, help='Visualization scale factor (e.g., 0.2 shows 1/5 size)')
    parser.add_argument('--max-seconds', type=float, default=None, help='Stop after this many seconds')
    parser.add_argument('--no-publish', dest='publish', action='store_false', help='Do not publish to graphs/<MAP>_G.pkl')
    parser.add_argument('--load', help='Path to session directory to load (e.g. graphs_generated/SHIP/...)')
    parser.add_argument('--bg-load', action='append', help='Load background graph (immutable, multiple allowed)')
    parser.add_argument('--export', dest='export', type=str, default=None, help='Path to export the recorded nodes as a pickle file')

    args = parser.parse_args()

    rec = GraphRecorder(
        map_name=args.map_name, 
        interval=args.interval, 
        node_spacing=args.node_spacing,
        connect_threshold=args.connect_threshold,
        merge_radius=args.merge_radius,
        delete_radius=args.delete_radius,
        translation_speed=args.translate_speed,
        visualize=args.visualize,
        viz_scale=args.viz_scale,
        load_from=args.load,
        bg_paths=args.bg_load,
        export_dir=args.export,
    )
    session = rec.run()
    # if session: publish_graph(args.map_name, session)