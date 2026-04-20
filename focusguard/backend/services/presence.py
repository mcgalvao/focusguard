"""
FocusGuard — Presence Service
Handles presence tracking, dynamic useful time calculation, and status updates.
"""
import logging
from datetime import datetime, date, timedelta
from typing import Optional

from ..config import AppConfig
from ..integrations.homeassistant import HomeAssistantClient
from .. import database as db

logger = logging.getLogger("focusguard.presence")

class PresenceService:
    def __init__(self, ha_client: HomeAssistantClient, config: AppConfig):
        self.ha = ha_client
        self.config = config

    async def update_presence(self) -> dict:
        ha_state = await self.ha.get_person_state()
        state = ha_state.get("state", "unknown")
        
        last_log = await db.get_last_presence()
        previous_state = last_log["state"] if last_log else "unknown"

        if state != previous_state:
            await db.log_presence(datetime.now().isoformat(), state, previous_state)
            if state == "home" and previous_state != "unknown":
                await self._handle_home_arrival()
                
        return ha_state

    async def _handle_home_arrival(self):
        today = date.today().isoformat()
        now = datetime.now()
        
        hospital_data = await self.ha.was_at_hospital_today()
        if not hospital_data.get("visited", False):
            return

        schedule_config = self.config.study_schedule
        if schedule_config.mode == "dynamic":
            end_time = now.replace(hour=schedule_config.end_of_day_hour, minute=0, second=0, microsecond=0)
            
            if now >= end_time:
                await db.log_home_arrival(today, now.isoformat(), 0, end_time.isoformat())
                return
                
            time_left_minutes = (end_time - now).total_seconds() / 60.0
            useful_minutes = time_left_minutes * schedule_config.useful_fraction
            deadline = now + timedelta(minutes=useful_minutes)
            
            await db.log_home_arrival(
                today, 
                now.isoformat(), 
                useful_minutes, 
                deadline.isoformat()
            )

    async def is_useful_time(self) -> dict:
        is_home = await self.ha.is_home()
        if not is_home:
            return {"is_useful": False, "reason": "not_home"}

        now = datetime.now()
        schedule_config = self.config.study_schedule

        if schedule_config.mode == "dynamic":
            hospital_data = await self.ha.was_at_hospital_today()
            if hospital_data.get("visited", False):
                latest_arrival = await db.get_latest_home_arrival_today()
                if latest_arrival and latest_arrival.get("study_deadline"):
                    deadline = datetime.fromisoformat(latest_arrival["study_deadline"])
                    if now <= deadline:
                        return {"is_useful": True, "reason": "dynamic_schedule", "deadline": deadline.isoformat()}
                    else:
                        return {"is_useful": False, "reason": "past_deadline"}

        day_name = now.strftime("%A").lower()
        fixed_intervals = schedule_config.fixed.get(day_name, [])
        
        for interval in fixed_intervals:
            start_str, end_str = interval.split("-")
            start_time = now.replace(hour=int(start_str.split(":")[0]), minute=int(start_str.split(":")[1]), second=0, microsecond=0)
            end_time = now.replace(hour=int(end_str.split(":")[0]), minute=int(end_str.split(":")[1]), second=0, microsecond=0)
            
            if start_time <= now <= end_time:
                return {"is_useful": True, "reason": "fixed_schedule", "deadline": end_time.isoformat()}

        return {"is_useful": False, "reason": "outside_schedule"}

    async def get_current_status(self) -> dict:
        ha_state = await self.ha.get_person_state()
        useful_info = await self.is_useful_time()
        
        active_session = await db.get_active_session()
        is_studying = active_session is not None
        
        study_duration = 0
        if is_studying:
            start_time = datetime.fromisoformat(active_session["start_time"])
            study_duration = (datetime.now() - start_time).total_seconds() / 60.0
            
        return {
            "timestamp": datetime.now().isoformat(),
            "presence": ha_state.get("state", "unknown"),
            "is_home": ha_state.get("state") == "home",
            "is_useful_time": useful_info["is_useful"],
            "useful_time_reason": useful_info.get("reason"),
            "useful_time_deadline": useful_info.get("deadline"),
            "is_studying": is_studying,
            "current_study_duration_minutes": study_duration
        }
