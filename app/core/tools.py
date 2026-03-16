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
    import tempfile, os, glob
    display = os.environ.get("DISPLAY") or ":1"
    env = {**os.environ, "DISPLAY": display}
    tmpdir = tempfile.mkdtemp(prefix="sc_wins_")

    # 1. Get all windows via wmctrl
    windows = []  # list of (win_id, title)
    try:
        wm = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True, timeout=3, env=env)
        if wm.returncode == 0:
            for line in wm.stdout.strip().splitlines():
                parts = line.split(None, 3)
                if len(parts) == 4:
                    win_id, _ws, _host, title = parts
                    # Skip system / desktop chrome
                    if any(skip in title for skip in ["Desktop Icons", "N/A", "xdg-desktop"]):
                        continue
                    windows.append((win_id, title))
    except Exception:
        pass

    # 2. Capture each window individually with ImageMagick `import -window`
    captured = []  # list of (tmpfile_path, title)
    for win_id, title in windows:
        out = os.path.join(tmpdir, f"{win_id}.jpg")
        try:
            r = subprocess.run(
                ["import", "-window", win_id, "-resize", "800x600>", "-quality", "70", out],
                capture_output=True, timeout=5, env=env,
            )
            if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 5000:
                captured.append((out, title))
        except Exception:
            pass

    # 3. If we got individual windows, montage them into one image with labels
    if captured:
        try:
            motage_args = []
            for path, title in captured:
                # ImageMagick montage -label per image
                motage_args += ["-label", title[:60], path]
            montage_out = os.path.join(tmpdir, "montage.jpg")
            cols = 2 if len(captured) > 1 else 1
            subprocess.run(
                ["montage"] + motage_args + [
                    "-tile", f"{cols}x",
                    "-geometry", "800x500+4+4",
                    "-font", "DejaVu-Sans",
                    "-pointsize", "14",
                    "-background", "#1e1e1e",
                    "-fill", "white",
                    montage_out,
                ],
                capture_output=True, timeout=15, env=env,
            )
            if os.path.exists(montage_out):
                with open(montage_out, "rb") as f:
                    img_bytes = f.read()
                titles = [t for _, t in captured]
                # Cleanup
                for f in glob.glob(os.path.join(tmpdir, "*")):
                    os.unlink(f)
                os.rmdir(tmpdir)
                return {
                    "status": "success",
                    "message": (
                        f"Captured {len(captured)} open window(s):\n"
                        + "\n".join(f"  • {t}" for t in titles)
                    ),
                    "image_bytes": img_bytes,
                }
        except Exception:
            pass

    # 4. Fallback: full desktop screenshot
    try:
        res_result = subprocess.run(
            ["xdpyinfo", "-display", display],
            capture_output=True, text=True, timeout=3, env=env,
        )
        resolution = "1920x1080"
        for line in res_result.stdout.splitlines():
            if "dimensions:" in line:
                resolution = line.strip().split()[1]
                break
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmppath = tmp.name
        r = subprocess.run(
            ["ffmpeg", "-y", "-f", "x11grab", "-video_size", resolution,
             "-i", display, "-vframes", "1", "-vf", "scale=1280:-1", "-q:v", "5", tmppath],
            capture_output=True, timeout=15, env=env,
        )
        if r.returncode == 0:
            with open(tmppath, "rb") as f:
                img_bytes = f.read()
            os.unlink(tmppath)
            titles = [t for _, t in windows]
            return {
                "status": "success",
                "message": "Desktop screenshot. Open windows:\n" + "\n".join(f"  • {t}" for t in titles),
                "image_bytes": img_bytes,
            }
        os.unlink(tmppath)
    except Exception:
        pass

    return {"status": "error", "message": f"Screenshot failed. DISPLAY={display}"}


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
    # TODO: make it cross platform
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
    
    # Attempt 1: pactl (PulseAudio/PipeWire standard)
    try:
        subprocess.run(
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"],
            check=True,
            capture_output=True,
        )
        return {"status": "success", "message": f"Volume set to {percent}% via pactl."}
    except Exception:
        pass

    # Attempt 2: wpctl (Modern PipeWire/WirePlumber)
    try:
        # wpctl uses fractional values (0.0 to 1.0)
        vol_decimal = percent / 100.0
        subprocess.run(
            ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{vol_decimal}"],
            check=True,
            capture_output=True,
        )
        return {"status": "success", "message": f"Volume set to {percent}% via wpctl."}
    except Exception:
        pass

    # Attempt 3: amixer (ALSA fallback)
    try:
        # Removed "-D pulse" which was causing 'Invalid CTL pulse' errors
        subprocess.run(
            ["amixer", "sset", "Master", f"{percent}%"],
            check=True,
            capture_output=True,
        )
        return {"status": "success", "message": f"Volume set to {percent}% via amixer."}
    except subprocess.CalledProcessError as e:
        return {
            "status": "error",
            "message": f"All volume control methods failed. Last error (amixer): {e.stderr.decode()}",
        }
    except Exception as e:
        return {"status": "error", "message": f"Unexpected error setting volume: {str(e)}"}


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



def set_dnd_mode(action: str) -> Dict[str, Any]:
    """Enable or disable GNOME Do Not Disturb (suppresses notification popups)."""
    if sys.platform != "linux":
        return {"status": "error", "message": "DND is only supported on Linux/GNOME."}
    if action not in ("on", "off"):
        return {"status": "error", "message": "Action must be 'on' or 'off'."}
    # DND = disable notification banners
    value = "false" if action == "on" else "true"
    try:
        subprocess.run(
            ["gsettings", "set", "org.gnome.desktop.notifications", "show-banners", value],
            check=True, capture_output=True,
        )
        state = "enabled" if action == "on" else "disabled"
        return {"status": "success", "message": f"Do Not Disturb {state}."}
    except subprocess.CalledProcessError as e:
        return {"status": "error", "message": f"gsettings error: {e.stderr.decode()}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def detect_active_meeting() -> Dict[str, Any]:
    """
    Detect whether a video-conferencing meeting is currently active by scanning
    open window titles for known meeting platforms (Google Meet, Zoom, Teams, etc.).
    Uses wmctrl (available by default on most Ubuntu setups).
    """
    MEETING_KEYWORDS = [
        "meet.google.com",
        "Google Meet",
        "Meet -",
        "Zoom Meeting",
        "zoom",
        "Microsoft Teams",
        "teams.microsoft.com",
        "Webex",
        "webex.com",
        "Jitsi",
        "jitsi",
        "BlueJeans",
    ]
    try:
        result = subprocess.run(
            ["wmctrl", "-l"], capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return {"status": "error", "message": "wmctrl failed."}

        windows = result.stdout.strip().split("\n")
        for line in windows:
            title_lower = line.lower()
            for keyword in MEETING_KEYWORDS:
                if keyword.lower() in title_lower:
                    return {
                        "status": "success",
                        "meeting_active": True,
                        "message": f"Active meeting detected: '{line.strip()}'",
                        "matched_keyword": keyword,
                    }
        return {"status": "success", "meeting_active": False, "message": "No active meeting detected."}
    except FileNotFoundError:
        return {"status": "error", "message": "wmctrl not found. Install with: sudo apt install wmctrl"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def show_system_dashboard() -> Dict[str, Any]:
    """Opens the full-screen system status dashboard in the UI."""
    try:
        from app.core import ui_events
        ui_events.post("show_dashboard")
        return {"status": "success", "message": "System dashboard opened."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# Dictionary matching schema names to functions
def get_battery_status() -> Dict[str, Any]:
    """Returns current battery level, charging state, and estimated time remaining."""
    try:
        import psutil
        battery = psutil.sensors_battery()
        if battery is None:
            return {"status": "success", "available": False, "message": "No battery detected (likely a desktop)."}
        secs_left = battery.secsleft
        if secs_left == psutil.POWER_TIME_UNLIMITED:
            time_left = "Charging (unlimited)"
        elif secs_left == psutil.POWER_TIME_UNKNOWN:
            time_left = "Unknown"
        else:
            hours, rem = divmod(int(secs_left), 3600)
            mins = rem // 60
            time_left = f"{hours}h {mins}m remaining"
        return {
            "status": "success",
            "available": True,
            "percent": round(battery.percent, 1),
            "plugged_in": battery.power_plugged,
            "charging": battery.power_plugged and battery.percent < 100,
            "time_left": time_left,
        }
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
    "set_dnd_mode": set_dnd_mode,
    "detect_active_meeting": detect_active_meeting,
    "get_battery_status": get_battery_status,
    "show_system_dashboard": show_system_dashboard,
}
