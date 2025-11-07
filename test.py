from amongus_reader.service import AmongUsReader

r = AmongUsReader(process_name="Among Us.exe", debug=False)
r.attach()
try:
    # all_players = r.list_players()
    # 로컬 플레이어 ID
    local_player = r.get_local_player()
    local_id = local_player.color_id if local_player else None

    # 모든 플레이어 좌표(초고속 per-call 경로)
    pos_map = r.positions()
    my_pos = pos_map.get(local_id) if local_id is not None else None

    # 색상 이름 매핑
    colors = r.colors()

    # 태스크 (로컬 플레이어 기준 예시)
    tasks = r.get_tasks(0) if local_id is not None else []

    # HUD Report 버튼 활성 여부(진단 포함)
    active, diag = r.is_report_active()
    
    flag, diag = r.is_local_impostor()

    # print("All players:", all_players)
    if flag is None:
        print("local_is_impostor=Unknown", diag)
    else:
        print(f"local_is_impostor={flag}")
        print("diagnostics:", diag)
    print("local_id:", local_id)
    print("my_pos:", local_player.position)
    print("tasks:")
    for task in tasks:
        print(f"task_type_id: {task.task_type_id:2}, step: {task.step}/{task.max_step}, location: {task.location}")
    print("report_active:", active)
finally:
    r.detach()