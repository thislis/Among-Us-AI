from PIL import ImageGrab
import ctypes
import win32gui
import pyautogui
import numpy as np
import cv2
import os
import sys
import pydirectinput

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from wake_keyboard import wake
from PIL import Image

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from amongus_reader import AmongUsReader
from amongus_reader.service.task_lookup import TASK_TYPE_NAMES
from amongus_reader.tools.check_player_death import get_player_death_status
from locator import place
from is_impostor import is_impostor

ctypes.windll.user32.SetProcessDPIAware()

service = AmongUsReader()
# service: AmongUsReader = None

def initialize_service():
    pass
    # global service
    # if service is None:
    #     print("[Utility] AmongUsReader를 초기화합니다...")
    #     service = AmongUsReader()

def close_service():
    pass
    # global service
    # if service:
    #     print("[Utility] AmongUsReader를 닫습니다...")
    #     service.detach()
    #     service = None

def get_service() -> AmongUsReader:
    """AmongUsReader 서비스에 접근할 때 사용하는 함수."""
    global service
    return service

with open("sendDataDir.txt") as f:
    line = f.readline().rstrip()
    SEND_DATA_PATH = line + "\\sendData.txt"

SABOTAGE_TASKS = ["Reset Reactor", "Fix Lights", "Fix Communications", "Restore Oxygen"]

def getGameData():
    service = get_service()
    player = service.get_local_player()
    position = player.position
    # status = "impostor" if is_impostor() else "crewmate"
    status = "shibal"
    tasks_info = service.get_tasks(player.color_id)
    tasks = [TASK_TYPE_NAMES[t.task_type_id] for t in tasks_info]
    task_locations = [t.location for t in tasks_info]
    task_steps = [f"{t.step}/{t.max_step}" for t in tasks_info]
    task_completed = [t.is_completed for t in tasks_info]
    map_id = "SHIP"
    dead = False # TODO: implement death status
    room = place(*position)

    return {
        "position": position,
        "status": status,
        "tasks": tasks,
        "task_locations": task_locations,
        "task_steps": task_steps,
        "task_completed": task_completed,
        "map_id": map_id,
        "dead": dead,
        "room": room
    }

def get_screenshot(dimensions=None, window_title="Among Us"):
    if window_title:
        hwnd = win32gui.FindWindow(None, window_title)
        if hwnd and not dimensions:
            win32gui.SetForegroundWindow(hwnd)
            x, y, x1, y1 = win32gui.GetClientRect(hwnd)
            x, y = win32gui.ClientToScreen(hwnd, (x, y))
            x1, y1 = win32gui.ClientToScreen(hwnd, (x1 - x, y1 - y))
            im = pyautogui.screenshot(region=(x, y, x1, y1))
            return im
        elif dimensions:
            im = pyautogui.screenshot(region=dimensions)
            return im
        else:
            print('Window not found!')
    else:
        im = pyautogui.screenshot()
        return im

def get_dimensions():
    window_title="Among Us"
    hwnd = win32gui.FindWindow(None, window_title)
    if hwnd:
        win32gui.SetForegroundWindow(hwnd)
        x, y, x1, y1 = win32gui.GetClientRect(hwnd)
        x, y = win32gui.ClientToScreen(hwnd, (x, y))
        x1, y1 = win32gui.ClientToScreen(hwnd, (x1 - x, y1 - y))
        return[x,y,x1,y1]
    else:
        print('Window not found!')

def click_use():
    wake()
    dim = get_dimensions()
    pydirectinput.moveTo(dim[0] + dim[2] - round(dim[2] / 13), dim[1] + dim[3] - round(dim[3] / 7))
    pydirectinput.click()
    return

def resize_images(dimensions, task_name):
    if task_name == "Unlock Manifolds":
        for i in range(1,11):
            loaded_img = Image.open(f"{get_dir()}\\task_solvers\\cv2-templates\\{task_name}\\{i}.png")
            new_img = loaded_img.resize((round(loaded_img.width * (dimensions[2] / 1920)), round(loaded_img.height*(dimensions[3] / 1080))))
            new_img.save(f"{get_dir()}\\task_solvers\\cv2-templates\\{task_name} resized\\{i}.png")
            
    elif task_name == "Fix Wiring":
        wire_colors = ["red", "blue", "yellow", "pink"]
        for color in wire_colors:
            loaded_img = Image.open(f"{get_dir()}\\task_solvers\\cv2-templates\\{task_name}\\{color}Wire.png")
            new_img = loaded_img.resize((round(loaded_img.width * (dimensions[2] / 1920)), round(loaded_img.height*(dimensions[3] / 1080))))
            new_img.save(f"{get_dir()}\\task_solvers\\cv2-templates\\{task_name} resized\\{color}Wire.png")

    elif task_name == "Stabilize Steering":
        loaded_img = Image.open(f"{get_dir()}\\task_solvers\\cv2-templates\\{task_name}\\crosshair.png")
        new_img = loaded_img.resize((round(loaded_img.width * (dimensions[2] / 1920)), round(loaded_img.height*(dimensions[3] / 1080))))
        new_img.save(f"{get_dir()}\\task_solvers\\cv2-templates\\{task_name} resized\\crosshair.png")

    elif task_name == "Inspect Sample":
        loaded_img = Image.open(f"{get_dir()}\\task_solvers\\cv2-templates\\{task_name}\\anomaly.png")
        new_img = loaded_img.resize((round(loaded_img.width * (dimensions[2] / 1920)), round(loaded_img.height*(dimensions[3] / 1080))))
        new_img.save(f"{get_dir()}\\task_solvers\\cv2-templates\\{task_name} resized\\anomaly.png")

    elif task_name == "close":
        loaded_img = Image.open(f"{get_dir()}\\task_solvers\\cv2-templates\\{task_name}\\closeX.png")
        new_img = loaded_img.resize((round(loaded_img.width * (dimensions[2] / 1920)), round(loaded_img.height*(dimensions[3] / 1080))))
        new_img.save(f"{get_dir()}\\task_solvers\\cv2-templates\\{task_name} resized\\closeX.png")


def get_dir():
    return os.getcwd()

def click_close():
    wake()
    dim = get_dimensions()
    resize_images(dim, "close")
    center = pyautogui.locateCenterOnScreen(f"{get_dir()}\\task_solvers\\cv2-templates\\close resized\\closeX.png", confidence=0.7, grayscale=True)
    pydirectinput.moveTo(center[0], center[1])
    pydirectinput.click()
    return

def get_screen_coords():
    while True:
        print(pyautogui.position(), end='\r')

def get_screen_ratio(dim):
    while True:
        print(round(abs(dim[2] / (pyautogui.position().x - dim[0])), 2), round(abs(dim[3] / (pyautogui.position().y - dim[1])), 2), end='\r')

def is_task_done(task):
    data = getGameData()

    try:
        if task in SABOTAGE_TASKS:
            if task in data["tasks"]:
                return False
            return True

        index = data["tasks"].index(task)
        return data["task_completed"][index]
        # steps = data["task_steps"][index].split('/')
        # return steps[0] == steps[1]
        
    # Index error on new ver
    except (IndexError, ValueError) as e:
        if task == "Reset Reactor" or task == "Reset Seismic Stabilizers":
            return not ("Reset Reactor" in data["tasks"] or "Reset Seismic Stabilizers" in data["tasks"])
        print("Index / Value error")
        print(task)
        print(data["tasks"])
        print(data["task_steps"])
        print(e)
        return False

def isDead() -> bool:
    dimensions = get_dimensions()
    x = dimensions[0] + round(dimensions[2] / 1.19)
    y = dimensions[1] + round(dimensions[3] / 1.17)
    col = pyautogui.pixel(x, y)
    # print(f"Dead pixel color: {col}")
    # print(f"Is dead: {col[0] == 8 and col[1] == 105 and col[2] == 206}")
    return col[0] == 8 and col[1] == 105 and col[2] == 206

def is_urgent_task() -> bool:
    data = getGameData()
    if isDead():
        return False

    urgent_tasks = ["Reset Reactor", "Restore Oxygen", "Reset Seismic Stabilizers"]
    for task in urgent_tasks:
        if task in data['tasks']:
            return True
    return False            