import cv2
import numpy as np
import time

RTSP_URL = "rtsp://ins046msc:wQpQk35t@85.141.77.197:7554/ISAPI/Streaming/Channels/103"
cap = cv2.VideoCapture(RTSP_URL)
prev = None
frz_counter = 0

def is_low_quality(frame, threshold=20):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    contrast = np.std(gray)
    return contrast < threshold

while True:
    ret, frame = cap.read()
    if not ret:
        print("Ошибка: изображение недоступно")
        time.sleep(2)
        continue

    if prev is not None:
        diff = cv2.absdiff(frame, prev)
        if np.sum(diff) < 1000:
            frz_counter += 1
        else:
            frz_counter = 0

        if frz_counter > 5:
            print("Изображение остановилось")
            frz_counter = 0

    if is_low_quality(frame):
        print("Изображение некачественное")

    prev = frame
    time.sleep(1)