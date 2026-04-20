"""
FocusGuard — Main FastAPI Application
Entry point for the backend orchestrator.
"""
import os
import logging
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ── Logging Setup (must be first) ──────────────────────────────────────────
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))
os.makedirs(DATA_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("focusguard")
logger.info("=== FocusGuard module loaded ===")

# ── Globals (populated at startup) ─────────────────────────────────────────
_config = None
_ha_client = None
_gtasks_client = None
_presence_service = None
_activity_service = None
_report_service = None
_scheduler: Optional[AsyncIOScheduler] = None
_last_tracker_ping: Optional[float] = None  # Unix timestamp of last tracker batch
_user_keywords: list = []  # Runtime study keywords added by user via dialog
_user_blacklist_keywords: list = []  # Runtime distraction keywords


class ActivityItem(BaseModel):
    timestamp: str
    app_name: str
    window_title: str
    duration_seconds: float


class ActivityBatch(BaseModel):
    activities: List[ActivityItem]


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config, _ha_client, _gtasks_client, _presence_service
    global _activity_service, _report_service, _scheduler

    logger.info("=== FocusGuard Backend Starting ===")

    try:
        from .config import AppConfig
        from . import database as db
        from .integrations.homeassistant import HomeAssistantClient
        from .integrations.google_tasks import GoogleTasksClient
        from .services.presence import PresenceService
        from .services.activity import ActivityService
        from .services.reports import ReportService

        _config = AppConfig.get()
        logger.info("Config loaded OK")

        _ha_client = HomeAssistantClient(
            _config.homeassistant.url,
            _config.homeassistant.token,
            _config.homeassistant.person_entity,
            _config.homeassistant.hospital_zone,
        )
        _gtasks_client = GoogleTasksClient(_config.google_tasks.task_list_name)
        _presence_service = PresenceService(_ha_client, _config)
        _activity_service = ActivityService(_config)
        _report_service = ReportService(_ha_client, _gtasks_client, _config)
        logger.info("Services initialized OK")

        await db.init_db()
        # Load user-added keywords from disk
        user_kw_path = os.path.join(DATA_DIR, "user_keywords.json")
        user_bl_path = os.path.join(DATA_DIR, "user_blacklist_keywords.json")
        if os.path.exists(user_kw_path):
            try:
                import json
                with open(user_kw_path) as f:
                    _user_keywords.extend(json.load(f))
                logger.info(f"Loaded {len(_user_keywords)} user keywords from disk")
            except Exception as e:
                logger.warning(f"Could not load user_keywords.json: {e}")
        if os.path.exists(user_bl_path):
            try:
                import json
                with open(user_bl_path) as f:
                    _user_blacklist_keywords.extend(json.load(f))
                logger.info(f"Loaded {len(_user_blacklist_keywords)} user blacklist keywords from disk")
            except Exception as e:
                logger.warning(f"Could not load user_blacklist_keywords.json: {e}")

        logger.info("Database initialized OK")

        _scheduler = AsyncIOScheduler()

        async def _check_presence():
            try:
                await _presence_service.update_presence()
            except Exception as e:
                logger.error(f"Presence check error: {e}")

        async def _daily_report():
            try:
                await _report_service.generate_daily_report()
            except Exception as e:
                logger.error(f"Daily report error: {e}")

        _scheduler.add_job(_check_presence, "interval", seconds=30)
        _scheduler.add_job(_daily_report, "cron", hour=23, minute=55)
        _scheduler.start()
        logger.info("Scheduler started OK")
        logger.info("=== FocusGuard Backend Ready ===")

    except Exception as e:
        logger.exception(f"STARTUP ERROR: {e}")
        # Don't crash — let the web server stay up so logs are accessible

    yield

    logger.info("FocusGuard shutting down...")
    if _scheduler:
        _scheduler.shutdown()
    if _ha_client:
        await _ha_client.close()


# ── FastAPI App ─────────────────────────────────────────────────────────────
app = FastAPI(title="FocusGuard API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def health():
    return {"status": "ok"}


@app.post("/api/activity")
async def receive_activity(batch: ActivityBatch, background_tasks: BackgroundTasks):
    global _last_tracker_ping
    import time
    _last_tracker_ping = time.time()
    if _activity_service is None:
        return {"status": "not_ready"}
    activities = [a.model_dump() for a in batch.activities]
    background_tasks.add_task(_activity_service.process_activity_batch, activities)
    return {"status": "accepted", "count": len(activities)}


@app.get("/api/status")
async def get_current_status(background_tasks: BackgroundTasks):
    import time
    if _presence_service is None:
        return {"status": "not_ready", "is_home": False, "is_useful_time": False, "is_studying": False, "tracker_connected": False}
    result = await _presence_service.get_current_status()
    # Tracker is considered connected if it sent data in the last 90 seconds
    tracker_connected = _last_tracker_ping is not None and (time.time() - _last_tracker_ping) < 90
    result["tracker_connected"] = tracker_connected
    result["tracker_last_seen"] = _last_tracker_ping
    
    if _activity_service is not None:
        result["last_classification"] = _activity_service.last_classification
        
    if _report_service is not None:
        try:
            report = await _report_service.generate_daily_report()
            result["procrastination_pct"] = report.get("procrastination_pct", 0.0)
            result["study_efficiency_pct"] = report.get("study_efficiency_pct", 0.0)
        except Exception as e:
            logger.error(f"Error generating report for status: {e}")
            result["procrastination_pct"] = 0.0
            result["study_efficiency_pct"] = 0.0
            
    background_tasks.add_task(_update_ha_sensor, result, report if _report_service else None)
    return result

async def _update_ha_sensor(status_dict, report_dict):
    if not _ha_client:
        return
    
    if not status_dict.get("tracker_connected"):
        state = "Tracker Offline"
        icon = "mdi:lan-disconnect"
    elif status_dict.get("is_studying"):
        state = "Estudando Focado"
        icon = "mdi:brain"
    elif status_dict.get("is_useful_time"):
        state = "Distraído (Ocioso)"
        icon = "mdi:alert-circle-outline"
    elif status_dict.get("is_home"):
        state = "Livre (Em Casa)"
        icon = "mdi:home"
    else:
        state = "Fora de Casa"
        icon = "mdi:car"
        
    attrs = {
        "friendly_name": "FocusGuard",
        "icon": icon,
    }
    
    if report_dict:
        attrs["study_efficiency"] = f"{round(report_dict.get('study_efficiency_pct', 0))}%"
        attrs["procrastination"] = f"{round(report_dict.get('procrastination_pct', 0))}%"
        
        def fmt_min(m):
            h = int(m // 60)
            mins = int(m % 60)
            return f"{h}h {mins}m" if h > 0 else f"{mins}m"
            
        attrs["total_study"] = fmt_min(report_dict.get("total_study_minutes", 0))
        attrs["total_useful"] = fmt_min(report_dict.get("total_useful_minutes", 0))
        
        top_kws = report_dict.get("top_keywords", [])
        if top_kws:
            attrs["top_keyword"] = top_kws[0]["name"]
            
        last_class = status_dict.get("last_classification")
        if last_class and last_class.get("classification"):
            attrs["last_reason"] = last_class["classification"].get("reason", "")
            
    await _ha_client.update_sensor_state("sensor.focusguard_status", state, attrs)


@app.get("/api/report/today")
async def get_today_report():
    if _report_service is None:
        return {"status": "not_ready"}
    return await _report_service.generate_daily_report()


@app.get("/api/report/{target_date}")
async def get_report(target_date: str):
    if _report_service is None:
        return {"status": "not_ready"}
    from . import database as db
    report = await db.get_daily_report(target_date)
    if not report:
        report = await _report_service.generate_daily_report(target_date)
    return report


@app.get("/api/tasks")
async def get_tasks():
    if _gtasks_client is None:
        return {"status": "not_ready"}
    summary = _gtasks_client.get_tasks_summary()
    if not _gtasks_client._initialized:
        return {"status": "not_initialized", "message": "Google Tasks needs authentication."}
    return summary


@app.post("/api/tasks/{task_id}/complete")
async def complete_task(task_id: str):
    if _gtasks_client is None:
        return {"success": False}
    success = _gtasks_client.complete_task(task_id)
    return {"success": success}


@app.get("/api/config")
async def get_config():
    if _config is None:
        return {}
    return _config.to_dict()


@app.get("/api/keywords")
async def get_keywords():
    if _config is None:
        return {"keywords": [], "user_keywords": []}
    all_kw = list(_config.study_detection.all_study_keywords) + _user_keywords
    return {"keywords": all_kw, "user_keywords": _user_keywords}


class KeywordPayload(BaseModel):
    keyword: str
    is_study: bool = True


@app.post("/api/keywords")
async def add_keyword_endpoint(payload: KeywordPayload):
    import json
    kw = payload.keyword.strip().lower()
    if not kw:
        return {"success": False, "error": "empty keyword"}
        
    if payload.is_study:
        if kw not in _user_keywords:
            _user_keywords.append(kw)
            user_kw_path = os.path.join(DATA_DIR, "user_keywords.json")
            try:
                with open(user_kw_path, "w") as f:
                    json.dump(_user_keywords, f)
            except Exception as e:
                logger.warning(f"Could not save user_keywords.json: {e}")
            if _activity_service is not None:
                _activity_service.config.study_detection.ophthalmology_keywords.append(kw)
            logger.info(f"User added study keyword: '{kw}'")
    else:
        if kw not in _user_blacklist_keywords:
            _user_blacklist_keywords.append(kw)
            user_bl_path = os.path.join(DATA_DIR, "user_blacklist_keywords.json")
            try:
                with open(user_bl_path, "w") as f:
                    json.dump(_user_blacklist_keywords, f)
            except Exception as e:
                logger.warning(f"Could not save user_blacklist_keywords.json: {e}")
            if _activity_service is not None:
                _activity_service.config.study_detection.blacklist_keywords.append(kw)
            logger.info(f"User added distraction keyword: '{kw}'")
            
    return {"success": True, "keyword": kw, "is_study": payload.is_study}


# ── Static Dashboard ────────────────────────────────────────────────────────
dashboard_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard")
if os.path.exists(dashboard_dir):
    app.mount("/static", StaticFiles(directory=dashboard_dir), name="static")

    @app.get("/")
    async def serve_dashboard():
        return FileResponse(os.path.join(dashboard_dir, "index.html"))
