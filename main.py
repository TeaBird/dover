import os
import logging
from datetime import datetime, date, timedelta
from typing import List, Optional
import asyncio

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import uvicorn

# Импорты для PostgreSQL
import psycopg2
from psycopg2.extras import RealDictCursor

# ==================== НАСТРОЙКИ ====================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL")  # Railway автоматически добавляет эту переменную

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== ПРИЛОЖЕНИЕ ====================
app = FastAPI(title="Power of Attorney Tracker")

# ==================== БАЗА ДАННЫХ ====================
def get_db_connection():
    """Получение соединения с PostgreSQL"""
    if not DATABASE_URL:
        raise Exception("DATABASE_URL не установлен. Проверьте настройки Railway.")
    
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

def init_database():
    """Инициализация базы данных"""
    try:
        conn, db_type = get_db_connection()
        cursor = conn.cursor()
        
        # Простая проверка/создание таблицы
        if db_type == 'postgresql':
            # Проверяем существует ли таблица
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'powers_of_attorney'
                )
            """)
            table_exists = cursor.fetchone()[0]
            
            if not table_exists:
                # Создаем таблицу
                cursor.execute('''
                    CREATE TABLE powers_of_attorney (
                        id SERIAL PRIMARY KEY,
                        full_name TEXT NOT NULL,
                        poa_type TEXT NOT NULL,
                        start_date DATE NOT NULL,
                        end_date DATE NOT NULL,
                        telegram_chat_id TEXT DEFAULT '-5140897831',
                        notification_sent BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                logger.info("Таблица powers_of_attorney создана в PostgreSQL")
            else:
                logger.info("Таблица powers_of_attorney уже существует")
                
        else:
            # SQLite
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS powers_of_attorney (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT NOT NULL,
                    poa_type TEXT NOT NULL,
                    start_date DATE NOT NULL,
                    end_date DATE NOT NULL,
                    telegram_chat_id TEXT DEFAULT '-5140897831',
                    notification_sent BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            logger.info("Таблица powers_of_attorney проверена/создана в SQLite")
        
        conn.commit()
        cursor.close()
        conn.close()
        
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {e}")
        # Не падаем, просто логируем ошибку

# Инициализируем БД при старте
init_database()

# ==================== API ENDPOINTS ====================
@app.get("/")
async def root():
    """Корневая страница"""
    return {
        "service": "Power of Attorney Tracker",
        "status": "running",
        "version": "1.0.0",
        "database": "PostgreSQL",
        "docs": "/docs",
        "ui": "/ui"
    }

@app.get("/api/health")
async def health_check():
    """Проверка здоровья"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        db_status = "healthy"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "database": db_status,
        "database_type": "PostgreSQL",
        "telegram_bot": "configured" if TELEGRAM_BOT_TOKEN else "not_configured",
        "port": os.getenv("PORT", "8000")
    }

@app.get("/api/db-info")
async def db_info():
    """Информация о базе данных"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Информация о таблице
        cursor.execute("SELECT COUNT(*) as count FROM powers_of_attorney")
        count_result = cursor.fetchone()
        total_records = count_result['count'] if count_result else 0
        
        # Информация о базе
        cursor.execute("SELECT current_database() as db_name, current_user as user")
        db_info = cursor.fetchone()
        
        # Размер таблицы
        cursor.execute("SELECT pg_size_pretty(pg_total_relation_size('powers_of_attorney')) as table_size")
        size_info = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        return {
            "status": "success",
            "database": "PostgreSQL",
            "total_records": total_records,
            "database_name": db_info['db_name'] if db_info else "unknown",
            "current_user": db_info['user'] if db_info else "unknown",
            "table_size": size_info['table_size'] if size_info else "unknown",
            "connection_url": DATABASE_URL[:50] + "..." if DATABASE_URL else "not_set"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "database_url_set": bool(DATABASE_URL)
        }

@app.post("/api/powers/")
async def create_power(
    full_name: str,
    poa_type: str,
    end_date: str
):
    """Создать новую доверенность"""
    try:
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Неправильный формат даты. Используйте YYYY-MM-DD")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO powers_of_attorney 
            (full_name, poa_type, start_date, end_date)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        ''', (
            full_name,
            poa_type,
            date.today().isoformat(),
            end_date_obj.isoformat()
        ))
        
        power_id = cursor.fetchone()[0]
        conn.commit()
        
        cursor.close()
        conn.close()
        
        logger.info(f"Создана доверенность ID {power_id} для {full_name}")
        
        return {
            "id": power_id,
            "message": "Доверенность создана",
            "full_name": full_name,
            "end_date": end_date,
            "database": "PostgreSQL"
        }
        
    except Exception as e:
        logger.error(f"Ошибка создания доверенности: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка базы данных: {str(e)}")

@app.get("/api/powers/")
async def get_powers():
    """Получить все доверенности"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Запрос с правильным вычислением days_remaining
        cursor.execute('''
            SELECT 
                id,
                full_name,
                poa_type,
                start_date,
                end_date,
                telegram_chat_id,
                notification_sent,
                created_at,
                (end_date - CURRENT_DATE) as days_remaining
            FROM powers_of_attorney 
            ORDER BY end_date ASC
        ''')
        
        powers = cursor.fetchall()
        
        # Конвертируем результат
        result = []
        for power in powers:
            power_dict = dict(power)
            
            # Преобразуем даты в строки
            if power_dict.get('start_date'):
                if isinstance(power_dict['start_date'], date):
                    power_dict['start_date'] = power_dict['start_date'].isoformat()
                elif isinstance(power_dict['start_date'], datetime):
                    power_dict['start_date'] = power_dict['start_date'].date().isoformat()
            
            if power_dict.get('end_date'):
                if isinstance(power_dict['end_date'], date):
                    power_dict['end_date'] = power_dict['end_date'].isoformat()
                elif isinstance(power_dict['end_date'], datetime):
                    power_dict['end_date'] = power_dict['end_date'].date().isoformat()
            
            if power_dict.get('created_at'):
                if isinstance(power_dict['created_at'], datetime):
                    power_dict['created_at'] = power_dict['created_at'].isoformat()
            
            # Обрабатываем days_remaining
            # В PostgreSQL (end_date - CURRENT_DATE) возвращает интервал
            # Нужно извлечь количество дней
            if power_dict.get('days_remaining') is not None:
                days_rem = power_dict['days_remaining']
                if hasattr(days_rem, 'days'):
                    # Это timedelta объект
                    power_dict['days_remaining'] = days_rem.days
                elif isinstance(days_rem, int):
                    # Уже число
                    power_dict['days_remaining'] = days_rem
                else:
                    # Другой тип, преобразуем
                    try:
                        power_dict['days_remaining'] = int(days_rem)
                    except:
                        power_dict['days_remaining'] = 0
            else:
                power_dict['days_remaining'] = 0
            
            result.append(power_dict)
        
        cursor.close()
        conn.close()
        
        logger.info(f"Получено {len(result)} доверенностей")
        return result
        
    except Exception as e:
        logger.error(f"Ошибка получения доверенностей: {e}")
        import traceback
        error_details = traceback.format_exc()
        
        # Для отладки: что возвращает запрос
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM powers_of_attorney LIMIT 1")
            sample = cursor.fetchone()
            cursor.close()
            conn.close()
        except:
            sample = None
        
        return {
            "error": True,
            "message": str(e),
            "sample_row": str(sample) if sample else "нет данных",
            "traceback": error_details
        }

@app.delete("/api/powers/{power_id}")
async def delete_power(power_id: int):
    """Удалить доверенность"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM powers_of_attorney WHERE id = %s', (power_id,))
        deleted = cursor.rowcount > 0
        
        conn.commit()
        cursor.close()
        conn.close()
        
        if not deleted:
            raise HTTPException(status_code=404, detail="Доверенность не найдена")
        
        logger.info(f"Удалена доверенность ID {power_id}")
        
        return {
            "message": "Доверенность удалена",
            "id": power_id,
            "database": "PostgreSQL"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка удаления доверенности: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка базы данных: {str(e)}")

# ==================== HTML ИНТЕРФЕЙС ====================
# (Оставьте HTML интерфейс без изменений из вашего предыдущего кода)
# ВАЖНО: Уберите лишний JavaScript код для telegram_chat_id

@app.get("/ui", response_class=HTMLResponse)
async def web_interface():
    """Веб-интерфейс"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Трекер доверенностей</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { box-sizing: border-box; }
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                max-width: 1200px; 
                margin: 0 auto; 
                padding: 20px; 
                background: #f5f5f5;
            }
            .header { 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white; 
                padding: 30px; 
                border-radius: 15px; 
                margin-bottom: 30px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            }
            .header h1 { margin: 0; font-size: 2.5em; }
            .header p { margin: 10px 0 0; opacity: 0.9; }
            
            .container { display: grid; grid-template-columns: 1fr 2fr; gap: 30px; }
            @media (max-width: 768px) {
                .container { grid-template-columns: 1fr; }
            }
            
            .card { 
                background: white; 
                border-radius: 12px; 
                padding: 25px; 
                margin-bottom: 20px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.05);
                border: 1px solid #eaeaea;
            }
            
            .form-group { margin-bottom: 20px; }
            label { 
                display: block; 
                margin-bottom: 8px; 
                font-weight: 600;
                color: #333;
            }
            input, select { 
                width: 100%; 
                padding: 12px; 
                border: 2px solid #e0e0e0; 
                border-radius: 8px; 
                font-size: 16px;
                transition: border 0.3s;
            }
            input:focus, select:focus { 
                outline: none; 
                border-color: #667eea;
            }
            
            .btn {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white; 
                border: none; 
                padding: 14px 28px; 
                border-radius: 8px; 
                cursor: pointer;
                font-size: 16px;
                font-weight: 600;
                width: 100%;
                transition: transform 0.2s, box-shadow 0.2s;
            }
            .btn:hover { 
                transform: translateY(-2px);
                box-shadow: 0 10px 20px rgba(102, 126, 234, 0.3);
            }
            .btn:active { transform: translateY(0); }
            
            table { 
                width: 100%; 
                border-collapse: collapse;
                margin-top: 15px;
            }
            th { 
                background: #f8f9fa; 
                padding: 15px; 
                text-align: left;
                font-weight: 600;
                color: #495057;
                border-bottom: 2px solid #e9ecef;
            }
            td { 
                padding: 15px; 
                border-bottom: 1px solid #e9ecef;
                vertical-align: top;
            }
            tr:hover { background: #f8f9fa; }
            
            .badge {
                display: inline-block;
                padding: 4px 12px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 600;
                margin: 2px;
            }
            .badge-success { background: #d4edda; color: #155724; }
            .badge-warning { background: #fff3cd; color: #856404; }
            .badge-danger { background: #f8d7da; color: #721c24; }
            .badge-info { background: #d1ecf1; color: #0c5460; }
            
            .delete-btn {
                background: #dc3545;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 12px;
            }
            .delete-btn:hover { background: #c82333; }
            
            .stats {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 15px;
                margin-top: 20px;
            }
            .stat-card {
                background: white;
                padding: 20px;
                border-radius: 10px;
                text-align: center;
                box-shadow: 0 3px 10px rgba(0,0,0,0.05);
            }
            .stat-value {
                font-size: 2em;
                font-weight: bold;
                color: #667eea;
                margin: 10px 0;
            }
            .stat-label {
                color: #6c757d;
                font-size: 14px;
            }
            
            .alert {
                padding: 15px;
                border-radius: 8px;
                margin: 15px 0;
                display: none;
            }
            .alert-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
            .alert-error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1> Трекер доверенностей (PostgreSQL)</h1>
            <p>Отслеживание сроков доверенностей с уведомлениями в Telegram</p>
        </div>
        
        <div class="container">
            <!-- Левая колонка: Форма -->
            <div>
                <div class="card">
                    <h2 style="margin-top: 0;">➕ Добавить доверенность</h2>
                    <div id="alert" class="alert"></div>
                    
                    <form id="addForm">
                        <div class="form-group">
                            <label>ФИО *</label>
                            <input type="text" id="full_name" required placeholder="Иванов Иван Иванович">
                        </div>
                        
                        <div class="form-group">
                            <label>Тип доверенности *</label>
                            <select id="poa_type" required>
                                <option value="">Выберите тип</option>
                                <option value="m4d">m4d</option>
                                <option value="Росстат">Росстат</option>
                                <option value="Таможня">Таможня</option>                           
                            </select>
                        </div>
                        
                        <div class="form-group">
                            <label>Дата окончания *</label>
                            <input type="date" id="end_date" required>
                        </div>
                        
                        <button type="submit" class="btn"> Сохранить доверенность</button>
                    </form>
                </div>
                
                <!-- Статистика -->
                <div class="card">
                    <h3>📊 Статистика</h3>
                    <div class="stats" id="stats">
                        <div class="stat-card">
                            <div class="stat-value" id="totalCount">0</div>
                            <div class="stat-label">Всего</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value" id="activeCount">0</div>
                            <div class="stat-label">Активных</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value" id="expiringCount">0</div>
                            <div class="stat-label">Истекает</div>
                        </div>
                    </div>
                </div>
                
                <!-- Информация о БД -->
                <div class="card">
                    <h3> База данных</h3>
                    <p>Используется: <strong>PostgreSQL</strong></p>
                    <p>Данные сохраняются навсегда</p>
                    <button onclick="checkDbStatus()" style="background: #6c757d; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; margin-top: 10px;">
                         Проверить статус БД
                    </button>
                </div>
            </div>
            
            <!-- Правая колонка: Список -->
            <div>
                <div class="card">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <h2 style="margin: 0;"> Список доверенностей</h2>
                        <button onclick="loadPowers()" style="background: #6c757d; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer;">
                             Обновить
                        </button>
                    </div>
                    
                    <div id="powersList">
                        <p>Загрузка данных...</p>
                    </div>
                </div>
                
                <!-- Статус системы -->
                <div class="card">
                    <h3>⚙️ Статус системы</h3>
                    <div id="status">
                        <p>Проверка статуса...</p>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            let allPowers = [];
            
            // Показать уведомление
            function showAlert(message, type = 'success') {
                const alert = document.getElementById('alert');
                alert.textContent = message;
                alert.className = 'alert alert-' + type;
                alert.style.display = 'block';
                
                setTimeout(() => {
                    alert.style.display = 'none';
                }, 5000);
            }
            
            // Проверить статус БД
            async function checkDbStatus() {
                try {
                    const response = await fetch('/api/db-info');
                    const info = await response.json();
                    
                    alert('Статус БД: ' + info.status + '\\nЗаписей в БД: ' + info.total_records + '\\nРазмер таблицы: ' + info.table_size);
                } catch (error) {
                    alert('Ошибка проверки БД');
                }
            }
            
            // Загрузить доверенности
            async function loadPowers() {
                try {
                    const response = await fetch('/api/powers/');
                    allPowers = await response.json();
                    
                    if (allPowers.length === 0) {
                        document.getElementById('powersList').innerHTML = '<p>Нет доверенностей. Добавьте первую!</p>';
                        updateStats();
                        return;
                    }
                    
                    let html = '<table><thead><tr><th>ФИО</th><th>Тип</th><th>Начало</th><th>Окончание</th><th>Осталось</th><th>Действия</th></tr></thead><tbody>';
                    
                    allPowers.forEach(power => {
                        const endDate = new Date(power.end_date);
                        const today = new Date();
                        const daysLeft = Math.ceil((endDate - today) / (1000 * 60 * 60 * 24));
                        
                        let badgeClass = 'badge badge-success';
                        let badgeText = daysLeft + ' дн.';
                        
                        if (daysLeft <= 0) {
                            badgeClass = 'badge badge-danger';
                            badgeText = 'Просрочено';
                        } else if (daysLeft <= 3) {
                            badgeClass = 'badge badge-danger';
                        } else if (daysLeft <= 7) {
                            badgeClass = 'badge badge-warning';
                        } else if (daysLeft <= 30) {
                            badgeClass = 'badge badge-info';
                        }
                        
                        html += 
                            '<tr>' +
                                '<td>' +
                                    '<strong>' + power.full_name + '</strong>' +
                                    '<br><small style="color: #28a745;"> Уведомления Telegram</small>' +
                                '</td>' +
                                '<td><span class="badge badge-info">' + power.poa_type + '</span></td>' +
                                '<td>' + power.start_date + '</td>' +
                                '<td>' + power.end_date + '</td>' +
                                '<td><span class="' + badgeClass + '">' + badgeText + '</span></td>' +
                                '<td>' +
                                    '<button onclick="deletePower(' + power.id + ')" class="delete-btn">🗑️ Удалить</button>' +
                                '</td>' +
                            '</tr>';
                    });
                    
                    html += '</tbody></table>';
                    document.getElementById('powersList').innerHTML = html;
                    
                    updateStats();
                    
                } catch (error) {
                    document.getElementById('powersList').innerHTML = '<p> Ошибка загрузки данных</p>';
                    console.error('Error:', error);
                }
            }
            
            // Обновить статистику
            function updateStats() {
                const today = new Date();
                
                const total = allPowers.length;
                const active = allPowers.filter(p => {
                    const endDate = new Date(p.end_date);
                    return endDate >= today;
                }).length;
                
                const expiring = allPowers.filter(p => {
                    const endDate = new Date(p.end_date);
                    const daysLeft = Math.ceil((endDate - today) / (1000 * 60 * 60 * 24));
                    return daysLeft >= 0 && daysLeft <= 7;
                }).length;
                
                document.getElementById('totalCount').textContent = total;
                document.getElementById('activeCount').textContent = active;
                document.getElementById('expiringCount').textContent = expiring;
            }
            
            // Загрузить статус системы
            async function loadStatus() {
                try {
                    const response = await fetch('/api/health');
                    const status = await response.json();
                    
                    const botStatus = status.telegram_bot === 'configured' 
                        ? '<span style="color: #28a745;"> Настроен</span>'
                        : '<span style="color: #dc3545;"> Не настроен</span>';
                    
                    document.getElementById('status').innerHTML = 
                        '<p><strong>Статус:</strong> <span style="color: #28a745;">● ' + status.status + '</span></p>' +
                        '<p><strong>База данных:</strong> ' + status.database + ' (' + status.database_type + ')</p>' +
                        '<p><strong>Telegram бот:</strong> ' + botStatus + '</p>' +
                        '<p><strong>Порт:</strong> ' + status.port + '</p>' +
                        '<p><strong>Время:</strong> ' + new Date(status.timestamp).toLocaleString() + '</p>';
                } catch (error) {
                    document.getElementById('status').innerHTML = '<p> Ошибка проверки статуса</p>';
                }
            }
            
            // Удалить доверенность
            async function deletePower(id) {
                if (!confirm('Удалить эту доверенность?')) return;
                
                try {
                    const response = await fetch('/api/powers/' + id, {
                        method: 'DELETE'
                    });
                    
                    if (response.ok) {
                        showAlert(' Доверенность удалена!');
                        loadPowers();
                    } else {
                        showAlert(' Ошибка при удалении', 'error');
                    }
                } catch (error) {
                    showAlert(' Ошибка сети', 'error');
                }
            }
            
            // Добавить доверенность
            document.getElementById('addForm').addEventListener('submit', async function(e) {
                e.preventDefault();
                
                const formData = {
                    full_name: document.getElementById('full_name').value,
                    poa_type: document.getElementById('poa_type').value,
                    end_date: document.getElementById('end_date').value
                };
                
                // Валидация
                if (!formData.full_name || !formData.poa_type || !formData.end_date) {
                    showAlert(' Заполните все обязательные поля', 'error');
                    return;
                }
                
                try {
                    // Формируем query string
                    const params = new URLSearchParams();
                    params.append('full_name', formData.full_name);
                    params.append('poa_type', formData.poa_type);
                    params.append('end_date', formData.end_date);
                    
                    const response = await fetch('/api/powers/?' + params.toString(), {
                        method: 'POST'
                    });
                    
                    if (response.ok) {
                        const result = await response.json();
                        showAlert(' Доверенность "' + formData.full_name + '" добавлена! (ID: ' + result.id + ')');
                        document.getElementById('addForm').reset();
                        loadPowers();
                    } else {
                        const error = await response.json();
                        showAlert(' Ошибка: ' + (error.detail || 'Неизвестная ошибка'), 'error');
                    }
                } catch (error) {
                    showAlert(' Ошибка сети', 'error');
                }
            });
            
            // Инициализация
            document.addEventListener('DOMContentLoaded', function() {
                // Устанавливаем минимальную дату - сегодня
                const today = new Date().toISOString().split('T')[0];
                document.getElementById('end_date').min = today;
                
                // Загружаем данные
                loadPowers();
                loadStatus();
                
                // Автообновление каждые 30 секунд
                setInterval(loadPowers, 30000);
                setInterval(loadStatus, 60000);
            });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# ==================== ЗАПУСК СЕРВЕРА ====================
if __name__ == "__main__":
    # Получаем порт из переменной окружения Railway
    PORT = int(os.getenv("PORT", 8000))
    HOST = "0.0.0.0"
    
    print("=" * 60)
    print(" Power of Attorney Tracker with PostgreSQL")
    print("=" * 60)
    print(f"Сервер запущен на: {HOST}:{PORT}")
    print(f"База данных: {'PostgreSQL (Railway)' if DATABASE_URL else 'Не настроена'}")
    print(f"Telegram бот: {' Настроен' if TELEGRAM_BOT_TOKEN else ' Не настроен'}")
    print("=" * 60)
    print("Доступные эндпоинты:")
    print(f"  • Веб-интерфейс: http://localhost:{PORT}/ui")
    print(f"  • API документация: http://localhost:{PORT}/docs")
    print(f"  • Проверка здоровья: http://localhost:{PORT}/api/health")
    print(f"  • Информация о БД: http://localhost:{PORT}/api/db-info")
    print(f"  • Список доверенностей: http://localhost:{PORT}/api/powers/")
    print("=" * 60)
    
    # Запускаем сервер
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        reload=False
    )
