"""
system_dashboard.py — Full-screen overlay showing live system metrics.

Opened by the agent when the user asks to see system status.
Press ESC or click Close to dismiss.
Auto-refreshes every 2 seconds.
"""

from __future__ import annotations

import math
import customtkinter as ctk
import psutil
from datetime import datetime


# ── Palette ───────────────────────────────────────────────────────────────────
BG         = "#0d1117"
CARD_BG    = "#161b22"
BORDER     = "#30363d"
GREEN      = "#39d353"
BLUE       = "#58a6ff"
YELLOW     = "#d29922"
RED        = "#f85149"
PURPLE     = "#bc8cff"
CYAN       = "#56d364"
TEXT       = "#e6edf3"
SUBTEXT    = "#8b949e"
FONT_TITLE = ("Segoe UI", 28, "bold")
FONT_HEAD  = ("Segoe UI", 13, "bold")
FONT_VAL   = ("Segoe UI", 22, "bold")
FONT_SUB   = ("Segoe UI", 11)
FONT_SM    = ("Segoe UI", 10)


def _bar_color(pct: float) -> str:
    if pct < 60:
        return GREEN
    if pct < 80:
        return YELLOW
    return RED


class MetricCard(ctk.CTkFrame):
    """A single metric card with a label, big value, and progress bar."""

    def __init__(self, parent, title: str, color: str = GREEN, **kwargs):
        super().__init__(
            parent,
            fg_color=CARD_BG,
            border_color=BORDER,
            border_width=1,
            corner_radius=12,
            **kwargs,
        )
        self._color = color
        self.grid_rowconfigure((0, 1, 2, 3), weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._title_lbl = ctk.CTkLabel(
            self, text=title, font=FONT_HEAD, text_color=SUBTEXT, anchor="w"
        )
        self._title_lbl.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 2))

        self._val_lbl = ctk.CTkLabel(
            self, text="—", font=FONT_VAL, text_color=TEXT, anchor="w"
        )
        self._val_lbl.grid(row=1, column=0, sticky="ew", padx=16, pady=2)

        self._bar = ctk.CTkProgressBar(
            self, height=8, corner_radius=4, progress_color=color, fg_color=BORDER
        )
        self._bar.set(0)
        self._bar.grid(row=2, column=0, sticky="ew", padx=16, pady=(4, 4))

        self._sub_lbl = ctk.CTkLabel(
            self, text="", font=FONT_SM, text_color=SUBTEXT, anchor="w"
        )
        self._sub_lbl.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 12))

    def update(self, value: str, pct: float, sub: str = "", auto_color: bool = True):
        self._val_lbl.configure(text=value)
        self._bar.set(min(pct / 100, 1.0))
        self._sub_lbl.configure(text=sub)
        if auto_color:
            c = _bar_color(pct)
            self._bar.configure(progress_color=c)
            self._val_lbl.configure(text_color=c)


class ProcessRow(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self._name = ctk.CTkLabel(self, text="", font=FONT_SM, text_color=TEXT, anchor="w")
        self._name.grid(row=0, column=0, columnspan=2, sticky="ew", padx=4)
        self._cpu = ctk.CTkLabel(self, text="", font=FONT_SM, text_color=BLUE, anchor="e")
        self._cpu.grid(row=0, column=2, sticky="ew", padx=4)
        self._ram = ctk.CTkLabel(self, text="", font=FONT_SM, text_color=PURPLE, anchor="e")
        self._ram.grid(row=0, column=3, sticky="ew", padx=4)

    def set(self, name: str, cpu: float, ram_mb: float):
        n = name[:28] + "…" if len(name) > 28 else name
        self._name.configure(text=n)
        self._cpu.configure(text=f"CPU {cpu:.1f}%")
        self._ram.configure(text=f"{ram_mb:.0f} MB")


class SystemDashboard(ctk.CTkToplevel):
    """Full-screen system metrics overlay."""

    _instance = None  # singleton guard

    def __init__(self, master):
        if SystemDashboard._instance and SystemDashboard._instance.winfo_exists():
            SystemDashboard._instance.lift()
            SystemDashboard._instance.focus_force()
            return

        super().__init__(master)
        SystemDashboard._instance = self

        self.title("System Status")
        self.configure(fg_color=BG)
        # self.attributes("-fullscreen", True) # Removed fullscreen
        self.geometry("900x640")
        self.resizable(False, False)
        self.bind("<Escape>", lambda _: self._close())

        self._build_ui()
        self._refresh()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Header bar
        header = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=0, height=56)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text="  ⬡  System Status", font=FONT_TITLE,
            text_color=GREEN, anchor="w"
        ).pack(side="left", padx=20, pady=8)

        self._clock_lbl = ctk.CTkLabel(
            header, text="", font=FONT_HEAD, text_color=SUBTEXT
        )
        self._clock_lbl.pack(side="right", padx=20)

        ctk.CTkButton(
            header, text="✕  Close", width=110, height=36,
            fg_color="#21262d", hover_color=RED, text_color=TEXT,
            font=FONT_HEAD, corner_radius=8,
            command=self._close,
        ).pack(side="right", padx=10, pady=10)

        # Body
        body = ctk.CTkFrame(self, fg_color=BG)
        body.pack(fill="both", expand=True, padx=24, pady=(16, 8))
        body.grid_rowconfigure((0, 1), weight=1)
        body.grid_columnconfigure((0, 1, 2, 3), weight=1)

        # Row 0 — metric cards
        self._cpu_card  = MetricCard(body, "🖥️  CPU")
        self._ram_card  = MetricCard(body, "🧠  RAM", color=BLUE)
        self._disk_card = MetricCard(body, "💾  Disk", color=YELLOW)
        self._bat_card  = MetricCard(body, "🔋  Battery", color=CYAN)

        for i, card in enumerate([self._cpu_card, self._ram_card, self._disk_card, self._bat_card]):
            card.grid(row=0, column=i, sticky="nsew", padx=8, pady=8)

        # Row 1 — network card + process list
        net_frame = ctk.CTkFrame(body, fg_color=CARD_BG, border_color=BORDER, border_width=1, corner_radius=12)
        net_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=8, pady=8)
        net_frame.grid_rowconfigure(1, weight=1)
        net_frame.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(net_frame, text="🌐  Network I/O", font=FONT_HEAD, text_color=SUBTEXT, anchor="w").grid(
            row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(14, 4)
        )
        self._net_sent_lbl = ctk.CTkLabel(net_frame, text="↑ —", font=FONT_VAL, text_color=BLUE, anchor="center")
        self._net_sent_lbl.grid(row=1, column=0, sticky="ew", padx=16, pady=8)
        self._net_recv_lbl = ctk.CTkLabel(net_frame, text="↓ —", font=FONT_VAL, text_color=GREEN, anchor="center")
        self._net_recv_lbl.grid(row=1, column=1, sticky="ew", padx=16, pady=8)
        self._net_sub = ctk.CTkLabel(net_frame, text="", font=FONT_SM, text_color=SUBTEXT)
        self._net_sub.grid(row=2, column=0, columnspan=2, padx=16, pady=(0, 12))
        self._net_baseline = None

        # Process list
        proc_frame = ctk.CTkFrame(body, fg_color=CARD_BG, border_color=BORDER, border_width=1, corner_radius=12)
        proc_frame.grid(row=1, column=2, columnspan=2, sticky="nsew", padx=8, pady=8)
        proc_frame.grid_rowconfigure(1, weight=1)
        proc_frame.grid_columnconfigure(0, weight=1)

        header_row = ctk.CTkFrame(proc_frame, fg_color="transparent")
        header_row.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))
        header_row.grid_columnconfigure((0, 1, 2, 3), weight=1)
        ctk.CTkLabel(header_row, text="⚡  Top Processes", font=FONT_HEAD, text_color=SUBTEXT, anchor="w").grid(row=0, column=0, columnspan=2, sticky="ew")
        ctk.CTkLabel(header_row, text="CPU", font=FONT_SM, text_color=BLUE, anchor="e").grid(row=0, column=2, sticky="ew")
        ctk.CTkLabel(header_row, text="RAM", font=FONT_SM, text_color=PURPLE, anchor="e").grid(row=0, column=3, sticky="ew", padx=4)

        self._proc_rows = []
        proc_list = ctk.CTkFrame(proc_frame, fg_color="transparent")
        proc_list.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 12))
        proc_list.grid_columnconfigure(0, weight=1)
        for i in range(8):
            row = ProcessRow(proc_list)
            row.grid(row=i, column=0, sticky="ew", pady=3)
            self._proc_rows.append(row)

        # Footer / Status Report
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", side="bottom", padx=24, pady=(0, 16))
        
        self._status_lbl = ctk.CTkLabel(
            footer, text="Everything in good condition", 
            font=FONT_HEAD, text_color=GREEN, anchor="e"
        )
        self._status_lbl.pack(side="right")

    # ── Data refresh ──────────────────────────────────────────────────────────

    def _refresh(self):
        if not self.winfo_exists():
            return
        try:
            self._update_metrics()
        except Exception:
            pass
        self.after(2000, self._refresh)

    def _fmt_bytes(self, b: float) -> str:
        for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
            if abs(b) < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} TB/s"

    def _update_metrics(self):
        # Clock
        self._clock_lbl.configure(text=datetime.now().strftime("%H:%M:%S  |  %a %d %b %Y"))

        # CPU
        cpu_pct = psutil.cpu_percent(interval=None)
        freq = psutil.cpu_freq()
        freq_str = f"{freq.current/1000:.2f} GHz" if freq else ""
        cores = psutil.cpu_count(logical=False)
        self._cpu_card.update(f"{cpu_pct:.1f}%", cpu_pct, sub=f"{cores} cores  {freq_str}")

        # RAM
        vm = psutil.virtual_memory()
        ram_used = vm.used / (1024**3)
        ram_total = vm.total / (1024**3)
        self._ram_card.update(f"{ram_used:.1f} GB", vm.percent, sub=f"of {ram_total:.1f} GB total")

        # Disk
        disk = psutil.disk_usage("/")
        disk_used = disk.used / (1024**3)
        disk_total = disk.total / (1024**3)
        self._disk_card.update(f"{disk_used:.0f} GB", disk.percent, sub=f"of {disk_total:.0f} GB total")

        # Battery
        bat = psutil.sensors_battery()
        if bat:
            status = "Charging" if bat.power_plugged else "Discharging"
            if bat.secsleft > 0 and not bat.power_plugged:
                h, m = divmod(int(bat.secsleft), 3600)
                m //= 60
                sub = f"{status} · {h}h {m}m left"
            else:
                sub = status
            self._bat_card.update(f"{bat.percent:.0f}%", bat.percent,
                                  sub=sub, auto_color=not bat.power_plugged)
            if bat.power_plugged:
                self._bat_card._bar.configure(progress_color=GREEN)
                self._bat_card._val_lbl.configure(text_color=GREEN)
        else:
            self._bat_card.update("N/A", 0, sub="No battery detected")

        # Network
        net = psutil.net_io_counters()
        if self._net_baseline is None:
            self._net_baseline = (net.bytes_sent, net.bytes_recv)
            sent_rate, recv_rate = 0.0, 0.0
        else:
            sent_rate = (net.bytes_sent - self._net_baseline[0]) / 2
            recv_rate = (net.bytes_recv - self._net_baseline[1]) / 2
            self._net_baseline = (net.bytes_sent, net.bytes_recv)

        self._net_sent_lbl.configure(text=f"↑  {self._fmt_bytes(sent_rate)}")
        self._net_recv_lbl.configure(text=f"↓  {self._fmt_bytes(recv_rate)}")
        total_sent = net.bytes_sent / (1024**3)
        total_recv = net.bytes_recv / (1024**3)
        self._net_sub.configure(text=f"Total: ↑ {total_sent:.2f} GB  ↓ {total_recv:.2f} GB")

        # Processes
        procs = sorted(
            psutil.process_iter(["name", "cpu_percent", "memory_info"]),
            key=lambda p: p.info.get("memory_info").rss if p.info.get("memory_info") else 0,
            reverse=True,
        )[:8]
        for i, (row, proc) in enumerate(zip(self._proc_rows, procs)):
            try:
                ram_mb = (proc.info["memory_info"].rss / (1024**2)) if proc.info.get("memory_info") else 0
                row.set(proc.info["name"] or "?", proc.info.get("cpu_percent", 0), ram_mb)
            except Exception:
                row.set("—", 0, 0)

        # Update Status Report
        self._update_status_report(cpu_pct, vm.percent)

    def _update_status_report(self, cpu_pct: float, ram_pct: float):
        if cpu_pct > 85 or ram_pct > 90:
            status = "System under heavy load"
            color = RED
        elif cpu_pct > 60 or ram_pct > 75:
            status = "System usage is moderate"
            color = YELLOW
        else:
            status = "Everything in good condition"
            color = GREEN
            
        self._status_lbl.configure(text=status, text_color=color)

    # ── Close ─────────────────────────────────────────────────────────────────

    def _close(self):
        SystemDashboard._instance = None
        self.destroy()
