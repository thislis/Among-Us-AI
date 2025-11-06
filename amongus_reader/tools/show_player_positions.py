"""
AmongUsReader를 활용해 모든 플레이어의 현재 좌표를 출력하는 도구.

Among Us 프로세스 메모리를 직접 읽어들이므로 관리자 권한으로 실행하는 것이
안전하며, 게임이 실행 중이어야 합니다.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from amongus_reader import AmongUsReader, PlayerData


DEFAULT_INTERVAL = 0.5
DEFAULT_RETRIES = 5
DEFAULT_RETRY_DELAY = 1.0

SnapshotRow = Tuple[Optional[int], Optional[int], Optional[float], Optional[float], str, bool]  # (color_id, player_id, x, y, color_name, is_local)


def _attempt_attach(
    reader: AmongUsReader,
    process_name: str,
    retries: int,
    retry_delay: float,
) -> bool:
    """Ensure the reader is attached to the target process."""
    if reader.is_attached():
        return True

    # 첫 시도에서는 명시적으로 프로세스 이름을 지정한다.
    if reader.attach(process_name):
        return True

    attempts = max(0, int(retries))
    for attempt in range(attempts):
        time.sleep(max(0.1, float(retry_delay)))
        if reader.attach():
            return True
    return reader.is_attached()


def _collect_snapshot(reader: AmongUsReader) -> List[SnapshotRow]:
    """Return a sorted list of (color_id, player_id, x, y, color_name, is_local)."""
    players: List[PlayerData] = reader.list_players() or []

    positions: Dict[int, Tuple[float, float]] = reader.positions() or {}
    if players and len(positions) < len(players):
        reader.invalidate_players_pc_map()
        positions = reader.positions() or {}

    colors = reader.colors()
    snapshot: List[SnapshotRow] = []
    seen: set[int] = set()

    for pdata in players:
        color_id: Optional[int] = getattr(pdata, "color_id", None)
        player_id: Optional[int] = getattr(pdata, "player_id", None)

        # PlayerData.position is generally reliable and per-player; prefer it over the
        # shared per-call positions() result so we avoid collapsing multiple players
        # that accidentally share the same color_id mapping.
        pos: Optional[Tuple[float, float]] = getattr(pdata, "position", None)
        if pos is None and color_id is not None:
            pos = positions.get(color_id)

        if pos is None:
            x_val = None
            y_val = None
        else:
            x_val, y_val = pos

        color_name = (
            getattr(pdata, "color_name", None)
            or (colors.get(color_id) if color_id is not None else None)
            or "Unknown"
        )
        is_local = bool(getattr(pdata, "is_local_player", False))
        snapshot.append((color_id, player_id, x_val, y_val, color_name, is_local))
        if color_id is not None:
            seen.add(color_id)

    # Include any players visible via positions() but missing from list_players()
    for color_id, pos in sorted(positions.items()):
        if color_id in seen:
            continue
        x_val, y_val = pos
        color_name = colors.get(color_id, "Unknown")
        snapshot.append((color_id, None, x_val, y_val, color_name, False))

    return snapshot


def _clear_screen() -> None:
    if os.name == "nt":
        os.system("cls")
    else:
        os.system("clear")


def _render_snapshot(rows: Iterable[SnapshotRow]) -> None:
    rows = list(rows)
    timestamp = time.strftime("%H:%M:%S")
    if not rows:
        print(f"[{timestamp}] 플레이어 위치 데이터를 찾을 수 없습니다. 게임이 로비 상태인지 확인하세요.")
        return

    print(f"[{timestamp}] 플레이어 위치 ({len(rows)}명)")
    print("ColorID | PlayerID | L | Color        |        X |        Y")
    print("------------------------------------------------------------")
    for color_id, player_id, x, y, color_name, is_local in rows:
        local_flag = "L" if is_local else " "
        x_str = f"{x:8.3f}" if x is not None else "   --   "
        y_str = f"{y:8.3f}" if y is not None else "   --   "
        color_id_str = "??" if color_id is None or color_id < 0 else f"{color_id:2d}"
        player_id_str = "??" if player_id is None or player_id < 0 else f"{player_id:2d}"
        print(f"{color_id_str:>7} | {player_id_str:>8} | {local_flag} | {color_name:<12} | {x_str} | {y_str}")


def _parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AmongUsReader를 사용해 모든 플레이어의 현재 위치를 출력합니다.",
    )
    parser.add_argument(
        "--process-name",
        default="Among Us.exe",
        help="대상 프로세스 이름 (기본값: Among Us.exe)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL,
        help="반복 출력 모드에서의 갱신 주기(초)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="위치를 한 번만 출력하고 종료합니다.",
    )
    parser.add_argument(
        "--no-clear",
        dest="clear_screen",
        action="store_false",
        help="반복 출력 시 화면을 지우지 않습니다.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=DEFAULT_RETRIES,
        help="프로세스 연결 실패 시 추가로 재시도할 횟수",
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=DEFAULT_RETRY_DELAY,
        help="재시도 사이의 대기 시간(초)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="AmongUsReader 디버그 로그를 활성화합니다.",
    )
    parser.set_defaults(clear_screen=True)
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])

    reader = AmongUsReader(process_name=args.process_name, debug=args.debug)
    attached = _attempt_attach(
        reader,
        process_name=args.process_name,
        retries=args.retries,
        retry_delay=args.retry_delay,
    )

    if not attached:
        print("Among Us 프로세스에 연결하지 못했습니다. 게임이 실행 중인지 확인하세요.", file=sys.stderr)
        return 1

    try:
        if args.once:
            if args.clear_screen:
                _clear_screen()
            snapshot = _collect_snapshot(reader)
            _render_snapshot(snapshot)
            return 0

        while True:
            if args.clear_screen:
                _clear_screen()
            snapshot = _collect_snapshot(reader)
            _render_snapshot(snapshot)
            time.sleep(max(0.05, float(args.interval)))
    except KeyboardInterrupt:
        print("\n중단합니다.")
        return 0
    finally:
        reader.detach()


if __name__ == "__main__":
    sys.exit(main())

