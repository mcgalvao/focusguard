import asyncio
import time
import logging
import threading
from monitor import WindowMonitor
from sender import DataSender
from tray import TrayApp
from overlay import TrackerOverlay

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("tracker")

# IMPORTANTE: Altere para o IP do seu Home Assistant!
# Exemplo: "http://192.168.1.15:8000"
BACKEND_URL = "http://homeassistant.local:8000"

SEND_INTERVAL = 30  # seconds between each batch send

monitor = WindowMonitor()
sender = DataSender(BACKEND_URL)
overlay = TrackerOverlay()

running = True
_dialog_open = False          # only one dialog at a time
_ignored_windows = set()      # windows user chose to ignore this session
_last_dialog_time = 0         # debounce: at least 2 min between dialogs

# Titles/apps to never ask about (system noise, our own overlay, etc.)
_SKIP_TITLES = {'tk', '', 'program manager', 'focusguard'}
_SKIP_APPS   = {'explorer.exe', 'searchhost.exe', 'shellexperiencehost.exe',
                'startmenuexperiencehost.exe', 'textinputhost.exe'}


def on_quit():
    global running
    running = False
    overlay.root.after(0, overlay.root.destroy)


def _build_reason(status: dict, last_window: dict | None) -> str:
    """Build a human-readable reason string for the current state."""
    parts = []

    if status.get("is_studying"):
        # Explicit reason from backend classification
        last_class = status.get("last_classification")
        if last_class and last_class.get("classification", {}).get("is_study"):
            kws = last_class["classification"].get("matched_keywords", [])
            kw_str = ", ".join(kws) if kws else "desconhecido"
            if last_window and last_window.get("window_title"):
                short = last_window["window_title"][:40]
                parts.append(f'"{short}" (por: {kw_str})')
            else:
                parts.append(f'Keyword: {kw_str}')
        else:
            if last_window and last_window.get("window_title"):
                short = last_window["window_title"][:40]
                parts.append(f'"{short}"')

    elif status.get("is_useful_time"):
        reason_code = status.get("useful_time_reason", "")
        mapping = {
            "dynamic_schedule": "Horário dinâmico (pós-hospital)",
            "fixed_schedule":   "Horário fixo de estudo",
        }
        parts.append(mapping.get(reason_code, reason_code))
        
        last_class = status.get("last_classification")
        if last_class and not last_class.get("classification", {}).get("is_study"):
            cls_reason = last_class["classification"].get("reason")
            if cls_reason == "blacklist":
                kws = last_class["classification"].get("matched_keywords", [])
                kw_str = ", ".join(kws) if kws else ""
                parts.append(f'Distração detectada: {kw_str}')
            elif cls_reason == "user_idle":
                parts.append("Inatividade detectada")
            
        deadline = status.get("useful_time_deadline")
        if deadline:
            try:
                from datetime import datetime
                dl = datetime.fromisoformat(deadline)
                parts.append(f'até {dl.strftime("%H:%M")}')
            except Exception:
                pass

    elif not status.get("is_home"):
        parts.append("Fora de casa")
    else:
        reason_code = status.get("useful_time_reason", "")
        if reason_code == "outside_schedule":
            parts.append("Fora do horário de estudo")
        elif reason_code == "past_deadline":
            parts.append("Passou do prazo")
        elif reason_code == "not_home":
            parts.append("Fora de casa")
        elif reason_code == "grace_period":
            parts.append("Descanso inicial")
            deadline = status.get("useful_time_deadline")
            if deadline:
                try:
                    from datetime import datetime
                    dl = datetime.fromisoformat(deadline)
                    parts.append(f'até {dl.strftime("%H:%M")}')
                except Exception:
                    pass

    return " · ".join([p for p in parts if p])


def _maybe_ask_keyword(status: dict, last_window: dict | None):
    """Show dialog if useful time but window not classified as study."""
    global _dialog_open, _last_dialog_time

    if _dialog_open:
        return
    if not status.get("is_useful_time"):
        return
    if status.get("is_studying"):
        return
    if last_window is None:
        return
    if time.time() - _last_dialog_time < 120:  # 2 min debounce
        return

    title = last_window.get("window_title", "").strip()
    app = last_window.get("app_name", "").strip().lower()

    # Skip our own overlay and system/shell windows
    if title.lower() in _SKIP_TITLES or app in _SKIP_APPS:
        return
    if title in _ignored_windows:
        return

    _dialog_open = True
    _last_dialog_time = time.time()

    logger.info(
        f"[UNKNOWN] Janela não classificada durante tempo útil: "
        f"app='{app}' title='{title}'"
    )

    def on_confirm(keyword: str, is_study: bool):
        global _dialog_open
        _dialog_open = False
        cat = "ESTUDO" if is_study else "DISTRAÇÃO"
        logger.info(f"[KEYWORD ADDED] '{keyword}' ({cat}) via janela: '{title}'")
        asyncio.run_coroutine_threadsafe(
            sender.add_keyword(keyword, is_study), _loop
        )

    def on_ignore():
        global _dialog_open
        _dialog_open = False
        _ignored_windows.add(title)
        logger.info(f"[IGNORED] Usuário ignorou janela: '{title}'")

    overlay.root.after(0, lambda: overlay.show_keyword_dialog(
        title, app, on_confirm, on_ignore
    ))


_loop: asyncio.AbstractEventLoop = None


async def main_loop():
    tray = TrayApp(on_quit)
    tray.start()

    batch = []
    last_send_time = 0  # Set to 0 so first evaluation happens immediately
    last_window = None
    window_start_time = time.time()

    overlay.set_status('connecting', 'Aguardando backend...', SEND_INTERVAL)
    logger.info("Tracker iniciado. Conectando ao backend...")

    while running:
        current_time = time.time()
        window_info = monitor.get_active_window_info()

        # ── Track window changes ──────────────────────────────────────────
        if window_info:
            if not last_window or (last_window["window_title"] != window_info["window_title"]):
                if last_window:
                    duration = current_time - window_start_time
                    last_window["duration_seconds"] = duration
                    batch.append(last_window)
                    logger.debug(
                        f"[WINDOW] '{last_window['app_name']}' — "
                        f"'{last_window['window_title'][:60]}' ({duration:.0f}s)"
                    )
                last_window = window_info
                window_start_time = current_time

        # ── Send batch every SEND_INTERVAL seconds ───────────────────────
        if current_time - last_send_time >= SEND_INTERVAL:
            # Flush current window into batch
            if last_window:
                duration = current_time - window_start_time
                copy = last_window.copy()
                copy["duration_seconds"] = duration
                batch.append(copy)
                window_start_time = current_time

            if batch:
                success = await sender.send_activities(batch)
                if success:
                    logger.info(f"[BATCH] {len(batch)} atividades enviadas.")
                    batch.clear()
                else:
                    logger.warning("[BATCH] Falha ao enviar — mantendo buffer.")

            # ── Get current status from backend ───────────────────────────
            status = await sender.get_status()

            if not status:
                tray.set_status("offline")
                overlay.set_status("offline", "Sem conexão com o backend", SEND_INTERVAL)
                logger.warning("[STATUS] Backend offline.")
            else:
                reason = _build_reason(status, last_window)
                proc_pct = status.get("procrastination_pct")

                if status.get("is_studying"):
                    overlay_status = "studying"
                    logger.info(
                        f"[STATUS] ✅ Estudando | {reason}"
                    )
                elif status.get("is_useful_time"):
                    overlay_status = "useful_idle"
                    logger.info(
                        f"[STATUS] ⚠️  Tempo útil OCIOSO | {reason} | "
                        f"Janela: '{(last_window or {}).get('window_title','?')[:60]}'"
                    )
                    _maybe_ask_keyword(status, last_window)
                else:
                    overlay_status = "free"
                    logger.info(f"[STATUS] 💤 Livre | {reason}")

                tray.set_status(overlay_status)
                overlay.set_status(overlay_status, reason, SEND_INTERVAL, proc_pct)

            last_send_time = current_time

        await asyncio.sleep(1)

    if batch:
        await sender.send_activities(batch)
    await sender.close()


def run_async():
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    try:
        _loop.run_until_complete(main_loop())
    except Exception as e:
        logger.error(f"Async loop error: {e}")
    finally:
        _loop.close()


if __name__ == "__main__":
    thread = threading.Thread(target=run_async, daemon=True)
    thread.start()
    overlay.run()
