from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Dict, Tuple, Optional, List

import time

from camera import Camera

import multiprocessing as mp
from multiprocessing.connection import Connection 
import redis
import json

from amongus_reader import AmongUsReader
from amongus_reader.tools.check_player_death import get_player_death_status

from is_impostor import is_impostor

from locator import place

from collections import deque

def can_see(me, opp, is_imposter):
    x1, y1 = me; x2, y2 = opp

    if is_imposter:
        a, b = 610.1303148042931*(5/3), 610.1303148042931*(5/3)
    else:
        a, b = 610.1303148042931, 610.1303148042931
    real_a = 3.2729492187499996
    ratio = real_a/a
    a = real_a
    b *= ratio

    dx, dy = x2-x1, y2-y1
    val = (dx/a)**2 + (dy/b)**2
    return val<=1

class InfoPipe:
    """
    고수준 게임 봇 추상화:
      - 메모리에서 좌표/상태값을 읽고
      - 입력을 보내 이동/행동한다.
    Among Us 예시 레지스트리를 기본값으로 포함함.
    """

    def __init__(self,
                 redis_host: str = 'localhost', 
                 redis_port: int = 6379, 
                 redis_password: str = None):
        self.camera = Camera()
        self.service = AmongUsReader()

        self.history = dict()
        players = self.service.list_players()
        self.round_offset = time.time()
        self.players_pos = dict()
        self.players_warm = dict()
        for p in players:
            self.players_warm[p.color_name] = True
            self.players_pos[p.color_name] = deque([(p.position, self.round_offset)])
            if p.is_local_player:
                continue
            clr = p.color_name
            self.history[clr] = [(0, "Cafeteria")] # history table. Everybody starts at Cafeteria

        self.dead_players = set()
        self.is_local_impostor = is_impostor()
        self._is_meeting = False
        self.caught_kill = False
        self.suspicious_player = None
        
        print(f"[InfoPipe] Redis 서버에 연결 시도... ({redis_host}:{redis_port})")
        try:
            self.redis = redis.Redis(
                host=redis_host,
                port=redis_port,
                password=redis_password,
                decode_responses=True  # <--- 바이트 대신 문자열로 자동 디코딩
            )
            self.redis.ping()
            print("[InfoPipe] Redis 연결 성공.")
        except redis.exceptions.ConnectionError as e:
            print(f"[InfoPipe] !!! Redis 연결 실패: {e}")
            print("[InfoPipe] !!! Redis 관련 기능이 작동하지 않습니다.")
            self.redis = None

        player_init_pipe = self.redis.pipeline() if self.redis else None
        
        colors = []
        for p in players:
            clr = p.color_name
            colors.append(clr)
            self.players_pos[clr] = deque([(p.position, self.round_offset)])
            if player_init_pipe:
                key = f"amongus:{clr}:is_dead"
                data = "False"
                player_init_pipe.set(key, data)
                
            self.history[clr] = [(0, "Cafeteria")]
            
            if p.is_local_player:
                if player_init_pipe:
                    key = f"amongus:{clr}:role"
                    data = "imposter" if self.is_local_impostor else "crewmate"
                    player_init_pipe.set(key, data)
            
            
        self.history["observed_kill"] = None

        if player_init_pipe:
            try:
                player_init_pipe.set("colors", json.dumps(colors))
                player_init_pipe.execute()
                print("[InfoPipe] Redis에 모든 플레이어 'alive' 플래그 초기화 완료.")
            except Exception as e:
                print(f"[InfoPipe] !!! 'alive' 플래그 초기화 실패: {e}")
        
    def get_screen(self, resize_to: Optional[Tuple[int, int]] = None):
        """
        현재 화면(BGR)을 Camera를 통해 받아온다.
        사용 예: frame = bot.get_screen();  # == bot.camera.get_screen()
        """
        return self.camera.get_screen(resize_to=resize_to)

    def get_seen_players(self) -> Tuple[list, list]:
        seens = []
        unseens = []

        p_me = self.service.get_local_player().position
        players = self.service.list_players()
        for p in players:
            if p.is_local_player:
                x, y = p.position
                # print(f"I'm at {place(x, y)} ({x, y})")
                continue
            pos = p.position
            if can_see(p_me, pos, self.is_local_impostor) and self.players_warm[p.color_name]:
                seens.append(p)
            else:
                unseens.append(p)

        return seens, unseens

    def update_info(self):
        """
        현재 observation을 기반으로
        1. 각 플레이어의 location table 추적
        """

        def closer(ref_pos, a_pos, b_pos):
            """
            a가 b보다 ref에 가까우면/같으면 True, 아니면 False
            """
            if ref_pos is None or a_pos is None or b_pos is None: return

            dist_with_a = (ref_pos[0] - a_pos[0])**2 + (ref_pos[1] - a_pos[1])**2
            dist_with_b = (ref_pos[0] - b_pos[0])**2 + (ref_pos[1] - b_pos[1])**2
            return dist_with_a <= dist_with_b

        cur = time.time()
        seens, unseens = self.get_seen_players()
        seens.append(self.service.get_local_player())
        for p in self.service.list_players():
            dq = self.players_pos[p.color_name]
            while len(dq) > 0 and cur - dq[0][1] > 3:
                dq.popleft()

            if not (len(dq) > 0 and dq[-1][0] == p.position):
                dq.append((p.position, cur))

        for seen in seens:
            table = self.history[seen.color_name]
            _, prev_place = table[-1]
            cur_place = place(*seen.position)
            is_seen_dead = seen.color_name in self.dead_players
            if is_seen_dead and self.players_warm[seen.color_name]:
                self.caught_kill = True # should be initialized after meeting
                self.suspicious_player = None
                for close_player in seens:
                    if close_player.color_id==self.service.get_local_player(): continue
                    if self.suspicious_player is None or closer(seen.position, self.suspicious_player.position, close_player.position):
                        self.suspicious_player = close_player
                
                self.players_warm[seen.color_name] = False
            if cur_place == prev_place:
                continue
            table.append((time.time() - self.round_offset, cur_place))

        for unseen in unseens:
            table = self.history[unseen.color_name]
            _, prev_place = table[-1]
            cur_place = "Unknown"
            is_unseen_dead = unseen.color_name in self.dead_players
            if is_unseen_dead:
                self.players_warm[unseen.color_name] = False
            if cur_place == prev_place:
                continue
            table.append((time.time() - self.round_offset, cur_place))

        # 1. 현재 미팅 상태 계산
        is_currently_meeting = True
        for clr, dq in self.players_pos.items():
            x, y = dq[-1][0]
            if place(x, y) != "Cafeteria":
                is_currently_meeting == False
                break
                
            if not dq: # 큐가 비어있으면 체크 불가
                is_currently_meeting = False
                break
            
            t_check = dq[-1][1] > self.round_offset + 10 # 최소 10초 경과
            s = set([x[0] for x in dq]) # 모든 플레이어 위치가 같은지
            if not (len(s) == 1 and t_check):
                is_currently_meeting = False
                break
            
        for player in self.service.list_players():
            is_dead, diag = get_player_death_status(self.service._ds, player.color_id)
            if is_dead:
                self.dead_players.add(player.color_name)

        if not is_currently_meeting and self._is_meeting:
            self.caught_kill = False

        # 2. 상태 전이(False -> True) 감지
        if is_currently_meeting and not self._is_meeting:
            print("[InfoPipe] ⭐️ 미팅 시작 감지! 히스토리를 Redis에 업로드합니다.")
            self._upload_history_to_redis()
        
        elif not is_currently_meeting and self._is_meeting:
            self.round_offset = time.time()
        
        # 3. 내부 상태 업데이트
        self._is_meeting = is_currently_meeting

    def _upload_history_to_redis(self):
        """
        (기존 코드)
        현재 `self.history` 상태를 Redis에 업로드합니다.
        """
        if not self.redis:
            print("[InfoPipe] (No Redis) 히스토리 업로드 스킵됨.")
            return

        try:
            pipe = self.redis.pipeline()
            loc_p = self.service.get_local_player()
            key = f"amongus:{loc_p.color_name}:observation"
            value = json.dumps(self.history)
            pipe.set(key, value)
            pipe.execute()
            print(f"[InfoPipe] Redis에 히스토리 업로드 완료.")
        except Exception as e:
            print(f"[InfoPipe] !!! Redis 히스토리 업로드 중 오류: {e}")

    # --- [신규 메서드 (Redis 리포트)] ---
    def _report_death_to_redis(self, color_name: str):
        """
        특정 플레이어의 사망을 Redis에 "False"로 기록합니다.
        """
        if not self.redis:
            print(f"[InfoPipe] (No Redis) {color_name} 사망 기록 스킵됨.")
            return
        
        try:
            key = f"amongus:player_alive:{color_name}"
            self.redis.set(key, "False") # 문자열 "False"로 저장
            print(f"[InfoPipe] Redis에 {color_name} 사망 기록 완료.")
        except Exception as e:
            print(f"[InfoPipe] !!! {color_name} 사망 기록 중 Redis 오류: {e}")
    
    def is_meeting(self):
        return self._is_meeting
    
# --- (자식 프로세스 실행 함수는 그대로 둡니다) ---
def _pipe_process(child_conn: Connection):
    """
    자식 프로세스에서 실행될 타겟 함수.
    [수정됨] 스스로 무한 루프를 돌며 정보를 수집하고,
    부모의 요청(interrupt)이 있는지 'poll'로 확인합니다.
    """
    print("[InfoPipe Process] 비동기 수집기 프로세스 시작됨.")
    pipe = InfoPipe(redis_host="134.185.110.57",
                    redis_port="16379",
                    redis_password="AmongSus")
    running = True
    update_freq = 0.01

    try:
        while running:
            # 1. (핵심) 스스로 정보를 계속 업데이트합니다.
            pipe.update_info()

            # 2. (핵심) 부모로부터 온 요청이 있는지 *기다리지 않고* 확인합니다.
            if child_conn.poll():
                # 요청이 있으면 recv()는 즉시 반환됩니다.
                try:
                    command, *args = child_conn.recv()
                except EOFError:
                    # 부모가 연결을 닫음
                    running = False
                    continue

                # 3. 요청 처리
                if command == "get_screen":
                    resize_to = args[0] if args else None
                    screen = pipe.get_screen(resize_to=resize_to)
                    child_conn.send(screen)
                    
                elif command == "get_seen_players":
                    result = pipe.get_seen_players()
                    child_conn.send(result)
                    
                elif command == "get_history":
                    # update_info()가 계속 갱신한 최신 히스토리 전송
                    child_conn.send(pipe.history)

                elif command == "get_dead_players":
                    child_conn.send(pipe.dead_players)

                elif command == "stop":
                    print("[InfoPipe Process] InfoPipe 프로세스 종료 신호 받음.")
                    child_conn.send("stopped")
                    running = False # 루프 탈출
                
                elif command == "is_meeting":
                    is_meeting = pipe.is_meeting()
                    child_conn.send(is_meeting)
                
                elif command == "set_freq":
                    update_freq = args[0]
                
                else:
                    child_conn.send(NotImplementedError(f"Unknown command: {command}"))

            # [선택적]
            # CPU 점유율이 100%로 치솟는 것을 방지하기 위해
            # 아주 짧은 sleep을 추가할 수 있습니다.
            # (게임 정보 갱신 주기와 AI의 요청 빈도에 따라 조절)
            time.sleep(update_freq) # 1ms (CPU 부담 완화)

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[InfoPipe Process] 오류 발생: {e}")
        raise e
    finally:
        child_conn.close()
        print("[InfoPipe Process] InfoPipe 프로세스 종료됨.")


# -------------------- 래퍼 클래스 (신규 추가) --------------------
class PipeController:
    """
    InfoPipe 프로세스와의 통신(send/recv)을 래핑하여
    간편한 메서드 기반 인터페이스를 제공합니다.

    `with` 구문과 함께 사용하는 것을 권장합니다.
    """
    def __init__(self, pipe_connection: Connection, freq: float = 0.01):
        if pipe_connection is None:
            raise ValueError("Pipe connection cannot be None")
        self.pipe = pipe_connection
        self._closed = False
        self.update_freq = freq
    
    def set_freq(self):
        """자식 프로세스의 update_info frequency를 설정합니다"""
        if self._closed:
            raise RuntimeError("Pipe is already closed")
        self.pipe.send(("set_freq", self.update_freq))
        return self.pipe.recv()

    def get_screen(self, resize_to: Optional[Tuple[int, int]] = None):
        """InfoPipe에 화면 캡처를 요청하고 스크린샷(numpy 배열)을 받습니다."""
        if self._closed:
            raise RuntimeError("Pipe is already closed")
        self.pipe.send(("get_screen", resize_to))
        return self.pipe.recv()

    def get_seen_players(self) -> Tuple[List, List]:
        """InfoPipe에 현재 시야 내/외 플레이어 목록을 요청합니다."""
        if self._closed:
            raise RuntimeError("Pipe is already closed")
        self.pipe.send(("get_seen_players",))
        return self.pipe.recv()

    def get_history(self) -> Dict:
        """InfoPipe에 현재까지의 플레이어 위치 히스토리를 요청합니다."""
        if self._closed:
            raise RuntimeError("Pipe is already closed")
        self.pipe.send(("get_history",))
        return self.pipe.recv()

    def get_dead_players(self) -> List:
        if self._closed:
            raise RuntimeError("Pipe is already closed")
        self.pipe.send(("get_dead_players"))
        return self.pipe.recv()        

    def close(self):
        """InfoPipe 프로세스에 종료 명령을 보내고 파이프를 닫습니다."""
        if self._closed:
            return  # 이미 닫혔으면 아무것도 하지 않음

        try:
            print("[PipeController] InfoPipe 프로세스에 종료를 요청합니다...")
            self.pipe.send(("stop",))
            response = self.pipe.recv()
            print(f"[PipeController] 종료 응답 수신: {response}")
        except EOFError:
            # 자식 프로세스가 이미 (오류 등으로) 종료된 경우
            print("[PipeController] 파이프가 이미 닫혀있습니다 (EOFError).")
        except Exception as e:
            print(f"[PipeController] 종료 중 오류 발생: {e}")
            raise e
        finally:
            self.pipe.close()
            self._closed = True
            print("[PipeController] 파이프를 닫았습니다.")

    def is_meeting(self) -> bool:
        """InfoPipe에 현재 미팅(회의) 상태를 요청합니다."""
        if self._closed:
            raise RuntimeError("Pipe is already closed")
        self.pipe.send(("is_meeting",))
        return self.pipe.recv()

    def __enter__(self):
        """'with' 구문 진입 시 자신을 반환합니다."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """'with' 구문 탈출 시 자동으로 close()를 호출합니다."""
        self.close()

    def __del__(self):
        """
        객체가 소멸될 때 (프로그램 종료 시 등)
        close가 호출되지 않았다면 시도합니다.
        (단, 'with'나 명시적 .close() 사용 권장)
        """
        if not self._closed:
            print("[PipeController] 경고: 파이프가 자동으로 닫힙니다 (close() 명시적 호출 권장).")
            self.close()


# -------------------- (pipewrapper는 그대로 둡니다) --------------------
def pipewrapper() -> Connection:
    """
    InfoPipe를 실행하는 별도 프로세스를 생성하고,
    메인 프로세스와 통신할 수 있는 파이프(Connection 객체)를 반환합니다.
    """
    parent_conn, child_conn = mp.Pipe()
    p = mp.Process(target=_pipe_process, args=(child_conn,))
    p.start()
    return parent_conn


# -------------------- 사용 예 (수정됨) --------------------
if __name__ == "__main__":

    print("[Main Process] InfoPipe 프로세스를 시작합니다...")

    # 'with' 구문을 사용하면 블록이 끝날 때
    # controller.close()가 자동으로 호출되어 매우 편리합니다.
    try:
        with PipeController(pipewrapper(), freq=0.01) as controller:
            # 2. 현재 히스토리 정보 요청
            print("\n[Main Process] 현재 히스토리 정보를 요청합니다...")
            # .get_history() 메서드 호출
            history = controller.get_history()
            print(f"[Main Process] 받은 히스토리 (키 개수: {len(history)})")
            # print(history) # (너무 길면 주석 처리)

            # 3. 화면 캡처 요청 (800x600 리사이즈)
            print("\n[Main Process] 화면 캡처를 요청합니다...")
            # .get_screen() 메서드 호출
            screen = controller.get_screen(resize_to=(800, 600))
            print(f"[Main Process] 화면 수신 완료. 크기: {screen.shape}")

    except Exception as e:
        print(f"[Main Process] 메인 프로세스 오류: {e}")

    print("\n[Main Process] 'with' 블록 종료. (컨트롤러가 자동으로 닫혔습니다)")
    print("[Main Process] 메인 프로세스 종료.")