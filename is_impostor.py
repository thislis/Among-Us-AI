from functools import lru_cache
import cv2
import time
import numpy as np
import pyautogui
import win32gui

def get_dimensions(window_title: str = "Among Us", bring_to_foreground: bool = True):
    """
    주어진 창 제목의 클라이언트 영역을 스크린 좌표(왼쪽, 위, 너비, 높이)로 반환합니다.
    창을 찾지 못하면 None을 반환합니다.
    bring_to_foreground=True면 창을 전경으로 가져옵니다.
    """
    try:
        hwnd = win32gui.FindWindow(None, window_title)
    except Exception:
        return None

    if not hwnd:
        return None

    # 창을 전경으로 가져오기(실패해도 계속)
    if bring_to_foreground:
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass

    # 클라이언트 영역(좌,상,우,하)을 얻어 스크린 좌표로 변환
    try:
        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        screen_left, screen_top = win32gui.ClientToScreen(hwnd, (left, top))
        width = right - left
        height = bottom - top
        return (screen_left, screen_top, width, height)
    except Exception:
        return None

@lru_cache(maxsize=1)
def is_impostor() -> bool:
    """
    Tab을 눌러 지도를 연 뒤 화면에서 빨강/파랑 픽셀 비율을 비교해
    빨강이 더 많으면 임포스터(True), 아니면 False를 반환합니다.
    (간단한 색검출 방식이며 환경에 따라 임계값 조정 필요)
    """

    # Among Us 창 영역을 얻습니다 (창이 없으면 False)
    region = None
    while not region:
        region = get_dimensions()
    time.sleep(0.2)  # 창이 완전히 전경에 오도록 잠시 대기
    
    x = region[0] + round(region[2] / 1.32)
    y = region[1] + round(region[3] / 1.207)

    col = pyautogui.pixel(x, y)
    return col[0] > 200 and col[2] < 5
    
if __name__ == "__main__":
    result = is_impostor()
    print("임포스터 여부:", result)