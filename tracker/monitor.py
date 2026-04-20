import win32gui
import win32process
import psutil
import time
from datetime import datetime

class WindowMonitor:
    def __init__(self):
        pass

    def get_active_window_info(self) -> dict:
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return None
                
            window_title = win32gui.GetWindowText(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            
            app_name = "Unknown"
            try:
                process = psutil.Process(pid)
                app_name = process.name()
            except Exception:
                pass
                
            return {
                "window_title": window_title,
                "app_name": app_name,
                "timestamp": datetime.now().isoformat()
            }
        except Exception:
            return None
