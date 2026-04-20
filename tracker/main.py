import asyncio
import time
import logging
import threading
from monitor import WindowMonitor
from sender import DataSender
from tray import TrayApp
from overlay import TrackerOverlay

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# IMPORTANTE: Altere para o IP do seu Home Assistant!
# Exemplo: "http://192.168.1.15:8000"
# O IP é o mesmo que você usa para acessar o HA no navegador, só troca a porta 8123 por 8000.
BACKEND_URL = "http://homeassistant.local:8000"

monitor = WindowMonitor()
sender = DataSender(BACKEND_URL)
overlay = TrackerOverlay()

running = True

def on_quit():
    global running
    running = False
    overlay.root.after(0, overlay.root.destroy)


async def main_loop():
    tray = TrayApp(on_quit)
    tray.start()

    batch = []
    last_send_time = time.time()
    last_window = None
    window_start_time = time.time()

    overlay.set_status('connecting')

    while running:
        current_time = time.time()
        window_info = monitor.get_active_window_info()

        if window_info:
            if not last_window or (last_window["window_title"] != window_info["window_title"]):
                if last_window:
                    duration = current_time - window_start_time
                    last_window["duration_seconds"] = duration
                    batch.append(last_window)
                last_window = window_info
                window_start_time = current_time

        if current_time - last_send_time > 30:
            if last_window:
                duration = current_time - window_start_time
                current_window_copy = last_window.copy()
                current_window_copy["duration_seconds"] = duration
                batch.append(current_window_copy)
                window_start_time = current_time

            if batch:
                success = await sender.send_activities(batch)
                if success:
                    batch.clear()

            status = await sender.get_status()
            if not status:
                tray.set_status("offline")
                overlay.set_status("offline")
            elif status.get("is_studying"):
                tray.set_status("studying")
                overlay.set_status("studying")
            elif status.get("is_useful_time"):
                tray.set_status("useful_idle")
                overlay.set_status("useful_idle")
            else:
                tray.set_status("free")
                overlay.set_status("free")

            last_send_time = current_time

        await asyncio.sleep(1)

    if batch:
        await sender.send_activities(batch)
    await sender.close()


def run_async():
    """Run the asyncio loop in a background thread."""
    try:
        asyncio.run(main_loop())
    except Exception as e:
        logging.error(f"Async loop error: {e}")


if __name__ == "__main__":
    # Asyncio in background thread, tkinter overlay on main thread
    thread = threading.Thread(target=run_async, daemon=True)
    thread.start()

    # This blocks until the overlay window is closed
    overlay.run()
