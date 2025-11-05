"""
지정한 좌표로 이동하는 간단한 스크립트
"""
import math
import time
from typing import Tuple

from move import (
    MovementController,
    move_player_to,
    get_current_map,
)

(TARGET_X, TARGET_Y) = (-18.92, -13.43)


def wait_for(seconds: float) -> None:
    end = time.time() + seconds
    remaining = int(seconds)
    while time.time() < end:
        print(f"{remaining}...")
        time.sleep(1)
        remaining -= 1


def main():
    target: Tuple[float, float] = (TARGET_X, TARGET_Y)
    current_map = get_current_map()
    print(f"목표: ({TARGET_X:.3f}, {TARGET_Y:.3f})")
    print("현재 맵:", current_map)
    print("3초 후 이동 시작...")
    wait_for(3)

    print("이동 중... (Ctrl+C로 중단)")

    try:
        ctrl = MovementController()
        path = ctrl.plan_path(target)
        if not path:
            print("경로를 찾을 수 없습니다.")
            return

        success = move_player_to(target, tick_rate=30.0, arrive_radius=0.5, deadzone=0.2)
        if success:
            print("\n도착!")
        else:
            print("\n목표 지점에 도달하지 못했습니다.")
    except KeyboardInterrupt:
        print("\n중단")


if __name__ == "__main__":
    main()
