import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../utils')))
from task_utility import *
import time
import pyautogui

click_use()
time.sleep(0.8)

dimensions = get_dimensions()
resize_images(dimensions, "Inspect Sample")

x = dimensions[0] + round(dimensions[2] / 1.52)
y = dimensions[1] + round(dimensions[3] / 1.16)

y_offset = dimensions[3]
dimensions[0] += round(dimensions[2] / 2.81)
dimensions[1] += round(dimensions[3] / 3.2)
dimensions[2] = round(dimensions[2] / 3.4)
dimensions[3] = round(dimensions[3] / 3.6)

pos = None
while pos is None:
    try:
        pos = pyautogui.locateCenterOnScreen(f"{get_dir()}\\task_solvers\\cv2-templates\\Inspect Sample resized\\anomaly.png", confidence=0.5, region=dimensions)4
        print("yeah!! pos found:", pos)
    except:
        print("waiting...")
        time.sleep(5)
pyautogui.click(pos[0], pos[1] + round(y_offset / 2.87))
print("clicked anomaly")
time.sleep(1.0)
print("shit?")