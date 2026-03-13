"""
Proactive Monitoring Engine — backend/agent/monitoring_engine.py

Runs as an asyncio background task per WebSocket session.
Polls system state every few seconds and calls orchestrator.push_alert()
when configurable thresholds are breached. Includes cooldown logic to
avoid spamming the user.
"""

import asyncio
import logging
import psutil
import subprocess
from datetime import datetime, time as dt_time
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.agent.gemini import GeminiOrchestrator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
CPU_HIGH_THRESHOLD = 85.0        # % — must be sustained for CPU_HIGH_STRIKES polls
CPU_HIGH_STRIKES = 3             # consecutive polls above threshold before alert
CPU_TEMP_THRESHOLD = 85.0        # °C  (thermal throttling typically starts ~90°C)
RAM_WARNING_THRESHOLD = 80.0     # %
RAM_CRITICAL_THRESHOLD = 90.0   # %
DISK_LOW_THRESHOLD = 10.0        # % free remaining
BATTERY_LOW_THRESHOLD = 20.0     # % — warn when below this
BATTERY_CRITICAL_THRESHOLD = 10.0  # % — urgent warning

# ---------------------------------------------------------------------------
# Cooldowns (seconds) — minimum time between alerts of the same type
# ---------------------------------------------------------------------------
COOLDOWNS = {
    "cpu_high":             180,
    "cpu_temp":             120,
    "ram_warning":          120,
    "ram_critical":         30,
    "disk_low":             300,
    "battery_low":          120,
    "battery_critical":     30,
    "better_wifi":          300,
    "nudge_sleep":          1800,
    "meeting_dnd":          600,
    # New rules
    "network_spike":        120,
    "disk_io_high":         120,
    "app_hang":             300,
    "theme_suggestion":     3600,  # once per hour
    "update_available":     86400, # once per day
    "connectivity_issue":   120,
    "notification_fatigue": 1800,
    "auto_shutdown":        1800,
    "malware_scan":         604800, # once per week
    "sleep_suggestion":     1800,
}

POLL_INTERVAL = 10  # seconds between each monitoring tick


class MonitoringEngine:
    def __init__(self, orchestrator: "GeminiOrchestrator", tier3=None):
        self.orchestrator = orchestrator
        self.tier3 = tier3  # MemoryTier3 instance for time-aware nudges

        # Last-fired timestamps per alert type
        self._last_alerts: dict[str, Optional[datetime]] = {k: None for k in COOLDOWNS}

        # CPU high-CPU strike counter
        self._cpu_strike_count = 0

        # Sleep nudge tracking — only fire once per sleep-time crossing
        self._sleep_nudge_fired_today = False
        self._last_nudge_date: Optional[str] = None

        # Meeting tracking
        self._meeting_dnd_suggested = False
        self._last_meeting_window: Optional[str] = None

        # Network / disk I/O baseline (set on first poll)
        self._net_bytes_sent: Optional[int] = None
        self._net_bytes_recv: Optional[int] = None
        self._net_last_time: Optional[datetime] = None
        self._disk_io_read: Optional[int] = None
        self._disk_io_write: Optional[int] = None
        self._disk_io_last_time: Optional[datetime] = None

        # Notification fatigue: track how many alerts we've fired
        self._alert_times: list = []  # list of datetime each alert fired (for fatigue detection)

        # Theme suggestion: track last suggested theme to avoid repeats
        self._last_theme_suggested: Optional[str] = None

        # Alert queue — prevents simultaneous spam; drains one alert every ALERT_DISPATCH_GAP seconds
        self._alert_queue: asyncio.Queue = asyncio.Queue(maxsize=5)
        self._last_dispatched: Optional[datetime] = None
        self.ALERT_DISPATCH_GAP = 45  # seconds between consecutive dispatched alerts

    async def run(self):
        """Main monitoring loop — runs until cancelled."""
        logger.info("Monitoring Engine starting in 60 seconds...")
        await asyncio.sleep(60) # Startup delay requested by user
        logger.info("Monitoring Engine active.")
        drain_task = asyncio.create_task(self._alert_drain_loop())
        try:
            while True:
                try:
                    await self._tick()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Monitoring Engine error: {e}", exc_info=True)
                await asyncio.sleep(POLL_INTERVAL)
        finally:
            drain_task.cancel()
            logger.info("Monitoring Engine stopped.")

    async def _alert_drain_loop(self):
        """Dispatches queued alerts one at a time with a minimum gap between each."""
        while True:
            try:
                alert_type, message = await asyncio.wait_for(self._alert_queue.get(), timeout=5)
                now = datetime.now()
                if self._last_dispatched is not None:
                    elapsed = (now - self._last_dispatched).total_seconds()
                    remaining = self.ALERT_DISPATCH_GAP - elapsed
                    if remaining > 0:
                        await asyncio.sleep(remaining)
                await self.orchestrator.push_alert(message)
                self._last_dispatched = datetime.now()
                self._alert_queue.task_done()
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.debug(f"Alert drain error: {e}")


    # -----------------------------------------------------------------------
    # Per-tick logic
    # -----------------------------------------------------------------------

    async def _tick(self):
        now = datetime.now()

        # --- CPU ---
        cpu = psutil.cpu_percent(interval=1)
        if cpu > CPU_HIGH_THRESHOLD:
            self._cpu_strike_count += 1
        else:
            self._cpu_strike_count = 0

        if self._cpu_strike_count >= CPU_HIGH_STRIKES:
            msg = (
                f"[SYSTEM ALERT — speak this aloud] CPU usage has been above "
                f"{CPU_HIGH_THRESHOLD:.0f}% for a sustained period — currently at {cpu:.0f}%. "
                "Identify the cause, tell the user what's hogging the CPU, and suggest what to do."
            )
            if self._can_fire("cpu_high", now):
                await self._fire("cpu_high", msg, now)
                self._cpu_strike_count = 0

        # --- CPU Temperature ---
        await self._check_cpu_temp(now)

        # --- RAM ---
        ram = psutil.virtual_memory()
        if ram.percent > RAM_CRITICAL_THRESHOLD:
            msg = (
                f"[SYSTEM ALERT — speak this aloud] RAM usage is critically high at "
                f"{ram.percent:.0f}% ({ram.used // (1024**3):.1f}GB of {ram.total // (1024**3):.1f}GB used). "
                "Tell the user urgently and suggest freeing memory."
            )
            if self._can_fire("ram_critical", now):
                await self._fire("ram_critical", msg, now)
        elif ram.percent > RAM_WARNING_THRESHOLD:
            msg = (
                f"[SYSTEM ALERT — speak this aloud] RAM usage is high at "
                f"{ram.percent:.0f}%. "
                "Briefly let the user know and suggest they consider closing some apps."
            )
            if self._can_fire("ram_warning", now):
                await self._fire("ram_warning", msg, now)

        # --- Disk ---
        disk = psutil.disk_usage("/")
        disk_free_pct = (disk.free / disk.total) * 100
        if disk_free_pct < DISK_LOW_THRESHOLD:
            msg = (
                f"[SYSTEM ALERT — speak this aloud] Disk space is running low — "
                f"only {disk_free_pct:.1f}% free ({disk.free // (1024**3):.1f}GB remaining). "
                "Tell the user and suggest running disk cleanup."
            )
            if self._can_fire("disk_low", now):
                await self._fire("disk_low", msg, now)

        # --- Battery ---
        await self._check_battery(now)

        # --- Better WiFi ---
        await self._check_better_wifi(now)

        # --- Active Meeting / DND suggestion ---
        await self._check_meeting(now)

        # --- Network spike ---
        await self._check_network_spike(now)

        # --- Disk I/O high ---
        await self._check_disk_io(now)

        # --- App hang detection ---
        await self._check_app_hang(now)

        # --- Theme auto-suggestion ---
        await self._check_theme_suggestion(now)

        # --- OS update available ---
        await self._check_updates(now)

        # --- Connectivity issue ---
        await self._check_connectivity(now)

        # --- Notification fatigue ---
        await self._check_notification_fatigue(now)

        # --- Auto shutdown recommendation ---
        await self._check_auto_shutdown(now)

        # --- Malware scan suggestion ---
        await self._check_malware_scan(now)

        # --- Sleep suggestion ---
        await self._check_sleep_suggestion(now)

        # --- Time-aware nudge ---
        await self._check_time_nudge(now)

    # -----------------------------------------------------------------------
    # Specific checks
    # -----------------------------------------------------------------------

    async def _check_cpu_temp(self, now: datetime):
        """Check CPU temperature via psutil sensors."""
        try:
            temps = psutil.sensors_temperatures()
            if not temps:
                return
            # Look for coretemp or acpitz (common on Linux)
            for sensor_name in ("coretemp", "acpitz", "k10temp", "zenpower"):
                if sensor_name in temps:
                    readings = temps[sensor_name]
                    max_temp = max(r.current for r in readings)
                    if max_temp > CPU_TEMP_THRESHOLD:
                        msg = (
                            f"[SYSTEM ALERT — speak this aloud] CPU temperature is high at "
                            f"{max_temp:.0f}°C. This is approaching thermal throttling territory. "
                            "Warn the user — they may want to check airflow or reduce load."
                        )
                        if self._can_fire("cpu_temp", now):
                            await self._fire("cpu_temp", msg, now)
                    return
        except Exception as e:
            logger.debug(f"CPU temp check failed: {e}")

    async def _check_battery(self, now: datetime):
        """Check battery level and charging state."""
        try:
            battery = psutil.sensors_battery()
            if battery is None or battery.power_plugged:
                return  # Plugged in — no alert needed

            pct = battery.percent
            if pct <= BATTERY_CRITICAL_THRESHOLD:
                msg = (
                    f"[SYSTEM ALERT — speak this aloud] Battery is critically low at {pct:.0f}%! "
                    "Tell the user urgently — they need to plug in immediately."
                )
                if self._can_fire("battery_critical", now):
                    await self._fire("battery_critical", msg, now)
            elif pct <= BATTERY_LOW_THRESHOLD:
                secs_left = battery.secsleft
                time_left = ""
                if secs_left and secs_left != psutil.POWER_TIME_UNLIMITED:
                    mins = secs_left // 60
                    time_left = f" (~{mins} minutes remaining)"
                msg = (
                    f"[SYSTEM ALERT — speak this aloud] Battery is at {pct:.0f}%{time_left}. "
                    "Gently let the user know they might want to plug in soon."
                )
                if self._can_fire("battery_low", now):
                    await self._fire("battery_low", msg, now)
        except Exception as e:
            logger.debug(f"Battery check failed: {e}")

    async def _check_better_wifi(self, now: datetime):
        """Detect if a stronger WiFi network is available than the one currently connected to."""
        if not self._can_fire("better_wifi", now):
            return
        try:
            # Get current SSID and signal
            result = subprocess.run(
                ["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL", "device", "wifi"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                return

            lines = result.stdout.strip().split("\n")
            current_signal = None
            current_ssid = None
            best_other_signal = 0
            best_other_ssid = None

            for line in lines:
                parts = line.split(":")
                if len(parts) < 3:
                    continue
                active, ssid, signal_str = parts[0], parts[1], parts[2]
                try:
                    sig = int(signal_str)
                except ValueError:
                    continue

                if active == "yes":
                    current_signal = sig
                    current_ssid = ssid
                elif sig > best_other_signal:
                    best_other_signal = sig
                    best_other_ssid = ssid

            if (
                current_signal is not None
                and best_other_ssid is not None
                and best_other_signal > current_signal + 20   # meaningfully better
            ):
                msg = (
                    f"[SYSTEM ALERT — speak this aloud] There's a stronger WiFi network available: "
                    f"'{best_other_ssid}' (signal {best_other_signal}) vs your current "
                    f"'{current_ssid}' (signal {current_signal}). "
                    "Let the user know they could switch to a better network."
                )
                await self._fire("better_wifi", msg, now)
        except Exception as e:
            logger.debug(f"WiFi check failed: {e}")

    async def _check_meeting(self, now: datetime):
        """Detect active Google Meet / Zoom / Teams windows and suggest enabling DND."""
        if not self._can_fire("meeting_dnd", now):
            return
        MEETING_KEYWORDS = [
            "meet.google.com", "google meet",
            "zoom meeting", "zoom",
            "microsoft teams", "teams.microsoft.com",
            "webex", "jitsi", "bluejeans",
        ]
        try:
            result = subprocess.run(
                ["wmctrl", "-l"], capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                return

            detected_window = None
            for line in result.stdout.strip().split("\n"):
                line_lower = line.lower()
                for kw in MEETING_KEYWORDS:
                    if kw in line_lower:
                        detected_window = line.strip()
                        break
                if detected_window:
                    break

            if detected_window:
                # New meeting — suggest DND if we haven't already for this window
                if detected_window != self._last_meeting_window:
                    self._last_meeting_window = detected_window
                    self._meeting_dnd_suggested = False

                if not self._meeting_dnd_suggested:
                    msg = (
                        f"[MEETING DETECTED — speak this aloud] It looks like you have an active "
                        f"video call going on ({detected_window}). "
                        "Ask the user if they'd like to enable Do Not Disturb to avoid notification interruptions during the call."
                    )
                    await self._fire("meeting_dnd", msg, now)
                    self._meeting_dnd_suggested = True
            else:
                # No meeting — reset so we can alert again next time
                self._last_meeting_window = None
                self._meeting_dnd_suggested = False
        except FileNotFoundError:
            logger.debug("wmctrl not found — meeting detection skipped.")
        except Exception as e:
            logger.debug(f"Meeting check failed: {e}")

    async def _check_network_spike(self, now: datetime):
        """Alert on large sudden spikes in network bandwidth."""
        try:
            net = psutil.net_io_counters()
            if self._net_bytes_sent is None:
                self._net_bytes_sent = net.bytes_sent
                self._net_bytes_recv = net.bytes_recv
                self._net_last_time = now
                return
            elapsed = (now - self._net_last_time).total_seconds() or 1
            sent_mbps = (net.bytes_sent - self._net_bytes_sent) / elapsed / 1024 / 1024
            recv_mbps = (net.bytes_recv - self._net_bytes_recv) / elapsed / 1024 / 1024
            self._net_bytes_sent = net.bytes_sent
            self._net_bytes_recv = net.bytes_recv
            self._net_last_time = now
            if (sent_mbps > 10 or recv_mbps > 10) and self._can_fire("network_spike", now):
                direction = "upload" if sent_mbps > recv_mbps else "download"
                speed = max(sent_mbps, recv_mbps)
                await self._fire("network_spike", (
                    f"[SYSTEM ALERT — speak this aloud] Network {direction} spike detected: "
                    f"{speed:.1f} MB/s. Something is using a lot of bandwidth. "
                    "Tell the user and offer to check which process is responsible."
                ), now)
        except Exception as e:
            logger.debug(f"Network spike check failed: {e}")

    async def _check_disk_io(self, now: datetime):
        """Alert on sustained high disk read/write activity."""
        try:
            io = psutil.disk_io_counters()
            if self._disk_io_read is None:
                self._disk_io_read = io.read_bytes
                self._disk_io_write = io.write_bytes
                self._disk_io_last_time = now
                return
            elapsed = (now - self._disk_io_last_time).total_seconds() or 1
            read_mbps = (io.read_bytes - self._disk_io_read) / elapsed / 1024 / 1024
            write_mbps = (io.write_bytes - self._disk_io_write) / elapsed / 1024 / 1024
            self._disk_io_read = io.read_bytes
            self._disk_io_write = io.write_bytes
            self._disk_io_last_time = now
            if (read_mbps > 50 or write_mbps > 50) and self._can_fire("disk_io_high", now):
                direction = "write" if write_mbps > read_mbps else "read"
                speed = max(read_mbps, write_mbps)
                await self._fire("disk_io_high", (
                    f"[SYSTEM ALERT — speak this aloud] High disk {direction} activity: "
                    f"{speed:.0f} MB/s sustained. This could indicate a backup, indexing, "
                    "or runaway process. Let the user know."
                ), now)
        except Exception as e:
            logger.debug(f"Disk IO check failed: {e}")

    async def _check_app_hang(self, now: datetime):
        """Detect zombie or stopped/hung processes."""
        if not self._can_fire("app_hang", now):
            return
        try:
            hung = []
            for proc in psutil.process_iter(["pid", "name", "status"]):
                try:
                    if proc.info["status"] in (psutil.STATUS_ZOMBIE, psutil.STATUS_STOPPED):
                        hung.append(f"{proc.info['name']} (PID {proc.info['pid']})")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            if hung:
                names = ", ".join(hung[:3])
                await self._fire("app_hang", (
                    f"[SYSTEM ALERT — speak this aloud] Detected unresponsive or zombie processes: "
                    f"{names}. Tell the user and ask if they'd like to terminate them."
                ), now)
        except Exception as e:
            logger.debug(f"App hang check failed: {e}")

    async def _check_theme_suggestion(self, now: datetime):
        """Auto-suggest dark mode in evenings and light mode in mornings."""
        if not self._can_fire("theme_suggestion", now):
            return
        hour = now.hour
        if 19 <= hour <= 23 or hour < 1:
            suggested = "dark"
        elif 7 <= hour <= 9:
            suggested = "light"
        else:
            return
        if suggested == self._last_theme_suggested:
            return
        self._last_theme_suggested = suggested
        await self._fire("theme_suggestion", (
            f"[SUGGESTION — speak this aloud] It's {now.strftime('%I:%M %p')}. "
            f"Would the user like to switch to {suggested} mode? "
            f"Use set_system_theme to apply it if they say yes."
        ), now)

    async def _check_updates(self, now: datetime):
        """Check for available apt package updates once per day."""
        if not self._can_fire("update_available", now):
            return
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["apt", "list", "--upgradable"],
                capture_output=True, text=True, timeout=15
            )
            lines = [l for l in result.stdout.strip().split("\n") if "/" in l]
            count = len(lines)
            if count > 0:
                await self._fire("update_available", (
                    f"[SYSTEM ALERT — speak this aloud] There are {count} package update(s) available "
                    f"on this system. Mention this to the user and ask if they'd like to update now."
                ), now)
        except Exception as e:
            logger.debug(f"Update check failed: {e}")

    async def _check_connectivity(self, now: datetime):
        """Detect internet connectivity issues via HTTP (more reliable than ping which ISPs block)."""
        if not self._can_fire("connectivity_issue", now):
            return
        import urllib.request

        def _http_check() -> bool:
            """Returns True if internet is reachable, False if not."""
            targets = [
                "http://connectivitycheck.gstatic.com/generate_204",
                "http://detectportal.firefox.com/success.txt",
                "http://www.msftconnecttest.com/connecttest.txt",
            ]
            for url in targets:
                try:
                    req = urllib.request.urlopen(url, timeout=5)
                    if req.status < 400:
                        return True  # At least one succeeded — we have internet
                except Exception:
                    continue
            return False  # All failed

        try:
            is_up = await asyncio.to_thread(_http_check)
            if not is_up:
                await self._fire("connectivity_issue", (
                    "[SYSTEM ALERT — speak this aloud] Internet connectivity appears to be down. "
                    "Multiple connectivity checks all failed. Tell the user and suggest checking their network."
                ), now)
        except Exception as e:
            logger.debug(f"Connectivity check failed: {e}")

    async def _check_notification_fatigue(self, now: datetime):
        """If many alerts have fired in the last 30 minutes, suggest muting."""
        # Prune old entries
        cutoff = (now.timestamp() - 1800)
        self._alert_times = [t for t in self._alert_times if t > cutoff]
        if len(self._alert_times) >= 5 and self._can_fire("notification_fatigue", now):
            await self._fire("notification_fatigue", (
                "[SUGGESTION — speak this aloud] You've had quite a few system alerts in the last "
                "30 minutes. Ask the user if they'd like to mute notifications for a while using DND mode."
            ), now)

    async def _check_auto_shutdown(self, now: datetime):
        """Recommend shutdown if it's late and the system has been running a long time."""
        if not self._can_fire("auto_shutdown", now):
            return
        if not (22 <= now.hour or now.hour < 2):
            return  # Only suggest shutting down late at night
        try:
            with open("/proc/uptime") as f:
                uptime_seconds = float(f.read().split()[0])
            uptime_hours = uptime_seconds / 3600
            if uptime_hours > 6:
                await self._fire("auto_shutdown", (
                    f"[SUGGESTION — speak this aloud] It's {now.strftime('%I:%M %p')} and the system "
                    f"has been running for {uptime_hours:.0f} hours. "
                    "Ask the user if they'd like to schedule a shutdown or if they're done for the day."
                ), now)
        except Exception as e:
            logger.debug(f"Auto shutdown check failed: {e}")

    async def _check_malware_scan(self, now: datetime):
        """Weekly reminder to run a security scan."""
        if not self._can_fire("malware_scan", now):
            return
        has_clamav = subprocess.run(["which", "clamscan"], capture_output=True).returncode == 0
        has_rkhunter = subprocess.run(["which", "rkhunter"], capture_output=True).returncode == 0
        if has_clamav or has_rkhunter:
            tool = "clamscan" if has_clamav else "rkhunter"
            await self._fire("malware_scan", (
                f"[WEEKLY SUGGESTION — speak this aloud] It's been a while since a security scan. "
                f"{tool} is available. Ask the user if they'd like to run a quick malware scan."
            ), now)
        else:
            await self._fire("malware_scan", (
                "[WEEKLY SUGGESTION — speak this aloud] No security scanner is installed. "
                "Ask the user if they'd like to install ClamAV for periodic malware scanning "
                "(sudo apt install clamav)."
            ), now)

    async def _check_sleep_suggestion(self, now: datetime):
        """Suggest sleep if it's late and CPU/network have been idle for a while."""
        if not self._can_fire("sleep_suggestion", now):
            return
        if not (23 <= now.hour or now.hour < 4):
            return
        try:
            cpu = psutil.cpu_percent(interval=1)
            net = psutil.net_io_counters()
            # Lightweight heuristic: low CPU + system running late = suggest sleep
            if cpu < 5.0:
                await self._fire("sleep_suggestion", (
                    f"[SUGGESTION — speak this aloud] It's {now.strftime('%I:%M %p')} and the system "
                    "seems idle. Ask the user if they'd like to put the computer to sleep "
                    "(systemctl suspend) or shut it down."
                ), now)
        except Exception as e:
            logger.debug(f"Sleep suggestion check failed: {e}")

    async def _check_time_nudge(self, now: datetime):
        """Use Tier 3 profile to fire time-aware nudges (e.g. sleep reminders)."""
        if not self.tier3:
            return
        if not self._can_fire("nudge_sleep", now):
            return

        try:
            prefs = self.tier3.get_preference("auto_shutdown_time")  # e.g. "23:00"
            if not prefs:
                return

            # Parse the shutdown/sleep time
            hour, minute = map(int, prefs.split(":"))
            sleep_time = dt_time(hour, minute)
            current_time = now.time()

            today_str = now.strftime("%Y-%m-%d")

            # Reset the daily nudge flag at midnight
            if self._last_nudge_date != today_str:
                self._sleep_nudge_fired_today = False
                self._last_nudge_date = today_str

            # Fire nudge if it's past the user's sleep time and we haven't nudged today
            if not self._sleep_nudge_fired_today and current_time >= sleep_time:
                minutes_past = (
                    (now.hour - hour) * 60 + (now.minute - minute)
                )
                msg = (
                    f"[TIME NUDGE — speak this aloud] It's {now.strftime('%I:%M %p')} — "
                    f"about {minutes_past} minutes past your usual wind-down time. "
                    "Gently remind the user it might be time to wrap up and get some rest."
                )
                await self._fire("nudge_sleep", msg, now)
                self._sleep_nudge_fired_today = True
        except Exception as e:
            logger.debug(f"Time nudge check failed: {e}")

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _can_fire(self, alert_type: str, now: datetime) -> bool:
        last = self._last_alerts.get(alert_type)
        if last is None:
            return True
        elapsed = (now - last).total_seconds()
        return elapsed >= COOLDOWNS.get(alert_type, 120)

    async def _fire(self, alert_type: str, message: str, now: datetime):
        logger.info(f"[MonitoringEngine] Queueing alert: {alert_type}")
        self._last_alerts[alert_type] = now
        self._alert_times.append(now.timestamp())
        try:
            if self._alert_queue.full():
                try:
                    self._alert_queue.get_nowait()  # drop oldest
                    self._alert_queue.task_done()
                    logger.debug(f"Queue full — dropped oldest to make room for {alert_type}")
                except asyncio.QueueEmpty:
                    pass
            self._alert_queue.put_nowait((alert_type, message))
        except Exception as e:
            logger.debug(f"Failed to queue alert {alert_type}: {e}")
