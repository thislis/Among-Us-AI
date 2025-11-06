# AmongUsReader 사용 가이드 (한글)

이 문서는 `amongus_reader` 패키지를 처음 사용하는 분들을 위해 설치부터 기본 사용법, 캐시 구조, 예제, 문제 해결까지 한눈에 정리했습니다.

- 대상: Windows + Python 환경에서 어몽어스(Among Us) 실시간 데이터(플레이어/좌표/태스크/HUD 등)를 읽고자 하는 개발자
- 권장 버전: Python 3.9+ / Among Us 프로세스명 `Among Us.exe`

## 1. 사전 준비
- Windows에서 Among Us를 실행합니다.
- Python 3.9 이상이 설치되어 있어야 합니다.
- 관리자 권한으로 실행하면 프로세스 메모리 접근 안정성이 좋아집니다.

## 2. 설치
- 필수 패키지
  - `pymem` (프로세스 메모리 접근)
- 선택 패키지
  - `networkx` (그래프 gpickle을 사용할 경우)

```bash
pip install pymem networkx
```

## 3. 패키지 개요
- 진입점(퍼사드): `amongus_reader.service.AmongUsReader`
- 리더(Readers): `players`, `tasks`, `hud` 모듈이 퍼사드 내부에서 사용됩니다.
- 캐시: 데이터 타입별 TTL/스냅샷/부분 무효화 지원
- 메타/스캐너: IL2CPP 메타 인덱스와 스캐너를 통해 클래스/필드 탐색
- 메타데이터 위치 우선순위
  1) `amongus_reader/Il2cpp_result/metadata.json`
  2) 리포지토리 루트 `Il2cpp_result/metadata.json`

구조 상세는 `docs/amongus_reader_structure.md`를 참고하세요.

## 4. 빠른 시작(Quickstart)
```python
from amongus_reader.service import AmongUsReader

r = AmongUsReader(process_name="Among Us.exe", debug=False)
r.attach()
try:
    # 로컬 플레이어 정보
    local_player = r.get_local_player()
    local_color_id = local_player.color_id if local_player else None

    # 모든 플레이어 좌표(초고속 per-call 경로, color_id를 키로 사용)
    pos_map = r.positions()
    my_pos = pos_map.get(local_color_id) if local_color_id is not None else None

    # 색상 이름 매핑 (color_id를 키로 사용)
    colors = r.colors()

    # 태스크 (로컬 플레이어 기준 예시, color_id 사용)
    tasks = r.get_tasks(local_color_id) if local_color_id is not None else []

    # HUD Report 버튼 활성 여부(진단 포함)
    active, diag = r.is_report_active()

    print("local_color_id:", local_color_id)
    print("my_pos:", my_pos)
    print("colors:", colors)
    print("tasks_count:", len(tasks))
    print("report_active:", active)
finally:
    r.detach()
```

### 4.1 세션 상태/맵 판별

AmongUsReader는 이제 안전한 세션 판별 API를 다시 제공합니다. 원격 icall 없이 `GameData`, `HUD`, `PlayerControl` 신호를 조합해 화면 상태를 추론합니다.

```python
from amongus_reader.service import AmongUsReader

r = AmongUsReader(process_name="Among Us.exe", debug=False)
r.attach()
try:
    state = r.get_session_state()          # "LOBBY" | "MATCHING" | "SHIP"
    print("state:", state)

    if state == "SHIP":
        # 맵을 식별할 수 있으면 구체적인 이름(SKELD/…)을 돌려줍니다.
        print("map:", r.get_current_map_name())

    # 진단 정보가 필요하다면 스냅샷 인터페이스를 활용하세요.
    state, snapshot = r.get_session_snapshot()
    print("diagnostics:", snapshot)
finally:
    r.detach()
```

- `get_session_state()`는 `LOBBY`, `MATCHING`, `SHIP` 중 하나를 반환합니다.
- `get_current_map_name()`은 SHIP 상태일 때 가능한 경우 맵명을 돌려주고, 그렇지 않으면 세션 상태 문자열을 그대로 반환합니다.
- `get_session_snapshot()`은 (상태, 신호 dict)을 반환해 휴리스틱을 튜닝할 때 유용합니다.

보조 디버깅 스크립트는 `Archive/session_debug/` 아래에 보관되어 있습니다. 예를 들어 콘솔에서 상태만 모니터링하려면 다음을 사용할 수 있습니다.

```bash
python Archive/session_debug/detect_session_state.py --verbose
```

## 5. 주요 API 한눈에 보기
- 세션/디버그
  - `attach(process_name=None) -> bool`
  - `detach() -> None`
  - `is_attached() -> bool`
  - `enable_debug(enabled: bool) -> None`
- 캐시/갱신
  - `refresh(types: list[str] | None = None, force: bool = False) -> None`
  - `invalidate(types: list[str] | None = None) -> None`
  - `snapshot(types: list[str] | None = None) -> dict`
  - `configure_hud(min_interval: float | None, time_budget: float | None) -> None`
  - `configure_players(pc_map_ttl: float | None) -> None`
  - `invalidate_players_pc_map() -> None`
- 플레이어/좌표/색상
  - `list_players() -> list[PlayerData]`
  - `get_local_player() -> PlayerData | None`
  - `get_local_player_id() -> int | None`
  - `get_player(color_id: int | ColorId) -> PlayerData | None`  (color_id 기반)
  - `find_player_by_color(color_id: int | ColorId) -> PlayerData | None`
  - `positions() -> dict[int, tuple[float,float]]`  (초고속 per-call 경로, color_id를 키로 사용)
  - `colors() -> dict[int, str]`  (color_id를 키로 사용)
  - `count() -> int`
- 태스크
  - `get_tasks(color_id: int | ColorId) -> list[TaskData]`  (color_id 기반)
  - `get_task_panel(color_id: int | ColorId | None = None, include_completed: bool = False) -> list[TaskPanelEntry]`  (color_id 기반)
- HUD/Report
  - `is_report_active() -> tuple[bool | None, dict]`  (진단 포함)

자세한 설명은 `docs/amongus_reader_api_design.md`를 참고하세요.

## 6. 캐시와 갱신 전략
- Per-call(즉시): `positions()`는 PlayerControl 포인터 맵(기본 TTL 1.0s)을 활용해 좌표만 빠르게 읽습니다. color_id를 키로 사용하는 딕셔너리를 반환합니다.
- Periodic(TTL): `players`, `colors`, `tasks`, `hud`는 타입별 TTL로 갱신됩니다(기본 예: players 0.15s, colors 1.0s, tasks 3.0s, hud 1.5s).
- 명시적 제어:
```python
# 선택 타입 강제 리프레시
r.refresh(types=["players", "colors"], force=False)

# 선택 타입 무효화
r.invalidate(types=["tasks"])  # 다음 접근 시 lazy fetch

# 스냅샷 취득
data = r.snapshot(["players", "colors"]) 
```
- 리더 설정:
```python
# HUD 스캔 최소 간격/타임버짓 조정
r.configure_hud(min_interval=2.0, time_budget=0.15)

# 좌표 빠른경로의 포인터맵 TTL 조정 및 무효화
r.configure_players(pc_map_ttl=0.5)
r.invalidate_players_pc_map()
```

## 7. 실용 예제
### 7.1 로컬 플레이어 좌표를 주기적으로 출력
```python
from amongus_reader.service import AmongUsReader
import time

r = AmongUsReader()
r.attach()
try:
    while True:
        local_player = r.get_local_player()
        if local_player:
            pos = r.positions().get(local_player.color_id)
            print(pos)
        time.sleep(0.5)
except KeyboardInterrupt:
    pass
finally:
    r.detach()
```

### 7.2 현재 맵(LOBBY/SHIP) 분류하여 출력(선택, 그래프 필요)
- `graphs/LOBBY_G.pkl`, `graphs/SHIP_G.pkl`가 있을 때 사용 가능한 휴리스틱 예제입니다.
- `networkx`가 없으면 `pickle`로 읽도록 폴백합니다.

```python
import os, pickle, time
from amongus_reader.service import AmongUsReader

# 그래프 노드 좌표 읽기
def load_graph_nodes(path: str):
    try:
        import networkx as nx
        G = nx.read_gpickle(path)
    except Exception:
        with open(path, 'rb') as f:
            G = pickle.load(f)
    nodes = [d.get('pos') for _, d in G.nodes(data=True) if isinstance(d.get('pos'), tuple)]
    return [(float(x), float(y)) for (x, y) in nodes]

base = os.path.dirname(__file__)
LOBBY = load_graph_nodes(os.path.join(base, 'graphs', 'LOBBY_G.pkl'))
SHIP  = load_graph_nodes(os.path.join(base, 'graphs', 'SHIP_G.pkl'))

# 가장 가까운 그래프에 매칭
def detect_map(pos):
    if pos is None:
        return 'Unknown'
    def best(nodes):
        if not nodes:
            return float('inf')
        x, y = float(pos[0]), float(pos[1])
        return min((x-nx)*(x-nx) + (y-ny)*(y-ny) for nx, ny in nodes)
    return 'LOBBY' if best(LOBBY) <= best(SHIP) else 'SHIP'

r = AmongUsReader(); r.attach()
try:
    while True:
        local_player = r.get_local_player()
        p = r.positions().get(local_player.color_id) if local_player else None
        print(detect_map(p))
        time.sleep(0.5)
except KeyboardInterrupt:
    pass
finally:
    r.detach()
```

### 7.3 로컬 임포스터 여부 판독
```python
from amongus_reader.service import AmongUsReader

r = AmongUsReader(); r.attach()
try:
    flag, diag = r.is_local_impostor()
    if flag is None:
        print("local_is_impostor=Unknown", diag)
    else:
        print(f"local_is_impostor={flag}")
        print("diagnostics:", diag)
finally:
    r.detach()
```

### 7.4 HUD Report 버튼 활성 상태와 진단
```python
from amongus_reader.service import AmongUsReader

r = AmongUsReader(); r.attach()
try:
    active, diag = r.is_report_active()
    print(active, diag)
finally:
    r.detach()
```

### 7.5 특정 플레이어의 태스크 목록 출력
```python
from amongus_reader.service import AmongUsReader

r = AmongUsReader(); r.attach()
try:
    for p in r.list_players():
        tasks = r.get_tasks(p.color_id)
        print(f"{p.color_name} (color_id: {p.color_id})", [(t.task_id, t.task_type_id, t.is_completed) for t in tasks])
finally:
    r.detach()
```

### 7.6 인게임 패널과 유사한 태스크 요약 가져오기
```python
from amongus_reader.service import AmongUsReader

r = AmongUsReader(); r.attach()
try:
    panel = r.get_task_panel()  # 기본: 로컬 플레이어, 미완료 태스크만
    for entry in panel:
        print(entry.display_text())      # "Storage: Fix Wiring (0/3)" 형식
        print("  id/type:", entry.task_id, entry.task_type_id)
        print("  좌표:", entry.coordinates)
finally:
    r.detach()
```
`TaskPanelEntry` 객체는 `room`, `task_name`, `completed_steps`, `total_steps`, `task_id`, `task_type_id`, `coordinates` 등의 속성을 제공합니다. `include_completed=True` 로 전달하면 완료된 태스크도 포함할 수 있습니다.
service/task_lookup.py에서 태스크의 위치와 이름을 변경할 수 있습니다.

### 7.7 다른 플레이어의 사망 여부 모니터링 (color_id 기반)
`tools/check_player_death.py` 스크립트는 `NetworkedPlayerInfo`의 RoleType 필드를 활용해 각 플레이어의 사망 여부를 안정적으로 판독합니다. 기본 사용법은 아래와 같습니다.

```bash
# 한 번만 확인
python tools/check_player_death.py --once

# 특정 color_id만 확인
python tools/check_player_death.py --once --color-id 0

# 주기적으로 모니터링 (Ctrl+C 로 종료)
python tools/check_player_death.py
```

코드에서 직접 사용하려면 `get_player_death_status()`를 임포트하면 됩니다.

```python
from tools.check_player_death import get_player_death_status
from amongus_reader.service import AmongUsReader

reader = AmongUsReader(); reader.attach()
try:
    target_color = 0  # 예: Red
    is_dead, diag = get_player_death_status(reader._ds, target_color)

    if is_dead is None:
        print("읽기 실패", diag.get("error"))
    elif is_dead:
        print("플레이어가 사망했습니다")
    else:
        print("플레이어가 생존 중입니다")
finally:
    reader.detach()
```

RoleType을 기반으로 판독하기 때문에 임포스터/서포터 등 확장 역할이 있어도 `CrewmateGhost`, `ImpostorGhost`, `GuardianAngel` 로 전환된 순간 사망으로 처리됩니다. 진단 딕셔너리에는 `role_snapshot`, `dead_role_colors`, `impostor_role_colors` 등이 포함되어 있어 디버깅에 활용할 수 있습니다.

## 8. 문제 해결
- `attach()` 실패
  - Among Us가 실행 중인지 확인하고, 관리자 권한으로 재시도하세요.
- 데이터가 간헐적으로 `None`/빈 값
  - 메모리 읽기 실패는 일시적으로 발생할 수 있습니다. API는 가능한 값만 반환합니다.
  - `refresh()`/`invalidate()`를 적절히 사용해 보세요.
- HUD 스캔이 느리거나 빈번
  - `configure_hud(min_interval, time_budget)`로 스로틀링/타임버짓을 조정하세요.

## 9. 제약/주의
- 현재 퍼사드 1차 범위에는 임포스터/사망 여부 등 고급 판독이 포함되어 있지 않습니다(향후 확장 예정).
- 레거시 코드(Archive/*)는 참고 전용이며 직접 사용/수정하지 않는 것을 권장합니다.

## 10. 참고 문서
- 설계/API 표면: `docs/amongus_reader_api_design.md`
- 포함 기능 개요: `docs/amongus_reader_feature_inventory.md`
- 패키지 구조/임포트: `docs/amongus_reader_structure.md`
