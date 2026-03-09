# kfold_cv_opencv_v2.py
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score, StratifiedKFold

# Load features file produced by extract_features_opencv_v2.py
df = pd.read_csv("features_opencv.csv")

if df.shape[0] == 0:
    print("⚠ features_opencv.csv is empty. Run data collection and extraction first.")
    exit()

# Separate features and labels
X = df.drop(columns=["label"]).values
y = df["label"].values

# Define model and 5-fold cross-validation
clf = RandomForestClassifier(n_estimators=200, random_state=42)
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

# Perform CV
scores = cross_val_score(clf, X, y, cv=cv, scoring="accuracy")

print("✅ 5-Fold Cross-Validation Accuracy Scores:", scores)
print("📊 Mean Accuracy:", round(scores.mean(), 4))
print("📈 Std Dev:", round(scores.std(), 4))
