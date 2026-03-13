"""
Tool declarations for Gemini. These are explicit FunctionDeclaration objects
that tell the model what tools it has access to. The actual tool implementations
live on the frontend (app/core/tools.py) and are executed there.
"""

from google.genai import types

system_tools = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="get_system_health",
                description="Returns the current CPU, RAM, disk usage, and network state of the user's system.",
            ),
            types.FunctionDeclaration(
                name="get_desktop_picture",
                description=(
                    "Takes a screenshot of the user's desktop and returns it as an image for visual analysis. "
                    "Use this whenever the user asks what is on their screen, wants you to see something, "
                    "or when visual context would help answer their question."
                ),
            ),
            types.FunctionDeclaration(
                name="get_all_process_and_resource_usage",
                description="Returns a list of the top resource-heavy processes running on the user's system, including PID, name, CPU%, and memory%.",
            ),
            types.FunctionDeclaration(
                name="terminate_process",
                description="Safely kills a specific process by its PID.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "pid": types.Schema(
                            type="INTEGER", description="The process ID to terminate."
                        ),
                    },
                    required=["pid"],
                ),
            ),
            types.FunctionDeclaration(
                name="set_focus_environment",
                description="Sets a focus/study environment on the user's system by enabling dark mode, Do Not Disturb, or closing distracting applications like Spotify, Discord, Slack.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "dark_mode": types.Schema(
                            type="BOOLEAN", description="Whether to enable dark mode."
                        ),
                        "dnd": types.Schema(
                            type="BOOLEAN",
                            description="Whether to enable Do Not Disturb.",
                        ),
                        "close_distracting_apps": types.Schema(
                            type="BOOLEAN",
                            description="Whether to close distracting applications.",
                        ),
                    },
                    required=["dark_mode", "dnd", "close_distracting_apps"],
                ),
            ),
            types.FunctionDeclaration(
                name="restart_graphics_server",
                description="Securely restarts the user's graphics service/driver (X11 or Wayland).",
            ),
            types.FunctionDeclaration(
                name="get_system_logs",
                description="Parses and returns recent OS logs (journalctl) to check for errors or warnings.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "lines": types.Schema(
                            type="INTEGER",
                            description="The number of recent log lines to fetch.",
                        ),
                    },
                    required=["lines"],
                ),
            ),
            types.FunctionDeclaration(
                name="disk_usage_scan",
                description="Scans the disk and returns a list of large files/directories (>100MB) in the Downloads folder.",
            ),
            types.FunctionDeclaration(
                name="cleanup_disk",
                description="Cleans up temporary files (cache, thumbnails) on the user's disk to free up space.",
            ),
            types.FunctionDeclaration(
                name="manage_browser_tabs",
                description="Manages browser tabs to free up resources by suspending or killing browser processes.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "browser": types.Schema(
                            type="STRING",
                            description="The name of the browser (e.g., 'chrome', 'firefox').",
                        ),
                        "action": types.Schema(
                            type="STRING",
                            description="The action to perform: 'suspend' or 'kill'.",
                        ),
                    },
                    required=["browser", "action"],
                ),
            ),
            types.FunctionDeclaration(
                name="manage_background_services",
                description="Stops or restarts a background systemd service on the user's system.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "service_name": types.Schema(
                            type="STRING",
                            description="The name of the service to manage.",
                        ),
                        "action": types.Schema(
                            type="STRING",
                            description="The action to perform: 'stop' or 'restart'.",
                        ),
                    },
                    required=["service_name", "action"],
                ),
            ),
            types.FunctionDeclaration(
                name="set_system_volume",
                description="Sets the master audio volume on the user's system.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "percent": types.Schema(
                            type="INTEGER",
                            description="The volume level to set (0-100).",
                        ),
                    },
                    required=["percent"],
                ),
            ),
            types.FunctionDeclaration(
                name="set_system_brightness",
                description="Sets the screen brightness on the user's system.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "percent": types.Schema(
                            type="INTEGER",
                            description="The brightness level to set (0-100).",
                        ),
                    },
                    required=["percent"],
                ),
            ),
            types.FunctionDeclaration(
                name="set_system_theme",
                description="Sets the system-wide visual theme to either 'dark' or 'light'.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "theme": types.Schema(
                            type="STRING",
                            description="The theme mode to apply: 'dark' or 'light'.",
                        ),
                    },
                    required=["theme"],
                ),
            ),
            types.FunctionDeclaration(
                name="manage_wifi",
                description="Turns the Wi-Fi adapter on or off.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "action": types.Schema(
                            type="STRING",
                            description="The desired Wi-Fi state: 'on' or 'off'.",
                        ),
                    },
                    required=["action"],
                ),
            ),
            types.FunctionDeclaration(
                name="manage_bluetooth",
                description="Turns the Bluetooth adapter on or off.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "action": types.Schema(
                            type="STRING",
                            description="The desired Bluetooth state: 'on' or 'off'.",
                        ),
                    },
                    required=["action"],
                ),
            ),
            types.FunctionDeclaration(
                name="set_dnd_mode",
                description=(
                    "Enables or disables GNOME Do Not Disturb mode, which suppresses "
                    "notification pop-ups. Use during meetings or focus sessions."
                ),
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "action": types.Schema(
                            type="STRING",
                            description="'on' to enable DND (suppress notifications), 'off' to disable it.",
                        ),
                    },
                    required=["action"],
                ),
            ),
            types.FunctionDeclaration(
                name="detect_active_meeting",
                description=(
                    "Checks whether a video-conferencing meeting is currently active "
                    "(Google Meet, Zoom, Teams, Webex, etc.) by scanning open window titles."
                ),
                parameters=types.Schema(
                    type="OBJECT",
                    properties={},
                ),
            ),
            types.FunctionDeclaration(
                name="get_battery_status",
                description=(
                    "Returns the current battery level (%), whether it is plugged in/charging, "
                    "and estimated time remaining. Returns a message if no battery is detected (e.g. desktop)."
                ),
                parameters=types.Schema(
                    type="OBJECT",
                    properties={},
                ),
            ),
            types.FunctionDeclaration(
                name="show_system_dashboard",
                description=(
                    "Opens a full-screen real-time system status dashboard in the UI, "
                    "showing CPU, RAM, disk, battery, network I/O, and top processes. "
                    "Call this when the user asks to 'show system status', 'show metrics', "
                    "'open dashboard', or similar."
                ),
                parameters=types.Schema(
                    type="OBJECT",
                    properties={},
                ),
            ),
        ]
    )
]
