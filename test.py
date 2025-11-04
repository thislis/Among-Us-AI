from amongus_reader.service import AmongUsReader

r = AmongUsReader(process_name="Among Us.exe", debug=False)
r.attach()
try:
    # 로컬 플레이어 ID
    local_id = r.get_local_player_id()

    # 모든 플레이어 좌표(초고속 per-call 경로)
    pos_map = r.positions()
    my_pos = pos_map.get(local_id) if local_id is not None else None

    # 색상 이름 매핑
    colors = r.colors()

    # 태스크 (로컬 플레이어 기준 예시)
    tasks = r.get_tasks(local_id) if local_id is not None else []

    # HUD Report 버튼 활성 여부(진단 포함)
    active, diag = r.is_report_active()

    print("local_id:", local_id)
    print("my_pos:", my_pos)
    print("colors:", colors)
    print("tasks:", tasks)
    print("report_active:", active)
finally:
    r.detach()