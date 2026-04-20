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

logger = logging.getLogger("focusguard.reports")

class ReportService:
    def __init__(self, ha_client: HomeAssistantClient, gtasks_client: GoogleTasksClient):
        self.ha = ha_client
        self.gtasks = gtasks_client

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
            home = await db.get_latest_home_arrival_today()
            if home:
                home_arrival = home.get("arrival_time")
                study_deadline = home.get("study_deadline")
                total_useful_minutes = home.get("calculated_useful_minutes", 0)

        efficiency = 0
        if total_useful_minutes > 0:
            efficiency = min(100.0, (total_study_minutes / total_useful_minutes) * 100)

        streak = await db.get_current_streak()

        report = {
            "report_date": target_date,
            "total_home_minutes": 0,
            "total_useful_minutes": total_useful_minutes,
            "total_study_minutes": total_study_minutes,
            "study_efficiency_pct": efficiency,
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
