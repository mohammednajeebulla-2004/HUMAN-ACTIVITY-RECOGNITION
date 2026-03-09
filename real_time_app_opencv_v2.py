import time
import math
from collections import defaultdict, deque
import threading

import cv2
import mediapipe as mp
import numpy as np
import win32com.client

# ─────────────────────────────────────────────
#  VOICE
# ─────────────────────────────────────────────
speaker = win32com.client.Dispatch("SAPI.SpVoice")

def speak(msg):
    def _run():
        try:
            speaker.Speak(msg)
        except:
            pass
    threading.Thread(target=_run, daemon=True).start()

# ─────────────────────────────────────────────
#  ALERTS & LABELS  (plain English only)
# ─────────────────────────────────────────────
VOICE_ALERTS = {
    "slouching":     "Please sit up straight.",
    "lean_left":     "You are leaning left. Please straighten up.",
    "lean_right":    "You are leaning right. Please straighten up.",
    "head_forward":  "Move your head back and sit tall.",
    "arms_crossed":  "Uncross your arms for better posture.",
    "touching_face": "Try to keep your hands away from your face.",
    "sleeping":      "Stay alert. Sit up straight.",
}

ISSUE_LABELS = {
    "slouching":     "Slouching",
    "lean_left":     "Leaning Left",
    "lean_right":    "Leaning Right",
    "head_forward":  "Head Too Far Forward",
    "arms_crossed":  "Arms Crossed",
    "touching_face": "Touching Face",
    "sleeping":      "Falling Asleep",
}

GESTURE_LABELS = {
    "thumbs_up":   "Thumbs Up",
    "thumbs_down": "Thumbs Down",
    "peace":       "Peace Sign",
    "ok_sign":     "OK",
    "pointing_up": "Pointing Up",
    "open_palm":   "Open Palm",
    "fist":        "Fist",
}

BAD_ACTIONS = set(VOICE_ALERTS.keys())

PRIORITY = [
    "sleeping", "slouching", "head_forward",
    "lean_left", "lean_right", "arms_crossed", "touching_face"
]

# ─────────────────────────────────────────────
#  THRESHOLDS
# ─────────────────────────────────────────────
DELTA_TORSO_SLOUCH    = 12.0
DELTA_NECK_FORWARD    = 18.0
DELTA_SHIFT_LEAN      = 0.15
CHEST_DIST            = 0.40
SLEEP_WINDOW          = 25
SLEEP_VAR_THRESH      = 0.00032
STABILITY_FRAMES      = 45
REPEAT_INTERVAL       = 8.0
GESTURE_STABLE_FRAMES = 20
CALIB_FRAMES          = 90

# ─────────────────────────────────────────────
#  DESIGN TOKENS  (all BGR)
# ─────────────────────────────────────────────
BG        = (18,  22,  30)
PANEL     = (24,  30,  42)
BORDER    = (40,  50,  68)
WHITE     = (245, 248, 252)
SUBTEXT   = (120, 135, 155)
MINT      = (80,  210, 150)
AMBER     = (45,  175, 245)
CORAL     = (75,  90,  235)
BLUE_ACC  = (220, 170,  60)
CALIB_C   = (160, 200, 255)

# ─────────────────────────────────────────────
#  DRAW HELPERS
# ─────────────────────────────────────────────
def alpha_rect(img, x1, y1, x2, y2, color, a):
    x1,y1,x2,y2 = max(0,x1),max(0,y1),min(img.shape[1],x2),min(img.shape[0],y2)
    if x2<=x1 or y2<=y1: return
    roi = img[y1:y2, x1:x2]
    blk = np.full_like(roi, color)
    cv2.addWeighted(blk, a, roi, 1-a, 0, roi)
    img[y1:y2, x1:x2] = roi

def card(img, x1, y1, x2, y2, a=0.85, bc=None):
    bc = bc or BORDER
    alpha_rect(img, x1, y1, x2, y2, PANEL, a)
    cv2.rectangle(img, (x1,y1), (x2,y2), bc, 1, cv2.LINE_AA)

def accent_bar(img, x, y1, y2, color, width=4):
    alpha_rect(img, x, y1, x+width, y2, color, 1.0)

def txt(img, s, x, y, scale, color, bold=False, align='left'):
    f = cv2.FONT_HERSHEY_DUPLEX if bold else cv2.FONT_HERSHEY_SIMPLEX
    th = 2 if bold else 1
    if align != 'left':
        (tw,_),_ = cv2.getTextSize(s, f, scale, th)
        if align == 'center': x -= tw//2
        elif align == 'right': x -= tw
    cv2.putText(img, s, (x,y), f, scale, color, th, cv2.LINE_AA)

def tw(s, scale, bold=False):
    f = cv2.FONT_HERSHEY_DUPLEX if bold else cv2.FONT_HERSHEY_SIMPLEX
    th = 2 if bold else 1
    (w,_),_ = cv2.getTextSize(s, f, scale, th)
    return w

def prog_bar(img, x, y, w, h, pct, fg, bg=BORDER):
    alpha_rect(img, x, y, x+w, y+h, bg, 0.8)
    if pct > 0.01:
        alpha_rect(img, x, y, x+max(h, int(w*pct)), y+h, fg, 1.0)

def h_line(img, x1, x2, y, color=BORDER):
    cv2.line(img, (x1,y), (x2,y), color, 1, cv2.LINE_AA)

def status_dot(img, cx, cy, color, frame_idx, animate=True):
    if animate:
        pulse = 0.55 + 0.45 * math.sin(frame_idx * 0.10)
        r_outer = int(7 * pulse)
        alpha_rect(img, cx-r_outer-1, cy-r_outer-1,
                   cx+r_outer+1, cy+r_outer+1,
                   tuple(int(c*0.18) for c in color), 0.7)
    cv2.circle(img, (cx,cy), 5, color, -1, cv2.LINE_AA)

# ─────────────────────────────────────────────
#  SCORE RING
# ─────────────────────────────────────────────
def draw_score_ring(img, cx, cy, score, frame_idx):
    R, T = 38, 5
    bg_color = (38, 48, 62)
    color = MINT if score>=80 else (AMBER if score>=50 else CORAL)

    cv2.circle(img, (cx,cy), R, bg_color, T, cv2.LINE_AA)
    angle = int(360 * score / 100)
    if angle > 0:
        cv2.ellipse(img, (cx,cy), (R,R), -90, 0, angle, color, T, cv2.LINE_AA)

    s = str(score)
    txt(img, s, cx, cy+6, 0.65, WHITE, bold=True, align='center')
    txt(img, "Score", cx, cy+R+16, 0.32, SUBTEXT, align='center')

# ─────────────────────────────────────────────
#  MAIN HUD
# ─────────────────────────────────────────────
def draw_hud(frame, h, w, state, issues, gesture_info,
             stab, calib_pct, frame_idx):

    BAR_H = 58

    # ── TOP BAR ──────────────────────────────────────────
    alpha_rect(frame, 0, 0, w, BAR_H, BG, 0.92)
    h_line(frame, 0, w, BAR_H, BORDER)

    # App name
    txt(frame, "PostureAI", 20, 38, 0.80, WHITE, bold=True)

    # Clock + label (right)
    clock = time.strftime("%H:%M:%S")
    txt(frame, clock,          w-18, 26, 0.52, WHITE,   align='right')
    txt(frame, "Live Session", w-18, 46, 0.34, SUBTEXT, align='right')

    # Status pill (center)
    if state == 'calibrating':
        pc, label = CALIB_C,  "Calibrating"
    elif state == 'good':
        pc, label = MINT,     "Good Posture"
    elif state == 'warning':
        pc, label = AMBER,    "Stay Aware"
    else:
        pc, label = CORAL,    "Fix Posture"

    lw_px = tw(label, 0.58, bold=True)
    pill_w = lw_px + 44
    pill_x = w//2 - pill_w//2
    pill_y = BAR_H//2 - 15
    alpha_rect(frame, pill_x, pill_y, pill_x+pill_w, pill_y+30,
               tuple(int(c*0.15) for c in pc), 1.0)
    cv2.rectangle(frame, (pill_x, pill_y), (pill_x+pill_w, pill_y+30),
                  pc, 1, cv2.LINE_AA)
    status_dot(frame, pill_x+16, BAR_H//2, pc, frame_idx)
    txt(frame, label, pill_x+30, BAR_H//2+7, 0.58, pc, bold=True)

    # ── CALIBRATION ─────────────────────────────────────
    if state == 'calibrating':
        alpha_rect(frame, 0, BAR_H, w, h, BG, 0.50)
        mid_y = BAR_H + (h - BAR_H)//2
        m1 = "Setting up your baseline"
        m2 = "Sit straight and look at the camera"
        txt(frame, m1, w//2, mid_y-28, 0.80, WHITE, bold=True, align='center')
        txt(frame, m2, w//2, mid_y,    0.46, SUBTEXT, align='center')
        bw, bh = 300, 6
        bx = w//2 - bw//2
        by = mid_y + 20
        prog_bar(frame, bx, by, bw, bh, calib_pct, CALIB_C, bg=(35,44,58))
        pct_s = f"{int(calib_pct*100)}%"
        txt(frame, pct_s, w//2, by+26, 0.45, CALIB_C, align='center')
        return

    # ── ISSUE CARDS (bottom-left) ────────────────────────
    bad_now = issues & BAD_ACTIONS
    sorted_issues = [i for i in PRIORITY if i in bad_now]

    CARD_W, CARD_H, GAP = 238, 50, 6
    CARDS_X = 14
    total_h  = len(sorted_issues) * (CARD_H + GAP) - GAP if sorted_issues else 0
    cards_y0 = h - total_h - 30

    for idx, issue in enumerate(sorted_issues):
        cy1 = cards_y0 + idx * (CARD_H + GAP)
        cy2 = cy1 + CARD_H
        sf  = stab.get(issue, 0)
        confirmed = sf >= STABILITY_FRAMES
        pct = min(1.0, sf / STABILITY_FRAMES)
        bc  = CORAL if confirmed else AMBER

        card(frame, CARDS_X, cy1, CARDS_X+CARD_W, cy2, a=0.90, bc=bc)
        accent_bar(frame, CARDS_X, cy1, cy2, bc, width=4)

        lbl = ISSUE_LABELS.get(issue, issue.title())
        txt(frame, lbl, CARDS_X+14, cy1+20, 0.50, WHITE, bold=True)

        sub = "Alert" if confirmed else "Detecting"
        txt(frame, sub, CARDS_X+14, cy1+38, 0.36, bc)

        prog_bar(frame, CARDS_X+135, cy1+30, 90, 4, pct, bc, bg=(38,48,62))

    # ── SCORE RING (top-right) ───────────────────────────
    confirmed_c = sum(1 for i in bad_now if stab.get(i,0) >= STABILITY_FRAMES)
    score = max(0, 100 - confirmed_c * 20)
    ring_cx = w - 58
    ring_cy = BAR_H + 60
    alpha_rect(frame, ring_cx-52, ring_cy-52, ring_cx+52, ring_cy+58, BG, 0.55)
    draw_score_ring(frame, ring_cx, ring_cy, score, frame_idx)

    # ── GESTURE BADGE (bottom-right) ────────────────────
    if gesture_info:
        g_key, g_label = gesture_info
        GW, GH = 215, 54
        gx = w - GW - 14
        gy = h - GH - 28
        card(frame, gx, gy, gx+GW, gy+GH, a=0.90, bc=MINT)
        accent_bar(frame, gx, gy, gy+GH, MINT)
        txt(frame, "Gesture Detected", gx+14, gy+20, 0.36, SUBTEXT)
        txt(frame, g_label,            gx+14, gy+42, 0.56, MINT, bold=True)

    # ── BOTTOM HINT BAR ──────────────────────────────────
    alpha_rect(frame, 0, h-22, w, h, BG, 0.78)
    txt(frame, "Q  to quit", w//2, h-7, 0.32, SUBTEXT, align='center')


# ─────────────────────────────────────────────
#  MEDIAPIPE
# ─────────────────────────────────────────────
mp_pose  = mp.solutions.pose
mp_hands = mp.solutions.hands
mp_draw  = mp.solutions.drawing_utils

PL_SPEC = mp_draw.DrawingSpec(color=(80, 200, 140), thickness=2, circle_radius=3)
PC_SPEC = mp_draw.DrawingSpec(color=(35, 90,  65),  thickness=1)
HL_SPEC = mp_draw.DrawingSpec(color=(210,165,  55),  thickness=2, circle_radius=3)
HC_SPEC = mp_draw.DrawingSpec(color=(100, 80,  25),  thickness=1)

pose_model  = mp_pose.Pose(min_detection_confidence=0.6,
                           min_tracking_confidence=0.6,
                           model_complexity=0)
hands_model = mp_hands.Hands(max_num_hands=2,
                              min_detection_confidence=0.55,
                              min_tracking_confidence=0.55)

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def get_pt(lm, idx):
    try:
        p = lm.landmark[idx]
        return np.array([p.x, p.y, p.z], dtype=np.float32)
    except:
        return None

def is_ext(hl, tip, pip):
    try:
        return hl.landmark[tip].y < hl.landmark[pip].y
    except:
        return False

def detect_gesture(hl):
    if not hl: return None
    te  = hl.landmark[4].x < hl.landmark[3].x
    ie  = is_ext(hl,8,6); me = is_ext(hl,12,10)
    re  = is_ext(hl,16,14); pe = is_ext(hl,20,18)
    cnt = sum([te,ie,me,re,pe])
    if cnt==0: return "fist"
    if te and not ie and not me and not re and not pe:
        return "thumbs_down" if hl.landmark[4].y > hl.landmark[0].y else "thumbs_up"
    if ie and me and not re and not pe: return "peace"
    tt=hl.landmark[4]; it=hl.landmark[8]
    if ((tt.x-it.x)**2+(tt.y-it.y)**2)**0.5 < 0.05 and not me and not re and not pe:
        return "ok_sign"
    if ie and not me and not re and not pe and not te: return "pointing_up"
    if cnt >= 4: return "open_palm"
    return None

def compute_metrics(lm):
    m = {}
    if lm is None: return m
    L = mp_pose.PoseLandmark
    ls=get_pt(lm,L.LEFT_SHOULDER); rs=get_pt(lm,L.RIGHT_SHOULDER)
    lh=get_pt(lm,L.LEFT_HIP);     rh=get_pt(lm,L.RIGHT_HIP)
    ns=get_pt(lm,L.NOSE)
    if any(p is None for p in [ls,rs,lh,rh,ns]): return m
    sm=(ls+rs)/2; hm=(lh+rh)/2; v=np.array([0.,-1.])
    tv=sm[:2]-hm[:2]; tn=np.linalg.norm(tv)
    m["torso"]=float(np.degrees(np.arccos(np.clip(np.dot(tv,v)/tn,-1,1)))) if tn>1e-9 else 0.
    nv=ns[:2]-sm[:2]; nn=np.linalg.norm(nv)
    m["neck"] =float(np.degrees(np.arccos(np.clip(np.dot(nv,v)/nn,-1,1)))) if nn>1e-9 else 0.
    m["shift"]=float(sm[0]-hm[0])
    return m

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
def main():
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("Camera not found."); return

    cs   = {"torso":[],"neck":[],"shift":[]}
    bl   = {}
    ready= False

    n_hist    = deque(maxlen=SLEEP_WINDOW)
    stab      = defaultdict(int)
    last_alert= defaultdict(float)
    g_stab    = defaultdict(int)
    last_g    = None
    last_g_t  = 0.
    fi        = 0

    print("Calibrating — sit straight.")

    while True:
        ret, frame = cap.read()
        if not ret: break

        frame = cv2.flip(frame,1)
        h,w   = frame.shape[:2]
        rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        pr = pose_model.process(rgb)
        lm = pr.pose_landmarks if pr else None
        if lm:
            mp_draw.draw_landmarks(frame,lm,mp_pose.POSE_CONNECTIONS,PL_SPEC,PC_SPEC)

        metrics = compute_metrics(lm)

        # CALIBRATION
        if not ready:
            if all(k in metrics for k in cs):
                for k in cs: cs[k].append(metrics[k])
            cnt = len(cs["torso"])
            draw_hud(frame,h,w,'calibrating',set(),None,stab,cnt/CALIB_FRAMES,fi)
            cv2.imshow("PostureAI",frame); fi+=1
            if cnt >= CALIB_FRAMES:
                bl = {k: float(np.mean(v)) for k,v in cs.items()}
                ready = True
                print("Baseline ready.")
            if cv2.waitKey(1)&0xFF==ord('q'): break
            continue

        # DETECTION
        issues = set()
        if all(k in metrics for k in ["torso","neck","shift"]):
            if metrics["torso"]-bl["torso"] > DELTA_TORSO_SLOUCH:  issues.add("slouching")
            if metrics["neck"] -bl["neck"]  > DELTA_NECK_FORWARD:  issues.add("head_forward")
            d = metrics["shift"]-bl["shift"]
            if   d >  DELTA_SHIFT_LEAN: issues.add("lean_right")
            elif d < -DELTA_SHIFT_LEAN: issues.add("lean_left")

        if lm:
            try:
                ny = lm.landmark[mp_pose.PoseLandmark.NOSE].y
                n_hist.append(float(ny))
                if (len(n_hist)==n_hist.maxlen
                        and np.var(np.array(n_hist)) < SLEEP_VAR_THRESH
                        and "head_forward" in issues):
                    issues.add("sleeping")
            except: pass

        # HANDS
        dg = None
        hr = hands_model.process(rgb)
        if hr and hr.multi_hand_landmarks:
            for hl in hr.multi_hand_landmarks:
                mp_draw.draw_landmarks(frame,hl,mp_hands.HAND_CONNECTIONS,HL_SPEC,HC_SPEC)
                g = detect_gesture(hl)
                if g: dg=g
            if not dg and lm:
                L=mp_pose.PoseLandmark
                ls=get_pt(lm,L.LEFT_SHOULDER); rs=get_pt(lm,L.RIGHT_SHOULDER)
                nsp=get_pt(lm,L.NOSE)
                cc=(ls+rs)/2. if ls is not None and rs is not None else None
                nf=nc=0
                for hl in hr.multi_hand_landmarks:
                    wr=np.array([hl.landmark[0].x,hl.landmark[0].y,hl.landmark[0].z])
                    if nsp is not None and np.linalg.norm(wr-nsp)<0.40: nf+=1
                    if cc  is not None and np.linalg.norm(wr-cc) <CHEST_DIST: nc+=1
                if nf>=1: issues.add("touching_face")
                if nc>=2: issues.add("arms_crossed")

        now = time.time()
        gd  = None
        if dg:
            g_stab[dg]+=1
            for k in GESTURE_LABELS:
                if k!=dg: g_stab[k]=0
            if g_stab[dg]>=GESTURE_STABLE_FRAMES:
                if dg!=last_g or now-last_g_t>2.:
                    print(f"Gesture: {GESTURE_LABELS.get(dg,dg)}")
                    last_g=dg; last_g_t=now
                gd=(dg, GESTURE_LABELS.get(dg,dg))
        else:
            for k in GESTURE_LABELS: g_stab[k]=0

        bad = issues & BAD_ACTIONS
        for i in BAD_ACTIONS:
            stab[i] = stab[i]+1 if i in bad else 0

        for i in PRIORITY:
            if (i in bad and stab[i]>=STABILITY_FRAMES
                    and now-last_alert[i]>=REPEAT_INTERVAL):
                speak(VOICE_ALERTS[i]); last_alert[i]=now; break

        confirmed = [i for i in bad if stab[i]>=STABILITY_FRAMES]
        tracking  = [i for i in bad if stab[i]< STABILITY_FRAMES]
        if   confirmed: state='alert'
        elif tracking:  state='warning'
        else:           state='good'

        draw_hud(frame,h,w,state,issues,gd,stab,1.0,fi)
        cv2.imshow("PostureAI",frame); fi+=1
        if cv2.waitKey(1)&0xFF==ord('q'): break

    cap.release()
    cv2.destroyAllWindows()

if __name__=="__main__":
    main()