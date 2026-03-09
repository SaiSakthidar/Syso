"""
Tier 2: Episodic Memory System using ChromaDB for RAG-based suggestions.

This module stores and retrieves historical system events, user responses, and outcomes.
It tracks confidence scores to identify patterns for promotion to Tier 3 (User Profile).

Event Types (Currently Implemented in system_ops.py):
- high_ram_usage: RAM usage exceeds threshold
- high_cpu_usage: CPU usage exceeds threshold
- low_storage: Disk space below threshold
- high_temperature: System temperature critical
- heavy_process_detected: Individual process using excessive resources

Event Types (Future System Monitoring - Not Yet Implemented):
- brightness_change: Display brightness adjustment suggestion
- volume_change: Audio volume adjustment suggestion
- network_usage_high: Network bandwidth spike detected
- battery_low: Battery level critical
- app_hang_detected: Application became unresponsive
- disk_io_high: Disk read/write operations excessive
- memory_leak_suspected: Suspicious memory growth pattern
- background_app_suggestion: Suggest closing background apps
- theme_preference_change: Auto-suggest dark/light theme based on time
- notification_fatigue: Too many notifications suggest muting
- auto_shutdown_recommendation: Suggest scheduled shutdown
- update_available: OS or app updates available
- malware_scan_suggestion: Suggest running security scan
- defrag_recommendation: Storage optimization suggestion
- connectivity_issue: WiFi/network reliability problems
"""

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
import math

try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    chromadb = None


class MemoryTier2:
    """
    Episodic Memory Manager for system events, suggestions, and outcomes.
    """

    def __init__(self, db_path: str = "data/chroma_db"):
        """
        Initialize ChromaDB client and create/load collection.

        Args:
            db_path: Path to ChromaDB persistence directory
        """
        if chromadb is None:
            raise ImportError(
                "ChromaDB not installed. Run: pip install chromadb"
            )

        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB with persistence
        settings = Settings(
            chroma_db_impl="duckdb+parquet",
            persist_directory=str(self.db_path),
            anonymized_telemetry=False,
        )
        self.client = chromadb.Client(settings)

        # Create or load collection
        self.collection = self.client.get_or_create_collection(
            name="system_events",
            metadata={"hnsw:space": "cosine"}
        )

    def create_event(
        self,
        event_type: str,
        system_state: Dict[str, Any],
        suggestion: str,
        suggestion_context: str,
    ) -> str:
        """
        Create and store a new episodic memory event.

        Args:
            event_type: Type of event (high_ram_usage, high_cpu_usage, etc.)
            system_state: Snapshot of CPU, RAM, processes, storage, temperature
            suggestion: Action suggested by agent (e.g., "close_chrome_tabs")
            suggestion_context: Human-readable context (e.g., "Chrome using 80% RAM")

        Returns:
            Event ID (UUID)
        """
        event_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        event = {
            "id": event_id,
            "timestamp": timestamp,
            "event_type": event_type,
            "system_state": system_state,
            "suggestion": suggestion,
            "suggestion_context": suggestion_context,
            "accepted_count": 0,
            "rejected_count": 0,
            "total_shown": 0,
            "confidence_score": 0.0,
            "promotion_status": "pending",  # pending, candidate, promoted, blacklisted
            "outcomes": [],  # List of outcome records from operation executions
        }

        # Serialize for ChromaDB storage
        metadata = {
            "event_type": event_type,
            "suggestion": suggestion,
            "timestamp": timestamp,
            "promotion_status": "pending",
        }

        # Create embeddings-friendly text for similarity search
        embedding_text = f"{event_type} {suggestion} {suggestion_context}"

        self.collection.add(
            ids=[event_id],
            documents=[embedding_text],
            metadatas=[metadata],
            documents_data=json.dumps(event)
        )

        return event_id

    def record_user_response(
        self,
        event_id: str,
        accepted: bool,
    ) -> Dict[str, Any]:
        """
        Record user's response to a suggestion and update confidence score.

        Args:
            event_id: ID of the event
            accepted: True if user accepted, False if rejected

        Returns:
            Updated event with new confidence score
        """
        # Retrieve event
        result = self.collection.get(ids=[event_id], include=["documents"])
        if not result or not result["ids"]:
            return {"status": "error", "message": f"Event {event_id} not found"}

        # Parse stored event
        event_json = result.get("documents")[0] if result.get("documents") else None
        if not event_json:
            return {"status": "error", "message": "Event data corrupted"}

        event = json.loads(event_json) if isinstance(event_json, str) else event_json

        # Update counters
        event["total_shown"] += 1
        if accepted:
            event["accepted_count"] += 1
        else:
            event["rejected_count"] += 1

        # Recalculate confidence score
        event["confidence_score"] = self._calculate_confidence_score(
            event["accepted_count"],
            event["total_shown"]
        )

        # Update promotion status based on thresholds
        event["promotion_status"] = self._determine_promotion_status(
            event["confidence_score"],
            event["accepted_count"],
            event["rejected_count"]
        )

        # Update in ChromaDB
        metadata = {
            "event_type": event["event_type"],
            "suggestion": event["suggestion"],
            "timestamp": event["timestamp"],
            "promotion_status": event["promotion_status"],
        }

        self.collection.update(
            ids=[event_id],
            metadatas=[metadata],
        )

        return event

    def record_operation_outcome(
        self,
        event_id: str,
        status: str,
        result_metrics: Optional[Dict[str, Any]] = None,
        execution_time_seconds: Optional[float] = None,
        side_effects: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Record the outcome/result of executing the suggested operation.

        Args:
            event_id: ID of the event
            status: Outcome status ("success", "partial", "failed")
            result_metrics: Dict of metrics showing impact (e.g., {"ram_freed_gb": 5.2})
            execution_time_seconds: How long the operation took
            side_effects: Any negative side effects or warnings

        Returns:
            Updated event with outcome recorded
        """
        event = self.get_event_by_id(event_id)
        if not event:
            return {"status": "error", "message": f"Event {event_id} not found"}

        outcome = {
            "timestamp": datetime.now().isoformat(),
            "status": status,  # success, partial, failed
            "result_metrics": result_metrics or {},
            "execution_time_seconds": execution_time_seconds,
            "side_effects": side_effects,
        }

        if "outcomes" not in event:
            event["outcomes"] = []

        event["outcomes"].append(outcome)

        # Update in ChromaDB
        metadata = {
            "event_type": event["event_type"],
            "suggestion": event["suggestion"],
            "timestamp": event["timestamp"],
            "promotion_status": event["promotion_status"],
        }

        self.collection.update(
            ids=[event_id],
            metadatas=[metadata],
        )

        return event

    def get_outcome_effectiveness(self, event_id: str) -> Dict[str, Any]:
        """
        Analyze effectiveness of all outcomes for an event.

        Returns success rate and average metrics impact.

        Args:
            event_id: Event to analyze

        Returns:
            Effectiveness summary with success_rate and avg_metrics
        """
        event = self.get_event_by_id(event_id)
        if not event or not event.get("outcomes"):
            return {"status": "no_outcomes", "success_rate": 0.0}

        outcomes = event["outcomes"]
        success_count = sum(1 for o in outcomes if o["status"] == "success")
        success_rate = success_count / len(outcomes) if outcomes else 0.0

        # Aggregate metrics across all outcomes
        aggregated_metrics = {}
        for outcome in outcomes:
            for metric_key, metric_value in outcome.get("result_metrics", {}).items():
                if metric_key not in aggregated_metrics:
                    aggregated_metrics[metric_key] = []
                if isinstance(metric_value, (int, float)):
                    aggregated_metrics[metric_key].append(metric_value)

        avg_metrics = {
            k: round(sum(v) / len(v), 2) for k, v in aggregated_metrics.items()
        }

        return {
            "success_rate": round(success_rate, 2),
            "total_outcomes": len(outcomes),
            "avg_metrics": avg_metrics,
        }

    def promote_candidates_to_tier3(self, effectiveness_threshold: float = 0.7) -> Dict[str, Any]:
        """
        Promote high-confidence, high-effectiveness candidates to Tier 3.

        Filters:
        - confidence_score > 0.8
        - accepted_count >= 3
        - outcome_effectiveness (if outcomes exist) > effectiveness_threshold

        Args:
            effectiveness_threshold: Min success_rate for outcomes (0.0-1.0)

        Returns:
            Dict with promoted events and count
        """
        # Fetch candidates directly
        results = self.collection.get(
            where={"promotion_status": {"$eq": "candidate"}},
            limit=1000
        )

        promoted = []
        for event_id in results.get("ids", []):
            event = self.get_event_by_id(event_id)
            if not event:
                continue

            # Check effectiveness if outcomes exist
            if event.get("outcomes"):
                effectiveness = self.get_outcome_effectiveness(event["id"])
                if effectiveness.get("success_rate", 0.0) < effectiveness_threshold:
                    continue  # Skip low-effectiveness suggestions

            # Mark as promoted
            event["promotion_status"] = "promoted"
            promoted.append(event)

            metadata = {
                "event_type": event["event_type"],
                "suggestion": event["suggestion"],
                "timestamp": event["timestamp"],
                "promotion_status": "promoted",
            }
            self.collection.update(
                ids=[event["id"]],
                metadatas=[metadata],
            )

        return {
            "promoted_count": len(promoted),
            "promoted_events": promoted,
        }

    @staticmethod
    def _calculate_confidence_score(accepted_count: int, total_shown: int) -> float:
        """
        Calculate confidence score with consistency reward and volume dampening.

        Formula: (accepted / total) × log(1 + total)
        - Rewards consistency over just volume
        - Log dampening prevents rapid promotion from early successes

        Args:
            accepted_count: Number of times user accepted
            total_shown: Total times suggestion was shown

        Returns:
            Confidence score (0.0 to ~1.4)
        """
        if total_shown == 0:
            return 0.0

        acceptance_rate = accepted_count / total_shown
        volume_factor = math.log(1 + total_shown)

        return round(acceptance_rate * volume_factor, 3)

    @staticmethod
    def _determine_promotion_status(
        confidence_score: float,
        accepted_count: int,
        rejected_count: int,
    ) -> str:
        """
        Determine promotion status based on confidence thresholds.

        Rules:
        - confidence > 0.8 AND accepted_count >= 3 → candidate
        - rejected_count >= 2 → blacklisted
        - Otherwise → pending

        Args:
            confidence_score: Calculated confidence score
            accepted_count: Number of acceptances
            rejected_count: Number of rejections

        Returns:
            Status: "candidate", "blacklisted", or "pending"
        """
        if rejected_count >= 2:
            return "blacklisted"

        if confidence_score > 0.8 and accepted_count >= 3:
            return "candidate"

        return "pending"

    def retrieve_similar_events(
        self,
        event_type: str,
        suggestion_context: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve similar past events using vector similarity search.

        Args:
            event_type: Type of event to search for
            suggestion_context: Optional context to refine search
            limit: Max number of results

        Returns:
            List of similar past episodes
        """
        query_text = event_type
        if suggestion_context:
            query_text += f" {suggestion_context}"

        # Query with metadata filter for promoted/candidate events only
        results = self.collection.query(
            query_texts=[query_text],
            n_results=limit,
            where={
                "$or": [
                    {"promotion_status": {"$eq": "promoted"}},
                    {"promotion_status": {"$eq": "candidate"}},
                ]
            }
        )

        episodes = []
        if results and results["ids"] and results["ids"][0]:
            for event_id, metadata in zip(results["ids"][0], results["metadatas"][0]):
                # For now return metadata as summary; full event can be loaded if needed
                episodes.append({
                    "event_id": event_id,
                    "event_type": metadata.get("event_type"),
                    "suggestion": metadata.get("suggestion"),
                    "promotion_status": metadata.get("promotion_status"),
                })

        return episodes

    def get_event_by_id(self, event_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve full event details by ID.

        Args:
            event_id: ID of event to retrieve

        Returns:
            Event dict or None if not found
        """
        result = self.collection.get(ids=[event_id])
        if result and result["ids"]:
            # ChromaDB returns documents as list; parse the event
            if result.get("documents"):
                doc = result["documents"][0]
                try:
                    return json.loads(doc) if isinstance(doc, str) else doc
                except json.JSONDecodeError:
                    return None
        return None


if __name__ == "__main__":
    # Example usage
    memory = MemoryTier2()

    # Create an event
    system_state = {
        "cpu_percent": 85.5,
        "memory_percent": 80.2,
        "available_memory_gb": 2.1,
        "top_process": "Chrome",
    }

    event_id = memory.create_event(
        event_type="high_ram_usage",
        system_state=system_state,
        suggestion="close_chrome_tabs",
        suggestion_context="Chrome using 80% RAM, consider closing inactive tabs",
    )

    print(f"Created event: {event_id}")

    # Simulate user accepting the suggestion
    updated = memory.record_user_response(event_id, accepted=True)
    print(f"After 1st acceptance: {updated.get('confidence_score')}")

    # Simulate second acceptance
    updated = memory.record_user_response(event_id, accepted=True)
    print(f"After 2nd acceptance: {updated.get('confidence_score')}")

    # Simulate third acceptance (should become candidate)
    updated = memory.record_user_response(event_id, accepted=True)
    print(f"After 3rd acceptance: {updated.get('confidence_score')}, Status: {updated.get('promotion_status')}")

    # Retrieve similar events
    similar = memory.retrieve_similar_events("high_ram_usage")
    print(f"Similar events: {similar}")

    # Promote candidates to Tier 3
    result = memory.promote_candidates_to_tier3()
    print(f"Promoted: {result['promoted_count']} events")
