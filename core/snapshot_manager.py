"""
Snapshot manager for screenplay version history.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from core.screenplay_engine import Screenplay
import json


class Snapshot:
    """Represents a snapshot of a screenplay at a specific point in time."""
    
    def __init__(self, screenplay: Screenplay, milestone: str, description: str = ""):
        self.timestamp = datetime.now().isoformat()
        self.milestone = milestone  # "premise", "outline", "framework", "storyboard", "manual"
        self.description = description
        self.screenplay_data = screenplay.to_dict()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert snapshot to dictionary."""
        return {
            "timestamp": self.timestamp,
            "milestone": self.milestone,
            "description": self.description,
            "screenplay_data": self.screenplay_data
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Snapshot':
        """Create snapshot from dictionary."""
        snapshot = cls.__new__(cls)
        snapshot.timestamp = data["timestamp"]
        snapshot.milestone = data["milestone"]
        snapshot.description = data.get("description", "")
        snapshot.screenplay_data = data["screenplay_data"]
        return snapshot
    
    def restore(self) -> Screenplay:
        """Restore screenplay from snapshot."""
        return Screenplay.from_dict(self.screenplay_data)


class SnapshotManager:
    """Manages snapshots for screenplay version history."""
    
    def __init__(self, max_snapshots: int = 50):
        self.snapshots: List[Snapshot] = []
        self.max_snapshots = max_snapshots
    
    def create_snapshot(self, screenplay: Screenplay, milestone: str, description: str = "") -> Snapshot:
        """Create a new snapshot."""
        snapshot = Snapshot(screenplay, milestone, description)
        self.snapshots.append(snapshot)
        
        # Limit number of snapshots
        if len(self.snapshots) > self.max_snapshots:
            self.snapshots = self.snapshots[-self.max_snapshots:]
        
        return snapshot
    
    def get_snapshots(self, milestone: Optional[str] = None) -> List[Snapshot]:
        """Get all snapshots, optionally filtered by milestone."""
        if milestone:
            return [s for s in self.snapshots if s.milestone == milestone]
        return self.snapshots.copy()
    
    def get_latest_snapshot(self, milestone: Optional[str] = None) -> Optional[Snapshot]:
        """Get the most recent snapshot, optionally filtered by milestone."""
        snapshots = self.get_snapshots(milestone)
        if not snapshots:
            return None
        return max(snapshots, key=lambda s: s.timestamp)
    
    def get_snapshot_at(self, timestamp: str) -> Optional[Snapshot]:
        """Get snapshot at specific timestamp."""
        for snapshot in self.snapshots:
            if snapshot.timestamp == timestamp:
                return snapshot
        return None
    
    def compare_snapshots(self, snapshot1: Snapshot, snapshot2: Snapshot) -> Dict[str, Any]:
        """Compare two snapshots and return differences."""
        diff = {
            "timestamp_diff": abs((datetime.fromisoformat(snapshot1.timestamp) - 
                                   datetime.fromisoformat(snapshot2.timestamp)).total_seconds()),
            "milestone_diff": snapshot1.milestone != snapshot2.milestone,
            "title_changed": snapshot1.screenplay_data.get("title") != snapshot2.screenplay_data.get("title"),
            "acts_count_diff": (len(snapshot1.screenplay_data.get("acts", [])) - 
                              len(snapshot2.screenplay_data.get("acts", []))),
            "scenes_count_diff": (sum(len(act.get("scenes", [])) for act in snapshot1.screenplay_data.get("acts", [])) -
                                 sum(len(act.get("scenes", [])) for act in snapshot2.screenplay_data.get("acts", []))),
            "items_count_diff": (len(snapshot1.screenplay_data.get("storyboard_items", [])) -
                               len(snapshot2.screenplay_data.get("storyboard_items", [])))
        }
        return diff
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert snapshot manager to dictionary."""
        return {
            "snapshots": [s.to_dict() for s in self.snapshots],
            "max_snapshots": self.max_snapshots
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SnapshotManager':
        """Create snapshot manager from dictionary."""
        manager = cls(max_snapshots=data.get("max_snapshots", 50))
        for snapshot_data in data.get("snapshots", []):
            manager.snapshots.append(Snapshot.from_dict(snapshot_data))
        return manager
