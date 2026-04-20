"""
FocusGuard — Home Assistant integration
Queries person presence and zone history via HA REST API.
"""
import httpx
import logging
from datetime import datetime, date, timedelta
from typing import Optional

logger = logging.getLogger("focusguard.ha")


class HomeAssistantClient:
    def __init__(self, url: str, token: str, person_entity: str, hospital_zone: str):
        self.url = url.rstrip("/")
        self.token = token
        self.person_entity = person_entity
        self.hospital_zone = hospital_zone
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        self._last_state: Optional[str] = None
        self._client = httpx.AsyncClient(timeout=10.0)

    async def get_person_state(self) -> dict:
        """Get current person state from HA."""
        try:
            resp = await self._client.get(
                f"{self.url}/api/states/{self.person_entity}",
                headers=self.headers
            )
            resp.raise_for_status()
            data = resp.json()
            state = data.get("state", "unknown")
            attrs = data.get("attributes", {})
            return {
                "state": state,
                "friendly_name": attrs.get("friendly_name", ""),
                "latitude": attrs.get("latitude"),
                "longitude": attrs.get("longitude"),
                "last_changed": data.get("last_changed", ""),
                "source": attrs.get("source", ""),
            }
        except Exception as e:
            logger.error(f"HA API error: {e}")
            return {"state": "unknown", "error": str(e)}

    async def is_home(self) -> bool:
        """Check if person is currently at home."""
        data = await self.get_person_state()
        return data.get("state") == "home"

    async def was_at_hospital_today(self) -> dict:
        today = date.today()
        start_time = datetime(today.year, today.month, today.day, 0, 0, 0).isoformat()

        try:
            resp = await self._client.get(
                f"{self.url}/api/history/period/{start_time}",
                headers=self.headers,
                params={
                    "filter_entity_id": self.person_entity,
                    "minimal_response": "true",
                    "no_attributes": "true",
                    "end_time": datetime.now().isoformat()
                }
            )
            resp.raise_for_status()
            data = resp.json()

            if not data or len(data) == 0:
                return {"visited": False}

            entity_history = data[0] if data else []
            hospital_zone_name = self.hospital_zone.replace("zone.", "")
            arrival_time = None
            departure_time = None
            visited = False

            for entry in entity_history:
                state = entry.get("state", "")
                timestamp = entry.get("last_changed", "")

                if state == hospital_zone_name or state == self.hospital_zone:
                    visited = True
                    if arrival_time is None:
                        arrival_time = timestamp
                elif visited and arrival_time and not departure_time:
                    departure_time = timestamp

            return {
                "visited": visited,
                "arrival_time": arrival_time,
                "departure_time": departure_time,
            }
        except Exception as e:
            logger.error(f"HA history error: {e}")
            return {"visited": False, "error": str(e)}

    async def close(self):
        await self._client.aclose()
