import win32gui
import win32process
import psutil
import uiautomation as auto
import time

def get_browser_url(hwnd):
    try:
        window = auto.WindowControl(searchDepth=1, Handle=hwnd)
        # In Chrome/Edge, the URL bar is an EditControl
        # Let's search all EditControls
        for edit in window.GetChildren():
            pass
        
        edit = window.EditControl()
        if edit.Exists(0, 0):
            val = edit.GetValuePattern().Value
            if val:
                return val
    except Exception as e:
        print("Error:", e)
    return None

print("Switch to Edge now! (5 seconds)")
time.sleep(5)
hwnd = win32gui.GetForegroundWindow()
title = win32gui.GetWindowText(hwnd)
print("Foreground:", title)
url = get_browser_url(hwnd)
print("URL:", url)
