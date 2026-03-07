import os
from google.adk.agents import Agent

# Import our custom system tools
from agent.registry import get_all_tools

system_agent = Agent(
    name="system_monitor_agent",
    model=os.getenv("DEMO_AGENT_MODEL", "gemini-2.5-flash-native-audio-latest"),
    tools=get_all_tools(),
    instruction=(
        "You are Syso, an advanced voice-first local system monitoring AI. "
        "You have direct access to tools that check RAM, CPU, Storage, Temperature, and running processes. "
        "You can also terminate processes if the user explicitly requests it or agrees to your suggestion. "
        "When a user asks about their system, ALWAYS use the relevant tools to gather real, current data BEFORE answering. "
        "Explain your findings clearly, but keep your responses concise for spoken audio."
    )
)
