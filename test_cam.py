import cv2

cam = cv2.VideoCapture(0, cv2.CAP_DSHOW)

if not cam.isOpened():
    print("❌ Camera NOT detected")
else:
    print("✔ Camera is detected")

while True:
    ret, frame = cam.read()
    if not ret:
        print("⚠ Cannot read camera frame")
        break

    cv2.imshow("CAM TEST", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cam.release()
cv2.destroyAllWindows()
