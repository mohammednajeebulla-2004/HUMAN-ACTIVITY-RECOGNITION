import pandas as pd
import sys
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
import joblib

FEATURES_FILE = "features_opencv.csv"
try:
    df = pd.read_csv(FEATURES_FILE)
except FileNotFoundError:
    print(f"{FEATURES_FILE} not found. Run extract_features_opencv_v2.py first.")
    sys.exit(1)

if df.shape[0] == 0:
    print(f"{FEATURES_FILE} has 0 rows. Collect data and re-run extract_features_opencv_v2.py before training.")
    sys.exit(1)

# rest of training...
X = df.drop(columns=["label"]).values
y = df["label"].values
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
clf = RandomForestClassifier(n_estimators=100, random_state=42)
clf.fit(X_train, y_train)
print("Train score:", clf.score(X_train, y_train))
print("Test score:", clf.score(X_test, y_test))
joblib.dump(clf, "posture_gesture_model.pkl")
print("Model saved to posture_gesture_model.pkl")
