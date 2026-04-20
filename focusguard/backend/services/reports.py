"""
FocusGuard — Reports Service
Generates daily performance reports.
"""
import logging
from datetime import datetime, date, timedelta
from typing import Optional
from collections import Counter

from .. import database as db
from ..integrations.homeassistant import HomeAssistantClient
from ..integrations.google_tasks import GoogleTasksClient

from ..config import AppConfig

logger = logging.getLogger("focusguard.reports")

class ReportService:
    def __init__(self, ha_client: HomeAssistantClient, gtasks_client: GoogleTasksClient, config: AppConfig):
        self.ha = ha_client
        self.gtasks = gtasks_client
        self.config = config

    async def generate_daily_report(self, target_date: str = None) -> dict:
        if not target_date:
            target_date = date.today().isoformat()
            
        activities = await db.get_activities_for_date(target_date)
        
        total_study_seconds = 0
        app_counter = Counter()
        keyword_counter = Counter()
        hourly_breakdown = {f"{i:02d}": 0 for i in range(24)}
        
        for act in activities:
            duration = act["duration_seconds"]
            if act["is_study"]:
                total_study_seconds += duration
                app_counter[act["app_name"]] += duration
                kws = act.get("matched_keywords", "").split(",")
                for kw in kws:
                    if kw:
                        keyword_counter[kw.strip()] += duration
                try:
                    hour = datetime.fromisoformat(act["timestamp"]).strftime("%H")
                    hourly_breakdown[hour] += (duration / 60.0)
                except ValueError:
                    pass

        total_study_minutes = total_study_seconds / 60.0
        tasks_summary = self.gtasks.get_tasks_summary()
        
        hospital_arrival = None
        home_arrival = None
        study_deadline = None
        total_useful_minutes = 0
        
        if target_date == date.today().isoformat():
            hosp = await db.get_hospital_visit_today()
            if hosp:
                hospital_arrival = hosp.get("arrival_time")

        total_useful_minutes = await self._calculate_useful_minutes_from_logs(target_date)

        efficiency = 0
        if total_useful_minutes > 0:
            efficiency = min(100.0, (total_study_minutes / total_useful_minutes) * 100)
            
        procrastination_pct = 100.0 - efficiency if total_useful_minutes > 0 else 0.0

        streak = await db.get_current_streak()

        report = {
            "report_date": target_date,
            "total_home_minutes": 0,
            "total_useful_minutes": total_useful_minutes,
            "total_study_minutes": total_study_minutes,
            "study_efficiency_pct": efficiency,
            "procrastination_pct": procrastination_pct,
            "tasks_completed": tasks_summary.get("completed", 0),
            "tasks_total": tasks_summary.get("total", 0),
            "hospital_arrival": hospital_arrival,
            "home_arrival": home_arrival,
            "study_deadline": study_deadline,
            "top_apps": [{"name": k, "minutes": v/60.0} for k, v in app_counter.most_common(5)],
            "top_keywords": [{"name": k, "minutes": v/60.0} for k, v in keyword_counter.most_common(5)],
            "hourly_breakdown": hourly_breakdown,
            "streak_days": streak
        }
        
        await db.save_daily_report(report)
        return report

    async def _calculate_useful_minutes_from_logs(self, target_date: str) -> float:
        db_conn = await db.get_db()
        try:
            cursor = await db_conn.execute(
                "SELECT state, timestamp FROM presence_logs WHERE date(timestamp) < ? ORDER BY timestamp DESC LIMIT 1", 
                (target_date,)
            )
            row = await cursor.fetchone()
            initial_state = row["state"] if row else "not_home"
            
            cursor = await db_conn.execute(
                "SELECT state, timestamp FROM presence_logs WHERE date(timestamp) = ? ORDER BY timestamp", 
                (target_date,)
            )
            logs = await cursor.fetchall()
        finally:
            await db_conn.close()

        intervals = []
        current_state = initial_state
        current_start = datetime.fromisoformat(f"{target_date}T00:00:00")
        
        for row in logs:
            ts = datetime.fromisoformat(row["timestamp"])
            new_state = row["state"]
            if current_state == "home":
                intervals.append((current_start, ts))
            current_state = new_state
            current_start = ts
            
        if current_state == "home":
            end_time = datetime.fromisoformat(f"{target_date}T23:59:59")
            if target_date == date.today().isoformat():
                end_time = min(end_time, datetime.now())
            intervals.append((current_start, end_time))

        total_useful = 0.0
        for start, end in intervals:
            day_start = start.replace(hour=8, minute=0, second=0, microsecond=0)
            day_end = start.replace(hour=22, minute=0, second=0, microsecond=0)
            
            is_midnight_start = (start.hour == 0 and start.minute == 0 and start.second == 0)
            grace_end = start if is_midnight_start else start + timedelta(minutes=35)
            
            useful_start = max(grace_end, day_start)
            useful_end = min(end, day_end)
            
            if useful_end > useful_start:
                total_useful += (useful_end - useful_start).total_seconds() / 60.0
                
        return total_useful
