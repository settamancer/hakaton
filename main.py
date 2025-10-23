from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import cv2
import numpy as np
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any
import logging
import json
import asyncio
from camera_monitor_new import CameraMonitor
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Camera Monitoring System", version="1.0.0")

# Добавляем CORS для работы с фронтендом
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

cameras: Dict[int, CameraMonitor] = {}
notifications: List[Dict[str, Any]] = []
notifications_lock = threading.Lock()

# WebSocket соединения
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        disconnected_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected_connections.append(connection)
        
        # Удаляем неактивные соединения
        for connection in disconnected_connections:
            self.disconnect(connection)

manager = ConnectionManager()

CAMERA_CONFIGS = [
    {
        "id": 1,
        "name": "Camera 1",
        "rtsp_url": "rtsp://ins046msc:wQpQk35t@85.141.77.197:7554/ISAPI/Streaming/Channels/103"
    },
]

def add_notification(camera_id: int, alert_types: List[str], message: str):
    notification: Dict[str, Any] = {}
    with notifications_lock:
        existing_notification = None
        for notification in notifications:
            if (notification["camera_id"] == camera_id and
                notification["alert_types"] == alert_types and
                not notification["resolved"]):
                existing_notification = notification
                break

        if existing_notification:
            existing_notification["timestamp"] = datetime.now().isoformat()
            existing_notification["message"] = message
            notification = existing_notification
            logger.warning(f"Updated notification: {message}")
        else:
            notification = {
                "id": len(notifications) + 1,
                "camera_id": camera_id,
                "timestamp": datetime.now().isoformat(),
                "alert_types": alert_types,
                "message": message,
                "resolved": False
            }
            notifications.append(notification)

            if len(notifications) > 100:
                notifications.pop(0)
            logger.warning(f"New notification: {message}")

        # Отправляем уведомление через WebSocket
        asyncio.create_task(manager.broadcast(json.dumps({
            "type": "notification",
            "data": notification
        })))

def start_camera_monitoring():
    for config in CAMERA_CONFIGS:
        camera = CameraMonitor(
            camera_id=config["id"],
            name=config["name"],
            rtsp_url=config["rtsp_url"]
        )
        cameras[config["id"]] = camera
        camera.start()
        logger.info(f"Started camera {config['id']}: {config['name']}")

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return """
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Система мониторинга камер с картой и уведомлениями</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin="" />
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
    border-radius: 12px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    overflow: hidden;
    height: 100vh;
    margin-bottom: 12px;
  }
  #map {
    height: 100%;
    width: 100%;
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
    box-shadow: 0 2px 6px rgba(0,0,0,0.1);
    font-weight: 600;
    font-size: 1.1rem;
    text-align: center;
    color: #1a73e8;
  }
  .camera-group {
    background: white;
    padding: 16px 20px;
    border-radius: 10px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.1);
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
  }
  .camera-item.online {
    background: #d0f0d6;
    color: #2d6a2d;
  }
  .camera-item.offline {
    background: #fde0dc;
    color: #b03030;
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
  #notifications {
    background: white;
    padding: 16px 20px;
    border-radius: 10px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.1);
    max-height: 25%;
    overflow-y: auto;
  }
  #notifications h2 {
    margin: 0 0 12px;
    color: #d32f2f;
    border-bottom: 2px solid #d32f2f;
    padding-bottom: 4px;
  }
  .notification-item {
    padding: 8px;
    background: #fff3f3;
    border-left: 4px solid #d32f2f;
    margin-bottom: 6px;
    border-radius: 4px;
    font-size: 0.9rem;
  }
  .toast {
    position: fixed;
    top: 20px;
    right: 20px;
    background: #d32f2f;
    color: white;
    padding: 12px 16px;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    z-index: 1000;
    max-width: 400px;
    animation: slideIn 0.3s ease-out;
  }
  @keyframes slideIn {
    from { transform: translateX(100%); opacity: 0; }
    to { transform: translateX(0); opacity: 1; }
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
</style>
</head>
<body>
<div id="map-container">
  <div id="map"></div>
</div>
<div id="right-panel">
  <button id="refresh-button" onclick="refreshStatus()">Обновить статусы камер</button>
  <div class="cameras-summary" id="cameras-summary">Всего камер: 0 | Онлайн: 0</div>
  <div class="camera-group" id="online-cameras">
    <h2>Рабочие камеры</h2>
    <div id="online-list">Загрузка...</div>
  </div>
  <div class="camera-group" id="offline-cameras">
    <h2>Не рабочие камеры</h2>
    <div id="offline-list">Загрузка...</div>
  </div>
  <div id="notifications">
    <h2>Уведомления для камеры 1</h2>
    <div id="notification-list"><em>Нет уведомлений</em></div>
  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" crossorigin=""></script>
<script>
  const moscowCoords = [55.7558, 37.6176];
  const map = L.map('map').setView(moscowCoords, 10);

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors'
  }).addTo(map);

  const greenIcon = L.icon({
    iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png',
    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
    iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41]
  });
  const redIcon = L.icon({
    iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
    iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41]
  });

  // Fake cameras for display
  const fakeCameras = [
    { id: 2, name: "Camera A", coords: [55.76, 37.62], online: true },
    { id: 3, name: "Camera B", coords: [55.75, 37.60], online: false },
    { id: 4, name: "Camera C", coords: [55.74, 37.63], online: true },
  ];
  const fakeCameraMarkers = [];

  let camera1Online = false;
  let camera1Marker = L.marker(moscowCoords, {icon: greenIcon}).addTo(map)
    .bindPopup("Загрузка статуса камеры 1...");

  // WebSocket соединение
  let ws = null;
  function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/notifications`;
    
    ws = new WebSocket(wsUrl);
    
    ws.onopen = function(event) {
      console.log('WebSocket соединение установлено');
    };
    
    ws.onmessage = function(event) {
      try {
        const data = JSON.parse(event.data);
        console.log('Получено WebSocket сообщение:', data);
        
        if (data.type === 'notification') {
          showToast(data.data.message);
          updateNotifications();
        }
      } catch (e) {
        console.error('Ошибка парсинга WebSocket сообщения:', e);
      }
    };
    
    ws.onclose = function(event) {
      console.log('WebSocket соединение закрыто, переподключение через 3 секунды...');
      setTimeout(connectWebSocket, 3000);
    };
    
    ws.onerror = function(error) {
      console.error('WebSocket ошибка:', error);
    };
  }

  function showToast(message) {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
      toast.remove();
    }, 5000);
  }

  async function loadCameras() {
    try {
      console.log('Загрузка статусов камер...');
      const resp = await fetch(`/api/cameras/status?t=${Date.now()}`);
      const cameras = await resp.json();
      console.log('Получены данные камер:', cameras);
      const cam1 = cameras.find(c => c.camera_id === 1);
      camera1Online = cam1 ? cam1.connection_good === true : false;
      console.log('Статус камеры 1:', camera1Online, cam1);
      camera1Marker.setIcon(camera1Online ? greenIcon : redIcon);
      camera1Marker.setPopupContent(`Камера 1: ${camera1Online ? "Работает" : "Не работает"}`);

      // Remove old fake markers
      fakeCameraMarkers.forEach(m => map.removeLayer(m));
      fakeCameraMarkers.length = 0;

      // Add fake cameras markers
      fakeCameras.forEach(fc => {
        const marker = L.marker(fc.coords, {icon: fc.online ? greenIcon : redIcon})
          .bindPopup(`${fc.name}: ${fc.online ? "Работает" : "Не работает"}`);
        marker.addTo(map);
        fakeCameraMarkers.push(marker);
      });

      // Combine real and fake cameras for the list
      const allCameras = cameras.concat(fakeCameras.map(fc => ({
        camera_id: fc.id,
        name: fc.name,
        connection_good: fc.online
      })));

      const onlineList = document.getElementById('online-list');
      const offlineList = document.getElementById('offline-list');
      const summary = document.getElementById('cameras-summary');
      onlineList.innerHTML = '';
      offlineList.innerHTML = '';

      let countOnline = 0;
      console.log('Обработка камер:', allCameras);
      allCameras.forEach(cam => {
        const isOnline = cam.connection_good === true;
        console.log(`Камера ${cam.camera_id}: ${cam.name} - ${isOnline ? 'онлайн' : 'офлайн'}`);
        if(isOnline) countOnline++;

        const item = document.createElement('div');
        item.className = 'camera-item ' + (isOnline ? 'online' : 'offline');
        item.title = cam.name;

        const textName = document.createElement('span');
        textName.textContent = `${cam.name} (ID: ${cam.camera_id})`;

        const statusSpan = document.createElement('span');
        statusSpan.className = 'camera-status ' + (isOnline ? 'status-online' : 'status-offline');
        statusSpan.textContent = isOnline ? 'Работает' : 'Отключена';

        item.appendChild(textName);
        item.appendChild(statusSpan);

        if(isOnline) onlineList.appendChild(item);
        else offlineList.appendChild(item);
      });

      summary.textContent = `Всего камер: ${allCameras.length} | Онлайн: ${countOnline}`;
      console.log(`Обновлено: ${allCameras.length} камер, ${countOnline} онлайн`);

      updateNotifications();

    } catch(e) {
      console.error("Ошибка загрузки камер или уведомлений:", e);
    }
  }

  async function updateNotifications() {
    try {
      const resp = await fetch('/api/notifications');
      const notifications = await resp.json();
      
      const notifList = document.getElementById('notification-list');
      notifList.innerHTML = '';
      
      if (notifications.length > 0) {
        notifications.slice(-5).reverse().forEach(notif => {
          const div = document.createElement('div');
          div.className = 'notification-item';
          div.textContent = notif.message;
          notifList.appendChild(div);
        });
      } else {
        notifList.innerHTML = '<em>Нет уведомлений</em>';
      }
    } catch(e) {
      console.error("Ошибка загрузки уведомлений:", e);
    }
  }

  function refreshStatus() {
    loadCameras();
  }

  setInterval(refreshStatus, 5000);
  window.onload = function() {
    connectWebSocket();
    refreshStatus();
  };
</script>
</body>
</html>
    """

# WebSocket endpoint
@app.websocket("/ws/notifications")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Эхо сообщение обратно
            await manager.send_personal_message(f"Message text was: {data}", websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/api/notifications")
async def get_notifications():
    with notifications_lock:
        return notifications[-20:]  # Последние 20 уведомлений

@app.get("/api/cameras/status")
async def get_cameras_status():
    status_list = []
    for camera_id, camera in cameras.items():
        status_list.append(camera.get_status())
    
    response = JSONResponse(content=status_list)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.get("/api/cameras/{camera_id}/video")
async def get_camera_video(camera_id: int):
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
                    consecutive_errors = 0  # Reset error count

                    height, width = frame.shape[:2]
                    if width > 640:
                        scale = 640 / width
                        new_width = int(width * scale)
                        new_height = int(height * scale)
                        frame = cv2.resize(frame, (new_width, new_height))

                    ret, buffer = cv2.imencode('.jpg', frame, [
                        cv2.IMWRITE_JPEG_QUALITY, 85,
                        cv2.IMWRITE_JPEG_OPTIMIZE, 1
                    ])
                    if ret:
                        frame_bytes = buffer.tobytes()
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

                    if frame_count % 100 == 0:
                        logger.debug(f"Камера {camera_id}: отправлено {frame_count} кадров")
                else:
                    consecutive_errors += 1
                    placeholder = np.zeros((200, 400, 3), dtype=np.uint8)
                    cv2.putText(placeholder, "No Video Signal", (50, 80),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                    cv2.putText(placeholder, f"Camera {camera_id}", (50, 120),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
                    cv2.putText(placeholder, f"Errors: {consecutive_errors}", (50, 160),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)

                    ret, buffer = cv2.imencode('.jpg', placeholder, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if ret:
                        frame_bytes = buffer.tobytes()
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

                frame_count += 1
                time.sleep(0.05)

            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Frame generation error for camera {camera_id}: {e}")
                if consecutive_errors >= max_errors:
                    logger.error(f"Too many errors for camera {camera_id}, stopping stream")
                    break
                time.sleep(1)

    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

def setup_camera_alerts():
    for camera in cameras.values():
        def create_alert_handler(cam_id: int, cam_name: str):
            def alert_handler(alert_types: List[str]):
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                message = f"[{timestamp}] Камера {cam_id} ({cam_name}): "
                if "frozen" in alert_types:
                    message += "ИЗОБРАЖЕНИЕ ЗАМОРОЖЕНО! "
                if "stopped" in alert_types:
                    message += "ИЗОБРАЖЕНИЕ ОСТАНОВИЛОСЬ! "
                if "pixelated" in alert_types:
                    message += "КАЧЕСТВО ИЗОБРАЖЕНИЯ УПАЛО! "
                add_notification(cam_id, alert_types, message)
            return alert_handler
        
        # Используем setattr для установки обработчика
        setattr(camera, 'send_alert', create_alert_handler(camera.camera_id, camera.name))

async def monitor_camera_status():
    previous_statuses = {}
    while True:
        for camera_id, camera in cameras.items():
            status = camera.get_status()
            prev_status = previous_statuses.get(camera_id)
            if prev_status != status:
                if not status.get('connection_good', True):
                    camera.send_alert(['stopped'])
            previous_statuses[camera_id] = status
        await asyncio.sleep(5)

@app.on_event("startup")
async def startup_event():
    logger.info("Запуск системы мониторинга камер...")
    start_camera_monitoring()
    # Даем время камерам инициализироваться перед настройкой алертов
    await asyncio.sleep(2)
    setup_camera_alerts()
    logger.info("Система мониторинга запущена")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Остановка системы мониторинга...")
    for camera in cameras.values():
        camera.stop()
    logger.info("Система мониторинга остановлена")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)