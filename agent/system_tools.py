from typing import List, Dict, Any, Optional
import core.system_ops as ops

def check_ram() -> str:
    """
    Checks the current system RAM (Memory) usage. 
    Returns a string detailing total, available, and used memory in GB, and the percentage used.
    Use this when the user asks about system memory, or before opening heavy applications.
    """
    try:
        data = ops.get_memory_usage()
        return f"RAM Usage: {data['used_gb']}GB / {data['total_gb']}GB ({data['percent_used']}% used). Available: {data['available_gb']}GB."
    except Exception as e:
        return f"Error checking RAM: {str(e)}"

def check_cpu() -> str:
    """
    Checks the current system CPU utilization.
    Returns a string percentage (e.g., '14.5%').
    Use this to determine if the processor is currently under heavy load.
    """
    try:
        data = ops.get_cpu_usage(interval=1)
        return f"CPU Utilization: {data}%"
    except Exception as e:
        return f"Error checking CPU: {str(e)}"

def check_storage(path: str = '/') -> str:
    """
    Checks the current disk space availability on the system.
    Args:
        path (str): The mount point to check. Defaults to '/' (root).
    Returns a string detailing total, used, and free space in GB.
    """
    try:
        data = ops.get_storage_info(path)
        if 'error' in data:
            return f"Error checking storage for path '{path}': {data['error']}"
        return f"Storage ({path}): {data['used_gb']}GB used of {data['total_gb']}GB total. {data['free_gb']}GB available ({data['percent_used']}% used)."
    except Exception as e:
         return f"Error checking storage: {str(e)}"

def check_temperature() -> str:
    """
    Checks the system hardware temperature sensors.
    Returns a formatted string of the current temperatures of various components.
    """
    try:
        data = ops.get_temperature()
        if data.get('status') != 'success':
            return data.get('message', 'Unknown temperature error.')
        
        output = ["System Temperatures:"]
        for sensor_name, entries in data.get('data', {}).items():
            for entry in entries:
                label = f" ({entry['label']})" if entry['label'] != "N/A" else ""
                output.append(f"  - {sensor_name}{label}: {entry['current']}°C (High: {entry['high']}°C, Critical: {entry['critical']}°C)")
        return "\n".join(output)
    except Exception as e:
        return f"Error checking temperature: {str(e)}"

def get_heavy_processes(sort_by: str = 'memory', limit: int = 5) -> str:
    """
    Retrieves a list of the most resource-intensive applications currently running.
    Multi-process applications (like browsers) are grouped together under their name.
    Args:
        sort_by (str): How to sort the processes. Must be either 'memory' or 'cpu'. Default is 'memory'.
        limit (int): The maximum number of processes to return. Default is 5.
    Returns a formatted list of applications with their Name, process counts/PIDs, RAM, and CPU usage.
    """
    try:
        if sort_by not in ['memory', 'cpu']:
            return "Error: sort_by must be 'memory' or 'cpu'."
            
        procs = ops.list_heavy_processes(sort_by=sort_by, limit=limit)
        if not procs:
            return "No processes found or unable to read process list."
            
        output = [f"Top {limit} Applications by {sort_by.upper()}:"]
        for p in procs:
             pid_str = f"PID {p['pids'][0]}" if len(p['pids']) == 1 else f"{len(p['pids'])} instances"
             output.append(f"  - {p['name']} ({pid_str}) (RAM: {p['memory_mb']}MB, CPU: {p['cpu_percent']}%)")
        return "\n".join(output)
    except Exception as e:
         return f"Error listing processes: {str(e)}"

def terminate_process(target: str) -> str:
    """
    Attempts to kill a specific process. You can provide either the exact process Name (to kill all instances) or a numeric PID.
    DANGEROUS: Always confirm with the user before using this tool, unless they explicitly asked you to kill a specific process.
    Args:
        target (str): The exact process Name (e.g., 'firefox') or an integer PID to terminate.
    """
    try:
        if target.strip().isdigit():
            result = ops.kill_process(int(target.strip()))
        else:
            result = ops.kill_process_by_name(target.strip())
            
        prefix = "SUCCESS" if result['status'] == 'success' else "WARNING" if result['status'] == 'warning' else "ERROR"
        return f"[{prefix}]: {result['message']}"
    except Exception as e:
        return f"[ERROR]: Failed to execute terminate_process tool: {str(e)}"
