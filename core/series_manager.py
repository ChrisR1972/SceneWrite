"""
Series Manager for the Episodic Series System.

Orchestrates series lifecycle: creating series folders, loading/saving the
Series Bible, spawning new episodes from bible data, finalizing episodes
back into the bible, and converting standalone stories into series.
"""

from __future__ import annotations

import datetime
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from config import get_stories_directory
from core.series_bible import SeriesBible


SERIES_BIBLE_FILENAME = "series_bible.json"


def _sanitize_folder_name(name: str) -> str:
    """Remove characters that are unsafe for directory names."""
    cleaned = re.sub(r'[<>:"/\\|?*]', '', name).strip()
    return cleaned or "Untitled Series"


class SeriesManager:
    """Orchestrates creation, loading, and management of episodic series."""

    # ── Series lifecycle ─────────────────────────────────────────────

    @staticmethod
    def create_series(title: str) -> Tuple[str, SeriesBible]:
        """Create a new series folder and empty Series Bible.

        Returns (series_folder_path, series_bible).
        """
        folder_name = _sanitize_folder_name(title)
        series_folder = os.path.join(get_stories_directory(), folder_name)
        os.makedirs(series_folder, exist_ok=True)

        bible = SeriesBible(series_title=title)
        bible_path = os.path.join(series_folder, SERIES_BIBLE_FILENAME)
        bible.save_to_file(bible_path)

        return series_folder, bible

    @staticmethod
    def load_series(folder_path: str) -> SeriesBible:
        """Load the Series Bible from a series folder."""
        bible_path = os.path.join(folder_path, SERIES_BIBLE_FILENAME)
        if not os.path.isfile(bible_path):
            raise FileNotFoundError(f"No series bible found at {bible_path}")
        return SeriesBible.load_from_file(bible_path)

    @staticmethod
    def save_series_bible(folder_path: str, bible: SeriesBible) -> None:
        """Save the Series Bible back to its folder."""
        bible_path = os.path.join(folder_path, SERIES_BIBLE_FILENAME)
        bible.save_to_file(bible_path)

    @staticmethod
    def is_series_folder(folder_path: str) -> bool:
        """Return True if the folder contains a series_bible.json."""
        return os.path.isfile(os.path.join(folder_path, SERIES_BIBLE_FILENAME))

    # ── Episode management ───────────────────────────────────────────

    @staticmethod
    def build_episode_filename(episode_number: int, episode_title: str) -> str:
        title_part = _sanitize_folder_name(episode_title)
        if title_part:
            return f"Episode {episode_number:02d} - {title_part}.json"
        return f"Episode {episode_number:02d}.json"

    @staticmethod
    def create_new_episode(
        series_bible: SeriesBible,
        series_folder: str,
        episode_number: int,
        episode_title: str,
        episode_premise: str,
    ):
        """Create a new Screenplay pre-populated from the Series Bible.

        Returns a Screenplay with series_metadata set and identity blocks
        copied from the bible for main characters and recurring locations/objects.
        """
        from core.screenplay_engine import Screenplay

        screenplay = Screenplay(
            title=f"{series_bible.series_title} - Episode {episode_number}: {episode_title}",
            premise=episode_premise,
        )

        screenplay.series_metadata = {
            "series_title": series_bible.series_title,
            "series_folder": series_folder,
            "episode_number": episode_number,
            "episode_title": episode_title,
            "episode_premise": episode_premise,
            "episode_summary": "",
            "episode_story_arc": "",
            "episode_scene_count": 0,
            "episode_status": "draft",
        }

        # Carry over custom episode duration from the series bible
        if getattr(series_bible, "episode_duration_seconds", 0) > 0:
            screenplay.story_length = "custom"
            screenplay.custom_duration_seconds = series_bible.episode_duration_seconds

        # Carry over world-level metadata
        if series_bible.world_context.get("tone"):
            screenplay.atmosphere = series_bible.world_context["tone"]

        # Build character registry from bible characters
        screenplay.character_registry = [
            ch.get("name") for ch in series_bible.main_characters if ch.get("name")
        ]
        screenplay.character_registry_frozen = True

        # Build story_outline characters from bible
        outline_chars = []
        for ch in series_bible.main_characters:
            outline_chars.append({
                "name": ch.get("name", ""),
                "role": ch.get("role", "main"),
                "species": ch.get("species", "Human"),
                "outline": "",
                "growth_arc": ch.get("growth_arc", ""),
                "physical_appearance": ch.get("physical_appearance", ""),
            })
        screenplay.story_outline = {
            "characters": outline_chars,
            "main_storyline": "",
            "subplots": [],
            "conclusion": "",
            "locations": [loc.get("name", "") for loc in series_bible.recurring_locations],
        }

        # Copy identity blocks from bible
        SeriesManager._copy_bible_identity_blocks(series_bible, screenplay)

        return screenplay

    @staticmethod
    def _copy_bible_identity_blocks(bible: SeriesBible, screenplay) -> None:
        """Copy identity blocks from the bible into a new episode Screenplay."""
        for char in bible.main_characters:
            eid = char.get("identity_block_id", "")
            block = char.get("identity_block", "")
            name = char.get("name", "")
            if eid and block:
                screenplay.identity_blocks[eid] = block
                screenplay.register_identity_block_id(name, "character", eid)
                screenplay.identity_block_metadata[eid] = {
                    "name": name,
                    "type": "character",
                    "scene_id": "",
                    "status": "approved",
                    "user_notes": "",
                    "identity_block": block,
                    "reference_image_prompt": char.get("reference_image_prompt", ""),
                    "image_path": char.get("reference_image_path", ""),
                    "source": "series_bible",
                    "created_at": char.get("created_at", datetime.datetime.now().isoformat()),
                    "updated_at": datetime.datetime.now().isoformat(),
                }
            # Copy wardrobe variants
            variants = char.get("wardrobe_variants", [])
            if variants and eid:
                screenplay.character_wardrobe_variants[eid] = list(variants)

        for loc in bible.recurring_locations:
            eid = loc.get("identity_block_id", "")
            block = loc.get("identity_block", "")
            name = loc.get("name", "")
            if eid and block:
                screenplay.identity_blocks[eid] = block
                screenplay.register_identity_block_id(name, "environment", eid)
                screenplay.identity_block_metadata[eid] = {
                    "name": name,
                    "type": "environment",
                    "scene_id": "",
                    "status": "approved",
                    "user_notes": loc.get("description", ""),
                    "identity_block": block,
                    "reference_image_prompt": "",
                    "image_path": loc.get("reference_image_path", ""),
                    "source": "series_bible",
                    "created_at": datetime.datetime.now().isoformat(),
                    "updated_at": datetime.datetime.now().isoformat(),
                }

        for obj in bible.recurring_objects:
            eid = obj.get("identity_block_id", "")
            block = obj.get("identity_block", "")
            name = obj.get("name", "")
            if eid and block:
                screenplay.identity_blocks[eid] = block
                screenplay.register_identity_block_id(name, "object", eid)
                screenplay.identity_block_metadata[eid] = {
                    "name": name,
                    "type": "object",
                    "scene_id": "",
                    "status": "approved",
                    "user_notes": obj.get("description", ""),
                    "identity_block": block,
                    "reference_image_prompt": "",
                    "image_path": "",
                    "source": "series_bible",
                    "created_at": datetime.datetime.now().isoformat(),
                    "updated_at": datetime.datetime.now().isoformat(),
                }

    # ── Finalize / sync ──────────────────────────────────────────────

    @staticmethod
    def finalize_episode(
        screenplay,
        bible: SeriesBible,
        series_folder: str,
        summary: str = "",
        story_arc: str = "",
        timeline_events: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Write episode results back into the Series Bible and save."""
        meta = getattr(screenplay, "series_metadata", None) or {}
        ep_num = meta.get("episode_number", bible.get_next_episode_number())
        ep_title = meta.get("episode_title", screenplay.title)

        all_scenes = screenplay.get_all_scenes() if hasattr(screenplay, "get_all_scenes") else []

        record = {
            "episode_number": ep_num,
            "title": ep_title,
            "premise": meta.get("episode_premise", screenplay.premise),
            "summary": summary or meta.get("episode_summary", ""),
            "story_arc": story_arc or meta.get("episode_story_arc", ""),
            "scene_count": len(all_scenes),
            "status": "complete",
            "filename": SeriesManager.build_episode_filename(ep_num, ep_title),
            "completed_at": datetime.datetime.now().isoformat(),
        }
        bible.add_episode_record(record)

        if timeline_events:
            for evt in timeline_events:
                bible.add_timeline_event(
                    ep_num,
                    evt.get("event", ""),
                    evt.get("description", ""),
                )

        # Update series_metadata on the screenplay itself
        if screenplay.series_metadata:
            screenplay.series_metadata["episode_summary"] = record["summary"]
            screenplay.series_metadata["episode_story_arc"] = record["story_arc"]
            screenplay.series_metadata["episode_scene_count"] = record["scene_count"]
            screenplay.series_metadata["episode_status"] = "complete"

        # Sync any new/updated identity blocks back into the bible
        SeriesManager._sync_identity_blocks_to_bible(screenplay, bible)

        SeriesManager.save_series_bible(series_folder, bible)

    @staticmethod
    def _sync_identity_blocks_to_bible(screenplay, bible: SeriesBible) -> None:
        """Push identity blocks from the screenplay back to the bible for persistence."""
        for eid, meta in screenplay.identity_block_metadata.items():
            etype = (meta.get("type") or "").lower()
            name = (meta.get("name") or "").strip()
            block = screenplay.identity_blocks.get(eid, "")
            if not name:
                continue

            if etype == "character":
                char = bible.get_character_by_name(name)
                if char:
                    if block:
                        char["identity_block"] = block
                        char["identity_block_id"] = eid
                    char["reference_image_path"] = meta.get("image_path", char.get("reference_image_path", ""))
                    char["reference_image_prompt"] = meta.get("reference_image_prompt", char.get("reference_image_prompt", ""))
            elif etype == "environment":
                loc = bible.get_location_by_name(name)
                if loc and block:
                    loc["identity_block"] = block
                    loc["identity_block_id"] = eid
                    loc["reference_image_path"] = meta.get("image_path", loc.get("reference_image_path", ""))

    # ── Convert standalone → series ──────────────────────────────────

    @staticmethod
    def convert_to_series(screenplay, series_title: str = "") -> Tuple[str, SeriesBible]:
        """Convert a standalone Screenplay into Episode 1 of a new series.

        Returns (series_folder, bible).
        """
        title = series_title or screenplay.title or "Untitled Series"
        series_folder, bible = SeriesManager.create_series(title)

        bible.world_context["tone"] = screenplay.atmosphere or ""
        if screenplay.genre:
            bible.world_context["setting_description"] = f"Genre: {', '.join(screenplay.genre)}"

        SeriesManager.import_series_bible_from_screenplay(screenplay, bible)

        # Set series_metadata on the screenplay
        ep_title = screenplay.title or "Pilot"
        screenplay.series_metadata = {
            "series_title": title,
            "series_folder": series_folder,
            "episode_number": 1,
            "episode_title": ep_title,
            "episode_premise": screenplay.premise,
            "episode_summary": "",
            "episode_story_arc": "",
            "episode_scene_count": len(screenplay.get_all_scenes()),
            "episode_status": "in_progress",
        }

        bible.add_episode_record({
            "episode_number": 1,
            "title": ep_title,
            "premise": screenplay.premise,
            "summary": "",
            "story_arc": "",
            "scene_count": len(screenplay.get_all_scenes()),
            "status": "in_progress",
            "filename": SeriesManager.build_episode_filename(1, ep_title),
            "created_at": datetime.datetime.now().isoformat(),
        })

        SeriesManager.save_series_bible(series_folder, bible)
        return series_folder, bible

    @staticmethod
    def import_series_bible_from_screenplay(screenplay, bible: SeriesBible) -> None:
        """Extract characters, locations, and objects from a Screenplay to seed the bible."""
        # Characters
        outline_chars = []
        if screenplay.story_outline and isinstance(screenplay.story_outline, dict):
            outline_chars = screenplay.story_outline.get("characters", [])

        for ch in (outline_chars if isinstance(outline_chars, list) else []):
            if not isinstance(ch, dict):
                continue
            name = ch.get("name", "").strip()
            if not name:
                continue
            eid = screenplay.identity_block_ids.get(f"character:{name}".lower(), "")
            char_data = {
                "name": name,
                "role": ch.get("role", "main"),
                "species": ch.get("species", "Human"),
                "physical_appearance": ch.get("physical_appearance", ""),
                "personality_traits": [],
                "relationships": [],
                "growth_arc": ch.get("growth_arc", ""),
                "identity_block": screenplay.identity_blocks.get(eid, ""),
                "identity_block_id": eid,
                "reference_image_path": "",
                "reference_image_prompt": "",
                "wardrobe_variants": [],
            }
            if eid:
                meta = screenplay.identity_block_metadata.get(eid, {})
                char_data["reference_image_path"] = meta.get("image_path", "")
                char_data["reference_image_prompt"] = meta.get("reference_image_prompt", "")
                variants = screenplay.character_wardrobe_variants.get(eid, [])
                char_data["wardrobe_variants"] = list(variants)
            bible.add_character(char_data)

        # Locations (from identity block metadata)
        for eid, meta in screenplay.identity_block_metadata.items():
            if (meta.get("type") or "").lower() != "environment":
                continue
            name = (meta.get("name") or "").strip()
            if not name:
                continue
            bible.add_location({
                "name": name,
                "description": meta.get("user_notes", ""),
                "structural_characteristics": "",
                "identity_block": screenplay.identity_blocks.get(eid, ""),
                "identity_block_id": eid,
                "reference_image_path": meta.get("image_path", ""),
            })

        # Objects
        for eid, meta in screenplay.identity_block_metadata.items():
            if (meta.get("type") or "").lower() != "object":
                continue
            name = (meta.get("name") or "").strip()
            if not name:
                continue
            bible.add_object({
                "name": name,
                "description": meta.get("user_notes", ""),
                "visual_appearance": "",
                "narrative_function": "",
                "identity_block": screenplay.identity_blocks.get(eid, ""),
                "identity_block_id": eid,
            })

    # ── Episode listing ──────────────────────────────────────────────

    @staticmethod
    def get_episode_list(series_folder: str) -> List[Dict[str, Any]]:
        """Scan a series folder for episode files. Returns metadata dicts."""
        episodes = []
        if not os.path.isdir(series_folder):
            return episodes

        pattern = re.compile(r"^Episode\s+(\d+)", re.IGNORECASE)
        for fname in sorted(os.listdir(series_folder)):
            if fname == SERIES_BIBLE_FILENAME:
                continue
            if not fname.lower().endswith(".json"):
                continue
            m = pattern.match(fname)
            if not m:
                continue
            ep_number = int(m.group(1))
            filepath = os.path.join(series_folder, fname)
            episodes.append({
                "episode_number": ep_number,
                "filename": fname,
                "filepath": filepath,
            })

        episodes.sort(key=lambda e: e["episode_number"])
        return episodes

    @staticmethod
    def list_all_series() -> List[Dict[str, Any]]:
        """List all series folders in the stories directory."""
        stories_dir = get_stories_directory()
        series_list = []
        if not os.path.isdir(stories_dir):
            return series_list

        for entry in sorted(os.listdir(stories_dir)):
            folder = os.path.join(stories_dir, entry)
            if os.path.isdir(folder) and SeriesManager.is_series_folder(folder):
                try:
                    bible = SeriesManager.load_series(folder)
                    series_list.append({
                        "title": bible.series_title,
                        "folder": folder,
                        "episode_count": len(bible.episode_history),
                    })
                except Exception:
                    series_list.append({
                        "title": entry,
                        "folder": folder,
                        "episode_count": 0,
                    })

        return series_list
