from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, HTMLResponse
import cv2
import numpy as np
import time
import threading

app = FastAPI()

RTSP_URL = "rtsp://ins046msc:wQpQk35t@85.141.77.197:7554/ISAPI/Streaming/Channels/103"
cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
prev_frame = None
frz_counter = 0

def is_low_quality(frame, threshold=20):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    contrast = np.std(gray)
    return contrast < threshold

def frame_generator():
    global prev_frame, frz_counter
    while True:
        ret, frame = cap.read()
        if not ret:
            time.sleep(2)
            continue

        # Анализ видео
        if prev_frame is not None:
            diff = cv2.absdiff(frame, prev_frame)
            if np.sum(diff) < 1000:
                frz_counter += 1
            else:
                frz_counter = 0

            if frz_counter > 5:
                print("Изображение остановилось")
                frz_counter = 0

            if is_low_quality(frame):
                print("Изображение некачественное")

        prev_frame = frame

        # Кодируем кадр в JPEG
        ret, jpeg = cv2.imencode('.jpg', frame)
        if not ret:
            continue

        # Отдаем как поток multipart
        frame_bytes = jpeg.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.get("/")
async def main_page():
    # Возвращает HTML страницу с элементом img для видео
    html_content = """
    <html>
        <head>
            <title>Камера Статус</title>
        </head>
        <body>
            <h1>Видео с камеры</h1>
            <img src="/video" width="640" height="480" />
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/video")
def video_feed():
    # Возвращает поток видео
    return StreamingResponse(frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame")
