import cv2
import numpy as np
import time
import logging
from typing import List, Dict, Optional, Callable
from datetime import datetime

# Настройка логирования
logger = logging.getLogger(__name__)

class VideoDiagnostics:
    """Класс для диагностики качества видео и детекции проблем"""
    
    def __init__(self, camera_id: int):
        self.camera_id = camera_id
        
        # Пороги для детекции
        self.freeze_threshold = 500
        self.freeze_frames = 3
        self.quality_threshold = 30
        self.motion_threshold = 100
        self.blur_threshold = 50
        self.no_motion_frames = 0
        self.no_motion_threshold = 10
        
        # Пороги для оценки качества соединения
        self.connection_quality_threshold = 0.7
        self.connection_check_frames = 5
        self.connection_quality_history = []
        
        # Состояние
        self.prev_frame = None
        self.freeze_counter = 0
        
        # Статистика
        self.stats = {
            'total_frames': 0,
            'frozen_frames': 0,
            'low_quality_frames': 0,
            'stopped_frames': 0,
            'connection_errors': 0,
            'last_alert': None
        }
        
        # Callbacks
        self.alert_callback = None
        
    def set_alert_callback(self, callback: Callable[[List[str]], None]):
        """Установка callback для уведомлений о проблемах"""
        self.alert_callback = callback
        
    def analyze_frame(self, frame: np.ndarray) -> List[str]:
        """Анализ кадра на различные проблемы"""
        alerts = []
        
        # Оцениваем качество соединения
        connection_quality = self._assess_connection_quality(frame)
        self.connection_quality_history.append(connection_quality)
        
        # Ограничиваем размер истории
        if len(self.connection_quality_history) > self.connection_check_frames * 2:
            self.connection_quality_history.pop(0)
        
        # Проверяем качество соединения
        if not self._is_connection_quality_good():
            logger.warning(f"Камера {self.camera_id}: Плохое качество соединения ({connection_quality:.2f})")
            
            # Детальный анализ при плохом качестве
            if self._is_frozen(frame):
                alerts.append("frozen")
                self.stats['frozen_frames'] += 1
                
            if self._is_image_stopped(frame):
                alerts.append("stopped")
                self.stats['stopped_frames'] += 1
                
            if self._is_pixelated(frame):
                alerts.append("pixelated")
                self.stats['low_quality_frames'] += 1
        else:
            logger.debug(f"Камера {self.camera_id}: Хорошее качество соединения ({connection_quality:.2f})")
            
            # Только критическая проверка при хорошем качестве
            if self._is_frozen(frame):
                alerts.append("frozen")
                self.stats['frozen_frames'] += 1
        
        # Обновляем статистику
        self.stats['total_frames'] += 1
        
        # Сохраняем кадр для следующего сравнения
        self.prev_frame = frame.copy()
        
        # Отправляем уведомления
        if alerts and self.alert_callback:
            self.alert_callback(alerts)
            
        return alerts
    
    def _assess_connection_quality(self, frame: np.ndarray) -> float:
        """Оценка качества соединения на основе кадра (0-1)"""
        if frame is None:
            return 0.0
            
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            quality_score = 0.0
            
            # 1. Контраст
            contrast = np.std(gray)
            contrast_score = min(contrast / 50.0, 1.0)
            quality_score += contrast_score * 0.3
            
            # 2. Резкость
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            sharpness_score = min(laplacian_var / 100.0, 1.0)
            quality_score += sharpness_score * 0.3
            
            # 3. Плотность границ
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.sum(edges) / (edges.shape[0] * edges.shape[1])
            edge_score = min(edge_density / 0.1, 1.0)
            quality_score += edge_score * 0.2
            
            # 4. Отсутствие артефактов
            block_size = 8
            h, w = gray.shape
            block_artifacts = 0
            total_blocks = 0
            for i in range(0, h - block_size, block_size):
                for j in range(0, w - block_size, block_size):
                    block = gray[i:i+block_size, j:j+block_size]
                    total_blocks += 1
                    if np.std(block) < 5:
                        block_artifacts += 1
            
            if total_blocks > 0:
                artifact_ratio = block_artifacts / total_blocks
                artifact_score = 1.0 - artifact_ratio
                quality_score += artifact_score * 0.2
            
            return min(quality_score, 1.0)
            
        except Exception as e:
            logger.warning(f"Ошибка при оценке качества соединения: {e}")
            return 0.0
    
    def _is_connection_quality_good(self) -> bool:
        """Проверка качества соединения"""
        if len(self.connection_quality_history) < self.connection_check_frames:
            return True
            
        avg_quality = np.mean(self.connection_quality_history[-self.connection_check_frames:])
        return avg_quality >= self.connection_quality_threshold
    
    def _is_frozen(self, current_frame: np.ndarray) -> bool:
        """Проверка на заморозку изображения"""
        if self.prev_frame is None:
            return False
            
        diff = cv2.absdiff(current_frame, self.prev_frame)
        total_diff = np.sum(diff)
        
        gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        std_diff = np.std(gray_diff)
        
        is_static = (total_diff < self.freeze_threshold) and (std_diff < self.motion_threshold)
        
        if is_static:
            self.freeze_counter += 1
        else:
            self.freeze_counter = 0
            
        return self.freeze_counter >= self.freeze_frames
    
    def _is_image_stopped(self, current_frame: np.ndarray) -> bool:
        """Проверка на остановку изображения"""
        if self.prev_frame is None:
            return False
            
        diff = cv2.absdiff(current_frame, self.prev_frame)
        total_diff = np.sum(diff)
        
        if total_diff < self.motion_threshold:
            self.no_motion_frames += 1
        else:
            self.no_motion_frames = 0
            
        return self.no_motion_frames >= self.no_motion_threshold
    
    def _is_pixelated(self, frame: np.ndarray) -> bool:
        """Проверка на пикселизацию/низкое качество"""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Контраст
        contrast = np.std(gray)
        
        # Границы
        edges = cv2.Canny(gray, 50, 150)
        edge_density = np.sum(edges) / (edges.shape[0] * edges.shape[1])
        
        # Резкость
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        # Блоки артефактов
        block_size = 8
        h, w = gray.shape
        block_artifacts = 0
        total_blocks = 0
        for i in range(0, h - block_size, block_size):
            for j in range(0, w - block_size, block_size):
                block = gray[i:i+block_size, j:j+block_size]
                total_blocks += 1
                if np.std(block) < 5:
                    block_artifacts += 1
        
        block_ratio = block_artifacts / total_blocks if total_blocks > 0 else 0
        
        # Комбинированная проверка
        low_contrast = contrast < self.quality_threshold
        low_edges = edge_density < 0.01
        low_sharpness = laplacian_var < self.blur_threshold
        high_blocks = block_ratio > 0.3
        
        return low_contrast or low_edges or low_sharpness or high_blocks
    
    def get_connection_quality(self) -> float:
        """Получение текущего качества соединения"""
        if self.connection_quality_history:
            return float(np.mean(self.connection_quality_history[-3:]))
        return 0.8 if self.stats['total_frames'] > 0 else 0.0
    
    def get_stats(self) -> Dict:
        """Получение статистики диагностики"""
        return {
            'camera_id': self.camera_id,
            'connection_quality': self.get_connection_quality(),
            'connection_quality_good': self._is_connection_quality_good(),
            'stats': self.stats.copy()
        }
    
    def reset_stats(self):
        """Сброс статистики"""
        self.stats = {
            'total_frames': 0,
            'frozen_frames': 0,
            'low_quality_frames': 0,
            'stopped_frames': 0,
            'connection_errors': 0,
            'last_alert': None
        }
        self.connection_quality_history.clear()
        self.freeze_counter = 0
        self.no_motion_frames = 0
