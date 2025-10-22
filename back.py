import cv2
import numpy as np
import time

class CameraMonitor:
    def __init__(self, name, rtsp_url):
        self.name = name
        self.rtsp_url = rtsp_url
        self.cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        self.prev = None
        self.frz_counter = 0
        self.connection_good = False

    def check_connection(self, test_frames=3):
        """Проверка связи: пытаемся получить несколько подряд успешных кадров."""
        ok_frames = 0
        for _ in range(test_frames):
            ret, frame = self.cap.read()
            if ret:
                ok_frames += 1
            else:
                ok_frames = 0
                break
            time.sleep(0.2)
        self.connection_good = ok_frames == test_frames
        return self.connection_good

    def is_low_quality(self, frame, threshold=20):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        contrast = np.std(gray)
        return contrast < threshold

    def analyze_stream(self):
        while True:
            if not self.check_connection():
                print(f"[{self.name}] Ошибка соединения: камера недоступна")
                time.sleep(2)
                continue

            ret, frame = self.cap.read()
            if not ret:
                print(f"[{self.name}] Нет кадра несмотря на успешное соединение")
                time.sleep(2)
                continue

            if self.prev is not None:
                diff = cv2.absdiff(frame, self.prev)
                if np.sum(diff) < 1000:
                    self.frz_counter += 1
                else:
                    self.frz_counter = 0

                if self.frz_counter > 5:
                    print(f"[{self.name}] Изображение остановилось")
                    self.frz_counter = 0

            # Проверяем качество кадра ТОЛЬКО если связь не идеальна
            # (например, можно убрать проверку качества вообще, если соединение good)
            if not self.connection_good and self.is_low_quality(frame):
                print(f"[{self.name}] Изображение некачественное")

            self.prev = frame
            time.sleep(1)

# Список камер для масштабирования
CAMERAS = [
    {"name": "Camera1", "rtsp_url": "rtsp://ins046msc:wQpQk35t@85.141.77.197:7554/ISAPI/Streaming/Channels/103"},
]

# Запуск мониторинга для всех камер (в одном потоке поочередно — можно переписать на потоки для одновременности!)
for camera_conf in CAMERAS:
    monitor = CameraMonitor(**camera_conf)
    monitor.analyze_stream()
