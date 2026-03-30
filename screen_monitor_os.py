#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════╗
║   SCREEN MONITOR OS — Frequency & FPS Display Tool   ║
║   Real-time display of screen refresh rate & FPS     ║
╚══════════════════════════════════════════════════════╝

Requirements:
    pip install tkinter screeninfo psutil

Run:
    python3 screen_monitor_os.py
"""

import tkinter as tk
from tkinter import font as tkfont
import time
import threading
import platform
import subprocess
import sys
import math
import random

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# ─── Platform-specific refresh rate detection ──────────────────────────────

def get_refresh_rate_windows():
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hdc = user32.GetDC(0)
        gdi32 = ctypes.windll.gdi32
        rate = gdi32.GetDeviceCaps(hdc, 116)  # VREFRESH = 116
        user32.ReleaseDC(0, hdc)
        return rate if rate > 0 else 60
    except Exception:
        return 60

def get_refresh_rate_linux():
    try:
        out = subprocess.check_output(
            ["xrandr", "--verbose"], stderr=subprocess.DEVNULL
        ).decode()
        for line in out.splitlines():
            if "*+" in line or ("*" in line and "+" in line):
                import re
                match = re.search(r'(\d+\.\d+)\*', line)
                if match:
                    return float(match.group(1))
        # fallback: look for refresh in xrandr output
        import re
        for line in out.splitlines():
            match = re.search(r'(\d+\.\d+)\s*\*', line)
            if match:
                return float(match.group(1))
    except Exception:
        pass
    return 60.0

def get_refresh_rate_macos():
    try:
        out = subprocess.check_output(
            ["system_profiler", "SPDisplaysDataType"], stderr=subprocess.DEVNULL
        ).decode()
        import re
        for line in out.splitlines():
            match = re.search(r'(\d+)\s*Hz', line)
            if match:
                return int(match.group(1))
    except Exception:
        pass
    return 60

def get_screen_refresh_rate():
    os_name = platform.system()
    if os_name == "Windows":
        return get_refresh_rate_windows()
    elif os_name == "Linux":
        return get_refresh_rate_linux()
    elif os_name == "Darwin":
        return get_refresh_rate_macos()
    return 60

def get_screen_resolution():
    try:
        root = tk.Tk()
        w = root.winfo_screenwidth()
        h = root.winfo_screenheight()
        root.destroy()
        return w, h
    except Exception:
        return 1920, 1080

# ─── FPS Tracker ───────────────────────────────────────────────────────────

class FPSTracker:
    def __init__(self, window_size=60):
        self.timestamps = []
        self.window_size = window_size
        self.lock = threading.Lock()

    def tick(self):
        now = time.perf_counter()
        with self.lock:
            self.timestamps.append(now)
            cutoff = now - 1.0
            self.timestamps = [t for t in self.timestamps if t > cutoff]

    def get_fps(self):
        with self.lock:
            if len(self.timestamps) < 2:
                return 0.0
            duration = self.timestamps[-1] - self.timestamps[0]
            if duration <= 0:
                return 0.0
            return (len(self.timestamps) - 1) / duration

# ─── OS Monitor Application ────────────────────────────────────────────────

class ScreenMonitorOS:
    # Design constants — CRT/Terminal OS aesthetic
    BG          = "#000a00"
    PANEL_BG    = "#000d00"
    GREEN_BRIGHT= "#00ff41"
    GREEN_MID   = "#00cc33"
    GREEN_DIM   = "#006618"
    GREEN_DARK  = "#002a06"
    AMBER       = "#ffb300"
    RED         = "#ff2244"
    CYAN        = "#00eeff"
    WHITE       = "#e8ffe8"
    GRID_COLOR  = "#001a00"

    FONT_MONO   = "Courier New"
    FONT_SIZE_XL= 72
    FONT_SIZE_LG= 36
    FONT_SIZE_MD= 18
    FONT_SIZE_SM= 12
    FONT_SIZE_XS= 10

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SCREEN MONITOR OS v1.0")
        self.root.configure(bg=self.BG)
        self.root.resizable(True, True)

        # State
        self.fps_tracker = FPSTracker()
        self.current_fps = 0.0
        self.refresh_rate = get_screen_refresh_rate()
        self.resolution   = get_screen_resolution()
        self.running      = True
        self.frame_count  = 0
        self.start_time   = time.perf_counter()
        self.fps_history  = [0.0] * 120
        self.scan_offset  = 0
        self.blink_state  = True
        self.cpu_usage    = 0.0
        self.mem_usage    = 0.0

        # Build UI
        self._setup_window()
        self._build_ui()

        # Start threads
        threading.Thread(target=self._poll_system_stats, daemon=True).start()
        self._animation_loop()

    def _setup_window(self):
        sw, sh = self.resolution
        ww, wh = min(sw, 1100), min(sh, 700)
        x = (sw - ww) // 2
        y = (sh - wh) // 2
        self.root.geometry(f"{ww}x{wh}+{x}+{y}")
        self.root.minsize(700, 450)

    def _build_ui(self):
        root = self.root

        # ── Top boot bar ──────────────────────────────────────────────────
        top = tk.Frame(root, bg=self.GREEN_DIM, height=2)
        top.pack(fill=tk.X)

        header_frame = tk.Frame(root, bg=self.BG, pady=4)
        header_frame.pack(fill=tk.X, padx=16)

        tk.Label(
            header_frame, text="■ SCREEN MONITOR OS",
            font=(self.FONT_MONO, self.FONT_SIZE_SM, "bold"),
            fg=self.GREEN_BRIGHT, bg=self.BG
        ).pack(side=tk.LEFT)

        self.lbl_clock = tk.Label(
            header_frame, text="",
            font=(self.FONT_MONO, self.FONT_SIZE_XS),
            fg=self.GREEN_DIM, bg=self.BG
        )
        self.lbl_clock.pack(side=tk.RIGHT)

        tk.Frame(root, bg=self.GREEN_DIM, height=1).pack(fill=tk.X)

        # ── Main content ──────────────────────────────────────────────────
        main = tk.Frame(root, bg=self.BG)
        main.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)

        # Left column: FPS + Refresh
        left = tk.Frame(main, bg=self.BG)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._build_fps_panel(left)
        self._build_freq_panel(left)
        self._build_info_panel(left)

        # Right column: Graph + Stats
        right = tk.Frame(main, bg=self.BG, width=320)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(12, 0))
        right.pack_propagate(False)

        self._build_graph_panel(right)
        self._build_sys_panel(right)

        # ── Bottom status bar ─────────────────────────────────────────────
        tk.Frame(root, bg=self.GREEN_DIM, height=1).pack(fill=tk.X)
        status = tk.Frame(root, bg="#000600", pady=3)
        status.pack(fill=tk.X)

        self.lbl_status = tk.Label(
            status,
            text="● SYSTEM ONLINE  │  MONITORING ACTIVE  │  PRESS ESC TO EXIT",
            font=(self.FONT_MONO, self.FONT_SIZE_XS),
            fg=self.GREEN_DIM, bg="#000600"
        )
        self.lbl_status.pack(side=tk.LEFT, padx=16)

        self.lbl_uptime = tk.Label(
            status, text="",
            font=(self.FONT_MONO, self.FONT_SIZE_XS),
            fg=self.GREEN_DIM, bg="#000600"
        )
        self.lbl_uptime.pack(side=tk.RIGHT, padx=16)

        # Key binding
        root.bind("<Escape>", lambda e: self._quit())
        root.protocol("WM_DELETE_WINDOW", self._quit)

    def _build_fps_panel(self, parent):
        frame = tk.Frame(parent, bg=self.GREEN_DARK, bd=0,
                         highlightthickness=1,
                         highlightbackground=self.GREEN_DIM)
        frame.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            frame, text="┌─ LIVE FPS ───────────────────────────┐",
            font=(self.FONT_MONO, self.FONT_SIZE_XS),
            fg=self.GREEN_DIM, bg=self.GREEN_DARK
        ).pack(anchor="w", padx=8, pady=(6, 0))

        inner = tk.Frame(frame, bg=self.GREEN_DARK)
        inner.pack(fill=tk.X, padx=16, pady=4)

        self.lbl_fps_value = tk.Label(
            inner, text="---",
            font=(self.FONT_MONO, self.FONT_SIZE_XL, "bold"),
            fg=self.GREEN_BRIGHT, bg=self.GREEN_DARK
        )
        self.lbl_fps_value.pack(side=tk.LEFT)

        tk.Label(
            inner, text=" FPS",
            font=(self.FONT_MONO, self.FONT_SIZE_LG),
            fg=self.GREEN_MID, bg=self.GREEN_DARK
        ).pack(side=tk.LEFT, anchor="s", pady=12)

        self.lbl_fps_bar = tk.Label(
            frame, text="",
            font=(self.FONT_MONO, self.FONT_SIZE_XS),
            fg=self.GREEN_MID, bg=self.GREEN_DARK
        )
        self.lbl_fps_bar.pack(anchor="w", padx=16, pady=(0, 4))

        self.lbl_fps_grade = tk.Label(
            frame, text="INITIALIZING...",
            font=(self.FONT_MONO, self.FONT_SIZE_SM),
            fg=self.AMBER, bg=self.GREEN_DARK
        )
        self.lbl_fps_grade.pack(anchor="w", padx=16, pady=(0, 6))

        tk.Label(
            frame, text="└──────────────────────────────────────┘",
            font=(self.FONT_MONO, self.FONT_SIZE_XS),
            fg=self.GREEN_DIM, bg=self.GREEN_DARK
        ).pack(anchor="w", padx=8, pady=(0, 4))

    def _build_freq_panel(self, parent):
        frame = tk.Frame(parent, bg=self.GREEN_DARK, bd=0,
                         highlightthickness=1,
                         highlightbackground=self.GREEN_DIM)
        frame.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            frame, text="┌─ SCREEN FREQUENCY ───────────────────┐",
            font=(self.FONT_MONO, self.FONT_SIZE_XS),
            fg=self.GREEN_DIM, bg=self.GREEN_DARK
        ).pack(anchor="w", padx=8, pady=(6, 0))

        inner = tk.Frame(frame, bg=self.GREEN_DARK)
        inner.pack(fill=tk.X, padx=16, pady=4)

        hz_val = f"{int(self.refresh_rate)}"
        self.lbl_hz_value = tk.Label(
            inner, text=hz_val,
            font=(self.FONT_MONO, self.FONT_SIZE_XL, "bold"),
            fg=self.CYAN, bg=self.GREEN_DARK
        )
        self.lbl_hz_value.pack(side=tk.LEFT)

        tk.Label(
            inner, text=" Hz",
            font=(self.FONT_MONO, self.FONT_SIZE_LG),
            fg="#00aacc", bg=self.GREEN_DARK
        ).pack(side=tk.LEFT, anchor="s", pady=12)

        hz_grade = self._get_hz_grade(self.refresh_rate)
        tk.Label(
            frame, text=f"REFRESH RATE PROFILE: {hz_grade}",
            font=(self.FONT_MONO, self.FONT_SIZE_SM),
            fg=self.CYAN, bg=self.GREEN_DARK
        ).pack(anchor="w", padx=16, pady=(0, 6))

        tk.Label(
            frame, text="└──────────────────────────────────────┘",
            font=(self.FONT_MONO, self.FONT_SIZE_XS),
            fg=self.GREEN_DIM, bg=self.GREEN_DARK
        ).pack(anchor="w", padx=8, pady=(0, 4))

    def _build_info_panel(self, parent):
        frame = tk.Frame(parent, bg=self.BG)
        frame.pack(fill=tk.X)

        self.lbl_res = tk.Label(
            frame,
            text=f"RESOLUTION  :  {self.resolution[0]} × {self.resolution[1]}",
            font=(self.FONT_MONO, self.FONT_SIZE_XS),
            fg=self.GREEN_DIM, bg=self.BG
        )
        self.lbl_res.pack(anchor="w")

        self.lbl_platform = tk.Label(
            frame,
            text=f"PLATFORM    :  {platform.system()} {platform.release()}",
            font=(self.FONT_MONO, self.FONT_SIZE_XS),
            fg=self.GREEN_DIM, bg=self.BG
        )
        self.lbl_platform.pack(anchor="w")

        self.lbl_python = tk.Label(
            frame,
            text=f"PYTHON      :  {platform.python_version()}",
            font=(self.FONT_MONO, self.FONT_SIZE_XS),
            fg=self.GREEN_DIM, bg=self.BG
        )
        self.lbl_python.pack(anchor="w")

        self.lbl_frame_total = tk.Label(
            frame, text="FRAMES TOTAL:  0",
            font=(self.FONT_MONO, self.FONT_SIZE_XS),
            fg=self.GREEN_DIM, bg=self.BG
        )
        self.lbl_frame_total.pack(anchor="w")

    def _build_graph_panel(self, parent):
        tk.Label(
            parent, text="┌─ FPS GRAPH (last 120 frames) ────────┐",
            font=(self.FONT_MONO, 8),
            fg=self.GREEN_DIM, bg=self.BG
        ).pack(anchor="w")

        self.canvas = tk.Canvas(
            parent, bg="#000500", height=160,
            highlightthickness=1,
            highlightbackground=self.GREEN_DIM
        )
        self.canvas.pack(fill=tk.X, pady=2)

        tk.Label(
            parent, text="└──────────────────────────────────────┘",
            font=(self.FONT_MONO, 8),
            fg=self.GREEN_DIM, bg=self.BG
        ).pack(anchor="w")

    def _build_sys_panel(self, parent):
        frame = tk.Frame(parent, bg=self.BG)
        frame.pack(fill=tk.X, pady=(8, 0))

        tk.Label(
            frame, text="SYSTEM RESOURCES",
            font=(self.FONT_MONO, self.FONT_SIZE_XS, "bold"),
            fg=self.GREEN_DIM, bg=self.BG
        ).pack(anchor="w")

        self.lbl_cpu = tk.Label(
            frame, text="CPU  : ░░░░░░░░░░░░░░░░░░░░  0.0%",
            font=(self.FONT_MONO, self.FONT_SIZE_XS),
            fg=self.GREEN_MID, bg=self.BG
        )
        self.lbl_cpu.pack(anchor="w")

        self.lbl_mem = tk.Label(
            frame, text="MEM  : ░░░░░░░░░░░░░░░░░░░░  0.0%",
            font=(self.FONT_MONO, self.FONT_SIZE_XS),
            fg=self.GREEN_MID, bg=self.BG
        )
        self.lbl_mem.pack(anchor="w")

        self.lbl_fps_avg = tk.Label(
            frame, text="FPS AVG (10s): ---",
            font=(self.FONT_MONO, self.FONT_SIZE_XS),
            fg=self.GREEN_MID, bg=self.BG
        )
        self.lbl_fps_avg.pack(anchor="w", pady=(4, 0))

        self.lbl_fps_min = tk.Label(
            frame, text="FPS MIN      : ---",
            font=(self.FONT_MONO, self.FONT_SIZE_XS),
            fg=self.GREEN_MID, bg=self.BG
        )
        self.lbl_fps_min.pack(anchor="w")

        self.lbl_fps_max = tk.Label(
            frame, text="FPS MAX      : ---",
            font=(self.FONT_MONO, self.FONT_SIZE_XS),
            fg=self.GREEN_MID, bg=self.BG
        )
        self.lbl_fps_max.pack(anchor="w")

    # ─── Helpers ───────────────────────────────────────────────────────────

    def _get_fps_color(self, fps):
        if fps >= self.refresh_rate * 0.95:
            return self.GREEN_BRIGHT
        elif fps >= self.refresh_rate * 0.6:
            return self.AMBER
        else:
            return self.RED

    def _get_fps_grade(self, fps):
        rr = self.refresh_rate
        if fps >= rr * 0.95:
            return "★ EXCELLENT — VSYNC LOCKED"
        elif fps >= rr * 0.8:
            return "▲ GOOD — NEAR TARGET"
        elif fps >= rr * 0.5:
            return "◆ MODERATE — BELOW TARGET"
        elif fps > 0:
            return "▼ LOW — PERFORMANCE DROP"
        else:
            return "● MEASURING..."

    def _get_hz_grade(self, hz):
        if hz >= 240: return "ULTRA HIGH-REFRESH (240Hz+)"
        elif hz >= 165: return "HIGH-REFRESH (165Hz+)"
        elif hz >= 120: return "HIGH-REFRESH (120Hz+)"
        elif hz >= 75:  return "ENHANCED (75–144Hz)"
        elif hz >= 60:  return "STANDARD (60Hz)"
        else:           return "LOW-REFRESH (<60Hz)"

    def _make_bar(self, value, max_val, width=30):
        filled = int((value / max_val) * width) if max_val > 0 else 0
        filled = min(filled, width)
        return "█" * filled + "░" * (width - filled)

    # ─── System stats thread ───────────────────────────────────────────────

    def _poll_system_stats(self):
        while self.running:
            if PSUTIL_AVAILABLE:
                try:
                    self.cpu_usage = psutil.cpu_percent(interval=1)
                    mem = psutil.virtual_memory()
                    self.mem_usage = mem.percent
                except Exception:
                    pass
            else:
                time.sleep(1)

    # ─── Draw FPS graph ────────────────────────────────────────────────────

    def _draw_graph(self):
        c = self.canvas
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 10 or h < 10:
            return

        # Grid lines
        for i in range(0, h, h // 4):
            c.create_line(0, i, w, i, fill=self.GRID_COLOR, dash=(2, 4))

        rr = float(self.refresh_rate)
        target_y = int(h - (rr / max(rr * 1.2, 1)) * h)
        c.create_line(0, target_y, w, target_y,
                      fill=self.CYAN, dash=(3, 6), width=1)
        c.create_text(w - 4, target_y - 4, text=f"{int(rr)}Hz",
                      anchor="e", fill=self.CYAN,
                      font=(self.FONT_MONO, 8))

        # FPS curve
        history = self.fps_history[-min(w // 3, 120):]
        if len(history) < 2:
            return

        max_fps = max(max(history), rr * 1.1)
        step = w / len(history)
        points = []
        for i, fps in enumerate(history):
            x = int(i * step)
            y = int(h - (fps / max_fps) * (h - 4)) if max_fps > 0 else h
            y = max(2, min(h - 2, y))
            points.append((x, y))

        # Fill under curve
        poly_pts = [(0, h)] + points + [(w, h)]
        flat = [coord for pt in poly_pts for coord in pt]
        c.create_polygon(flat, fill="#001a00", outline="")

        # Draw line segments colored by performance
        for i in range(1, len(points)):
            fps = history[i]
            color = self._get_fps_color(fps)
            x0, y0 = points[i - 1]
            x1, y1 = points[i]
            c.create_line(x0, y0, x1, y1, fill=color, width=2)

        # Scan line animation
        sl_x = int((self.scan_offset % w))
        c.create_line(sl_x, 0, sl_x, h, fill="#004400", width=1)

    # ─── Main animation loop ───────────────────────────────────────────────

    def _animation_loop(self):
        if not self.running:
            return

        # Tick FPS
        self.fps_tracker.tick()
        self.current_fps = self.fps_tracker.get_fps()
        self.frame_count += 1
        self.scan_offset += 3

        # Update history
        self.fps_history.append(self.current_fps)
        if len(self.fps_history) > 300:
            self.fps_history = self.fps_history[-300:]

        # Blink cursor
        self.blink_state = not self.blink_state

        # ── Update widgets ──
        fps_int  = int(self.current_fps)
        fps_col  = self._get_fps_color(self.current_fps)
        fps_text = f"{fps_int:3d}" if self.current_fps > 0 else "---"

        self.lbl_fps_value.configure(text=fps_text, fg=fps_col)
        self.lbl_fps_grade.configure(
            text=self._get_fps_grade(self.current_fps),
            fg=fps_col
        )

        rr = float(self.refresh_rate)
        bar = self._make_bar(self.current_fps, rr * 1.2, width=36)
        self.lbl_fps_bar.configure(text=f"[{bar}]")

        # FPS stats
        recent = [f for f in self.fps_history[-300:] if f > 0]
        if recent:
            avg = sum(recent) / len(recent)
            mn  = min(recent)
            mx  = max(recent)
            self.lbl_fps_avg.configure(text=f"FPS AVG (10s): {avg:5.1f}")
            self.lbl_fps_min.configure(text=f"FPS MIN      : {mn:5.1f}")
            self.lbl_fps_max.configure(text=f"FPS MAX      : {mx:5.1f}")

        # System resources
        cpu_bar = self._make_bar(self.cpu_usage, 100, width=20)
        mem_bar = self._make_bar(self.mem_usage, 100, width=20)
        cpu_col = self.GREEN_MID if self.cpu_usage < 80 else self.AMBER
        mem_col = self.GREEN_MID if self.mem_usage < 85 else self.RED

        self.lbl_cpu.configure(
            text=f"CPU  : [{cpu_bar}] {self.cpu_usage:4.1f}%", fg=cpu_col
        )
        self.lbl_mem.configure(
            text=f"MEM  : [{mem_bar}] {self.mem_usage:4.1f}%", fg=mem_col
        )

        # Frame counter
        elapsed = time.perf_counter() - self.start_time
        self.lbl_frame_total.configure(
            text=f"FRAMES TOTAL: {self.frame_count:,}"
        )

        # Clock & uptime
        now_str  = time.strftime("%Y-%m-%d  %H:%M:%S")
        up_h = int(elapsed // 3600)
        up_m = int((elapsed % 3600) // 60)
        up_s = int(elapsed % 60)
        self.lbl_clock.configure(text=now_str)
        self.lbl_uptime.configure(
            text=f"UPTIME  {up_h:02d}:{up_m:02d}:{up_s:02d}"
        )

        # Status blink
        cursor = "█" if self.blink_state else " "
        self.lbl_status.configure(
            text=f"● ONLINE  │  FPS:{fps_int:4d}  Hz:{int(rr):4d}  │  ESC=EXIT {cursor}"
        )

        # Draw graph
        self._draw_graph()

        # Schedule next frame — aim for ~60 GUI updates/sec
        self.root.after(16, self._animation_loop)

    def _quit(self):
        self.running = False
        self.root.destroy()

    def run(self):
        self.root.mainloop()

# ─── Entry point ───────────────────────────────────────────────────────────

def check_dependencies():
    missing = []
    if not PSUTIL_AVAILABLE:
        missing.append("psutil")
    if missing:
        print(f"[WARN] Optional packages missing: {', '.join(missing)}")
        print(f"       Install with: pip install {' '.join(missing)}")
        print("       Continuing without system stats...\n")

def main():
    print("╔══════════════════════════════════════════╗")
    print("║       SCREEN MONITOR OS  v1.0            ║")
    print("║  Real-time FPS & Frequency Display Tool  ║")
    print("╚══════════════════════════════════════════╝")
    check_dependencies()

    rr = get_screen_refresh_rate()
    res = get_screen_resolution()
    print(f"[INFO] Detected refresh rate : {rr} Hz")
    print(f"[INFO] Screen resolution     : {res[0]}×{res[1]}")
    print(f"[INFO] Platform              : {platform.system()} {platform.release()}")
    print("[INFO] Launching monitor UI...\n")

    app = ScreenMonitorOS()
    app.run()

if __name__ == "__main__":
    main()
