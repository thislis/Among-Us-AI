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
    
    # 잠시 대기(안정화)
    try:
        time.sleep(0.2)
    except Exception:
        return False

    map_opened = False
    try:
        # Among Us 창 영역을 얻습니다 (창이 없으면 False)
        region = get_dimensions()
        if region is None:
            # 창을 찾지 못하면 더 이상 진행할 수 없습니다
            return False

        # 지도 열기 — 먼저 창을 전경으로 가져오므로 탭 입력이 해당 창에만 전달됩니다
        pyautogui.press("tab")
        map_opened = True
        time.sleep(0.45)  # 지도 애니메이션을 기다립니다

        # 스크린샷 (Pillow 이미지) — 창 내부 영역만 캡처
        # pyautogui.screenshot의 region 인자는 (left, top, width, height)
        left, top, width, height = region
        img = pyautogui.screenshot(region=(left, top, width, height))

        # 지도 닫기(옵션 — 이미지 캡처 후 바로 닫기)
        try:
            print("Closing map...")
            pyautogui.press("tab")
            map_opened = False
        except Exception:
            # 닫기 실패시에도 계속 처리하되 finally에서 보장
            pass

        # PIL -> numpy array (RGB) -> BGR for OpenCV
        frame = np.array(img)[:, :, ::-1].copy()

        # HSV로 변환
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # 빨강 범위 (두 구간)
        lower_r1 = np.array([0, 120, 70])
        upper_r1 = np.array([10, 255, 255])
        lower_r2 = np.array([170, 120, 70])
        upper_r2 = np.array([180, 255, 255])
        mask_r1 = cv2.inRange(hsv, lower_r1, upper_r1)
        mask_r2 = cv2.inRange(hsv, lower_r2, upper_r2)
        mask_red = cv2.bitwise_or(mask_r1, mask_r2)

        # 파랑 범위
        lower_b = np.array([100, 150, 0])
        upper_b = np.array([140, 255, 255])
        mask_blue = cv2.inRange(hsv, lower_b, upper_b)

        # 픽셀 수 계산
        red_count = int(cv2.countNonZero(mask_red))
        blue_count = int(cv2.countNonZero(mask_blue))

        # 최소 픽셀 수(잡음 방지)
        if max(red_count, blue_count) < 50:
            return False

        # 빨강이 더 많으면 임포스터로 판단
        return red_count > blue_count
    except Exception:
        return False
    finally:
        # 만약 예외가 발생해 지도가 열린 상태로 남았다면 닫기 시도
        if map_opened:
            try:
                pyautogui.press("tab")
            except Exception:
                pass
    
if __name__ == "__main__":
    result = is_impostor()
    print("임포스터 여부:", result)