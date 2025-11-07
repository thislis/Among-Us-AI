import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../utils')))
from task_utility import *
import time

click_use()
time.sleep(0.8)

while not is_task_done("Submit Scan"):
    time.sleep(1/60)
time.sleep(1.0)