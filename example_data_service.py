from amongus_reader import (
    get_data_service,
    get_local_player,
    get_all_players,
    get_player_by_id,
    get_player_by_color,
    get_all_player_positions,
    get_local_player_position,
    get_local_player_id,
    reset_data_service,
    ColorId,
)


def basic_usage():
    print("=== 기본 사용법 ===")
    
    service = get_data_service()

    service.enable_debug(True)
    service.set_scan_interval(0.1)  # 0.1초, 스캔 주기
    
    # 로컬 플레이어 : 지금 조종하는 플레이어
    local = get_local_player()
    if local:
        print(f"로컬 플레이어: {local.color_name} (ID: {local.player_id})")
        print(f"위치: ({local.position[0]:.2f}, {local.position[1]:.2f})")

    # 로컬 플레이어 ID만 조회
    local_id = get_local_player_id()
    if local_id is not None:
        print(f"로컬 플레이어 ID: {local_id}")
    
    # 모든 플레이어
    players = get_all_players()
    print(f"총 플레이어 수: {len(players)}")
    
    for player in players:
        if player.is_local_player:
            print(f"  당신: {player.color_name} - {player.position}")
        else:
            print(f"  플레이어 {player.player_id}: {player.color_name} - {player.position}")


def high_performance_usage():
    """자주 호출하는 경우"""

    # 모든 플레이어 위치
    positions = get_all_player_positions()
    print("현재 모든 플레이어 위치:")
    for player_id, pos in positions.items():
        print(f"  Player {player_id}: ({pos[0]:.2f}, {pos[1]:.2f})")
    
    # 색상 매핑
    color_map = get_data_service().get_color_mapping()
    print("플레이어-색상 매핑:")
    for player_id, color_name in color_map.items():
        print(f"  Player {player_id}: {color_name}")
    
    # 스냅샷(타임스탬프, 플레이어 목록)
    ts, players = get_data_service().get_snapshot()
    print(f"스냅샷 시각: {ts:.3f}, 플레이어 수: {len(players)}")
    
    # 로컬 플레이어 위치만 요청
    my_pos = get_local_player_position()
    if my_pos:
        print(f"로컬 플레이어 위치(빠른): ({my_pos[0]:.2f}, {my_pos[1]:.2f})")


def search_examples():
    print("\n=== 검색 예시 ===")
    
    service = get_data_service()
    
    # 색상으로 검색
    red_player = get_player_by_color(ColorId.RED)
    if red_player:
        print(f"빨간 플레이어: ID {red_player.player_id}, 위치 {red_player.position}")
    
    # ID로 검색
    if red_player:
        same_player = get_player_by_id(red_player.player_id)
        print(f"ID {red_player.player_id}로 다시 검색: {same_player.color_name}")
    
    # 색상 이름으로 검색
    blue_players = get_data_service().get_players_by_color_name("blue")
    print(f"파란 플레이어 수: {len(blue_players)}")
    
    # 태스크 조회 예시 (빨간 플레이어 기준)
    if red_player:
        tasks = service.get_tasks_for_player(red_player.player_id)
        if tasks:
            print("빨간 플레이어 태스크:")
            for t in tasks:
                status = "완료" if t.is_completed else "미완료"
                print(f"  - id={t.task_id}, type={t.task_type_id}, 상태={status}")
        else:
            print("빨간 플레이어 태스크가 없습니다 또는 읽을 수 없습니다.")


def monitoring_example():

    print("\n=== 실시간 모니터링 예시 ===")
    
    service = get_data_service()
    
    import time
    
    try:
        for i in range(20):
            print(f"\n--- {i+1} ---")
            # 필요 시 즉시 갱신
            service.refresh(force=True)
            # 빠른 위치: 서비스 자동 갱신 기반
            positions = get_all_player_positions()
            local = get_local_player()
            
            if local:
                # 로컬 전용 위치를 우선 사용, 없으면 전체 맵에서 추출
                my_pos = get_local_player_position() or positions.get(local.player_id, (0, 0))
                print(f"당신의 위치: ({my_pos[0]:.2f}, {my_pos[1]:.2f})")
                
                # 다른 플레이어와의 거리 계산 (player_id가 중복될 수 있어 리스트 기반으로 계산)
                for p in get_all_players():
                    if not p.is_local_player:
                        pos = p.position
                        distance = ((pos[0] - my_pos[0])**2 + (pos[1] - my_pos[1])**2)**0.5
                        print(f"  {p.color_name}까지 거리: {distance:.2f}")
            
            time.sleep(0.5)  # 1초 대기
    
    except KeyboardInterrupt:
        print("\n모니터링 중단")


def cleanup_example():

    print("\n=== 리소스 정리 ===")
    
    reset_data_service()
    print("데이터 서비스 리셋 완료")


if __name__ == "__main__":
    try:
        

        basic_usage()

        high_performance_usage()

        search_examples()

        monitoring_example()

    except Exception as e:
        print(f"오류 발생: {e}")
        raise e
    finally:
        cleanup_example()
