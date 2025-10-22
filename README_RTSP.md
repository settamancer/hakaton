# Система мониторинга камер с улучшенной RTSP обработкой

## Архитектура системы

Система разделена на три основных компонента:

### 1. RTSPHandler / AdvancedRTSPHandler
- **Назначение**: Обработка RTSP потоков
- **Функции**: 
  - Установка соединения с RTSP камерой
  - Получение и буферизация кадров
  - Обработка ошибок соединения
  - Статистика потока (FPS, битрейт)

### 2. VideoDiagnostics
- **Назначение**: Анализ качества видео и детекция проблем
- **Функции**:
  - Детекция заморозки изображения
  - Анализ качества соединения
  - Детекция пикселизации
  - Оценка резкости и контраста

### 3. CameraMonitor
- **Назначение**: Координация между RTSP обработчиком и диагностикой
- **Функции**:
  - Управление жизненным циклом компонентов
  - Обработка уведомлений
  - Предоставление API для внешних систем

## Установка зависимостей

### Базовые зависимости
```bash
pip install -r requirements.txt
```

### Для улучшенной RTSP обработки
```bash
pip install -r requirements_rtsp.txt
```

### Установка специализированной библиотеки BBC
```bash
pip install git+https://github.com/bbc/rd-apmm-python-lib-rtp.git
```

## Использование

### Базовое использование
```python
from camera_monitor_new import CameraMonitor

# Создание монитора камеры
camera = CameraMonitor(
    camera_id=1,
    name="Camera 1",
    rtsp_url="rtsp://user:pass@ip:port/stream"
)

# Подключение и запуск
camera.connect()
camera.start()

# Получение статуса
status = camera.get_status()
print(f"Статус: {status['connection_good']}")
print(f"Качество: {status['connection_quality']}")

# Получение текущего кадра
frame = camera.get_current_frame()
if frame is not None:
    # Обработка кадра
    pass

# Остановка
camera.stop()
```

### Использование с продвинутым RTSP обработчиком
```python
from rtsp_handler_advanced import AdvancedRTSPHandler

# Создание продвинутого обработчика
rtsp_handler = AdvancedRTSPHandler(
    camera_id=1,
    rtsp_url="rtsp://user:pass@ip:port/stream",
    buffer_size=2  # MB
)

# Настройка callbacks
def on_frame(frame):
    print(f"Получен кадр: {frame.shape}")

def on_error(error):
    print(f"Ошибка: {error}")

rtsp_handler.set_frame_callback(on_frame)
rtsp_handler.set_error_callback(on_error)

# Запуск
rtsp_handler.connect()
rtsp_handler.start_monitoring()
rtsp_handler.start_video_stream()
```

## Преимущества новой архитектуры

### 1. Разделение ответственности
- **RTSPHandler**: Только работа с потоком
- **VideoDiagnostics**: Только анализ качества
- **CameraMonitor**: Координация и API

### 2. Улучшенная стабильность
- Отдельные потоки для мониторинга и видео
- Буферизация кадров
- Автоматическое переподключение

### 3. Расширяемость
- Легко добавить новые типы диагностики
- Возможность замены RTSP обработчика
- Модульная архитектура

### 4. Производительность
- Оптимизированная обработка кадров
- Асинхронная обработка
- Эффективное использование ресурсов

## Настройка

### Параметры RTSP соединения
```python
# В rtsp_handler.py или rtsp_handler_advanced.py
buffer_size = 1  # Размер буфера в MB
timeout = 10     # Таймаут соединения в секундах
fps_monitoring = 10  # FPS для мониторинга
fps_video = 20       # FPS для видео потока
```

### Параметры диагностики
```python
# В video_diagnostics.py
freeze_threshold = 500      # Порог заморозки
quality_threshold = 30      # Порог качества
connection_quality_threshold = 0.7  # Порог качества соединения
```

## Мониторинг и отладка

### Логирование
```python
import logging

# Настройка уровня логирования
logging.basicConfig(level=logging.DEBUG)

# Логирование компонентов
logger = logging.getLogger('rtsp_handler')
logger.setLevel(logging.INFO)
```

### Статистика
```python
# Получение статистики RTSP
rtsp_info = rtsp_handler.get_connection_info()
print(f"FPS: {rtsp_info['fps']}")
print(f"Ошибки: {rtsp_info['connection_errors']}")

# Получение статистики диагностики
diag_info = diagnostics.get_stats()
print(f"Качество: {diag_info['connection_quality']}")
print(f"Замороженные кадры: {diag_info['stats']['frozen_frames']}")
```

## Интеграция с FastAPI


# Создание камеры
camera = CameraMonitor(
    camera_id=1,
    name="Camera 1", 
    rtsp_url="rtsp://user:pass@ip:port/stream"
)

# Запуск мониторинга
camera.connect()
camera.start()
```

Все существующие API endpoints продолжают работать без изменений.
