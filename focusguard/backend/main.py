"""
FocusGuard — Main FastAPI Application
Entry point for the backend orchestrator.
"""
import os
import logging
from datetime import datetime, date
from contextlib import asynccontextmanager
from typing import List, Dict, Any

from fastapi import FastAPI, BackgroundTasks, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import AppConfig
from . import database as db
from .integrations.homeassistant import HomeAssistantClient
from .integrations.google_tasks import GoogleTasksClient
from .services.presence import PresenceService
from .services.activity import ActivityService
from .services.reports import ReportService

# --- Logging Setup ---
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))
os.makedirs(DATA_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(DATA_DIR, "focusguard.log"))
    ]
)
logger = logging.getLogger("focusguard")

config = AppConfig.get()
ha_client = HomeAssistantClient(
    config.homeassistant.url, 
    config.homeassistant.token,
    config.homeassistant.person_entity,
    config.homeassistant.hospital_zone
)
gtasks_client = GoogleTasksClient(config.google_tasks.task_list_name)

presence_service = PresenceService(ha_client, config)
activity_service = ActivityService(config)
report_service = ReportService(ha_client, gtasks_client)

scheduler = AsyncIOScheduler()

class ActivityItem(BaseModel):
    timestamp: str
    app_name: str
    window_title: str
    duration_seconds: float

class ActivityBatch(BaseModel):
    activities: List[ActivityItem]

async def check_presence_task():
    try:
        await presence_service.update_presence()
    except Exception as e:
        logger.error(f"Error check_presence: {e}")

async def sync_tasks_task():
    pass

async def generate_daily_report_task():
    try:
        await report_service.generate_daily_report()
    except Exception as e:
        logger.error(f"Error daily report: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting FocusGuard Backend...")
    await db.init_db()
    
    scheduler.add_job(check_presence_task, 'interval', seconds=30)
    scheduler.add_job(sync_tasks_task, 'interval', minutes=15)
    scheduler.add_job(generate_daily_report_task, 'cron', hour=23, minute=55)
    scheduler.start()
    
    yield
    
    logger.info("Shutting down FocusGuard Backend...")
    scheduler.shutdown()
    await ha_client.close()

app = FastAPI(title="FocusGuard API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/activity")
async def receive_activity(batch: ActivityBatch, background_tasks: BackgroundTasks):
    activities = [a.model_dump() for a in batch.activities]
    background_tasks.add_task(activity_service.process_activity_batch, activities)
    return {"status": "accepted", "count": len(activities)}

@app.get("/api/status")
async def get_current_status():
    return await presence_service.get_current_status()

@app.get("/api/report/today")
async def get_today_report():
    return await report_service.generate_daily_report()

@app.get("/api/report/{target_date}")
async def get_report(target_date: str):
    report = await db.get_daily_report(target_date)
    if not report:
        report = await report_service.generate_daily_report(target_date)
    return report

@app.get("/api/tasks")
async def get_tasks():
    summary = gtasks_client.get_tasks_summary()
    if summary.get("total", 0) == 0 and len(summary.get("tasks", [])) == 0:
        if not gtasks_client._initialized:
            return {"status": "not_initialized", "message": "Google Tasks needs authentication."}
    return summary

@app.post("/api/tasks/{task_id}/complete")
async def complete_task(task_id: str):
    success = gtasks_client.complete_task(task_id)
    return {"success": success}

@app.get("/api/config")
async def get_config():
    return config.to_dict()

dashboard_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard")
if os.path.exists(dashboard_dir):
    app.mount("/static", StaticFiles(directory=dashboard_dir), name="static")

    @app.get("/")
    async def serve_dashboard():
        return FileResponse(os.path.join(dashboard_dir, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
