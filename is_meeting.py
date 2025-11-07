from utils.task_utility import get_dimensions, get_dir
import pyautogui
import time

def is_meeting() -> bool:
    """화면에 회의 중임을 나타내는 요소가 있는지 확인합니다."""
    dimensions = get_dimensions()
    pos = [(1570, 90), (1600, 100), (1615, 55)]
    colors = [(244, 243, 244), (192, 199, 209), (176, 177, 181)]
    for p, c in zip(pos, colors):
        x = dimensions[0] + p[0]
        y = dimensions[1] + p[1]
        pixel_color = pyautogui.pixel(x, y)
        if pixel_color != c:
            return False
    return True

if __name__ == "__main__":
    while True:
        start = time.time()
        print(is_meeting())
        print("Time taken:", time.time() - start)