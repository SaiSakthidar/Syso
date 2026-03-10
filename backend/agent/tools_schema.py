"""
Tool declarations for Gemini. These are explicit FunctionDeclaration objects
that tell the model what tools it has access to. The actual tool implementations
live on the frontend (app/core/tools.py) and are executed there.
"""
from google.genai import types

system_tools = [
    types.Tool(function_declarations=[
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
                    "pid": types.Schema(type="INTEGER", description="The process ID to terminate."),
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
                    "dark_mode": types.Schema(type="BOOLEAN", description="Whether to enable dark mode."),
                    "dnd": types.Schema(type="BOOLEAN", description="Whether to enable Do Not Disturb."),
                    "close_distracting_apps": types.Schema(type="BOOLEAN", description="Whether to close distracting applications."),
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
                    "lines": types.Schema(type="INTEGER", description="The number of recent log lines to fetch."),
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
                    "browser": types.Schema(type="STRING", description="The name of the browser (e.g., 'chrome', 'firefox')."),
                    "action": types.Schema(type="STRING", description="The action to perform: 'suspend' or 'kill'."),
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
                    "service_name": types.Schema(type="STRING", description="The name of the service to manage."),
                    "action": types.Schema(type="STRING", description="The action to perform: 'stop' or 'restart'."),
                },
                required=["service_name", "action"],
            ),
        ),
    ])
]
