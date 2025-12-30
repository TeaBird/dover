# main.py - Точка входа для Railway
import os
import uvicorn

if __name__ == "__main__":
    # Получаем порт из переменной окружения Railway
    PORT = int(os.getenv("PORT", 8000))
    HOST = "0.0.0.0"
    
    print("=" * 50)
    print("🚀 Starting Power of Attorney Tracker")
    print("=" * 50)
    print(f"Host: {HOST}")
    print(f"Port: {PORT}")
    print(f"PYTHONPATH: {os.getenv('PYTHONPATH', 'Not set')}")
    print(f"Current directory: {os.getcwd()}")
    print("Files in current directory:")
    for file in os.listdir("."):
        print(f"  - {file}")
    print("=" * 50)
    
    # Запускаем сервер
    uvicorn.run(
        "app:app",
        host=HOST,
        port=PORT,
        reload=False,
        access_log=True,
        log_level="info"
    )
