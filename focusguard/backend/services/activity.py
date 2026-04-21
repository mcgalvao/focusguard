"""
FocusGuard — Activity Service
Classifies window activity and manages study sessions.
"""
import logging
from datetime import datetime, timedelta
import re
import unicodedata

from ..config import AppConfig
from .. import database as db

logger = logging.getLogger("focusguard.activity")

class ActivityService:
    def __init__(self, config: AppConfig):
        self.config = config
        self.last_classification = None

    def _normalize_text(self, text: str) -> str:
        if not text: return ""
        # Remove accents and convert to lowercase
        n_text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
        return n_text.lower()

    def classify_activity(self, app_name: str, window_title: str, idle_seconds: float = 0, idle_threshold_seconds: float = 180) -> dict:
        # If the user is idle beyond the dynamic threshold, it's not study
        if idle_seconds > idle_threshold_seconds:
            return {"is_study": False, "matched_keywords": [], "reason": "user_idle"}

        app_name_norm = self._normalize_text(app_name)
        title_norm = self._normalize_text(window_title)
        detection_config = self.config.study_detection
        
        for kw in detection_config.blacklist_keywords:
            kw_norm = self._normalize_text(kw)
            if kw_norm in title_norm or kw_norm in app_name_norm:
                return {"is_study": False, "matched_keywords": [kw], "reason": "blacklist"}

        matched_kws = []
        for kw in detection_config.ophthalmology_keywords:
            kw_norm = self._normalize_text(kw)
            if not kw_norm: continue
            
            # Use word boundaries for better precision on short keywords
            if len(kw_norm) <= 5:
                if re.search(r'\b' + re.escape(kw_norm) + r'\b', title_norm):
                    matched_kws.append(kw)
            elif kw_norm in title_norm:
                matched_kws.append(kw)
                
        for kw in detection_config.general_study_keywords:
            kw_norm = self._normalize_text(kw)
            if not kw_norm: continue
            
            if kw_norm in title_norm or kw_norm in app_name_norm:
                matched_kws.append(kw)
                
        is_study = len(matched_kws) > 0
        return {
            "is_study": is_study,
            "matched_keywords": matched_kws,
            "reason": "keywords" if is_study else "no_match"
        }

    async def process_activity_batch(self, activities: list):
        if not activities:
            return

        try:
            await self._process_activity_batch_inner(activities)
        except Exception as e:
            logger.error(f"[BATCH] Erro crítico no processamento de atividades: {e}", exc_info=True)

    async def _process_activity_batch_inner(self, activities: list):
        processed_activities = []
        has_study_activity = False
        apps_used = set()
        keywords_matched = set()

        # ── Dynamic idle threshold ───────────────────────────────────────
        # Base: 3 min (180s). Exception: if last session was long, allow
        # a break of 5/6 of that session duration before going idle.
        BASE_IDLE_THRESHOLD = 180  # 3 minutes in seconds
        idle_threshold = BASE_IDLE_THRESHOLD
        try:
            last_session = await db.get_last_completed_session()
            if last_session and last_session.get("duration_minutes"):
                session_seconds = last_session["duration_minutes"] * 60
                allowed_break = session_seconds * (5 / 6)
                if allowed_break > BASE_IDLE_THRESHOLD:
                    idle_threshold = allowed_break
                    logger.debug(
                        f"[IDLE] Threshold dinâmico: {idle_threshold:.0f}s "
                        f"(sessão anterior: {last_session['duration_minutes']:.1f}min)"
                    )
        except Exception as e:
            logger.warning(f"[IDLE] Falha ao obter última sessão, usando base {BASE_IDLE_THRESHOLD}s: {e}")
        
        for act in activities:
            classification = self.classify_activity(
                act["app_name"], 
                act["window_title"], 
                act.get("idle_seconds", 0),
                idle_threshold_seconds=idle_threshold
            )
            is_study = classification["is_study"]

            if classification["reason"] == "user_idle":
                logger.info(
                    f"[IDLE] Inativo por {act.get('idle_seconds', 0):.0f}s "
                    f"(limite: {idle_threshold:.0f}s) — não conta como estudo."
                )
            
            act_record = {
                **act,
                "is_study": is_study,
                "matched_keywords": ",".join(classification["matched_keywords"])
            }
            processed_activities.append(act_record)
            
            if is_study:
                has_study_activity = True
                apps_used.add(act["app_name"])
                keywords_matched.update(classification["matched_keywords"])

            self.last_classification = {
                "app_name": act["app_name"],
                "window_title": act["window_title"],
                "classification": classification
            }
                
        await db.log_activity_batch(processed_activities)
        await self._manage_study_sessions(has_study_activity, apps_used, keywords_matched)

    async def _manage_study_sessions(self, is_studying_now: bool, apps_used: set, keywords_matched: set):
        active_session = await db.get_active_session()
        now = datetime.now()
        
        if is_studying_now:
            if not active_session:
                await db.start_study_session(now.isoformat())
        else:
            if active_session:
                start_time = datetime.fromisoformat(active_session["start_time"])
                duration = (now - start_time).total_seconds() / 60.0
                await db.end_study_session(
                    active_session["id"],
                    now.isoformat(),
                    duration,
                    ",".join(list(apps_used))[:255],
                    ",".join(list(keywords_matched))[:255]
                )
