import cv2
import numpy as np
import time
import threading
import logging
from typing import Optional, Callable, Dict, Any
from datetime import datetime

# Настройка логирования
logger = logging.getLogger(__name__)

class RTSPHandler:
    """Класс для обработки RTSP потока с использованием специализированных библиотек"""
    
    def __init__(self, camera_id: int, rtsp_url: str, buffer_size: int = 1):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.buffer_size = buffer_size
        
        # Состояние соединения
        self.is_connected = False
        self.is_running = False
        self.last_frame_time = None
        self.connection_errors = 0
        
        # Поток и кадры
        self.cap = None
        self.video_cap = None  # Отдельный поток для видео
        self.current_frame = None
        self.frame_lock = threading.Lock()
        
        # Статистика
        self.stats = {
            'total_frames': 0,
            'connection_errors': 0,
            'last_connection_time': None,
            'connection_uptime': 0
        }
        
        # Callbacks
        self.frame_callback = None
        self.error_callback = None
        
    def set_frame_callback(self, callback: Callable[[np.ndarray], None]):
        """Установка callback для обработки кадров"""
        self.frame_callback = callback
        
    def set_error_callback(self, callback: Callable[[str], None]):
        """Установка callback для обработки ошибок"""
        self.error_callback = callback
        
    def connect(self) -> bool:
        """Установка соединения с RTSP потоком"""
        try:
            if self.cap is not None:
                self.cap.release()
            if self.video_cap is not None:
                self.video_cap.release()
            
            # Основное соединение для мониторинга
            self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, self.buffer_size)
            
            # Отдельное соединение для видео потока
            self.video_cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            self.video_cap.set(cv2.CAP_PROP_BUFFERSIZE, self.buffer_size)
            
            # Тестируем соединение
            ret, frame = self.cap.read()
            if ret and frame is not None:
                self.is_connected = True
                self.last_frame_time = time.time()
                self.stats['last_connection_time'] = datetime.now()
                logger.info(f"RTSP соединение установлено для камеры {self.camera_id}")
                return True
            else:
                self.is_connected = False
                logger.warning(f"Не удалось установить RTSP соединение для камеры {self.camera_id}")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка установки RTSP соединения для камеры {self.camera_id}: {e}")
            self.is_connected = False
            self.connection_errors += 1
            return False
    
    def start_monitoring(self):
        """Запуск мониторинга RTSP потока"""
        if self.is_running:
            return
            
        self.is_running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info(f"Мониторинг RTSP потока запущен для камеры {self.camera_id}")
    
    def start_video_stream(self):
        """Запуск видео потока"""
        if self.is_running:
            return
            
        self.is_running = True
        self.video_thread = threading.Thread(target=self._video_loop, daemon=True)
        self.video_thread.start()
        logger.info(f"Видео поток запущен для камеры {self.camera_id}")
    
    def _monitor_loop(self):
        """Основной цикл мониторинга"""
        while self.is_running:
            try:
                if not self.is_connected or self._is_connection_lost():
                    if not self.connect():
                        self.stats['connection_errors'] += 1
                        time.sleep(5)
                        continue
                
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    logger.warning(f"Не удалось получить кадр с RTSP потока камеры {self.camera_id}")
                    self.stats['connection_errors'] += 1
                    time.sleep(2)
                    continue
                
                # Обновляем текущий кадр
                with self.frame_lock:
                    self.current_frame = frame.copy()
                
                # Вызываем callback если установлен
                if self.frame_callback:
                    try:
                        self.frame_callback(frame)
                    except Exception as e:
                        logger.error(f"Ошибка в frame callback для камеры {self.camera_id}: {e}")
                
                self.stats['total_frames'] += 1
                self.last_frame_time = time.time()
                
                time.sleep(0.1)  # 10 FPS для мониторинга
                
            except Exception as e:
                logger.error(f"Ошибка в мониторинге RTSP потока камеры {self.camera_id}: {e}")
                self.stats['connection_errors'] += 1
                if self.error_callback:
                    self.error_callback(str(e))
                time.sleep(5)
    
    def _video_loop(self):
        """Цикл для видео потока"""
        while self.is_running:
            try:
                if not self.is_connected:
                    time.sleep(1)
                    continue
                
                ret, frame = self.video_cap.read()
                if ret and frame is not None:
                    with self.frame_lock:
                        self.current_frame = frame.copy()
                    self.stats['total_frames'] += 1
                    self.last_frame_time = time.time()
                else:
                    time.sleep(0.1)
                    
                time.sleep(0.05)  # 20 FPS для видео
                
            except Exception as e:
                logger.error(f"Ошибка в видео потоке камеры {self.camera_id}: {e}")
                time.sleep(1)
    
    def _is_connection_lost(self) -> bool:
        """Проверка на потерю соединения"""
        if self.last_frame_time is None:
            return True
        return time.time() - self.last_frame_time > 10  # 10 секунд таймаут
    
    def get_current_frame(self) -> Optional[np.ndarray]:
        """Получение текущего кадра"""
        with self.frame_lock:
            return self.current_frame.copy() if self.current_frame is not None else None
    
    def get_connection_info(self) -> Dict[str, Any]:
        """Получение информации о соединении"""
        return {
            'camera_id': self.camera_id,
            'is_connected': self.is_connected,
            'is_running': self.is_running,
            'last_frame_time': self.last_frame_time,
            'connection_errors': self.connection_errors,
            'stats': self.stats.copy()
        }
    
    def stop(self):
        """Остановка RTSP потока"""
        self.is_running = False
        
        if hasattr(self, 'monitor_thread'):
            self.monitor_thread.join(timeout=5)
        if hasattr(self, 'video_thread'):
            self.video_thread.join(timeout=5)
            
        if self.cap:
            self.cap.release()
        if self.video_cap:
            self.video_cap.release()
            
        logger.info(f"RTSP поток остановлен для камеры {self.camera_id}")
