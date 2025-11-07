# ---------- 문 좌표(네가 준 값) ----------
NAV_R = (15.450209617614746, -4.726806640625)
O2_R = (7.6681671142578125, -3.3614068031311035)
WEP_D = (9.62669563293457, -0.9255144596099854)
WEP_L = (7.053859710693359, 1.2734507322311401)
CAF_R = (5.053867340087891, 1.2734507322311401) 
CAF_L = (-6.294198036193848, 1.2066624164581299)
CAF_D = (-0.7988332509994507, -4.59734582901001)
MED_U = (-9.129260063171387, -0.7117370367050171)
UE_R = (-14.84645938873291, 1.1721446514129639)
UE_D = (-16.842432022094727, -1.7874093055725098)
REAC_R = (-19.358478546142578, -5.220103740692139)
SEC_L = (-14.515016555786133, -5.396880626678467)
DE_U = (-16.868568420410156, -9.417086601257324)
DE_R = (-14.705851554870605, -11.698345184326172)
ELEC_D = (-9.5758695602417, -13.346381187438965)
STORAGE_L = (-5.084258079528809, -14.56778335571289)
STORAGE_U = (-0.6408945322036743, -8.798002243041992)
STORAGE_R = (1.1512784957885742, -12.25683879852295)
COMM_U = (5.180538654327393, -13.925233840942383)
SHIL_L = (6.7243242263793945, -11.002277183532715)
SHIL_U = (9.54090404510498, -10.041803359985352)
ADMIN_L = (2.1010854244232178, -7.049682140350342)

EL_MED_Y = -6.376680850982666
MED_SEC_X = -11.839820861816406
MED_R_X = -5.386955261230469

CAF_MED_LINE = sum([-5.3929948806762695, -5.155691623687744]) # pos at edge of med. x+y=c
O2_L_EDGE = (4.703471660614014, -3.8572630882263184)
O2_D_EDGE_Y = -4.717148780822754
CAF_O2_LINE = O2_L_EDGE[0] - O2_L_EDGE[1]

def place(x, y):
    if CAF_L[0]<x<CAF_R[0] and y>CAF_D[1] and x+y>CAF_MED_LINE and x-y<CAF_O2_LINE:
        return "Cafeteria"
    
    if WEP_L[0]<x and WEP_D[1]<y:
        return "Weapons"
    
    if STORAGE_U[1]<y:
        if O2_L_EDGE[0]<x<O2_R[0] and y<WEP_D[1]:
            return "O2"
    
        if NAV_R[0]<x:
            return "Navigation"
    if ADMIN_L[0]<x<O2_R[0] and SHIL_L[1]<y<O2_D_EDGE_Y-0.1:
        return "Admin"
    
    if y<SHIL_U[1] and SHIL_L[0]<x:
        return "Shields"
    
    if STORAGE_R[0]<x<SHIL_L[0] and y<COMM_U[1]:
        return "Communication"
    
    if STORAGE_L[0]<x<STORAGE_R[0] and y<STORAGE_U[1]:
        return "Storage"
    
    if ELEC_D[1]<y<EL_MED_Y and (MED_SEC_X+0.5)<x<(STORAGE_L[0]+0.1):
        return "Electrical"
    
    # we already puruned every other room at right side of medbay. only check rooms at left
    if EL_MED_Y<y<MED_U[1] and MED_SEC_X<x<MED_R_X+0.5:
        return "MedBay"
    
    if SEC_L[0]<x<MED_SEC_X and DE_U[1]<y<UE_D[1]:
        return "Security"
    
    if x<REAC_R[0] and DE_U[1]<y<UE_D[1]:
        return "Reactor"
    
    if y<DE_U[1] and x<DE_R[0]:
        return "Lower Engine"
    
    if UE_D[1]<y and x<UE_R[0]:
        return "Upper Engine"

    # ---------- 복도(사각형 바운더리) ----------
    # Top: Upper Engine <-> Cafeteria <-> Weapons
    if UE_R[0] < x < WEP_L[0] and (min(UE_R[1], WEP_L[1], MED_U[1]) - 0.8) < y < (max(UE_R[1], WEP_L[1]) + 0.8):
        return "Corridor_Top"

    # Right: Weapons/O2/Shields 라인(수직)
    if O2_R[0] < x < NAV_R[0] and (SHIL_U[1] - 0.8) < y < (WEP_D[1] + 1.0):
        return "Corridor_Right"

    # Bottom: Lower Engine <-> Storage <-> Communications/Shields
    if DE_R[0] < x < SHIL_L[0] and (COMM_U[1] - 0.5) < y < (DE_U[1] + 0.5):
        return "Corridor_Bottom"

    # Left Upper: Upper Engine ~ Med 왼쪽 수직 복도
    if REAC_R[0] < x < MED_SEC_X and UE_D[1] < y < (UE_R[1] + 0.8):
        return "Corridor_Left_Upper"

    # Left Lower: Reactor ~ Security 구간 수직 복도
    if REAC_R[0] < x < MED_SEC_X and DE_U[1] < y < UE_D[1]:
        return "Corridor_Left_Lower"

    # Center Vertical: Cafeteria 아래로 Storage까지 내려가는 중앙 수직 복도
    if (CAF_D[0] - 1.0) < x < ADMIN_L[0] and STORAGE_U[1] < y < CAF_D[1]:
        return "Corridor_Center_Vert"

    # Center Horizontal: Storage 윗변(일렉트리컬쪽 <-> Admin/Shields쪽)
    if (MED_SEC_X + 0.2) < x < SHIL_L[0] and (STORAGE_U[1] - 0.6) < y < (STORAGE_U[1] + 0.6):
        return "Corridor_Center_Hor"

    return "Corridor"