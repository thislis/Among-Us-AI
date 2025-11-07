import os
import pickle
import networkx as nx
import json
from copy import deepcopy

JSON_PATH = r"C:\repositories\ist-tech-proj\graph_builder\amongus_reader_2.2\tools\position_jungsanghwaed\SHIP_TASK_TYPES.json"
GRAPH_PATH = r"C:\repositories\ist-tech-proj\graph_builder\amongus_reader_2.2\tools\graph_exported_old\SHIP_G.pkl"
OUTPUT_PATH = r"C:\repositories\ist-tech-proj\graph_builder\amongus_reader_2.2\tools\graph_exported_old\SHIP_G_jungsanghwaed.pkl"

with open(JSON_PATH, 'r') as f:
    task_data = json.load(f)

with open(GRAPH_PATH, 'rb') as f:
    G = pickle.load(f)

def dist2(p1, p2):
    return (p1[0] - p2[0])**2 + (p1[1] - p2[1])**2

# print(G.nodes)

new_graph = deepcopy(G)

for subtree in task_data.values():
    for task_pos in subtree.values():
        task_pos_tuple = (task_pos[0], task_pos[1])
        closest_node = min(G.nodes, key=lambda node: dist2(node, task_pos_tuple))

        new_graph.add_node(task_pos_tuple)
        new_graph.add_edge(closest_node, task_pos_tuple)
    
with open(OUTPUT_PATH, 'wb') as f:
    pickle.dump(new_graph, f)