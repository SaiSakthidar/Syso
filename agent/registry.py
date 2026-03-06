from typing import Callable, List
from agent import system_tools

def get_all_tools() -> List[Callable]:
    """
    Returns a list of all available system interaction tools for the agent.
    These function references can be passed directly to an LLM framework 
    (like LangChain or LlamaIndex) which will extract their names, schemas, 
    and docstrings to create the agent's action space.
    """
    return [
        system_tools.check_ram,
        system_tools.check_cpu,
        system_tools.check_storage,
        system_tools.check_temperature,
        system_tools.get_heavy_processes,
        system_tools.terminate_process
    ]
