import cv2
import numpy as np
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CameraMonitor:
    def __init__(self, camera_id: int, name: str, rtsp_url: str):
        self.camera_id = camera_id
        self.name = name
        self.rtsp_url = rtsp_url
        self.cap = None
        self.prev_frame = None
        self.freeze_counter = 0
        self.connection_good = False
        self.last_frame_time = None
        self.is_running = False
        self.thread = None
        
        # Пороги для детекции
        self.freeze_threshold = 1000  # Минимальная разность между кадрами
        self.freeze_frames = 5       # Количество кадров для определения заморозки
        self.quality_threshold = 20  # Порог качества изображения
        self.timeout_seconds = 10    # Таймаут для определения отсутствия кадров
        
        # Статистика
        self.stats = {
            'total_frames': 0,
            'frozen_frames': 0,
            'low_quality_frames': 0,
            'connection_errors': 0,
            'last_alert': None
        }

    def connect(self) -> bool:
        """Установка соединения с камерой"""
        try:
            if self.cap is not None:
                self.cap.release()
            
            self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Минимальный буфер
            
            # Тестируем соединение
            ret, frame = self.cap.read()
            if ret and frame is not None:
                self.connection_good = True
                self.last_frame_time = time.time()
                logger.info(f"Камера {self.camera_id} ({self.name}) подключена")
                return True
            else:
                self.connection_good = False
                logger.warning(f"Не удалось подключиться к камере {self.camera_id} ({self.name})")
                return False
        except Exception as e:
            logger.error(f"Ошибка подключения к камере {self.camera_id}: {e}")
            self.connection_good = False
            return False

    def is_frozen(self, current_frame) -> bool:
        """Проверка на заморозку изображения"""
        if self.prev_frame is None:
            return False
            
        # Вычисляем разность между кадрами
        diff = cv2.absdiff(current_frame, self.prev_frame)
        total_diff = np.sum(diff)
        
        if total_diff < self.freeze_threshold:
            self.freeze_counter += 1
        else:
            self.freeze_counter = 0
            
        return self.freeze_counter >= self.freeze_frames

    def is_pixelated(self, frame) -> bool:
        """Проверка на пикселизацию/низкое качество"""
        # Конвертируем в серый
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Вычисляем контраст (стандартное отклонение)
        contrast = np.std(gray)
        
        # Проверяем на блоки артефакты (характерные для пикселизации)
        # Используем детектор границ для поиска блоков
        edges = cv2.Canny(gray, 50, 150)
        edge_density = np.sum(edges) / (edges.shape[0] * edges.shape[1])
        
        return contrast < self.quality_threshold or edge_density < 0.01

    def is_connection_lost(self) -> bool:
        """Проверка на потерю соединения"""
        if self.last_frame_time is None:
            return True
        return time.time() - self.last_frame_time > self.timeout_seconds

    def analyze_frame(self, frame):
        """Анализ кадра на различные проблемы"""
        alerts = []
        
        # Проверка на заморозку
        if self.is_frozen(frame):
            alerts.append("frozen")
            self.stats['frozen_frames'] += 1
            
        # Проверка на пикселизацию
        if self.is_pixelated(frame):
            alerts.append("pixelated")
            self.stats['low_quality_frames'] += 1
            
        # Обновляем статистику
        self.stats['total_frames'] += 1
        self.last_frame_time = time.time()
        
        return alerts

    def monitor_loop(self):
        """Основной цикл мониторинга"""
        logger.info(f"Запуск мониторинга камеры {self.camera_id} ({self.name})")
        
        while self.is_running:
            try:
                # Проверяем соединение
                if not self.connection_good or self.is_connection_lost():
                    if not self.connect():
                        self.stats['connection_errors'] += 1
                        time.sleep(5)
                        continue
                
                # Читаем кадр
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    logger.warning(f"Не удалось получить кадр с камеры {self.camera_id}")
                    self.stats['connection_errors'] += 1
                    time.sleep(2)
                    continue
                
                # Анализируем кадр
                alerts = self.analyze_frame(frame)
                
                # Отправляем уведомления
                if alerts:
                    self.send_alert(alerts)
                
                # Сохраняем кадр для следующего сравнения
                self.prev_frame = frame.copy()
                
                # Небольшая задержка для снижения нагрузки
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Ошибка в мониторинге камеры {self.camera_id}: {e}")
                self.stats['connection_errors'] += 1
                time.sleep(5)

    def send_alert(self, alert_types: List[str]):
        """Отправка уведомления о проблемах"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        alert_message = f"[{timestamp}] Камера {self.camera_id} ({self.name}): "
        
        if "frozen" in alert_types:
            alert_message += "ИЗОБРАЖЕНИЕ ЗАМОРОЖЕНО! "
        if "pixelated" in alert_types:
            alert_message += "НИЗКОЕ КАЧЕСТВО/ПИКСЕЛИЗАЦИЯ! "
            
        logger.warning(alert_message)
        self.stats['last_alert'] = {
            'timestamp': timestamp,
            'types': alert_types,
            'message': alert_message
        }

    def start(self):
        """Запуск мониторинга в отдельном потоке"""
        if self.is_running:
            return
            
        self.is_running = True
        self.thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.thread.start()
        logger.info(f"Мониторинг камеры {self.camera_id} запущен")

    def stop(self):
        """Остановка мониторинга"""
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=5)
        if self.cap:
            self.cap.release()
        logger.info(f"Мониторинг камеры {self.camera_id} остановлен")

    def get_status(self) -> Dict:
        """Получение текущего статуса камеры"""
        return {
            'camera_id': self.camera_id,
            'name': self.name,
            'rtsp_url': self.rtsp_url,
            'is_running': self.is_running,
            'connection_good': self.connection_good,
            'last_frame_time': self.last_frame_time,
            'stats': self.stats.copy()
        }

    def get_current_frame(self) -> Optional[np.ndarray]:
        """Получение текущего кадра для отображения"""
        if self.cap and self.connection_good:
            ret, frame = self.cap.read()
            if ret and frame is not None:
                return frame
        return None
