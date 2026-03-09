import cv2
import mediapipe as mp
import csv
import os
import time
from datetime import datetime

mp_pose = mp.solutions.pose
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

POSE = mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)
HANDS = mp_hands.Hands(static_image_mode=False, max_num_hands=1,
                       min_detection_confidence=0.5, min_tracking_confidence=0.5)

OUT_DIR = "collected_opencv"
os.makedirs(OUT_DIR, exist_ok=True)

def header():
    hdr = ["label", "timestamp"]
    for i in range(33):
        hdr += [f"pose_x{i}", f"pose_y{i}", f"pose_z{i}", f"pose_vis{i}"]
    for i in range(21):
        hdr += [f"hand_x{i}", f"hand_y{i}"]
    return hdr

def flatten_landmarks(landmarks, pose=True):
    if pose:
        return [val for lm in landmarks.landmark for val in (lm.x, lm.y, lm.z, lm.visibility)]
    else:
        return [val for lm in landmarks.landmark for val in (lm.x, lm.y)]

if __name__ == "__main__":
    label = input("Enter label (e.g., straight, slouch, lean, wave, stretch, hand_raise, none): ").strip()
    filename = os.path.join(OUT_DIR, f"{label}_{int(time.time())}.csv")
    cap = cv2.VideoCapture(0)
    recording = False
    print("Press 's' to start/stop recording. Press 'q' to quit.")

    with open(filename, "w", newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header())
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Failed to grab frame")
                break
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pose_results = POSE.process(frame_rgb)
            hand_results = HANDS.process(frame_rgb)
            disp_frame = frame.copy()

            if pose_results.pose_landmarks:
                mp_drawing.draw_landmarks(disp_frame, pose_results.pose_landmarks, mp_pose.POSE_CONNECTIONS)

            if hand_results.multi_hand_landmarks:
                mp_drawing.draw_landmarks(disp_frame, hand_results.multi_hand_landmarks[0], mp_hands.HAND_CONNECTIONS)

            display_label = label if recording else "Not Recording"
            cv2.putText(disp_frame, f"Label: {label}  {display_label}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.imshow("Collect Data", disp_frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('s'):
                recording = not recording
                print(f"Recording {'started' if recording else 'stopped'}")
            elif key == ord('q'):
                break

            if recording:
                row = [label, datetime.utcnow().isoformat()]
                if pose_results.pose_landmarks:
                    row += flatten_landmarks(pose_results.pose_landmarks, pose=True)
                else:
                    row += [0.0] * (33 * 4)
                if hand_results.multi_hand_landmarks:
                    row += flatten_landmarks(hand_results.multi_hand_landmarks[0], pose=False)
                else:
                    row += [0.0] * (21 * 2)
                writer.writerow(row)

    cap.release()
    cv2.destroyAllWindows()
    print(f"Data saved to {filename}")
