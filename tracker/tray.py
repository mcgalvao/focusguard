import pystray
from PIL import Image, ImageDraw
import threading
from typing import Callable

class TrayApp:
    def __init__(self, on_quit: Callable):
        self.icon = None
        self.on_quit = on_quit
        
    def _create_image(self, color):
        image = Image.new('RGB', (64, 64), color=(0,0,0))
        d = ImageDraw.Draw(image)
        d.ellipse((16, 16, 48, 48), fill=color)
        return image

    def set_status(self, status: str):
        if not self.icon:
            return
            
        if status == "studying":
            color = (16, 185, 129) # Emerald
        elif status == "useful_idle":
            color = (245, 158, 11) # Amber
        elif status == "offline":
            color = (225, 29, 72) # Rose
        else:
            color = (148, 163, 184) # Slate
            
        self.icon.icon = self._create_image(color)

    def _setup_icon(self):
        image = self._create_image((148, 163, 184))
        menu = pystray.Menu(
            pystray.MenuItem('Sair', self._quit_action)
        )
        self.icon = pystray.Icon("FocusGuard", image, "FocusGuard Tracker", menu)
        self.icon.run()

    def _quit_action(self, icon, item):
        self.on_quit()
        icon.stop()

    def start(self):
        self.thread = threading.Thread(target=self._setup_icon, daemon=True)
        self.thread.start()
