"""
FocusGuard — Configuration loader
Reads app_config.yaml and provides typed access to all settings.
"""
import yaml
import os
import json
from typing import Optional

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app_config.yaml")
ADDON_OPTIONS_PATH = "/data/options.json"


class StudyScheduleConfig:
    def __init__(self, data: dict):
        self.mode = data.get("mode", "dynamic")
        self.end_of_day_hour = data.get("end_of_day_hour", 22)
        self.useful_fraction = data.get("useful_fraction", 2 / 3)
        self.fixed = data.get("fixed", {})


class StudyDetectionConfig:
    def __init__(self, data: dict):
        self.ophthalmology_keywords = [k.lower() for k in data.get("ophthalmology_keywords", [])]
        self.general_study_keywords = [k.lower() for k in data.get("general_study_keywords", [])]
        self.blacklist_keywords = [k.lower() for k in data.get("blacklist_keywords", [])]

    @property
    def all_study_keywords(self):
        return self.ophthalmology_keywords + self.general_study_keywords


class HomeAssistantConfig:
    def __init__(self, data: dict):
        self.url = data.get("url", "http://homeassistant.local:8123").rstrip("/")
        self.token = data.get("token", "")
        self.person_entity = data.get("person_entity", "person.matheus_galvao")
        self.hospital_zone = data.get("hospital_zone", "zone.hospital")


class PomodoroConfig:
    def __init__(self, data: dict):
        self.focus_minutes = data.get("focus_minutes", 25)
        self.short_break_minutes = data.get("short_break_minutes", 5)
        self.long_break_minutes = data.get("long_break_minutes", 15)
        self.cycles_before_long_break = data.get("cycles_before_long_break", 4)


class NotificationConfig:
    def __init__(self, data: dict):
        self.idle_reminder_minutes = data.get("idle_reminder_minutes", 15)
        self.pomodoro_enabled = data.get("pomodoro_enabled", True)


class GoogleTasksConfig:
    def __init__(self, data: dict):
        self.task_list_name = data.get("task_list_name", "Estudos Oftalmologia")


class AppConfig:
    _instance: Optional["AppConfig"] = None

    def __init__(self, config_path: str = CONFIG_PATH):
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # Check if running as a Home Assistant Add-on
        ha_data = data.get("homeassistant", {})
        if os.path.exists(ADDON_OPTIONS_PATH):
            try:
                with open(ADDON_OPTIONS_PATH, "r", encoding="utf-8") as f:
                    options = json.load(f)
                    # When running inside HA Add-on, we use the internal supervisor API
                    ha_data["url"] = "http://supervisor/core"
                    ha_data["token"] = os.environ.get("SUPERVISOR_TOKEN", "")
                    ha_data["person_entity"] = options.get("person_entity", ha_data.get("person_entity"))
                    ha_data["hospital_zone"] = options.get("hospital_zone", ha_data.get("hospital_zone"))
            except Exception as e:
                print(f"Error loading Add-on options: {e}")

        self.homeassistant = HomeAssistantConfig(ha_data)
        self.study_schedule = StudyScheduleConfig(data.get("study_schedule", {}))
        self.study_detection = StudyDetectionConfig(data.get("study_detection", {}))
        self.pomodoro = PomodoroConfig(data.get("pomodoro", {}))
        self.notifications = NotificationConfig(data.get("notifications", {}))
        self.google_tasks = GoogleTasksConfig(data.get("google_tasks", {}))
        self._raw = data

    @classmethod
    def get(cls, config_path: str = CONFIG_PATH) -> "AppConfig":
        if cls._instance is None:
            cls._instance = cls(config_path)
        return cls._instance

    @classmethod
    def reload(cls, config_path: str = CONFIG_PATH) -> "AppConfig":
        cls._instance = cls(config_path)
        return cls._instance

    def to_dict(self) -> dict:
        return self._raw

    def update_from_dict(self, data: dict, config_path: str = CONFIG_PATH):
        """Update config file with new data."""
        merged = {**self._raw, **data}
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(merged, f, default_flow_style=False, allow_unicode=True)
        AppConfig.reload(config_path)
