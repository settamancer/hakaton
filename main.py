from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import cv2
import numpy as np
import json
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional
import logging
from camera_monitor import CameraMonitor

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Camera Monitoring System", version="1.0.0")

# Глобальное хранилище камер и уведомлений
cameras: Dict[int, CameraMonitor] = {}
notifications: List[Dict] = []
notifications_lock = threading.Lock()

# Конфигурация камер (можно расширить)
CAMERA_CONFIGS = [
    {
        "id": 1,
        "name": "Camera 1",
        "rtsp_url": "rtsp://ins046msc:wQpQk35t@85.141.77.197:7554/ISAPI/Streaming/Channels/103"
    },
]

def add_notification(camera_id: int, alert_types: List[str], message: str):
    """Добавление уведомления в систему"""
    with notifications_lock:
        # Проверяем, есть ли уже активное уведомление для этой камеры с такими же типами ошибок
        existing_notification = None
        for notification in notifications:
            if (notification["camera_id"] == camera_id and 
                notification["alert_types"] == alert_types and 
                not notification["resolved"]):
                existing_notification = notification
                break
        
        if existing_notification:
            # Обновляем существующее уведомление
            existing_notification["timestamp"] = datetime.now().isoformat()
            existing_notification["message"] = message
            logger.warning(f"Обновлено уведомление: {message}")
        else:
            # Создаем новое уведомление
            notification = {
                "id": len(notifications) + 1,
                "camera_id": camera_id,
                "timestamp": datetime.now().isoformat(),
                "alert_types": alert_types,
                "message": message,
                "resolved": False
            }
            notifications.append(notification)
            
            # Ограничиваем количество уведомлений (последние 100)
            if len(notifications) > 100:
                notifications.pop(0)
            
            logger.warning(f"Новое уведомление: {message}")

def start_camera_monitoring():
    """Запуск мониторинга всех камер"""
    for config in CAMERA_CONFIGS:
        camera = CameraMonitor(
            camera_id=config["id"],
            name=config["name"],
            rtsp_url=config["rtsp_url"]
        )
        cameras[config["id"]] = camera
        camera.start()
        logger.info(f"Запущена камера {config['id']}: {config['name']}")

# API Endpoints

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Главная страница с дашбордом камер"""
    html_content = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Система мониторинга камер — Новый дизайн</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0; padding: 0;
            background-color: #f0f2f5;
            color: #333;
            height: 100vh;
            display: grid;
            grid-template-columns: 1fr 480px;
            grid-gap: 12px;
            padding: 20px;
        }
        #map-container {
            background: #e0e0e0;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgb(0 0 0 / 0.15);
            display: flex;
            justify-content: center;
            align-items: center;
            color: #666;
            font-size: 1.2rem;
            user-select: none;
        }
        #right-panel {
            display: flex;
            flex-direction: column;
            gap: 16px;
            max-height: 100vh;
            overflow-y: auto;
        }
        .cameras-summary {
            background: white;
            padding: 16px 24px;
            border-radius: 10px;
            box-shadow: 0 2px 6px rgb(0 0 0 / 0.1);
            font-weight: 600;
            font-size: 1.1rem;
            text-align: center;
            color: #1a73e8;
        }
        .camera-group {
            background: white;
            padding: 16px 20px;
            border-radius: 10px;
            box-shadow: 0 2px 6px rgb(0 0 0 / 0.1);
        }
        .camera-group h2 {
            margin: 0 0 12px;
            font-size: 1.2rem;
            border-bottom: 2px solid #1a73e8;
            padding-bottom: 4px;
            color: #1a73e8;
        }
        .camera-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 12px;
            border-radius: 7px;
            margin-bottom: 6px;
            font-size: 0.95rem;
            font-weight: 500;
            cursor: default;
            transition: background-color 0.25s ease;
        }
        .camera-item.online {
            background: #d0f0d6;
            color: #2d6a2d;
        }
        .camera-item.offline {
            background: #fde0dc;
            color: #b03030;
        }
        .camera-item:last-child {
            margin-bottom: 0;
        }
        .camera-status {
            font-weight: 700;
            font-size: 0.9rem;
            padding: 3px 10px;
            border-radius: 15px;
            user-select: none;
            white-space: nowrap;
        }
        .status-online {
            background-color: #4caf50;
            color: white;
        }
        .status-offline {
            background-color: #f44336;
            color: white;
        }
        #refresh-button {
            background: #1a73e8;
            border: none;
            color: white;
            font-size: 1rem;
            font-weight: 600;
            padding: 10px;
            border-radius: 10px;
            cursor: pointer;
            margin-bottom: 8px;
            width: 100%;
            transition: background-color 0.3s ease;
        }
        #refresh-button:hover {
            background: #1558b0;
        }
        #footer {
            text-align: center;
            font-size: 0.8rem;
            color: #888;
            margin-top: 20px;
        }
        /* Scrollbar styling for right panel */
        #right-panel::-webkit-scrollbar {
            width: 9px;
        }
        #right-panel::-webkit-scrollbar-thumb {
            background-color: rgba(26, 115, 232, 0.4);
            border-radius: 4px;
        }
        #right-panel::-webkit-scrollbar-track {
            background: transparent;
        }
    </style>
</head>
<body>
    <div id="map-container">
        <!-- Здесь будет карта -->
        Карта (заготовка)
    </div>
    <div id="right-panel">
        <button id="refresh-button" onclick="refreshStatus()">Обновить статусы камер</button>
        <div class="cameras-summary" id="cameras-summary">
            Всего камер: 0 | Онлайн: 0
        </div>
        <div class="camera-group" id="online-cameras">
            <h2>Рабочие камеры</h2>
            <div id="online-list">Загрузка...</div>
        </div>
        <div class="camera-group" id="offline-cameras">
            <h2>Не рабочие камеры</h2>
            <div id="offline-list">Загрузка...</div>
        </div>
    </div>

    <script>
        async function loadCameras() {
            try {
                const resp = await fetch('/api/cameras/status');
                const cameras = await resp.json();

                const onlineList = document.getElementById('online-list');
                const offlineList = document.getElementById('offline-list');
                const summary = document.getElementById('cameras-summary');

                onlineList.innerHTML = '';
                offlineList.innerHTML = '';

                let countOnline = 0;
                cameras.forEach(cam => {
                    const isOnline = cam.connection_good === true;
                    if (isOnline) countOnline++;

                    const item = document.createElement('div');
                    item.className = `camera-item ${isOnline ? 'online' : 'offline'}`;
                    item.title = cam.name;

                    const textName = document.createElement('span');
                    textName.textContent = `${cam.name} (ID: ${cam.camera_id})`;

                    const statusSpan = document.createElement('span');
                    statusSpan.className = 'camera-status ' + (isOnline ? 'status-online' : 'status-offline');
                    statusSpan.textContent = isOnline ? 'Работает' : 'Отключена';

                    item.appendChild(textName);
                    item.appendChild(statusSpan);

                    if (isOnline) {
                        onlineList.appendChild(item);
                    } else {
                        offlineList.appendChild(item);
                    }
                });

                summary.textContent = `Всего камер: ${cameras.length} | Онлайн: ${countOnline}`;

                if (onlineList.children.length === 0) onlineList.innerHTML = '<em>Нет рабочих камер</em>';
                if (offlineList.children.length === 0) offlineList.innerHTML = '<em>Нет не рабочих камер</em>';
            } catch (e) {
                console.error('Ошибка загрузки камер:', e);
                document.getElementById('online-list').innerHTML = 'Ошибка загрузки';
                document.getElementById('offline-list').innerHTML = 'Ошибка загрузки';
                document.getElementById('cameras-summary').textContent = 'Ошибка загрузки камер';
            }
        }

        function refreshStatus() {
            loadCameras();
        }

        // Автообновление статусов каждые 10 секунд
        setInterval(refreshStatus, 10000);
        window.onload = refreshStatus;
    </script>
</body>
</html>

    """
    return html_content

@app.get("/api/cameras/status")
async def get_cameras_status():
    """Получение статуса всех камер"""
    status_list = []
    for camera_id, camera in cameras.items():
        status_list.append(camera.get_status())
    return status_list

@app.get("/api/cameras/{camera_id}/video")
async def get_camera_video(camera_id: int):
    """Получение видео потока с камеры"""
    if camera_id not in cameras:
        raise HTTPException(status_code=404, detail="Камера не найдена")
    
    camera = cameras[camera_id]
    
    def generate_frames():
        frame_count = 0
        consecutive_errors = 0
        max_errors = 10
        
        while True:
            try:
                frame = camera.get_current_frame()
                if frame is not None:
                    consecutive_errors = 0  # Сбрасываем счетчик ошибок
                    
                    # Изменяем размер кадра для оптимизации
                    height, width = frame.shape[:2]
                    if width > 640:  # Масштабируем если слишком большое
                        scale = 640 / width
                        new_width = int(width * scale)
                        new_height = int(height * scale)
                        frame = cv2.resize(frame, (new_width, new_height))
                    
                    # Кодируем кадр в JPEG с оптимизацией
                    ret, buffer = cv2.imencode('.jpg', frame, [
                        cv2.IMWRITE_JPEG_QUALITY, 85,
                        cv2.IMWRITE_JPEG_OPTIMIZE, 1
                    ])
                    if ret:
                        frame_bytes = buffer.tobytes()
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                        
                        # Логируем каждые 100 кадров
                        if frame_count % 100 == 0:
                            logger.debug(f"Камера {camera_id}: отправлено {frame_count} кадров")
                else:
                    consecutive_errors += 1
                    # Отправляем placeholder изображение с информацией
                    placeholder = np.zeros((200, 400, 3), dtype=np.uint8)
                    cv2.putText(placeholder, "No Video Signal", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                    cv2.putText(placeholder, f"Camera {camera_id}", (50, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
                    cv2.putText(placeholder, f"Errors: {consecutive_errors}", (50, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
                    
                    ret, buffer = cv2.imencode('.jpg', placeholder, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if ret:
                        frame_bytes = buffer.tobytes()
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                
                frame_count += 1
                # Небольшая задержка для снижения нагрузки
                time.sleep(0.05)  # 20 FPS
                
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Ошибка в генерации кадра для камеры {camera_id}: {e}")
                
                if consecutive_errors >= max_errors:
                    logger.error(f"Слишком много ошибок для камеры {camera_id}, приостанавливаем поток")
                    break
                    
                time.sleep(1)
    
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.get("/api/notifications")
async def get_notifications():
    """Получение списка уведомлений"""
    with notifications_lock:
        return notifications.copy()

@app.post("/api/notifications/clear")
async def clear_notifications():
    """Очистка всех уведомлений"""
    with notifications_lock:
        notifications.clear()
    return {"message": "Уведомления очищены"}

@app.post("/api/notifications/{notification_id}/resolve")
async def resolve_notification(notification_id: int):
    """Разрешение конкретного уведомления"""
    with notifications_lock:
        for notification in notifications:
            if notification["id"] == notification_id:
                notification["resolved"] = True
                return {"message": f"Уведомление {notification_id} разрешено"}
    raise HTTPException(status_code=404, detail="Уведомление не найдено")

@app.post("/api/cameras/{camera_id}/resolve-alerts")
async def resolve_camera_alerts(camera_id: int):
    """Разрешение всех уведомлений для конкретной камеры"""
    with notifications_lock:
        resolved_count = 0
        for notification in notifications:
            if notification["camera_id"] == camera_id and not notification["resolved"]:
                notification["resolved"] = True
                resolved_count += 1
    return {"message": f"Разрешено {resolved_count} уведомлений для камеры {camera_id}"}

@app.get("/api/cameras/{camera_id}/stats")
async def get_camera_stats(camera_id: int):
    """Получение статистики камеры"""
    if camera_id not in cameras:
        raise HTTPException(status_code=404, detail="Камера не найдена")
    
    return cameras[camera_id].get_status()

@app.get("/api/cameras/{camera_id}/video-status")
async def get_video_status(camera_id: int):
    """Проверка статуса видео потока камеры"""
    if camera_id not in cameras:
        raise HTTPException(status_code=404, detail="Камера не найдена")
    
    camera = cameras[camera_id]
    frame = camera.get_current_frame()
    
    return {
        "camera_id": camera_id,
        "has_frame": frame is not None,
        "connection_good": camera.connection_good,
        "video_cap_active": camera.video_cap is not None and camera.video_cap.isOpened() if hasattr(camera, 'video_cap') else False,
        "frame_shape": frame.shape if frame is not None else None
    }

@app.post("/api/cameras/{camera_id}/restart")
async def restart_camera(camera_id: int):
    """Перезапуск камеры"""
    if camera_id not in cameras:
        raise HTTPException(status_code=404, detail="Камера не найдена")
    
    camera = cameras[camera_id]
    camera.stop()
    time.sleep(2)
    camera.start()
    
    return {"message": f"Камера {camera_id} перезапущена"}

@app.post("/api/cameras/{camera_id}/test-alerts")
async def test_camera_alerts(camera_id: int):
    """Тестирование системы уведомлений камеры"""
    if camera_id not in cameras:
        raise HTTPException(status_code=404, detail="Камера не найдена")
    
    camera = cameras[camera_id]
    camera.force_test_alerts()
    
    return {"message": f"Тестовые уведомления отправлены для камеры {camera_id}"}

@app.post("/api/cameras/{camera_id}/simulate-poor-connection")
async def simulate_poor_connection(camera_id: int):
    """Симуляция плохого качества соединения для тестирования"""
    if camera_id not in cameras:
        raise HTTPException(status_code=404, detail="Камера не найдена")
    
    camera = cameras[camera_id]
    camera.simulate_poor_connection()
    
    return {"message": f"Симуляция плохого соединения активирована для камеры {camera_id}"}

# Переопределяем метод send_alert в CameraMonitor для интеграции с FastAPI
def setup_camera_alerts():
    """Настройка системы уведомлений для камер"""
    for camera in cameras.values():
        # Переопределяем метод send_alert для интеграции с FastAPI
        def create_alert_handler(cam_id):
            def alert_handler(alert_types):
                # Создаем сообщение аналогично оригинальному методу
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                message = f"[{timestamp}] Камера {cam_id} ({camera.name}): "
                
                if "frozen" in alert_types:
                    message += "ИЗОБРАЖЕНИЕ ЗАМОРОЖЕНО! "
                if "stopped" in alert_types:
                    message += "ИЗОБРАЖЕНИЕ ОСТАНОВИЛОСЬ! "
                if "pixelated" in alert_types:
                    message += "КАЧЕСТВО ИЗОБРАЖЕНИЯ УПАЛО! "
                
                add_notification(cam_id, alert_types, message)
            return alert_handler
        
        camera.send_alert = create_alert_handler(camera.camera_id)

# Запуск системы при старте приложения
@app.on_event("startup")
async def startup_event():
    """Инициализация при запуске приложения"""
    logger.info("Запуск системы мониторинга камер...")
    start_camera_monitoring()
    setup_camera_alerts()
    logger.info("Система мониторинга запущена")

@app.on_event("shutdown")
async def shutdown_event():
    """Остановка системы при завершении приложения"""
    logger.info("Остановка системы мониторинга...")
    for camera in cameras.values():
        camera.stop()
    logger.info("Система мониторинга остановлена")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
