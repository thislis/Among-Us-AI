from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from amongus_reader.service import AmongUsReader
from amongus_reader.service.task_lookup import format_task_entry


def main() -> None:
    reader = AmongUsReader(process_name="Among Us.exe", debug=False)
    if not reader.attach():
        print("Among Us 프로세스에 연결하지 못했습니다.")
        return

    try:
        while True:
            local_player = reader.get_local_player()
            local_id = local_player.color_id if local_player else None
            if local_id is None:
                print("로컬 플레이어를 찾는 중... (게임 로딩 대기)")
                time.sleep(0.5)
                continue

            # always force a fresh read; the first call after 라운드 시작 시 빈 결과가 나올 수 있어 재시도
            reader.invalidate(["tasks"])
            tasks = reader.get_tasks(local_id) if local_id is not None else []
            if not tasks:
                print("태스크 데이터를 불러오는 중입니다... (다시 시도)")
                time.sleep(0.5)
                continue

            totals = Counter(t.task_type_id for t in tasks)
            completed_counts = Counter(
                t.task_type_id for t in tasks if t.is_completed
            )

            print(f"[플레이어 {local_id}] 태스크 현황:")
            for task in tasks:
                if task.is_completed:
                    continue  # 완료된 태스크는 건너뜀

                entry = format_task_entry(task, totals, completed_counts)
                coord = entry.coordinates
                coord_text = (
                    f"({coord[0]:.2f}, {coord[1]:.2f})" if coord else "좌표 미상"
                )
                suffix = entry.progress_suffix()
                progress = f" {suffix}" if suffix else ""
                print(
                    f"{entry.room}: {entry.task_name}{progress} "
                    f"(Id={entry.task_id}, Type={entry.task_type_id}) → {coord_text}"
                )
            break
    finally:
        reader.detach()


if __name__ == "__main__":
    main()

