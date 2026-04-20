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
        pass # Deprecated by new business rules

    async def is_useful_time(self) -> dict:
        is_home = await self.ha.is_home()
        if not is_home:
            return {"is_useful": False, "reason": "not_home"}

        now = datetime.now()
        if now.hour < 8 or now.hour >= 22:
            return {"is_useful": False, "reason": "outside_schedule"}

        last_log = await db.get_last_presence()
        if last_log and last_log["state"] == "home":
            try:
                arrival_time = datetime.fromisoformat(last_log["timestamp"])
                elapsed_minutes = (now - arrival_time).total_seconds() / 60.0
                if elapsed_minutes < 35:
                    grace_end = arrival_time + timedelta(minutes=35)
                    return {"is_useful": False, "reason": "grace_period", "deadline": grace_end.isoformat()}
            except Exception:
                pass

        end_of_day = now.replace(hour=22, minute=0, second=0, microsecond=0)
        return {"is_useful": True, "reason": "home_active", "deadline": end_of_day.isoformat()}

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
