"""
Tier 3: Semantic/Profile Memory - User Preferences and Habits.

This module manages user_profile.json, which stores:
- Direct user preferences (e.g., "never_close Spotify")
- Learned preferences from promoted Tier 2 events
- Auto-shutdown times, theme preferences, etc.
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime


class MemoryTier3:
    """
    User Profile Manager for semantic and preference memory.
    """

    def __init__(self, profile_path: str = "data/user_profile.json"):
        """
        Initialize or load user profile.

        Args:
            profile_path: Path to user_profile.json
        """
        self.profile_path = Path(profile_path)
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)

        # Load or create default profile
        if self.profile_path.exists():
            with open(self.profile_path, "r") as f:
                self.profile = json.load(f)
        else:
            self.profile = self._create_default_profile()
            self.save()

    def _create_default_profile(self) -> Dict[str, Any]:
        """
        Create default empty user profile structure.

        Returns:
            Default profile dict
        """
        return {
            "user_id": "user_0",
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "preferences": {
                "never_kill": [],  # Apps never to close
                "auto_actions": {},  # Auto-actions (e.g., close Chrome on high RAM)
                "theme": "light",
                "auto_shutdown_time": None,
            },
            "learned_behaviors": [],  # From promoted Tier 2 events
            "blacklist": [],  # Suggestions never to show again
        }

    def save(self) -> None:
        """
        Save profile to disk.
        """
        self.profile["last_updated"] = datetime.now().isoformat()
        with open(self.profile_path, "w") as f:
            json.dump(self.profile, f, indent=2)

    def add_preference(self, key: str, value: Any) -> Dict[str, str]:
        """
        Add a direct user preference.

        Args:
            key: Preference key (e.g., "never_kill")
            value: Preference value

        Returns:
            Status dict
        """
        if key in self.profile["preferences"]:
            self.profile["preferences"][key] = value
            self.save()
            return {"status": "success", "message": f"Preference '{key}' updated"}
        return {"status": "error", "message": f"Unknown preference key '{key}'"}

    def add_learned_behavior(
        self, event_type: str, suggestion: str, context: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        Add a learned behavior from promoted Tier 2 event.

        Args:
            event_type: Type of event (high_ram_usage, etc.)
            suggestion: The suggested action
            context: Additional context from the event

        Returns:
            Status dict
        """
        behavior = {
            "event_type": event_type,
            "suggestion": suggestion,
            "context": context,
            "added_at": datetime.now().isoformat(),
        }

        self.profile["learned_behaviors"].append(behavior)
        self.save()
        return {"status": "success", "message": f"Learned: {event_type} → {suggestion}"}

    def add_to_blacklist(self, event_type: str, suggestion: str) -> Dict[str, str]:
        """
        Add a suggestion to the blacklist (never suggest again).

        Args:
            event_type: Type of event
            suggestion: Suggestion to blacklist

        Returns:
            Status dict
        """
        blacklist_item = {
            "event_type": event_type,
            "suggestion": suggestion,
            "added_at": datetime.now().isoformat(),
        }

        self.profile["blacklist"].append(blacklist_item)
        self.save()
        return {
            "status": "success",
            "message": f"Blacklisted: {event_type} → {suggestion}",
        }

    def get_profile(self) -> Dict[str, Any]:
        """
        Get full user profile.

        Returns:
            User profile dict
        """
        return self.profile

    def get_preference(self, key: str) -> Optional[Any]:
        """
        Get a specific preference value.

        Args:
            key: Preference key

        Returns:
            Preference value or None
        """
        return self.profile["preferences"].get(key)

    def get_learned_behaviors(self) -> List[Dict[str, Any]]:
        """
        Get all learned behaviors.

        Returns:
            List of learned behaviors
        """
        return self.profile["learned_behaviors"]

    def get_blacklist(self) -> List[Dict[str, Any]]:
        """
        Get all blacklisted suggestions.

        Returns:
            List of blacklisted items
        """
        return self.profile["blacklist"]


if __name__ == "__main__":
    # Example usage
    tier3 = MemoryTier3()

    # Add direct preference
    tier3.add_preference("never_kill", ["Spotify", "Discord"])
    tier3.add_preference("theme", "dark")

    # Add learned behavior
    tier3.add_learned_behavior(
        event_type="high_ram_usage",
        suggestion="close_chrome_tabs",
        context={"success_rate": 0.9, "avg_ram_freed_gb": 5.2},
    )

    # Add to blacklist
    tier3.add_to_blacklist("battery_low", "force_shutdown")

    # Print profile
    profile = tier3.get_profile()
    print(json.dumps(profile, indent=2))
