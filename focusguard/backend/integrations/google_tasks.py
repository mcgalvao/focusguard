"""
FocusGuard — Google Tasks integration
OAuth 2.0 authentication and task list management.
"""
import os
import pickle
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger("focusguard.gtasks")

SCOPES = ["https://www.googleapis.com/auth/tasks"]

# Em ambiente de add-on, salvar token na pasta /config para persistência fora do container
CONFIG_DIR = os.environ.get("CONFIG_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"))
TOKEN_PATH = os.path.join(CONFIG_DIR, "google_token.pickle")
CREDENTIALS_PATH = os.path.join(CONFIG_DIR, "credentials.json")


class GoogleTasksClient:
    def __init__(self, task_list_name: str = "Estudos Oftalmologia"):
        self.task_list_name = task_list_name
        self.service = None
        self._task_list_id: Optional[str] = None
        self._initialized = False

    def _ensure_dirs(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)

    def initialize(self) -> bool:
        self._ensure_dirs()

        if not os.path.exists(CREDENTIALS_PATH):
            logger.warning(
                f"Google Tasks credentials not found at {CREDENTIALS_PATH}. "
                "Please download credentials.json from Google Cloud Console."
            )
            return False

        try:
            from google.auth.transport.requests import Request
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build

            creds = None
            if os.path.exists(TOKEN_PATH):
                with open(TOKEN_PATH, "rb") as token:
                    creds = pickle.load(token)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    # No ambiente do HA Add-on não temos navegador.
                    # O ideal seria um OAuth Flow de Device Code ou Console
                    flow = InstalledAppFlow.from_client_secrets_file(
                        CREDENTIALS_PATH, SCOPES
                    )
                    # Como estamos no HA, tentaremos console flow
                    creds = flow.run_console()

                with open(TOKEN_PATH, "wb") as token:
                    pickle.dump(creds, token)

            self.service = build("tasks", "v1", credentials=creds)
            self._initialized = True
            logger.info("Google Tasks initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Google Tasks init error: {e}")
            return False

    def _get_or_create_list(self) -> Optional[str]:
        if self._task_list_id:
            return self._task_list_id

        if not self._initialized:
            if not self.initialize():
                return None

        try:
            results = self.service.tasklists().list().execute()
            items = results.get("items", [])

            for item in items:
                if item["title"] == self.task_list_name:
                    self._task_list_id = item["id"]
                    return self._task_list_id

            new_list = self.service.tasklists().insert(
                body={"title": self.task_list_name}
            ).execute()
            self._task_list_id = new_list["id"]
            return self._task_list_id
        except Exception as e:
            logger.error(f"Error getting/creating task list: {e}")
            return None

    def get_tasks(self, list_id: Optional[str] = None, show_completed: bool = True) -> list:
        if not self._initialized:
            if not self.initialize():
                return []

        target_list = list_id or self._get_or_create_list()
        if not target_list:
            return []

        try:
            params = {
                "tasklist": target_list,
                "showCompleted": show_completed,
                "showHidden": show_completed,
                "maxResults": 100,
            }
            results = self.service.tasks().list(**params).execute()
            return results.get("items", [])
        except Exception as e:
            logger.error(f"Error getting tasks: {e}")
            return []

    def get_tasks_summary(self, list_id: Optional[str] = None) -> dict:
        tasks = self.get_tasks(list_id, show_completed=True)
        completed = [t for t in tasks if t.get("status") == "completed"]
        pending = [t for t in tasks if t.get("status") == "needsAction"]
        return {
            "total": len(tasks),
            "completed": len(completed),
            "pending": len(pending),
            "tasks": tasks,
            "completed_tasks": completed,
            "pending_tasks": pending,
        }

    def complete_task(self, task_id: str, list_id: Optional[str] = None) -> bool:
        target_list = list_id or self._get_or_create_list()
        if not target_list:
            return False

        try:
            task = self.service.tasks().get(
                tasklist=target_list, task=task_id
            ).execute()
            task["status"] = "completed"
            self.service.tasks().update(
                tasklist=target_list, task=task_id, body=task
            ).execute()
            return True
        except Exception as e:
            return False
