import time
from collections import defaultdict, deque
from datetime import datetime
import cv2
import mediapipe as mp
import numpy as np
import pyttsx3

# ==========================================
# ----------- SPEECH (place here) ----------
# ==========================================

tts_engine = pyttsx3.init()
tts_engine.setProperty("rate", 180)
tts_engine.setProperty("volume", 1.0)

def speak(msg):
    try:
        tts_engine.stop()
        tts_engine.say(msg)
        tts_engine.runAndWait()
    except Exception as e:
        print("TTS error:", e)

# ==========================================
# ------------- CONSTANTS -------------------
# ==========================================

CAM_INDEX = 0
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
REPEAT_INTERVAL = 0.8

ANGLE_SLOUCH = 8.0
ANGLE_NECK_FORWARD = 6.0
SHIFT_LEAN = 0.05

PHONE_DISTANCE = 0.32
CHEST_DISTANCE = 0.34
FACE_DISTANCE = 0.30
ARM_RAISE_DELTA = 0.04

SLEEP_WINDOW = 20
SLEEP_VAR_THRESH = 4.0e-4

COLOR_GOOD = (0, 200, 0)
COLOR_BAD = (0, 0, 255)
COLOR_WARN = (0, 165, 255)
COLOR_TEXT = (255, 255, 255)
COLOR_BG = (20, 20, 20)

VOICE_ALERTS = {
    "slouching":     "Sit straight.",
    "lean_left":     "You are leaning left. Sit straight.",
    "lean_right":    "You are leaning right. Sit straight.",
    "head_forward":  "Bring your head back and sit straight.",
    "phone_use":     "Don't use your phone!",
    "arms_crossed":  "Uncross your arms.",
    "arms_raised":   "Lower your arms.",
    "touching_face": "Don't touch your face.",
    "sleeping":      "Wake up and sit straight.",
}
BAD_ACTIONS = set(VOICE_ALERTS.keys())
GOOD_MESSAGE = "Good posture, thank you."

mp_pose = mp.solutions.pose
mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils

pose = mp_pose.Pose(min_detection_confidence=0.5,
                    min_tracking_confidence=0.5,
                    model_complexity=0)

hands = mp_hands.Hands(max_num_hands=2,
                       min_detection_confidence=0.5,
                       min_tracking_confidence=0.5)


# ==========================================
# ----------- UTIL FUNCTIONS ----------------
# ==========================================

def get_point(lm, idx):
    try:
        p = lm.landmark[idx]
        return np.array([p.x, p.y, p.z], dtype=np.float32)
    except:
        return None


def detect_posture(pose_lm):
    issues = set()
    metrics = {}
    if pose_lm is None:
        return issues, metrics

    L = mp_pose.PoseLandmark
    left_sh = get_point(pose_lm, L.LEFT_SHOULDER)
    right_sh = get_point(pose_lm, L.RIGHT_SHOULDER)
    left_hip = get_point(pose_lm, L.LEFT_HIP)
    right_hip = get_point(pose_lm, L.RIGHT_HIP)
    nose = get_point(pose_lm, L.NOSE)

    if any(x is None for x in [left_sh, right_sh, left_hip, right_hip, nose]):
        return issues, metrics

    shoulder_mid = (left_sh + right_sh) / 2.0
    hip_mid = (left_hip + right_hip) / 2.0
    vertical = np.array([0.0, -1.0])

    torso_vec = shoulder_mid[:2] - hip_mid[:2]
    cos_t = np.dot(torso_vec, vertical) / (np.linalg.norm(torso_vec) + 1e-9)
    torso_angle = float(np.degrees(np.arccos(np.clip(cos_t, -1, 1))))
    metrics["torso"] = torso_angle
    if torso_angle > ANGLE_SLOUCH:
        issues.add("slouching")

    neck_vec = nose[:2] - shoulder_mid[:2]
    cos_n = np.dot(neck_vec, vertical) / (np.linalg.norm(neck_vec) + 1e-9)
    neck_angle = float(np.degrees(np.arccos(np.clip(cos_n, -1, 1))))
    metrics["neck"] = neck_angle
    if neck_angle > ANGLE_NECK_FORWARD:
        issues.add("head_forward")

    shift = float(shoulder_mid[0] - 0.5)
    metrics["shift"] = shift
    if abs(shift) > SHIFT_LEAN:
        issues.add("lean_left" if shift < 0 else "lean_right")

    return issues, metrics


def detect_hand(pose_lm, hand_res):
    issues = set()
    if pose_lm is None or hand_res is None or not hand_res.multi_hand_landmarks:
        return issues

    L = mp_pose.PoseLandmark
    left_sh = get_point(pose_lm, L.LEFT_SHOULDER)
    right_sh = get_point(pose_lm, L.RIGHT_SHOULDER)
    nose = get_point(pose_lm, L.NOSE)

    if left_sh is not None and right_sh is not None:
        chest_center = (left_sh + right_sh) / 2.0
        shoulder_y = min(left_sh[1], right_sh[1])
    else:
        chest_center = None
        shoulder_y = None

    near_chest = 0
    near_face = 0

    for h in hand_res.multi_hand_landmarks:
        wrist = np.array([h.landmark[0].x, h.landmark[0].y, h.landmark[0].z])

        # PHONE USE — hand near face
        if nose is not None:
            dist = float(np.linalg.norm(wrist - nose))
            if dist < FACE_DISTANCE + 0.06:
                if chest_center is not None:
                    if wrist[1] < chest_center[1] + 0.05:
                        issues.add("phone_use")

        # TOUCHING FACE
        if nose is not None:
            if float(np.linalg.norm(wrist - nose)) < FACE_DISTANCE:
                near_face += 1

        # ARMS CROSSED
        if chest_center is not None:
            if float(np.linalg.norm(wrist - chest_center)) < CHEST_DISTANCE:
                near_chest += 1

    if near_face >= 1:
        issues.add("touching_face")
    if near_chest >= 2:
        issues.add("arms_crossed")

    return issues


def detect_sleep(pose_lm, nose_hist, metrics):
    if pose_lm is None or "neck" not in metrics:
        return False

    head_down = metrics["neck"] > 12

    try:
        ny = pose_lm.landmark[mp_pose.PoseLandmark.NOSE].y
        nose_hist.append(float(ny))
        if len(nose_hist) == nose_hist.maxlen:
            if np.var(np.array(nose_hist)) < SLEEP_VAR_THRESH and head_down:
                return True
    except:
        pass
    return False


# ==========================================
# -------------- MAIN LOOP -----------------
# ==========================================

def main():
    cap = cv2.VideoCapture(CAM_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, 30)

    nose_hist = deque(maxlen=SLEEP_WINDOW)
    last_alert = defaultdict(float)
    active = set()

    print("\nPOSTURE + PHONE + VOICE READY ✔\n")

    while True:
        ret, frame = cap.read()
        if not ret: break

        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        pose_res = pose.process(rgb)
        hand_res = hands.process(rgb)

        if pose_res.pose_landmarks:
            mp_draw.draw_landmarks(frame, pose_res.pose_landmarks, mp_pose.POSE_CONNECTIONS)
        if hand_res.multi_hand_landmarks:
            for h in hand_res.multi_hand_landmarks:
                mp_draw.draw_landmarks(frame, h, mp_hands.HAND_CONNECTIONS)

        posture_issues, metrics = detect_posture(pose_res.pose_landmarks)
        hand_issues = detect_hand(pose_res.pose_landmarks, hand_res)
        issues = posture_issues | hand_issues

        if detect_sleep(pose_res.pose_landmarks, nose_hist, metrics):
            issues.add("sleeping")

        now = time.time()
        bad = issues.intersection(BAD_ACTIONS)

        # ---------- VOICE ----------
        for iss in bad:
            if now - last_alert[iss] > REPEAT_INTERVAL:
                speak(VOICE_ALERTS[iss])
                last_alert[iss] = now
                print("⚠", iss)

        # ------------ UI ------------
        h, w = frame.shape[:2]
        cv2.rectangle(frame, (0, 0), (w, 50), COLOR_BG, -1)
        txt = "POSTURE OK" if not bad else "ISSUES: " + ", ".join(sorted(bad))
        cv2.putText(frame, txt, (10, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, COLOR_TEXT, 2)

        cv2.imshow("Posture+Phone Monitor", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()

# -------- RUN ----------
if __name__ == "__main__":
    main()
