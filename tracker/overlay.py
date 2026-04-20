"""
FocusGuard Tracker — Floating overlay window
Small, draggable, always-on-top status indicator.
"""
import tkinter as tk
import threading


class TrackerOverlay:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)          # No title bar / decorations
        self.root.wm_attributes('-topmost', True)  # Always on top
        self.root.wm_attributes('-alpha', 0.90)    # Slightly transparent
        self.root.configure(bg='#1e293b')

        # Start at top-right area of screen
        sw = self.root.winfo_screenwidth()
        self.root.geometry(f'+{sw - 220}+20')

        self._status = 'connecting'
        self._drag_x = 0
        self._drag_y = 0
        self._build_ui()

        # Drag support
        for widget in (self.root, self._frame, self._dot, self._label, self._close_btn):
            widget.bind('<Button-1>', self._on_drag_start)
            widget.bind('<B1-Motion>', self._on_drag)

        # Close button click
        self._close_btn.bind('<Button-1>', lambda e: self.root.destroy())

        self.root.after(500, self._refresh_ui)

    def _build_ui(self):
        self._frame = tk.Frame(
            self.root, bg='#1e293b',
            padx=12, pady=7,
            highlightbackground='#334155',
            highlightthickness=1
        )
        self._frame.pack()

        # Colored status dot
        self._dot = tk.Label(
            self._frame, text='●', bg='#1e293b',
            fg='#94a3b8', font=('Segoe UI', 11)
        )
        self._dot.pack(side=tk.LEFT, padx=(0, 7))

        # Status text
        self._label = tk.Label(
            self._frame, text='FocusGuard...', bg='#1e293b',
            fg='#f8fafc', font=('Segoe UI', 9, 'bold'), width=16, anchor='w'
        )
        self._label.pack(side=tk.LEFT)

        # Close button
        self._close_btn = tk.Label(
            self._frame, text='✕', bg='#1e293b',
            fg='#475569', font=('Segoe UI', 8), cursor='hand2'
        )
        self._close_btn.pack(side=tk.LEFT, padx=(6, 0))

    def _on_drag_start(self, event):
        self._drag_x = event.x_root - self.root.winfo_x()
        self._drag_y = event.y_root - self.root.winfo_y()

    def _on_drag(self, event):
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.root.geometry(f'+{x}+{y}')

    def set_status(self, status: str):
        """Called from asyncio thread — thread-safe via after()."""
        self._status = status
        self.root.after(0, self._refresh_ui)

    def _refresh_ui(self):
        cfg = {
            'studying':    ('#10b981', '● Estudando'),
            'useful_idle': ('#f59e0b', '● Tempo útil!'),
            'free':        ('#94a3b8', '● Livre'),
            'offline':     ('#ef4444', '● Offline'),
            'connecting':  ('#6366f1', '● Conectando...'),
        }
        color, text = cfg.get(self._status, ('#94a3b8', '● —'))
        dot_text = text[0]   # '●'
        label_text = text[2:]  # rest
        self._dot.config(fg=color)
        self._label.config(text=label_text)

    def run(self):
        """Blocking — must be called from the main thread."""
        self.root.mainloop()
