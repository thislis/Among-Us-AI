import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../utils')))
import time
from task_utility import *
import pyautogui

click_use()
time.sleep(0.8)

dim = get_dimensions()

x = dim[0] + round(dim[2] / 1.64)
y = dim[1] + round(dim[3] / 4.54)

y2 = dim[1] + round(dim[3] / 1.26)
pyautogui.moveTo(x,y)
pyautogui.dragTo(x, y2, duration=0.8)

click_close()
time.sleep(1.0)
raise SystemExit(0)