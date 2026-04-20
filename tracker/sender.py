import httpx
import logging
from typing import List, Dict

logger = logging.getLogger("tracker.sender")


class DataSender:
    def __init__(self, backend_url: str):
        self.backend_url = backend_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=5.0)

    async def send_activities(self, activities: List[Dict]) -> bool:
        if not activities:
            return True
        try:
            resp = await self.client.post(
                f"{self.backend_url}/api/activity",
                json={"activities": activities}
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Error sending activities to {self.backend_url}: {e}")
            return False

    async def get_status(self) -> dict:
        try:
            resp = await self.client.get(f"{self.backend_url}/api/status")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return {}

    async def add_keyword(self, keyword: str, is_study: bool = True) -> bool:
        try:
            resp = await self.client.post(
                f"{self.backend_url}/api/keywords",
                json={"keyword": keyword, "is_study": is_study}
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Error adding keyword: {e}")
            return False

    async def fetch_keywords(self) -> dict:
        try:
            resp = await self.client.get(f"{self.backend_url}/api/keywords")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Error fetching keywords: {e}")
            return {}

    async def close(self):
        await self.client.aclose()
