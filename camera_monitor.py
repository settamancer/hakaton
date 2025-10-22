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
        
        # Пороги для детекции (более чувствительные настройки)
        self.freeze_threshold = 1000   # Минимальная разность между кадрами (уменьшено)
        self.freeze_frames = 3        # Количество кадров для определения заморозки (уменьшено)
        self.quality_threshold = 30   # Порог качества изображения (увеличен)
        self.timeout_seconds = 20      # Таймаут для определения отсутствия кадров (уменьшен)
        
        # Дополнительные пороги для более точной детекции
        self.motion_threshold = 100   # Порог для детекции движения
        self.blur_threshold = 50      # Порог для детекции размытия
        self.no_motion_frames = 0     # Счетчик кадров без движения
        self.no_motion_threshold = 10  # Количество кадров без движения для детекции остановки
        
        # Пороги для оценки качества соединения
        self.connection_quality_threshold = 0.7  # Минимальное качество соединения (0-1)
        self.connection_check_frames = 5        # Количество кадров для оценки соединения
        self.connection_quality_history = []    # История качества соединения
        
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
        """Проверка на заморозку изображения (улучшенная детекция)"""
        if self.prev_frame is None:
            return False
            
        # Вычисляем разность между кадрами
        diff = cv2.absdiff(current_frame, self.prev_frame)
        total_diff = np.sum(diff)
        
        # Дополнительная проверка на основе стандартного отклонения
        gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        std_diff = np.std(gray_diff)
        
        # Комбинированная проверка: общая разность И стандартное отклонение
        is_static = (total_diff < self.freeze_threshold) and (std_diff < self.motion_threshold)
        
        if is_static:
            self.freeze_counter += 1
        else:
            self.freeze_counter = 0
            
        return self.freeze_counter >= self.freeze_frames

    def is_pixelated(self, frame) -> bool:
        """Проверка на пикселизацию/низкое качество (улучшенная детекция)"""
        # Конвертируем в серый
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Вычисляем контраст (стандартное отклонение)
        contrast = np.std(gray)
        
        # Проверяем на блоки артефакты (характерные для пикселизации)
        edges = cv2.Canny(gray, 50, 150)
        edge_density = np.sum(edges) / (edges.shape[0] * edges.shape[1])
        
        # Дополнительная проверка на размытие
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        # Проверка на блоки пикселей (характерно для сжатия)
        block_size = 8
        h, w = gray.shape
        block_artifacts = 0
        for i in range(0, h - block_size, block_size):
            for j in range(0, w - block_size, block_size):
                block = gray[i:i+block_size, j:j+block_size]
                if np.std(block) < 5:  # Очень низкая вариация в блоке
                    block_artifacts += 1
        
        block_ratio = block_artifacts / ((h // block_size) * (w // block_size))
        
        # Комбинированная проверка качества
        low_contrast = contrast < self.quality_threshold
        low_edges = edge_density < 0.01
        low_sharpness = laplacian_var < self.blur_threshold
        high_blocks = block_ratio > 0.3
        
        return low_contrast or low_edges or low_sharpness or high_blocks

    def is_image_stopped(self, current_frame) -> bool:
        """Проверка на остановку изображения (отсутствие движения)"""
        if self.prev_frame is None:
            return False
            
        # Вычисляем разность между кадрами
        diff = cv2.absdiff(current_frame, self.prev_frame)
        total_diff = np.sum(diff)
        
        # Если движение очень малое, увеличиваем счетчик
        if total_diff < self.motion_threshold:
            self.no_motion_frames += 1
        else:
            self.no_motion_frames = 0
            
        return self.no_motion_frames >= self.no_motion_threshold

    def assess_connection_quality(self, frame) -> float:
        """Оценка качества соединения на основе кадра (0-1, где 1 - отличное качество)"""
        if frame is None:
            return 0.0
            
        try:
            # Конвертируем в серый
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Оценка качества на основе нескольких факторов
            quality_score = 0.0
            
            # 1. Контраст (стандартное отклонение)
            contrast = np.std(gray)
            contrast_score = min(contrast / 50.0, 1.0)  # Нормализуем к 0-1
            quality_score += contrast_score * 0.3
            
            # 2. Резкость (Laplacian variance)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            sharpness_score = min(laplacian_var / 100.0, 1.0)  # Нормализуем к 0-1
            quality_score += sharpness_score * 0.3
            
            # 3. Плотность границ
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.sum(edges) / (edges.shape[0] * edges.shape[1])
            edge_score = min(edge_density / 0.1, 1.0)  # Нормализуем к 0-1
            quality_score += edge_score * 0.2
            
            # 4. Отсутствие блоков артефактов
            block_size = 8
            h, w = gray.shape
            block_artifacts = 0
            total_blocks = 0
            for i in range(0, h - block_size, block_size):
                for j in range(0, w - block_size, block_size):
                    block = gray[i:i+block_size, j:j+block_size]
                    total_blocks += 1
                    if np.std(block) < 5:  # Очень низкая вариация в блоке
                        block_artifacts += 1
            
            if total_blocks > 0:
                artifact_ratio = block_artifacts / total_blocks
                artifact_score = 1.0 - artifact_ratio  # Чем меньше артефактов, тем лучше
                quality_score += artifact_score * 0.2
            
            return min(quality_score, 1.0)
            
        except Exception as e:
            logger.warning(f"Ошибка при оценке качества соединения: {e}")
            return 0.0

    def is_connection_quality_good(self) -> bool:
        """Проверка качества соединения на основе истории"""
        if len(self.connection_quality_history) < self.connection_check_frames:
            return True  # Недостаточно данных для оценки
            
        # Среднее качество за последние кадры
        avg_quality = np.mean(self.connection_quality_history[-self.connection_check_frames:])
        return avg_quality >= self.connection_quality_threshold

    def is_connection_lost(self) -> bool:
        """Проверка на потерю соединения"""
        if self.last_frame_time is None:
            return True
        return time.time() - self.last_frame_time > self.timeout_seconds

    def analyze_frame(self, frame):
        """Анализ кадра на различные проблемы с приоритетом проверки соединения"""
        alerts = []
        
        # Сначала оцениваем качество соединения
        connection_quality = self.assess_connection_quality(frame)
        self.connection_quality_history.append(connection_quality)
        
        # Ограничиваем размер истории
        if len(self.connection_quality_history) > self.connection_check_frames * 2:
            self.connection_quality_history.pop(0)
        
        # Проверяем качество соединения
        if not self.is_connection_quality_good():
            # При плохом качестве соединения - детальный анализ
            logger.warning(f"Камера {self.camera_id}: Плохое качество соединения ({connection_quality:.2f})")
            
            # Проверка на заморозку
            if self.is_frozen(frame):
                alerts.append("frozen")
                self.stats['frozen_frames'] += 1
                
            # Проверка на остановку изображения
            if self.is_image_stopped(frame):
                alerts.append("stopped")
                self.stats['frozen_frames'] += 1
                
            # Проверка на пикселизацию/низкое качество
            if self.is_pixelated(frame):
                alerts.append("pixelated")
                self.stats['low_quality_frames'] += 1
        else:
            # При хорошем качестве соединения - только базовая проверка
            logger.debug(f"Камера {self.camera_id}: Хорошее качество соединения ({connection_quality:.2f})")
            
            # Только проверка на полную заморозку (критическая проблема)
            if self.is_frozen(frame):
                alerts.append("frozen")
                self.stats['frozen_frames'] += 1
            
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
        if "stopped" in alert_types:
            alert_message += "ИЗОБРАЖЕНИЕ ОСТАНОВИЛОСЬ! "
        if "pixelated" in alert_types:
            alert_message += "КАЧЕСТВО ИЗОБРАЖЕНИЯ УПАЛО! "
            
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
        # Вычисляем текущее качество соединения
        current_quality = 0.0
        if self.connection_quality_history:
            current_quality = np.mean(self.connection_quality_history[-3:])  # Среднее за последние 3 кадра
        
        return {
            'camera_id': self.camera_id,
            'name': self.name,
            'rtsp_url': self.rtsp_url,
            'is_running': self.is_running,
            'connection_good': self.connection_good,
            'connection_quality': current_quality,
            'connection_quality_good': self.is_connection_quality_good(),
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

    def force_test_alerts(self):
        """Принудительная генерация тестовых ошибок для проверки системы"""
        logger.info(f"Генерация тестовых ошибок для камеры {self.camera_id}")
        
        # Тест остановки изображения
        self.send_alert(["stopped"])
        time.sleep(1)
        
        # Тест падения качества
        self.send_alert(["pixelated"])
        time.sleep(1)
        
        # Тест заморозки
        self.send_alert(["frozen"])
        
        logger.info(f"Тестовые ошибки сгенерированы для камеры {self.camera_id}")

    def simulate_poor_connection(self):
        """Симуляция плохого качества соединения для тестирования"""
        logger.info(f"Симуляция плохого качества соединения для камеры {self.camera_id}")
        
        # Добавляем плохие значения в историю качества
        for _ in range(self.connection_check_frames):
            self.connection_quality_history.append(0.3)  # Плохое качество
        
        logger.info(f"Качество соединения искусственно снижено для камеры {self.camera_id}")
