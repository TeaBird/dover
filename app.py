
import os
from fastapi import FastAPI
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI()

@app.get("/")
async def root():
    logger.info("Root endpoint called")
    return {"message": "Power of Attorney Tracker", "status": "running"}

@app.get("/api/health")
async def health():
    logger.info("Health check called")
    return {
        "status": "healthy",
        "service": "POA Tracker",
        "port": os.getenv("PORT", "8000")
    }

@app.get("/api/test")
async def test():
    return {"test": "ok", "env": dict(os.environ)}
