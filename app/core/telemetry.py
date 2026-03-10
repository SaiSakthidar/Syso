import psutil
import subprocess
import sys
from typing import Dict, Any, List
from shared.schemas import SystemMetricsData


class TelemetryMonitor:
    def __init__(self):
        # Prevent initial 0.0 reading for CPU
        psutil.cpu_percent()

    def get_current_metrics(self) -> SystemMetricsData:
        """Collects high-level system metrics."""
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        return SystemMetricsData(
            cpu_percent=cpu,
            memory_percent=mem.percent,
            disk_percent=disk.percent,
            active_window=self.get_active_window(),
            top_processes=self.get_top_processes(limit=5),
        )

    def get_active_window(self) -> str:
        """Gets the active foreground window title based on OS."""
        try:
            if sys.platform == "linux":
                result = subprocess.run(["xdotool", "getactivewindow", "getwindowname"], capture_output=True, text=True, timeout=1)
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
            # Can add Windows/Mac support here later
            return "Unknown"
        except Exception:
            return "Unknown"

    def get_top_processes(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Gets processes sorted by memory usage."""
        processes = []
        for proc in psutil.process_iter(
            ["pid", "name", "memory_percent", "cpu_percent"]
        ):
            try:
                pinfo = proc.info
                # Some processes might return None for memory_percent
                if pinfo.get("memory_percent") is not None:
                    processes.append(pinfo)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        # Sort by memory usage
        processes = sorted(
            processes, key=lambda p: p["memory_percent"] or 0, reverse=True
        )
        return processes[:limit]


telemetry = TelemetryMonitor()
