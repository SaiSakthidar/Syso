import psutil
import subprocess
import io
import os
import sys
from PIL import ImageGrab
from typing import Dict, Any
from app.core.telemetry import TelemetryMonitor

telemetry = TelemetryMonitor()


def get_system_health() -> Dict[str, Any]:
    metrics = telemetry.get_current_metrics()
    return metrics.model_dump()


def get_desktop_picture() -> Dict[str, Any]:
    try:
        # Take screenshot
        screenshot = ImageGrab.grab()
        # Resize to save bandwidth
        screenshot.thumbnail((1280, 720))

        byte_stream = io.BytesIO()
        screenshot.save(byte_stream, format="JPEG", quality=70)
        img_bytes = byte_stream.getvalue()

        # Let's return the actual bytes along with the success message
        return {
            "status": "success",
            "message": "Screenshot grabbed.",
            "image_bytes": img_bytes,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Screenshot failed: {e}. Note: Wayland may block this.",
        }


def get_all_process_and_resource_usage() -> Dict[str, Any]:
    return {"status": "success", "processes": telemetry.get_top_processes(limit=15)}


def terminate_process(pid: int) -> Dict[str, Any]:
    try:
        proc = psutil.Process(pid)
        name = proc.name()
        proc.terminate()
        return {"status": "success", "message": f"Terminated {name} (PID {pid})"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def set_focus_environment(
    dark_mode: bool, dnd: bool, close_distracting_apps: bool
) -> Dict[str, Any]:
    # Cross platform environment setting
    actions_taken = []

    # 1. Dark Mode
    if dark_mode:
        if sys.platform == "win32":
            try:
                subprocess.run(
                    [
                        "powershell",
                        "-Command",
                        "Set-ItemProperty -Path HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize -Name AppsUseLightTheme -Value 0",
                    ],
                    check=True,
                )
                actions_taken.append("Enabled Windows Dark Mode")
            except Exception:
                pass
        elif sys.platform == "darwin":
            try:
                subprocess.run(
                    [
                        "osascript",
                        "-e",
                        'tell app "System Events" to tell appearance preferences to set dark mode to true',
                    ],
                    check=True,
                )
                actions_taken.append("Enabled macOS Dark Mode")
            except Exception:
                pass
        elif sys.platform == "linux":
            try:
                subprocess.run(
                    [
                        "gsettings",
                        "set",
                        "org.gnome.desktop.interface",
                        "color-scheme",
                        "'prefer-dark'",
                    ],
                    check=True,
                )
                actions_taken.append("Enabled GNOME Dark Mode")
            except Exception:
                pass

    # 2. DND
    if dnd:
        if sys.platform == "darwin":
            # Very hacky on macos, requires focus modes. Skipping complex implementation.
            actions_taken.append("[Skipped] DND on macOS")
        elif sys.platform == "linux":
            try:
                subprocess.run(
                    [
                        "gsettings",
                        "set",
                        "org.gnome.desktop.notifications",
                        "show-banners",
                        "false",
                    ],
                    check=True,
                )
                actions_taken.append("Enabled GNOME Do Not Disturb")
            except Exception:
                pass

    # 3. Close distractions
    if close_distracting_apps:
        distractions = ["spotify", "discord", "telegram-desktop", "slack"]
        killed = []
        for p in psutil.process_iter(["pid", "name"]):
            if p.info["name"] and any(
                d in p.info["name"].lower() for d in distractions
            ):
                try:
                    psutil.Process(p.info["pid"]).terminate()
                    killed.append(p.info["name"])
                except Exception:
                    pass
        actions_taken.append(
            f"Closed distracting apps: {', '.join(killed) if killed else 'None found'}"
        )

    return {"status": "success", "actions_taken": actions_taken}


def restart_graphics_server() -> Dict[str, Any]:
    return {
        "status": "error",
        "message": "Denied. Restarting X11/Wayland remotely drops the websocket and kills the GUI.",
    }


def get_system_logs(lines: int = 50) -> Dict[str, Any]:
    try:
        result = subprocess.run(
            ["journalctl", "-n", str(lines), "--no-pager"],
            capture_output=True,
            text=True,
        )
        return {"status": "success", "logs": result.stdout}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def disk_usage_scan() -> Dict[str, Any]:
    home = os.path.expanduser("~")
    # Just list some large files in Downloads
    downloads = os.path.join(home, "Downloads")
    large_files = []
    if os.path.exists(downloads):
        for f in os.listdir(downloads):
            path = os.path.join(downloads, f)
            if (
                os.path.isfile(path) and os.path.getsize(path) > 100 * 1024 * 1024
            ):  # >100MB
                large_files.append(
                    {
                        "name": f,
                        "size_mb": round(os.path.getsize(path) / (1024 * 1024), 2),
                    }
                )
    return {"status": "success", "large_items_in_downloads": large_files}


def cleanup_disk() -> Dict[str, Any]:
    # Very safe mock
    return {"status": "success", "message": "Emptied ~/.cache/thumbnails/ (Mocked)"}


def manage_browser_tabs(browser: str, action: str) -> Dict[str, Any]:
    # Finding browser processes
    browser_procs = []
    for p in psutil.process_iter(["pid", "name"]):
        if p.info["name"] and browser.lower() in p.info["name"].lower():
            browser_procs.append(p)

    if not browser_procs:
        return {"status": "error", "message": f"{browser} not found running."}

    if action == "kill":
        for p in browser_procs:
            try:
                p.terminate()
            except:
                pass
        return {
            "status": "success",
            "message": f"Killed {len(browser_procs)} {browser} processes.",
        }
    else:
        # psutil suspend
        for p in browser_procs:
            try:
                p.suspend()
            except:
                pass
        return {
            "status": "success",
            "message": f"Suspended {len(browser_procs)} {browser} processes.",
        }


def manage_background_services(service_name: str, action: str) -> Dict[str, Any]:
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["sc", action, service_name], check=True, capture_output=True
            )
        elif sys.platform == "darwin":
            # For mac, it depends heavily on launchctl syntax which is complex. Mocking.
            return {
                "status": "error",
                "message": f"Service management on Mac requires root launchctl.",
            }
        elif sys.platform == "linux":
            subprocess.run(
                ["systemctl", "--user", action, service_name],
                check=True,
                capture_output=True,
            )
        return {"status": "success", "message": f"Service {service_name} {action}ed."}
    except subprocess.CalledProcessError as e:
        return {
            "status": "error",
            "message": f"Failed to {action} {service_name}: {e.stderr.decode()}",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def set_system_volume(percent: int) -> Dict[str, Any]:
    if sys.platform != "linux":
        return {
            "status": "error",
            "message": "Volume control is currently only supported on Linux/Ubuntu.",
        }
    try:
        # Using amixer to set pulse volume
        subprocess.run(
            ["amixer", "-D", "pulse", "sset", "Master", f"{percent}%"],
            check=True,
            capture_output=True,
        )
        return {"status": "success", "message": f"Volume set to {percent}%"}
    except subprocess.CalledProcessError as e:
        return {
            "status": "error",
            "message": f"Failed to set volume: {e.stderr.decode()}",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def set_system_brightness(percent: int) -> Dict[str, Any]:
    if sys.platform != "linux":
        return {
            "status": "error",
            "message": "Brightness control is currently only supported on Linux/Ubuntu.",
        }
    try:
        # Use native GNOME dbus which doesn't require sudo or external packages
        subprocess.run(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                "org.gnome.SettingsDaemon.Power",
                "--object-path",
                "/org/gnome/SettingsDaemon/Power",
                "--method",
                "org.freedesktop.DBus.Properties.Set",
                "org.gnome.SettingsDaemon.Power.Screen",
                "Brightness",
                f"<int32 {percent}>",
            ],
            check=True,
            capture_output=True,
        )
        return {"status": "success", "message": f"Brightness set to {percent}%"}
    except subprocess.CalledProcessError as e:
        return {
            "status": "error",
            "message": f"Failed to set brightness via dbus: {e.stderr.decode()}",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def set_system_theme(theme: str) -> Dict[str, Any]:
    if sys.platform != "linux":
        return {
            "status": "error",
            "message": "Theme control is currently only supported on Linux/Ubuntu.",
        }
    try:
        scheme = "'prefer-dark'" if theme.lower() == "dark" else "'default'"
        subprocess.run(
            ["gsettings", "set", "org.gnome.desktop.interface", "color-scheme", scheme],
            check=True,
            capture_output=True,
        )
        return {"status": "success", "message": f"System theme set to {theme} mode."}
    except subprocess.CalledProcessError as e:
        return {
            "status": "error",
            "message": f"Failed to set theme: {e.stderr.decode()}",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def manage_wifi(action: str) -> Dict[str, Any]:
    if sys.platform != "linux":
        return {
            "status": "error",
            "message": "Wi-Fi control is currently only supported on Linux/Ubuntu.",
        }
    try:
        if action not in ["on", "off"]:
            return {"status": "error", "message": "Action must be 'on' or 'off'."}
        subprocess.run(
            ["nmcli", "radio", "wifi", action], check=True, capture_output=True
        )
        return {"status": "success", "message": f"Wi-Fi turned {action}."}
    except subprocess.CalledProcessError as e:
        return {
            "status": "error",
            "message": f"Failed to modify Wi-Fi state: {e.stderr.decode()}",
        }
    except FileNotFoundError:
        return {"status": "error", "message": "nmcli not found."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def manage_bluetooth(action: str) -> Dict[str, Any]:
    if sys.platform != "linux":
        return {
            "status": "error",
            "message": "Bluetooth control is currently only supported on Linux/Ubuntu.",
        }
    try:
        if action not in ["on", "off"]:
            return {"status": "error", "message": "Action must be 'on' or 'off'."}
        rfkill_action = "block" if action == "off" else "unblock"
        subprocess.run(
            ["rfkill", rfkill_action, "bluetooth"], check=True, capture_output=True
        )
        return {"status": "success", "message": f"Bluetooth turned {action}."}
    except subprocess.CalledProcessError as e:
        return {
            "status": "error",
            "message": f"Failed to modify Bluetooth state: {e.stderr.decode()}",
        }
    except FileNotFoundError:
        return {"status": "error", "message": "rfkill not found."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# Dictionary matching schema names to functions
LOCAL_TOOLS = {
    "get_system_health": get_system_health,
    "get_desktop_picture": get_desktop_picture,
    "get_all_process_and_resource_usage": get_all_process_and_resource_usage,
    "terminate_process": terminate_process,
    "set_focus_environment": set_focus_environment,
    "restart_graphics_server": restart_graphics_server,
    "get_system_logs": get_system_logs,
    "disk_usage_scan": disk_usage_scan,
    "cleanup_disk": cleanup_disk,
    "manage_browser_tabs": manage_browser_tabs,
    "manage_background_services": manage_background_services,
    "set_system_volume": set_system_volume,
    "set_system_brightness": set_system_brightness,
    "set_system_theme": set_system_theme,
    "manage_wifi": manage_wifi,
    "manage_bluetooth": manage_bluetooth,
}
