import os
import json
from copy import deepcopy

JSON_PATH = r"C:\repositories\ist-tech-proj\graph_builder\tasks-json\SHIP_TASK_TYPES.json"
OUTPUT_PATH = r"C:\repositories\ist-tech-proj\graph_builder\amongus_reader_2.2\tools\position_jungsanghwaed\SHIP_TASK_TYPES.json"

with open(JSON_PATH, 'r') as f:
    task_data = json.load(f)

new_data = {}

for task_name, subtree in task_data.items():
    new_data[task_name] = {}
    for task_location, task_pos in subtree.items():
        x, y = task_pos
        new_data[task_name][task_location] = [x, y + 0.4]
    

os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
with open(OUTPUT_PATH, 'w') as f:
    json.dump(new_data, f)