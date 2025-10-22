#!/usr/bin/env python3
"""
Тестовый скрипт для проверки системы мониторинга камер
"""

import requests
import time
import json

BASE_URL = "http://localhost:8000"

def test_api_endpoints():
    """Тестирование API endpoints"""
    print("🧪 Тестирование API endpoints...")
    
    try:
        # Тест статуса камер
        response = requests.get(f"{BASE_URL}/api/cameras/status")
        if response.status_code == 200:
            cameras = response.json()
            print(f"✅ Статус камер получен: {len(cameras)} камер")
            for camera in cameras:
                print(f"   - Камера {camera['camera_id']}: {camera['name']} - {'Онлайн' if camera['connection_good'] else 'Офлайн'}")
        else:
            print(f"❌ Ошибка получения статуса камер: {response.status_code}")
            
        # Тест уведомлений
        response = requests.get(f"{BASE_URL}/api/notifications")
        if response.status_code == 200:
            notifications = response.json()
            print(f"✅ Уведомления получены: {len(notifications)} уведомлений")
        else:
            print(f"❌ Ошибка получения уведомлений: {response.status_code}")
            
        # Тест главной страницы
        response = requests.get(f"{BASE_URL}/")
        if response.status_code == 200:
            print("✅ Главная страница доступна")
        else:
            print(f"❌ Ошибка главной страницы: {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Не удается подключиться к серверу. Убедитесь, что сервер запущен на localhost:8000")
        return False
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")
        return False
        
    return True

def test_camera_management():
    """Тестирование управления камерами"""
    print("\n🎥 Тестирование управления камерами...")
    
    try:
        # Получаем список камер
        response = requests.get(f"{BASE_URL}/api/cameras/status")
        if response.status_code != 200:
            print("❌ Не удается получить список камер")
            return False
            
        cameras = response.json()
        if not cameras:
            print("⚠️ Нет доступных камер для тестирования")
            return True
            
        # Тестируем перезапуск первой камеры
        camera_id = cameras[0]['camera_id']
        print(f"🔄 Тестирование перезапуска камеры {camera_id}...")
        
        response = requests.post(f"{BASE_URL}/api/cameras/{camera_id}/restart")
        if response.status_code == 200:
            print("✅ Камера успешно перезапущена")
        else:
            print(f"❌ Ошибка перезапуска камеры: {response.status_code}")
            
        # Тестируем получение статистики
        response = requests.get(f"{BASE_URL}/api/cameras/{camera_id}/stats")
        if response.status_code == 200:
            stats = response.json()
            print(f"✅ Статистика камеры получена: {stats['stats']['total_frames']} кадров")
        else:
            print(f"❌ Ошибка получения статистики: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Ошибка тестирования управления камерами: {e}")
        return False
        
    return True

def test_notifications():
    """Тестирование системы уведомлений"""
    print("\n🚨 Тестирование системы уведомлений...")
    
    try:
        # Получаем уведомления
        response = requests.get(f"{BASE_URL}/api/notifications")
        if response.status_code == 200:
            notifications = response.json()
            print(f"✅ Получено {len(notifications)} уведомлений")
            
            if notifications:
                print("Последние уведомления:")
                for notif in notifications[-3:]:  # Показываем последние 3
                    print(f"   - [{notif['timestamp']}] Камера {notif['camera_id']}: {notif['message']}")
        else:
            print(f"❌ Ошибка получения уведомлений: {response.status_code}")
            
        # Тестируем очистку уведомлений
        response = requests.post(f"{BASE_URL}/api/notifications/clear")
        if response.status_code == 200:
            print("✅ Уведомления очищены")
        else:
            print(f"❌ Ошибка очистки уведомлений: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Ошибка тестирования уведомлений: {e}")
        return False
        
    return True

def main():
    """Основная функция тестирования"""
    print("🚀 Запуск тестирования системы мониторинга камер")
    print("=" * 50)
    
    # Ждем немного, чтобы сервер успел запуститься
    print("⏳ Ожидание запуска сервера...")
    time.sleep(3)
    
    # Тестируем API
    api_ok = test_api_endpoints()
    
    if api_ok:
        # Тестируем управление камерами
        camera_ok = test_camera_management()
        
        # Тестируем уведомления
        notifications_ok = test_notifications()
        
        print("\n" + "=" * 50)
        print("📊 Результаты тестирования:")
        print(f"   API endpoints: {'✅ OK' if api_ok else '❌ FAIL'}")
        print(f"   Управление камерами: {'✅ OK' if camera_ok else '❌ FAIL'}")
        print(f"   Система уведомлений: {'✅ OK' if notifications_ok else '❌ FAIL'}")
        
        if api_ok and camera_ok and notifications_ok:
            print("\n🎉 Все тесты пройдены успешно!")
            print(f"🌐 Откройте браузер и перейдите по адресу: {BASE_URL}")
        else:
            print("\n⚠️ Некоторые тесты не прошли. Проверьте логи сервера.")
    else:
        print("\n❌ Не удается подключиться к серверу.")
        print("Убедитесь, что сервер запущен: python main.py")

if __name__ == "__main__":
    main()
