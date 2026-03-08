def get_system_health():
    """Returns the current CPU, RAM, and Network state of the user's system."""
    pass

def get_desktop_picture():
    """Takes a screenshot of the user's desktop and returns it for analysis."""
    pass

def get_all_process_and_resource_usage():
    """Returns a list of the top resource-heavy processes running on the user's system."""
    pass

def terminate_process(pid: int):
    """Safely kills a specific process by its PID.
    
    Args:
        pid: The process ID to terminate.
    """
    pass

def set_focus_environment(dark_mode: bool, dnd: bool, close_distracting_apps: bool):
    """Sets a focus environment on the user's system by enabling dark mode, DND, or closing distractions.
    
    Args:
        dark_mode: Whether to enable dark mode.
        dnd: Whether to enable Do Not Disturb.
        close_distracting_apps: Whether to close distracting applications.
    """
    pass

def restart_graphics_server():
    """Securely restarts the user's graphics service/driver."""
    pass

def get_system_logs(lines: int):
    """Parses and returns recent OS logs to check for errors.
    
    Args:
        lines: The number of recent log lines to fetch.
    """
    pass

def disk_usage_scan():
    """Scans the disk and returns a list of large files/directories taking up space."""
    pass

def cleanup_disk():
    """Cleans up temporary files on the user's disk to free up space."""
    pass

def manage_browser_tabs(browser: str, action: str):
    """Manages browser tabs to free up resources.
    
    Args:
        browser: The name of the browser (e.g., 'chrome', 'firefox').
        action: The action to perform ('suspend', 'kill').
    """
    pass

def manage_background_services(service_name: str, action: str):
    """Stops or restarts a background service on the user's system.
    
    Args:
        service_name: The name of the service to manage.
        action: The action to perform ('stop', 'restart').
    """
    pass


# Export the list of tool definitions for Gemini
system_tools = [
    get_system_health,
    get_desktop_picture,
    get_all_process_and_resource_usage,
    terminate_process,
    set_focus_environment,
    restart_graphics_server,
    get_system_logs,
    disk_usage_scan,
    cleanup_disk,
    manage_browser_tabs,
    manage_background_services
]
