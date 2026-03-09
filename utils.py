import math
import numpy as np

def angle_between(p1, p2, p3):
    """Calculate the angle (in degrees) at p2 formed by points p1–p2–p3."""
    a = np.array(p1)
    b = np.array(p2)
    c = np.array(p3)
    ba = a - b
    bc = c - b
    cosine_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-6)
    angle = np.degrees(np.arccos(np.clip(cosine_angle, -1.0, 1.0)))
    return angle

def normalize_hand_features(hand_points):
    """Normalize hand coordinates to be relative to wrist (index 0)."""
    if len(hand_points) < 21 * 2:
        return hand_points
    coords = np.array(hand_points).reshape(-1, 2)
    wrist = coords[0]
    normalized = coords - wrist
    max_val = np.max(np.abs(normalized)) + 1e-6
    normalized /= max_val
    return normalized.flatten().tolist()
