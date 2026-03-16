"""
Series Bible data model for the Episodic Series System.

The Series Bible stores persistent narrative elements that remain consistent
across all episodes in a series: characters, locations, world context,
recurring objects, factions, timeline events, and episode history.
"""

from __future__ import annotations

import datetime
import json
import os
from typing import Any, Dict, List, Optional


class SeriesBible:
    """Persistent narrative data shared across all episodes in a series."""

    def __init__(self, series_title: str = ""):
        self.series_title: str = series_title
        self.version: str = "1.0"
        self.created_at: str = datetime.datetime.now().isoformat()
        self.updated_at: str = datetime.datetime.now().isoformat()

        # Persistent characters with stable identity, personality, and appearance
        self.main_characters: List[Dict[str, Any]] = []
        # Each entry: {
        #     "name": str,
        #     "role": str,  ("main" or "supporting")
        #     "species": str,
        #     "physical_appearance": str,
        #     "personality_traits": List[str],
        #     "relationships": List[Dict],  [{target, type, description}]
        #     "growth_arc": str,
        #     "identity_block": str,
        #     "identity_block_id": str,
        #     "reference_image_path": str,
        #     "reference_image_prompt": str,
        #     "wardrobe_variants": List[Dict],
        # }

        # Key locations that remain consistent across episodes
        self.recurring_locations: List[Dict[str, Any]] = []
        # Each entry: {
        #     "name": str,
        #     "description": str,
        #     "structural_characteristics": str,
        #     "identity_block": str,
        #     "identity_block_id": str,
        #     "reference_image_path": str,
        # }

        # Broader world setting
        self.world_context: Dict[str, Any] = {
            "setting_description": "",
            "time_period": "",
            "rules_and_lore": "",
            "tone": "",
        }

        # Important props or story objects that may reappear
        self.recurring_objects: List[Dict[str, Any]] = []
        # Each entry: {
        #     "name": str,
        #     "description": str,
        #     "visual_appearance": str,
        #     "narrative_function": str,
        #     "identity_block": str,
        #     "identity_block_id": str,
        # }

        # Organizations or groups within the story world
        self.factions_or_groups: List[Dict[str, Any]] = []
        # Each entry: {
        #     "name": str,
        #     "description": str,
        #     "members": List[str],
        #     "goals": str,
        # }

        # Target episode duration for the series (0 = no custom duration)
        self.episode_duration_seconds: int = 0

        # Chronological events auto-populated from episode summaries
        self.timeline_events: List[Dict[str, Any]] = []
        # Each entry: {
        #     "episode_number": int,
        #     "event": str,
        #     "description": str,
        # }

        # Completed episode records
        self.episode_history: List[Dict[str, Any]] = []
        # Each entry: {
        #     "episode_number": int,
        #     "title": str,
        #     "premise": str,
        #     "summary": str,
        #     "story_arc": str,
        #     "scene_count": int,
        #     "status": str,  ("draft", "in_progress", "complete")
        #     "filename": str,
        #     "created_at": str,
        #     "completed_at": str,
        # }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "series_title": self.series_title,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "main_characters": self.main_characters,
            "recurring_locations": self.recurring_locations,
            "world_context": self.world_context,
            "recurring_objects": self.recurring_objects,
            "factions_or_groups": self.factions_or_groups,
            "timeline_events": self.timeline_events,
            "episode_history": self.episode_history,
            **({"episode_duration_seconds": self.episode_duration_seconds} if self.episode_duration_seconds > 0 else {}),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SeriesBible":
        bible = cls(series_title=data.get("series_title", ""))
        bible.version = data.get("version", "1.0")
        bible.created_at = data.get("created_at", "")
        bible.updated_at = data.get("updated_at", "")
        bible.main_characters = data.get("main_characters", [])
        bible.recurring_locations = data.get("recurring_locations", [])
        bible.world_context = data.get("world_context", {
            "setting_description": "",
            "time_period": "",
            "rules_and_lore": "",
            "tone": "",
        })
        bible.recurring_objects = data.get("recurring_objects", [])
        bible.factions_or_groups = data.get("factions_or_groups", [])
        bible.timeline_events = data.get("timeline_events", [])
        bible.episode_history = data.get("episode_history", [])
        bible.episode_duration_seconds = data.get("episode_duration_seconds", 0)
        return bible

    def save_to_file(self, filepath: str) -> None:
        dirname = os.path.dirname(filepath)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        self.updated_at = datetime.datetime.now().isoformat()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
            f.flush()
            try:
                if hasattr(f, "fileno"):
                    os.fsync(f.fileno())
            except (OSError, AttributeError):
                pass

    @classmethod
    def load_from_file(cls, filepath: str) -> "SeriesBible":
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    # ── Query helpers ────────────────────────────────────────────────

    def get_next_episode_number(self) -> int:
        if not self.episode_history:
            return 1
        return max(ep.get("episode_number", 0) for ep in self.episode_history) + 1

    def get_episode(self, episode_number: int) -> Optional[Dict[str, Any]]:
        for ep in self.episode_history:
            if ep.get("episode_number") == episode_number:
                return ep
        return None

    def get_character_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        name_lower = name.strip().lower()
        for char in self.main_characters:
            if char.get("name", "").strip().lower() == name_lower:
                return char
        return None

    def get_location_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        name_lower = name.strip().lower()
        for loc in self.recurring_locations:
            if loc.get("name", "").strip().lower() == name_lower:
                return loc
        return None

    # ── Mutation helpers ─────────────────────────────────────────────

    def add_character(self, character: Dict[str, Any]) -> None:
        existing = self.get_character_by_name(character.get("name", ""))
        if existing:
            existing.update(character)
        else:
            self.main_characters.append(character)
        self.updated_at = datetime.datetime.now().isoformat()

    def add_location(self, location: Dict[str, Any]) -> None:
        existing = self.get_location_by_name(location.get("name", ""))
        if existing:
            existing.update(location)
        else:
            self.recurring_locations.append(location)
        self.updated_at = datetime.datetime.now().isoformat()

    def add_object(self, obj: Dict[str, Any]) -> None:
        self.recurring_objects.append(obj)
        self.updated_at = datetime.datetime.now().isoformat()

    def add_faction(self, faction: Dict[str, Any]) -> None:
        self.factions_or_groups.append(faction)
        self.updated_at = datetime.datetime.now().isoformat()

    def add_timeline_event(self, episode_number: int, event: str, description: str = "") -> None:
        self.timeline_events.append({
            "episode_number": episode_number,
            "event": event,
            "description": description,
        })
        self.updated_at = datetime.datetime.now().isoformat()

    def add_episode_record(self, record: Dict[str, Any]) -> None:
        ep_num = record.get("episode_number")
        existing = self.get_episode(ep_num) if ep_num else None
        if existing:
            existing.update(record)
        else:
            self.episode_history.append(record)
        self.episode_history.sort(key=lambda e: e.get("episode_number", 0))
        self.updated_at = datetime.datetime.now().isoformat()

    def get_series_summary_for_ai(self) -> str:
        """Build a condensed context string for injection into AI prompts."""
        parts = []
        parts.append(f"SERIES: {self.series_title}")

        if self.world_context.get("setting_description"):
            parts.append(f"\nWORLD SETTING: {self.world_context['setting_description']}")
        if self.world_context.get("time_period"):
            parts.append(f"TIME PERIOD: {self.world_context['time_period']}")
        if self.world_context.get("rules_and_lore"):
            parts.append(f"RULES/LORE: {self.world_context['rules_and_lore']}")
        if self.world_context.get("tone"):
            parts.append(f"TONE: {self.world_context['tone']}")

        if self.main_characters:
            parts.append("\nPERSISTENT CHARACTERS:")
            for char in self.main_characters:
                name = char.get("name", "Unknown")
                role = char.get("role", "")
                traits = ", ".join(char.get("personality_traits", []))
                appearance = char.get("physical_appearance", "")
                arc = char.get("growth_arc", "")
                line = f"  - {name} ({role})"
                if traits:
                    line += f" | Traits: {traits}"
                if appearance:
                    line += f" | Appearance: {appearance}"
                if arc:
                    line += f" | Arc: {arc}"
                rels = char.get("relationships", [])
                if rels:
                    rel_strs = [f"{r.get('target', '?')} ({r.get('type', '?')})" for r in rels]
                    line += f" | Relationships: {', '.join(rel_strs)}"
                parts.append(line)

        if self.recurring_locations:
            parts.append("\nRECURRING LOCATIONS:")
            for loc in self.recurring_locations:
                desc = loc.get("description", "")
                parts.append(f"  - {loc.get('name', 'Unknown')}: {desc}")

        if self.recurring_objects:
            parts.append("\nRECURRING OBJECTS:")
            for obj in self.recurring_objects:
                parts.append(f"  - {obj.get('name', 'Unknown')}: {obj.get('description', '')}")

        if self.factions_or_groups:
            parts.append("\nFACTIONS/GROUPS:")
            for fac in self.factions_or_groups:
                parts.append(f"  - {fac.get('name', 'Unknown')}: {fac.get('description', '')}")

        if self.episode_history:
            parts.append("\nPREVIOUS EPISODES:")
            for ep in sorted(self.episode_history, key=lambda e: e.get("episode_number", 0)):
                summary = ep.get("summary", ep.get("premise", ""))
                parts.append(f"  Episode {ep.get('episode_number', '?')}: {ep.get('title', 'Untitled')} - {summary}")

        if self.timeline_events:
            recent = self.timeline_events[-20:]
            parts.append("\nKEY TIMELINE EVENTS:")
            for evt in recent:
                parts.append(f"  [Ep {evt.get('episode_number', '?')}] {evt.get('event', '')}")

        return "\n".join(parts)
