"""
Скрипт для запуска системы мониторинга камер
"""

import uvicorn
import sys
import os

def main():
    """Запуск системы мониторинга"""
    print("🚀 Запуск системы мониторинга камер...")
    print("=" * 50)
    
    # Проверяем наличие необходимых файлов
    required_files = ['main.py', 'camera_monitor.py', 'requirements.txt']
    missing_files = [f for f in required_files if not os.path.exists(f)]
    
    if missing_files:
        print(f"❌ Отсутствуют необходимые файлы: {', '.join(missing_files)}")
        sys.exit(1)
    
    print("✅ Все необходимые файлы найдены")
    print("🌐 Сервер будет доступен по адресу: http://localhost:8000")
    print("📱 Веб-интерфейс: http://localhost:8000")
    print("🔧 API документация: http://localhost:8000/docs")
    print("\n💡 Для остановки сервера нажмите Ctrl+C")
    print("=" * 50)
    
    try:
        # Запускаем сервер
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8000,
            reload=False,  # Отключаем автоперезагрузку для стабильности
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n🛑 Сервер остановлен пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка запуска сервера: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
