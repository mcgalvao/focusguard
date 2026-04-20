"""
FocusGuard Tracker — Floating overlay window
Small, draggable, always-on-top status indicator with reason and countdown.
"""
import tkinter as tk
import time


class TrackerOverlay:
    STATUS_CONFIG = {
        'studying':    ('#10b981', 'Estudando'),
        'useful_idle': ('#f59e0b', 'Tempo útil!'),
        'free':        ('#94a3b8', 'Livre'),
        'offline':     ('#ef4444', 'Offline'),
        'connecting':  ('#6366f1', 'Conectando...'),
    }

    def __init__(self, on_keyword_added=None):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.wm_attributes('-topmost', True)
        self.root.wm_attributes('-alpha', 0.92)
        self.root.configure(bg='#0f172a')

        sw = self.root.winfo_screenwidth()
        self.root.geometry(f'+{sw - 230}+24')

        self._status = 'connecting'
        self._reason = ''
        self._next_check_in = 30
        self._last_check_time = time.time()
        self._drag_x = 0
        self._drag_y = 0
        self.on_keyword_added = on_keyword_added

        self._build_ui()
        self._bind_drag(self.root, self._frame_outer, self._frame_inner,
                        self._dot, self._lbl_status, self._lbl_reason, self._lbl_timer)
        self._close_btn.bind('<Button-1>', lambda e: self.root.destroy())

        self.root.after(1000, self._tick)

    def _build_ui(self):
        self._frame_outer = tk.Frame(self.root, bg='#0f172a', padx=1, pady=1)
        self._frame_outer.pack()

        self._frame_inner = tk.Frame(
            self._frame_outer, bg='#1e293b',
            padx=12, pady=8,
            highlightbackground='#334155',
            highlightthickness=1
        )
        self._frame_inner.pack()

        # ── Row 1: dot + status + close ─────────────────────────────────
        row1 = tk.Frame(self._frame_inner, bg='#1e293b')
        row1.pack(fill='x')

        self._dot = tk.Label(row1, text='●', bg='#1e293b',
                             fg='#6366f1', font=('Segoe UI', 11))
        self._dot.pack(side=tk.LEFT, padx=(0, 6))

        self._lbl_status = tk.Label(row1, text='Conectando...', bg='#1e293b',
                                    fg='#f8fafc', font=('Segoe UI', 9, 'bold'),
                                    width=14, anchor='w')
        self._lbl_status.pack(side=tk.LEFT)

        self._close_btn = tk.Label(row1, text='✕', bg='#1e293b',
                                   fg='#475569', font=('Segoe UI', 8),
                                   cursor='hand2')
        self._close_btn.pack(side=tk.LEFT, padx=(8, 0))

        # ── Row 2: reason (small, muted) ─────────────────────────────────
        self._lbl_reason = tk.Label(self._frame_inner, text='',
                                    bg='#1e293b', fg='#64748b',
                                    font=('Segoe UI', 7), anchor='w',
                                    wraplength=200)
        self._lbl_reason.pack(fill='x', pady=(1, 0))

        # ── Row 3: countdown timer ────────────────────────────────────────
        self._lbl_timer = tk.Label(self._frame_inner, text='',
                                   bg='#1e293b', fg='#334155',
                                   font=('Segoe UI', 7), anchor='e')
        self._lbl_timer.pack(fill='x', pady=(2, 0))

    def _bind_drag(self, *widgets):
        for w in widgets:
            w.bind('<Button-1>', self._on_drag_start)
            w.bind('<B1-Motion>', self._on_drag)

    def _on_drag_start(self, event):
        self._drag_x = event.x_root - self.root.winfo_x()
        self._drag_y = event.y_root - self.root.winfo_y()

    def _on_drag(self, event):
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.root.geometry(f'+{x}+{y}')

    def _tick(self):
        """Update the countdown timer every second."""
        elapsed = time.time() - self._last_check_time
        remaining = max(0, int(self._next_check_in - elapsed))
        self._lbl_timer.config(text=f'Próx. avaliação: {remaining}s')
        self.root.after(1000, self._tick)

    def set_status(self, status: str, reason: str = '', check_interval: int = 30):
        """Thread-safe update — called from asyncio thread."""
        self._status = status
        self._reason = reason
        self._next_check_in = check_interval
        self._last_check_time = time.time()
        self.root.after(0, self._refresh_ui)

    def _refresh_ui(self):
        color, label = self.STATUS_CONFIG.get(self._status, ('#94a3b8', '—'))
        self._dot.config(fg=color)
        self._lbl_status.config(text=label)
        self._lbl_reason.config(text=self._reason)

    def show_keyword_dialog(self, window_title: str, app_name: str,
                            on_confirm, on_ignore):
        """Non-blocking popup asking the user for a keyword."""
        dialog = tk.Toplevel(self.root)
        dialog.overrideredirect(True)
        dialog.wm_attributes('-topmost', True)
        dialog.configure(bg='#1e293b')

        # Position near overlay
        ox = self.root.winfo_x()
        oy = self.root.winfo_y() + self.root.winfo_height() + 8
        dialog.geometry(f'+{ox}+{oy}')

        tk.Label(dialog, text='🔍 Janela não reconhecida',
                 bg='#1e293b', fg='#f59e0b',
                 font=('Segoe UI', 9, 'bold'),
                 padx=12, pady=(10, 2)).pack(anchor='w')

        title_short = (window_title[:45] + '…') if len(window_title) > 45 else window_title
        tk.Label(dialog, text=f'  {title_short}',
                 bg='#1e293b', fg='#94a3b8',
                 font=('Segoe UI', 8), padx=12).pack(anchor='w')

        tk.Label(dialog, text='Keyword para classificar como estudo:',
                 bg='#1e293b', fg='#cbd5e1',
                 font=('Segoe UI', 8), padx=12, pady=(8, 2)).pack(anchor='w')

        entry_var = tk.StringVar()
        entry = tk.Entry(dialog, textvariable=entry_var, width=28,
                         bg='#0f172a', fg='#f8fafc',
                         insertbackground='white',
                         relief='flat', font=('Segoe UI', 9))
        entry.pack(padx=12, pady=(0, 8))
        entry.focus()

        def _confirm():
            kw = entry_var.get().strip()
            if kw:
                on_confirm(kw)
            dialog.destroy()

        def _ignore():
            on_ignore()
            dialog.destroy()

        btn_row = tk.Frame(dialog, bg='#1e293b')
        btn_row.pack(padx=12, pady=(0, 10), anchor='e')

        tk.Button(btn_row, text='Ignorar', command=_ignore,
                  bg='#334155', fg='#94a3b8', relief='flat',
                  font=('Segoe UI', 8), padx=8, pady=3,
                  cursor='hand2').pack(side=tk.LEFT, padx=(0, 6))

        tk.Button(btn_row, text='Adicionar', command=_confirm,
                  bg='#8b5cf6', fg='white', relief='flat',
                  font=('Segoe UI', 8, 'bold'), padx=8, pady=3,
                  cursor='hand2').pack(side=tk.LEFT)

        entry.bind('<Return>', lambda e: _confirm())
        entry.bind('<Escape>', lambda e: _ignore())

    def run(self):
        self.root.mainloop()
