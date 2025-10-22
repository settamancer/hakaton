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
        
        logger.warning(f"Уведомление: {message}")

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
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Система мониторинга камер</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background-color: #f5f5f5;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 20px;
                border-radius: 10px;
                margin-bottom: 20px;
                text-align: center;
            }
            .cameras-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            .camera-card {
                background: white;
                border-radius: 10px;
                padding: 20px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                border-left: 4px solid #4CAF50;
            }
            .camera-card.offline {
                border-left-color: #f44336;
            }
            .camera-card.warning {
                border-left-color: #ff9800;
            }
            .camera-title {
                font-size: 18px;
                font-weight: bold;
                margin-bottom: 10px;
            }
            .camera-status {
                display: inline-block;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
                margin-bottom: 10px;
            }
            .status-online { background: #4CAF50; color: white; }
            .status-offline { background: #f44336; color: white; }
            .status-warning { background: #ff9800; color: white; }
            .camera-video {
                width: 100%;
                height: 100%;
                background: #000;
                object-fit: contain;
                display: block;
                margin: 0 auto;
                transition: opacity 0.3s ease;
            }
            .camera-video-container {
                position: relative;
                width: 100%;
                height: 200px;
                background: #000;
                border-radius: 5px;
                overflow: hidden;
                border: 1px solid #ddd;
            }
            .camera-video-overlay {
                position: absolute;
                top: 5px;
                right: 5px;
                background: rgba(0, 0, 0, 0.7);
                color: white;
                padding: 2px 6px;
                border-radius: 3px;
                font-size: 10px;
                font-weight: bold;
                z-index: 10;
            }
            .camera-video-container:hover .camera-video-overlay {
                background: rgba(0, 0, 0, 0.9);
            }
            .camera-video-container::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: linear-gradient(45deg, transparent 49%, rgba(255,255,255,0.1) 50%, transparent 51%);
                opacity: 0;
                transition: opacity 0.3s ease;
                pointer-events: none;
            }
            .camera-video-container:hover::before {
                opacity: 1;
            }
            .notifications {
                background: white;
                border-radius: 10px;
                padding: 20px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }
            .notification-item {
                padding: 10px;
                border-left: 4px solid #f44336;
                margin-bottom: 10px;
                background: #fff3cd;
                border-radius: 4px;
            }
            .notification-time {
                font-size: 12px;
                color: #666;
            }
            .controls {
                margin-bottom: 20px;
            }
            .btn {
                background: #4CAF50;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                cursor: pointer;
                margin-right: 10px;
            }
            .btn:hover {
                background: #45a049;
            }
            .btn-danger {
                background: #f44336;
            }
            .btn-danger:hover {
                background: #da190b;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🎥 Система мониторинга камер</h1>
            <p>Мониторинг в реальном времени с детекцией проблем</p>
        </div>
        
        <div class="controls">
            <button class="btn" onclick="refreshStatus()">🔄 Обновить статус</button>
            <button class="btn btn-danger" onclick="clearNotifications()">🗑️ Очистить уведомления</button>
            <button class="btn" onclick="testAlerts()" style="background: #ff9800;">🧪 Тест ошибок</button>
            <button class="btn" onclick="simulatePoorConnection()" style="background: #9c27b0;">📡 Симуляция плохого соединения</button>
        </div>
        
        <div class="cameras-grid" id="camerasGrid">
            <!-- Камеры будут загружены через JavaScript -->
        </div>
        
        <div class="notifications">
            <h3>🚨 Уведомления</h3>
            <div id="notificationsList">
                <!-- Уведомления будут загружены через JavaScript -->
            </div>
        </div>
        
        <script>
            async function loadCameras() {
                try {
                    const response = await fetch('/api/cameras/status');
                    const cameras = await response.json();
                    
                    const grid = document.getElementById('camerasGrid');
                    grid.innerHTML = '';
                    
                    cameras.forEach(camera => {
                        const card = document.createElement('div');
                        card.className = `camera-card ${camera.connection_good ? 'online' : 'offline'}`;
                        
                        let statusClass, statusText;
                        if (camera.connection_good && camera.connection_quality_good) {
                            statusClass = 'status-online';
                            statusText = 'Онлайн';
                        } else if (camera.connection_good && !camera.connection_quality_good) {
                            statusClass = 'status-warning';
                            statusText = 'Плохое качество';
                        } else {
                            statusClass = 'status-offline';
                            statusText = 'Офлайн';
                        }
                        
                        card.innerHTML = `
                            <div class="camera-title">${camera.name} (ID: ${camera.camera_id})</div>
                            <div class="camera-status ${statusClass}">${statusText}</div>
                            <div class="camera-video-container">
                                <img class="camera-video" src="/api/cameras/${camera.camera_id}/video" 
                                     onload="this.style.opacity='1'" 
                                     onerror="this.src='data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDAwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjMzMzIi8+PHRleHQgeD0iNTAlIiB5PSI0MCUiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSIxNiIgZmlsbD0iI2ZmZiIgdGV4dC1hbmNob3I9Im1pZGRsZSI+U3RyZWFtIEVycm9yPC90ZXh0Pjx0ZXh0IHg9IjUwJSIgeT0iNjAlIiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMTIiIGZpbGw9IiNjY2MiIHRleHQtYW5jaG9yPSJtaWRkbGUiPkNhbWVyYSB7Y2FtZXJhLmNhbWVyYV9pZH08L3RleHQ+PC9zdmc+'; this.style.opacity='1'"
                                     style="opacity: 0;">
                                <div class="camera-video-overlay">LIVE</div>
                            </div>
                            <div style="margin-top: 10px; font-size: 12px;">
                                <div>Кадров: ${camera.stats.total_frames}</div>
                                <div>Ошибок: ${camera.stats.connection_errors}</div>
                                <div>Качество соединения: ${(camera.connection_quality * 100).toFixed(1)}%</div>
                                ${camera.stats.last_alert ? `<div style="color: #f44336;">Последнее уведомление: ${camera.stats.last_alert.timestamp}</div>` : ''}
                            </div>
                        `;
                        
                        grid.appendChild(card);
                    });
                } catch (error) {
                    console.error('Ошибка загрузки камер:', error);
                }
            }
            
            async function loadNotifications() {
                try {
                    const response = await fetch('/api/notifications');
                    const notifications = await response.json();
                    
                    const list = document.getElementById('notificationsList');
                    list.innerHTML = '';
                    
                    if (notifications.length === 0) {
                        list.innerHTML = '<div style="color: #666; font-style: italic;">Нет уведомлений</div>';
                        return;
                    }
                    
                    notifications.slice(-10).reverse().forEach(notification => {
                        const item = document.createElement('div');
                        item.className = 'notification-item';
                        item.innerHTML = `
                            <div><strong>Камера ${notification.camera_id}:</strong> ${notification.message}</div>
                            <div class="notification-time">${new Date(notification.timestamp).toLocaleString()}</div>
                        `;
                        list.appendChild(item);
                    });
                } catch (error) {
                    console.error('Ошибка загрузки уведомлений:', error);
                }
            }
            
            function refreshStatus() {
                loadCameras();
                loadNotifications();
            }
            
            async function clearNotifications() {
                try {
                    await fetch('/api/notifications/clear', { method: 'POST' });
                    loadNotifications();
                } catch (error) {
                    console.error('Ошибка очистки уведомлений:', error);
                }
            }
            
            async function testAlerts() {
                try {
                    // Тестируем для первой камеры (ID: 1)
                    const response = await fetch('/api/cameras/1/test-alerts', { method: 'POST' });
                    const result = await response.json();
                    alert('Тестовые ошибки отправлены: ' + result.message);
                    // Обновляем уведомления через 2 секунды
                    setTimeout(loadNotifications, 2000);
                } catch (error) {
                    console.error('Ошибка тестирования:', error);
                    alert('Ошибка при тестировании: ' + error.message);
                }
            }
            
            async function simulatePoorConnection() {
                try {
                    // Симулируем плохое соединение для первой камеры (ID: 1)
                    const response = await fetch('/api/cameras/1/simulate-poor-connection', { method: 'POST' });
                    const result = await response.json();
                    alert('Симуляция плохого соединения активирована: ' + result.message);
                    // Обновляем статус через 1 секунду
                    setTimeout(refreshStatus, 1000);
                } catch (error) {
                    console.error('Ошибка симуляции:', error);
                    alert('Ошибка при симуляции: ' + error.message);
                }
            }
            
            // Автообновление каждые 5 секунд
            setInterval(refreshStatus, 5000);
            
            // Загрузка при старте
            refreshStatus();
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
        while True:
            try:
                frame = camera.get_current_frame()
                if frame is not None:
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
                else:
                    # Отправляем placeholder изображение с информацией
                    placeholder = np.zeros((200, 400, 3), dtype=np.uint8)
                    cv2.putText(placeholder, "No Video Signal", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                    cv2.putText(placeholder, f"Camera {camera_id}", (50, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
                    
                    ret, buffer = cv2.imencode('.jpg', placeholder, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if ret:
                        frame_bytes = buffer.tobytes()
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                
                frame_count += 1
                # Небольшая задержка для снижения нагрузки
                time.sleep(0.05)  # 20 FPS
                
            except Exception as e:
                logger.error(f"Ошибка в генерации кадра для камеры {camera_id}: {e}")
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

@app.get("/api/cameras/{camera_id}/stats")
async def get_camera_stats(camera_id: int):
    """Получение статистики камеры"""
    if camera_id not in cameras:
        raise HTTPException(status_code=404, detail="Камера не найдена")
    
    return cameras[camera_id].get_status()

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
