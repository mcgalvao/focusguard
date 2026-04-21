"""
FocusGuard — Database module
SQLite database for activity logs, presence, sessions and daily reports.
"""
import aiosqlite
import os
from datetime import datetime, date
from typing import Optional
import json

# Use /data inside Add-on
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))
DB_PATH = os.path.join(DATA_DIR, "focusguard.db")


async def get_db() -> aiosqlite.Connection:
    """Get a database connection."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db():
    """Initialize database tables."""
    db = await get_db()
    try:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                app_name TEXT,
                window_title TEXT,
                duration_seconds REAL DEFAULT 0,
                is_study INTEGER DEFAULT 0,
                study_confidence REAL DEFAULT 0,
                matched_keywords TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS presence_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                state TEXT NOT NULL,
                previous_state TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS study_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time TEXT NOT NULL,
                end_time TEXT,
                duration_minutes REAL DEFAULT 0,
                apps_used TEXT,
                keywords_matched TEXT,
                session_type TEXT DEFAULT 'active',
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS daily_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_date TEXT NOT NULL UNIQUE,
                total_home_minutes REAL DEFAULT 0,
                total_useful_minutes REAL DEFAULT 0,
                total_study_minutes REAL DEFAULT 0,
                study_efficiency_pct REAL DEFAULT 0,
                tasks_completed INTEGER DEFAULT 0,
                tasks_total INTEGER DEFAULT 0,
                hospital_arrival TEXT,
                home_arrival TEXT,
                study_deadline TEXT,
                top_apps TEXT,
                top_keywords TEXT,
                hourly_breakdown TEXT,
                streak_days INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS hospital_visits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                visit_date TEXT NOT NULL,
                arrival_time TEXT,
                departure_time TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS home_arrivals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                arrival_date TEXT NOT NULL,
                arrival_time TEXT NOT NULL,
                calculated_useful_minutes REAL DEFAULT 0,
                study_deadline TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE INDEX IF NOT EXISTS idx_activity_timestamp ON activity_logs(timestamp);
            CREATE INDEX IF NOT EXISTS idx_activity_date ON activity_logs(created_at);
            CREATE INDEX IF NOT EXISTS idx_presence_timestamp ON presence_logs(timestamp);
            CREATE INDEX IF NOT EXISTS idx_sessions_start ON study_sessions(start_time);
            CREATE INDEX IF NOT EXISTS idx_reports_date ON daily_reports(report_date);
            CREATE INDEX IF NOT EXISTS idx_hospital_date ON hospital_visits(visit_date);
            CREATE INDEX IF NOT EXISTS idx_home_arrival_date ON home_arrivals(arrival_date);
        """)
        await db.commit()
    finally:
        await db.close()


# ─── Activity Logs ───

async def log_activity(timestamp: str, app_name: str, window_title: str,
                       duration_seconds: float, is_study: bool,
                       study_confidence: float = 0, matched_keywords: str = ""):
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO activity_logs 
               (timestamp, app_name, window_title, duration_seconds, is_study, study_confidence, matched_keywords)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (timestamp, app_name, window_title, duration_seconds,
             1 if is_study else 0, study_confidence, matched_keywords)
        )
        await db.commit()
    finally:
        await db.close()


async def log_activity_batch(activities: list):
    """Log multiple activities at once."""
    db = await get_db()
    try:
        await db.executemany(
            """INSERT INTO activity_logs 
               (timestamp, app_name, window_title, duration_seconds, is_study, study_confidence, matched_keywords)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [(a["timestamp"], a["app_name"], a["window_title"], a["duration_seconds"],
              1 if a["is_study"] else 0, a.get("study_confidence", 0),
              a.get("matched_keywords", "")) for a in activities]
        )
        await db.commit()
    finally:
        await db.close()


async def get_activities_for_date(target_date: str) -> list:
    """Get all activities for a specific date (YYYY-MM-DD)."""
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT * FROM activity_logs 
               WHERE date(timestamp) = ? 
               ORDER BY timestamp""",
            (target_date,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_study_minutes_today() -> float:
    """Get total study minutes for today."""
    today = date.today().isoformat()
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT COALESCE(SUM(duration_seconds), 0) / 60.0 as minutes
               FROM activity_logs 
               WHERE date(timestamp) = ? AND is_study = 1""",
            (today,)
        )
        row = await cursor.fetchone()
        return row["minutes"] if row else 0
    finally:
        await db.close()


# ─── Presence Logs ───

async def log_presence(timestamp: str, state: str, previous_state: str = None):
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO presence_logs (timestamp, state, previous_state)
               VALUES (?, ?, ?)""",
            (timestamp, state, previous_state)
        )
        await db.commit()
    finally:
        await db.close()


async def get_last_presence() -> Optional[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM presence_logs ORDER BY timestamp DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def get_presence_for_date(target_date: str) -> list:
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT * FROM presence_logs 
               WHERE date(timestamp) = ? ORDER BY timestamp""",
            (target_date,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


# ─── Hospital Visits ───

async def log_hospital_visit(visit_date: str, arrival_time: str = None, departure_time: str = None):
    db = await get_db()
    try:
        # Check if visit already exists for this date
        cursor = await db.execute(
            "SELECT id FROM hospital_visits WHERE visit_date = ?", (visit_date,)
        )
        existing = await cursor.fetchone()
        if existing:
            if departure_time:
                await db.execute(
                    "UPDATE hospital_visits SET departure_time = ? WHERE visit_date = ?",
                    (departure_time, visit_date)
                )
        else:
            await db.execute(
                """INSERT INTO hospital_visits (visit_date, arrival_time, departure_time)
                   VALUES (?, ?, ?)""",
                (visit_date, arrival_time, departure_time)
            )
        await db.commit()
    finally:
        await db.close()


async def get_hospital_visit_today() -> Optional[dict]:
    today = date.today().isoformat()
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM hospital_visits WHERE visit_date = ? ORDER BY arrival_time DESC LIMIT 1",
            (today,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


# ─── Home Arrivals ───

async def log_home_arrival(arrival_date: str, arrival_time: str,
                           calculated_useful_minutes: float, study_deadline: str):
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO home_arrivals 
               (arrival_date, arrival_time, calculated_useful_minutes, study_deadline)
               VALUES (?, ?, ?, ?)""",
            (arrival_date, arrival_time, calculated_useful_minutes, study_deadline)
        )
        await db.commit()
    finally:
        await db.close()


async def get_latest_home_arrival_today() -> Optional[dict]:
    today = date.today().isoformat()
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT * FROM home_arrivals 
               WHERE arrival_date = ? ORDER BY arrival_time DESC LIMIT 1""",
            (today,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


# ─── Study Sessions ───

async def start_study_session(start_time: str) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO study_sessions (start_time) VALUES (?)",
            (start_time,)
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def end_study_session(session_id: int, end_time: str,
                            duration_minutes: float, apps_used: str, keywords_matched: str):
    db = await get_db()
    try:
        await db.execute(
            """UPDATE study_sessions 
               SET end_time = ?, duration_minutes = ?, apps_used = ?, keywords_matched = ?
               WHERE id = ?""",
            (end_time, duration_minutes, apps_used, keywords_matched, session_id)
        )
        await db.commit()
    finally:
        await db.close()


async def get_sessions_for_date(target_date: str) -> list:
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT * FROM study_sessions 
               WHERE date(start_time) = ? ORDER BY start_time""",
            (target_date,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_active_session() -> Optional[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM study_sessions WHERE end_time IS NULL ORDER BY start_time DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def get_last_completed_session() -> Optional[dict]:
    """Get the most recently completed study session (not the active one)."""
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT * FROM study_sessions 
               WHERE end_time IS NOT NULL 
               ORDER BY end_time DESC LIMIT 1"""
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


# ─── Daily Reports ───

async def save_daily_report(report: dict):
    db = await get_db()
    try:
        await db.execute(
            """INSERT OR REPLACE INTO daily_reports 
               (report_date, total_home_minutes, total_useful_minutes, total_study_minutes,
                study_efficiency_pct, tasks_completed, tasks_total,
                hospital_arrival, home_arrival, study_deadline,
                top_apps, top_keywords, hourly_breakdown, streak_days)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (report["report_date"], report.get("total_home_minutes", 0),
             report.get("total_useful_minutes", 0), report.get("total_study_minutes", 0),
             report.get("study_efficiency_pct", 0),
             report.get("tasks_completed", 0), report.get("tasks_total", 0),
             report.get("hospital_arrival"), report.get("home_arrival"),
             report.get("study_deadline"),
             json.dumps(report.get("top_apps", [])),
             json.dumps(report.get("top_keywords", [])),
             json.dumps(report.get("hourly_breakdown", {})),
             report.get("streak_days", 0))
        )
        await db.commit()
    finally:
        await db.close()


async def get_daily_report(target_date: str) -> Optional[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM daily_reports WHERE report_date = ?",
            (target_date,)
        )
        row = await cursor.fetchone()
        if row:
            r = dict(row)
            r["top_apps"] = json.loads(r["top_apps"]) if r["top_apps"] else []
            r["top_keywords"] = json.loads(r["top_keywords"]) if r["top_keywords"] else []
            r["hourly_breakdown"] = json.loads(r["hourly_breakdown"]) if r["hourly_breakdown"] else {}
            return r
        return None
    finally:
        await db.close()


async def get_reports_range(start_date: str, end_date: str) -> list:
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT * FROM daily_reports 
               WHERE report_date BETWEEN ? AND ? 
               ORDER BY report_date""",
            (start_date, end_date)
        )
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            r = dict(row)
            r["top_apps"] = json.loads(r["top_apps"]) if r["top_apps"] else []
            r["top_keywords"] = json.loads(r["top_keywords"]) if r["top_keywords"] else []
            r["hourly_breakdown"] = json.loads(r["hourly_breakdown"]) if r["hourly_breakdown"] else {}
            results.append(r)
        return results
    finally:
        await db.close()


async def get_current_streak() -> int:
    """Calculate consecutive days with >50% study efficiency."""
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT report_date, study_efficiency_pct 
               FROM daily_reports ORDER BY report_date DESC"""
        )
        rows = await cursor.fetchall()
        streak = 0
        for row in rows:
            if row["study_efficiency_pct"] >= 50:
                streak += 1
            else:
                break
        return streak
    finally:
        await db.close()
