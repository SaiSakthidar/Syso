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
    "cpu_high":         180,   # 3 min
    "cpu_temp":         120,   # 2 min
    "ram_warning":      120,
    "ram_critical":     30,
    "disk_low":         300,   # 5 min
    "battery_low":      120,
    "battery_critical": 30,
    "better_wifi":      300,   # 5 min
    "nudge_sleep":      1800,  # 30 min — only nag twice per hour max
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

    async def run(self):
        """Main monitoring loop — runs until cancelled."""
        logger.info("Monitoring Engine started.")
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                logger.info("Monitoring Engine stopped.")
                return
            except Exception as e:
                logger.error(f"Monitoring Engine error: {e}", exc_info=True)
            await asyncio.sleep(POLL_INTERVAL)

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
        logger.info(f"[MonitoringEngine] Firing alert: {alert_type}")
        self._last_alerts[alert_type] = now
        await self.orchestrator.push_alert(message)
