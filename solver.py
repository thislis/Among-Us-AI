import info_pipe
import utility
import subprocess
import time
import pyautogui
import random
import sys, os
import keyboard
from utils.task_utility import get_dimensions, get_screen_coords, wake

PYTHON_PATH = os.path.join(
    os.path.abspath(os.path.dirname(__file__)), r".venv\Scripts\python.exe"
)
SOLVER_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), r"task_solvers")

cols_dict = {
    "RED": (208, 68, 74),
    "BLUE": (62, 91, 234),
    "GREEN": (55, 156, 95),
    "PINK": (241, 123, 217),
    "ORANGE": (241, 156, 70),
    "YELLOW": (241, 246, 130),
    "BLACK": (97, 111, 122),
    "WHITE": (223, 240, 251),
    "PURPLE": (134, 91, 214),
    "BROWN": (138, 110, 83),
    "CYAN": (95, 245, 245),
    "LIME": (108, 244, 107),
    "MAROON": (121, 75, 95),
    "ROSE": (241, 213, 236),
    "BANANA": (239, 244, 199),
    "GRAY": (142, 162, 181),
    "TAN": (162, 163, 156),
    "CORAL": (226, 136, 144),
    "GREY": (142, 162, 181),
    "SKIP": (),
}


def col_diff(col1: tuple, col2: tuple) -> int:
    return abs(col1[0] - col2[0]) + abs(col1[1] - col2[1]) + abs(col1[2] - col2[2])


def find_col_pos(dimensions, col: str):
    x = dimensions[0] + round(dimensions[2] / 7.38)
    y = dimensions[1] + round(dimensions[3] / 4.30)

    x_offset = round(dimensions[2] / 3.68)
    y_offset = round(dimensions[3] / 7.88)

    for i in range(3):
        for j in range(5):
            pixel = pyautogui.pixel(x + x_offset * i, y + y_offset * j)
            if col != "SKIP" and col_diff(cols_dict[col], pixel) < 30:
                return (x + x_offset * i, y + y_offset * j)
    return None


def vote(color: str = "SKIP"):
    dimensions = get_dimensions()
    x = dimensions[0] + round(dimensions[2] / 1.12)
    y = dimensions[1] + round(dimensions[3] / 19.6)
    wake()
    time.sleep(0.1)

    pos = find_col_pos(dimensions, color)
    if pos is None:
        # skip
        time.sleep(0.3)
        pyautogui.click(
            dimensions[0] + round(dimensions[2] / 6.74),
            dimensions[1] + round(dimensions[3] / 1.15),
            duration=0.2,
        )
        time.sleep(0.3)
        pyautogui.click(
            dimensions[0] + round(dimensions[2] / 3.87),
            dimensions[1] + round(dimensions[3] / 1.17),
            duration=0.2,
        )
    else:
        pyautogui.click(pos, duration=0.2)
        pyautogui.click(pos[0] + round(dimensions[2] / 8.07), pos[1], duration=0.2)


def generate_files():
    possible_tasks = utility.load_dict().keys()
    for task in possible_tasks:
        with open(os.path.join(SOLVER_PATH, f"{task}.py"), "w") as f:
            f.close()


def chat(can_vote_flag: bool):
    if utility.isDead():
        print("chat dead cycle")
        while utility.in_meeting():
            if keyboard.is_pressed("`"):
                raise SystemExit(0)
            time.sleep(1 / 60)
            continue
        time.sleep(10)
        return

    print("회의 시간을 대기합니다...")
    time.sleep(25)

    print("회의 시작. 투표 신호를 대기합니다...")
    player_color = utility.getGameData()["color"]
    controller = info_pipe.get_controller()
    vote_color = controller.get_vote_info(player_color)
    print(f"초기 투표 신호: {vote_color}")
    while vote_color not in cols_dict.keys() and utility.in_meeting():
        if keyboard.is_pressed("`"):
            raise SystemExit(0)
        time.sleep(1 / 60)
        vote_color = controller.get_vote_info(player_color)

    # 스킵 투표 스크립트 실행
    print("투표 신호를 받아 투표를 실행합니다...", vote_color)
    vote(vote_color)

    while utility.in_meeting():
        if keyboard.is_pressed("`"):
            raise SystemExit(0)
        time.sleep(1 / 60)


def solve_task(task_name=None, task_location=None) -> int:
    """
    Runs the correct task solver file in a subprocess

    Note - the AI only goes to the upper location of sabotages

    Returns
    --------
    int
        0 if success

        1 if meeting was called or died

        2 if a meeting was called and the task was inspect sample (so it doesn't wait later)

        -1 if task not found
    """
    print(f"solving task: {task_name} at {task_location}")
    dead: bool = utility.isDead()
    if task_name == "vote":
        print("Should never be here")
        if not dead:
            p = subprocess.Popen([PYTHON_PATH, os.path.join(SOLVER_PATH, "vote.py")])
        else:
            return 0
        p.wait()
        return 0

    if utility.isImpostor():
        # Record last task done
        if not utility.isDead():
            with open("last_task.txt", "w") as f:
                f.write(f"{task_name} in {task_location}")
            f.close()
        time.sleep(1.5)
        urgent = utility.is_urgent_task()
        if urgent is None:
            return 0
            # # Open solver file
            # if random.randint(1,3) % 3 == 0:
            #     p = subprocess.Popen([PYTHON_PATH, os.path.join(SOLVER_PATH, "Sabotage.py")])
            # else:
            #     return 0
        else:
            if utility.in_meeting():
                return 1
            return 0

        # Wait for process to finish
        while p.poll() is None:
            if utility.in_meeting() or keyboard.is_pressed("`"):
                p.kill()
                return 1
            time.sleep(1 / 30)

        time.sleep(3)  # Fake doing stuff
        return 0

    if utility.is_urgent_task() is not None:
        if task_name is not None and task_name != utility.is_urgent_task()[0]:
            return 1

    if task_name is not None and task_name != ():
        # Record last task done
        with open("last_task.txt", "w") as f:
            f.write(f"{task_name} in {task_location}")
        f.close()

        # Open solver file
        comm = [PYTHON_PATH, f"{os.path.join(SOLVER_PATH, f'{task_name}.py')}"]
        print(" ".join(comm))
        p = subprocess.Popen(comm)

        # Wait for process to finish
        while p.poll() is None:
            if (
                utility.in_meeting()
                or (utility.isDead() != dead)
                or keyboard.is_pressed("`")
            ):
                p.kill()
                if task_name == "Inspect Sample" or task_name == "Reboot Wifi":
                    return 2
                else:
                    return 1
            time.sleep(1 / 30)

        if task_name == "Inspect Sample" or task_name == "Reboot Wifi":
            return 2
        else:
            return 0

    print("Task not found")
    return -1
