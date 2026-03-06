import os
import psutil
from typing import List, Dict, Any, Optional

def get_memory_usage() -> Dict[str, float]:
    """Retrieves current RAM usage statistics."""
    mem = psutil.virtual_memory()
    return {
        "total_gb": round(mem.total / (1024**3), 2),
        "available_gb": round(mem.available / (1024**3), 2),
        "used_gb": round(mem.used / (1024**3), 2),
        "percent_used": mem.percent
    }

def get_cpu_usage(interval: int = 1) -> float:
    """Retrieves current CPU utilization percentage."""
    return psutil.cpu_percent(interval=interval)

def get_storage_info(path: str = '/') -> Dict[str, float]:
    """Retrieves disk space statistics for the given path."""
    try:
        usage = psutil.disk_usage(path)
        return {
            "total_gb": round(usage.total / (1024**3), 2),
            "used_gb": round(usage.used / (1024**3), 2),
            "free_gb": round(usage.free / (1024**3), 2),
            "percent_used": usage.percent
        }
    except Exception as e:
        return {"error": str(e)}

def get_temperature() -> Dict[str, Any]:
    """Retrieves system temperature statistics (if supported by OS/Hardware)."""
    try:
        temps = psutil.sensors_temperatures()
        if not temps:
            return {"status": "unsupported", "message": "Temperature sensors not accessible or not supported on this device."}
        
        result = {}
        for name, entries in temps.items():
            result[name] = [{"label": entry.label or "N/A", "current": entry.current, "high": entry.high, "critical": entry.critical} for entry in entries]
        return {"status": "success", "data": result}
    except Exception as e:
         return {"status": "error", "message": str(e)}

def list_heavy_processes(sort_by: str = 'memory', limit: int = 5) -> List[Dict[str, Any]]:
    """
    Returns a list of running processes sorted by either 'memory' or 'cpu'.
    Processes with the same name are aggregated together to concisely group multi-process applications (like browsers).
    """
    processes_dict = {}
    for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent']):
        try:
            info = proc.info
            name = info['name']
            cpu = info.get('cpu_percent') or 0.0
            mem_mb = (info.get('memory_info').rss / (1024**2)) if info.get('memory_info') else 0.0
            
            if name not in processes_dict:
                processes_dict[name] = {
                    "name": name,
                    "memory_mb": 0.0,
                    "cpu_percent": 0.0,
                    "pids": []
                }
            processes_dict[name]["memory_mb"] += mem_mb
            processes_dict[name]["cpu_percent"] += cpu
            processes_dict[name]["pids"].append(info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    processes = list(processes_dict.values())
    for p in processes:
        p["memory_mb"] = round(p["memory_mb"], 2)
        p["cpu_percent"] = round(p["cpu_percent"], 1)

    if sort_by.lower() == 'cpu':
        processes.sort(key=lambda p: p['cpu_percent'], reverse=True)
    else:
        processes.sort(key=lambda p: p['memory_mb'], reverse=True)

    return processes[:limit]

def kill_process(pid: int) -> Dict[str, str]:
    """
    Attempts to terminate a specific process safely.
    Includes basic safety checks to prevent terminating critical system PIDs (like init/systemd).
    """
    if pid <= 1:
            return {"status": "error", "message": f"Cannot kill critical system process with PID {pid}."}
    try:
        p = psutil.Process(pid)
        name = p.name()
        
        
        p.terminate()
        p.wait(timeout=3)
        return {"status": "success", "message": f"Successfully terminated process '{name}' (PID {pid})."}
    except psutil.NoSuchProcess:
        return {"status": "error", "message": f"No process found with PID {pid}."}
    except psutil.AccessDenied:
        return {"status": "error", "message": f"Permission denied to kill PID {pid}. (May require root)."}
    except psutil.TimeoutExpired:
        
        try:
           p.kill()
           return {"status": "warning", "message": f"Process {pid} did not terminate gracefully. Used SIGKILL."}
        except Exception as e:
           return {"status": "error", "message": f"Failed to force kill PID {pid}: {str(e)}"}
    except Exception as e:
         return {"status": "error", "message": f"Unexpected error killing PID {pid}: {str(e)}"}

def kill_process_by_name(name: str) -> Dict[str, str]:
    """
    Attempts to terminate all processes matching exactly the given name.
    """
    killed_count = 0
    errors = []
    
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if proc.info['name'] == name:
                pid = proc.info['pid']
                if pid <= 1: continue
                proc.terminate()
                killed_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
            errors.append(str(e))
    
    if killed_count == 0:
        return {"status": "error", "message": f"No processes named '{name}' were terminated. Errors: {errors}"}
        
    return {"status": "success", "message": f"Attempted termination on {killed_count} processes named '{name}'."}
