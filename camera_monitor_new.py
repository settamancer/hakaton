import cv2
import numpy as np
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional
import logging
from rtsp_handler import RTSPHandler
from video_diagnostics import VideoDiagnostics

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CameraMonitor:
    def __init__(self, camera_id: int, name: str, rtsp_url: str):
        self.camera_id = camera_id
        self.name = name
        self.rtsp_url = rtsp_url
        
        # Инициализируем компоненты
        self.rtsp_handler = RTSPHandler(camera_id, rtsp_url)
        self.diagnostics = VideoDiagnostics(camera_id)
        
        # Настройка callbacks
        self.rtsp_handler.set_frame_callback(self._on_frame_received)
        self.rtsp_handler.set_error_callback(self._on_rtsp_error)
        self.diagnostics.set_alert_callback(self._on_alert_detected)
        
        # Состояние
        self.is_running = False
        self.last_alert = None
        
        # Статистика
        self.stats = {
            'total_frames': 0,
            'frozen_frames': 0,
            'low_quality_frames': 0,
            'connection_errors': 0,
            'last_alert': None
        }

    def _on_frame_received(self, frame: np.ndarray):
        """Callback для обработки полученных кадров"""
        try:
            # Анализируем кадр через диагностику
            alerts = self.diagnostics.analyze_frame(frame)
            
            # Обновляем статистику
            self.stats['total_frames'] += 1
            
        except Exception as e:
            logger.error(f"Ошибка обработки кадра для камеры {self.camera_id}: {e}")

    def _on_rtsp_error(self, error_message: str):
        """Callback для обработки ошибок RTSP"""
        logger.error(f"RTSP ошибка для камеры {self.camera_id}: {error_message}")
        self.stats['connection_errors'] += 1

    def _on_alert_detected(self, alert_types: List[str]):
        """Callback для обработки обнаруженных проблем"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        alert_message = f"[{timestamp}] Камера {self.camera_id} ({self.name}): "
        
        if "frozen" in alert_types:
            alert_message += "ИЗОБРАЖЕНИЕ ЗАМОРОЖЕНО! "
            self.stats['frozen_frames'] += 1
        if "stopped" in alert_types:
            alert_message += "ИЗОБРАЖЕНИЕ ОСТАНОВИЛОСЬ! "
        if "pixelated" in alert_types:
            alert_message += "КАЧЕСТВО ИЗОБРАЖЕНИЯ УПАЛО! "
            self.stats['low_quality_frames'] += 1
            
        logger.warning(alert_message)
        self.last_alert = {
            'timestamp': timestamp,
            'types': alert_types,
            'message': alert_message
        }
        self.stats['last_alert'] = self.last_alert

    def connect(self) -> bool:
        """Установка соединения с камерой"""
        return self.rtsp_handler.connect()

    def start(self):
        """Запуск мониторинга"""
        if self.is_running:
            return
            
        self.is_running = True
        
        # Запускаем RTSP обработчик
        self.rtsp_handler.start_monitoring()
        self.rtsp_handler.start_video_stream()
        
        logger.info(f"Мониторинг камеры {self.camera_id} запущен")

    def stop(self):
        """Остановка мониторинга"""
        self.is_running = False
        self.rtsp_handler.stop()
        logger.info(f"Мониторинг камеры {self.camera_id} остановлен")

    def get_status(self) -> Dict:
        rtsp_info = self.rtsp_handler.get_connection_info()
        diag_info = self.diagnostics.get_stats()

        return {
            'camera_id': self.camera_id,
            'name': self.name,
            'rtsp_url': self.rtsp_url,
            'is_running': bool(self.is_running),
            'connection_good': bool(rtsp_info['is_connected']),
            'connection_quality': float(diag_info['connection_quality']) if diag_info['connection_quality'] is not None else None,
            'connection_quality_good': bool(diag_info['connection_quality_good']) if diag_info['connection_quality_good'] is not None else None,
            'last_frame_time': rtsp_info['last_frame_time'],
            'stats': {
                **self.stats,
                **diag_info['stats']
            }
        }


    def get_current_frame(self) -> Optional[np.ndarray]:
        """Получение текущего кадра для отображения"""
        return self.rtsp_handler.get_current_frame()

    def force_test_alerts(self):
        """Принудительная генерация тестовых ошибок"""
        logger.info(f"Генерация тестовых ошибок для камеры {self.camera_id}")
        
        # Тест остановки изображения
        self._on_alert_detected(["stopped"])
        time.sleep(1)
        
        # Тест падения качества
        self._on_alert_detected(["pixelated"])
        time.sleep(1)
        
        # Тест заморозки
        self._on_alert_detected(["frozen"])
        
        logger.info(f"Тестовые ошибки сгенерированы для камеры {self.camera_id}")

    def simulate_poor_connection(self):
        """Симуляция плохого качества соединения"""
        logger.info(f"Симуляция плохого качества соединения для камеры {self.camera_id}")
        
        # Добавляем плохие значения в историю качества диагностики
        for _ in range(5):
            self.diagnostics.connection_quality_history.append(0.3)
        
        logger.info(f"Качество соединения искусственно снижено для камеры {self.camera_id}")

    def get_connection_quality(self) -> float:
        """Получение качества соединения"""
        return self.diagnostics.get_connection_quality()

    def is_connection_quality_good(self) -> bool:
        """Проверка качества соединения"""
        return self.diagnostics._is_connection_quality_good()
