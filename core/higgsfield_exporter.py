"""
Export functionality for Higgsfield Cinema Studio 2.0.

Produces three export formats:
  - JSON (general-purpose storyboard data)
  - CSV  (tabular storyboard data)
  - Higgsfield API-compatible JSON (ready for direct API submission)
"""

import json
import csv
import os
from typing import List, Dict, Any, Optional
from .screenplay_engine import Screenplay, StoryboardItem
from .video_prompt_builder import (
    build_keyframe_prompt,
    build_identity_prompt,
    build_video_prompt,
    compile_all_prompts,
)

HIGGSFIELD_IMAGE_MODELS = {
    "higgsfield-ai/soul/standard": "Soul Standard — creative character images",
    "higgsfield-ai/soul/2.0": "Soul 2.0 — fashion-forward, cultural fluency",
    "higgsfield-ai/nano-banana/pro": "Nano Banana Pro — 4K image generation",
}

HIGGSFIELD_VIDEO_MODELS = {
    "higgsfield-ai/dop/standard": "DoP Standard — high-quality image animation",
    "higgsfield-ai/dop/preview": "DoP Preview — fast preview generation",
    "kling-video/v2.1/pro/image-to-video": "Kling 2.1 Pro — realistic human motion",
    "kling-video/v3.0/pro/image-to-video": "Kling 3.0 Pro — faster generation, reduced wait times",
    "bytedance/seedance/v1/pro/image-to-video": "Seedance Pro — character motion",
}

HIGGSFIELD_MODELS = {**HIGGSFIELD_IMAGE_MODELS, **HIGGSFIELD_VIDEO_MODELS}


class HiggsfieldExporter:
    """Handles export of storyboards for Higgsfield Cinema Studio 2.0."""

    def export_to_json(self, screenplay: Screenplay, filename: str) -> None:
        """Export screenplay to general-purpose JSON with 3-layer prompts."""

        all_items = screenplay.get_all_storyboard_items()

        export_data = {
            "title": screenplay.title,
            "premise": screenplay.premise,
            "genre": screenplay.genre,
            "atmosphere": screenplay.atmosphere,
            "total_duration_seconds": screenplay.get_total_duration(),
            "total_duration_formatted": screenplay.get_total_duration_formatted(),
            "item_count": len(all_items),
            "storyboard": [],
        }

        if screenplay.acts:
            export_data["framework"] = {
                "acts": len(screenplay.acts),
                "scenes": sum(len(act.scenes) for act in screenplay.acts),
                "story_structure": screenplay.story_structure,
            }

        for item in all_items:
            scene = self._find_scene_for_item(screenplay, item)
            prompts = compile_all_prompts(item, screenplay, scene)

            export_item = {
                "sequence": item.sequence_number,
                "duration_seconds": item.duration,
                "shot_type": item.shot_type,
                "focal_length": getattr(item, "focal_length", 35),
                "aperture_style": getattr(item, "aperture_style", "cinematic_bokeh"),
                "camera_motion": getattr(item, "camera_motion", "static"),
                "keyframe_prompt": prompts["keyframe_prompt"],
                "identity_prompt": prompts["identity_prompt"],
                "video_prompt": prompts["video_prompt"],
                "storyline": item.storyline,
                "dialogue": item.dialogue or None,
                "scene_type": item.scene_type.value,
                "hero_frame_path": item.environment_start_image or None,
                "end_frame_path": (
                    getattr(item, "environment_end_image", "") or None
                ),
                "image_assignments": getattr(item, "image_assignments", {}),
            }

            audio_intent = getattr(item, "audio_intent", "") or ""
            audio_notes = getattr(item, "audio_notes", "") or ""
            if audio_intent or audio_notes:
                export_item["audio"] = {
                    "intent": audio_intent or None,
                    "notes": audio_notes or None,
                    "source": getattr(item, "audio_source", "none"),
                }

            export_data["storyboard"].append(export_item)

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

    def export_to_csv(self, screenplay: Screenplay, filename: str) -> None:
        """Export screenplay to CSV with 3-layer prompts."""

        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            writer.writerow([
                "Sequence",
                "Duration (s)",
                "Shot Type",
                "Camera Motion",
                "Focal Length",
                "Keyframe Prompt",
                "Identity Prompt",
                "Video Prompt",
                "Storyline",
                "Dialogue",
                "Scene Type",
                "Hero Frame Path",
            ])

            for item in screenplay.get_all_storyboard_items():
                scene = self._find_scene_for_item(screenplay, item)
                prompts = compile_all_prompts(item, screenplay, scene)

                writer.writerow([
                    item.sequence_number,
                    item.duration,
                    item.shot_type,
                    getattr(item, "camera_motion", "static"),
                    getattr(item, "focal_length", 35),
                    prompts["keyframe_prompt"],
                    prompts["identity_prompt"],
                    prompts["video_prompt"],
                    item.storyline,
                    item.dialogue or "",
                    item.scene_type.value,
                    item.environment_start_image or "",
                ])

    def export_prompts_only(self, screenplay: Screenplay, filename: str) -> None:
        """Export prompt layers as plain text."""

        with open(filename, "w", encoding="utf-8") as f:
            for item in screenplay.get_all_storyboard_items():
                scene = self._find_scene_for_item(screenplay, item)
                prompts = compile_all_prompts(item, screenplay, scene)

                f.write(f"=== Segment #{item.sequence_number} ({item.duration}s) ===\n\n")

                if prompts["keyframe_prompt"]:
                    f.write(f"KEYFRAME:\n{prompts['keyframe_prompt']}\n\n")
                if prompts["identity_prompt"]:
                    f.write(f"IDENTITY:\n{prompts['identity_prompt']}\n\n")
                if prompts["video_prompt"]:
                    f.write(f"VIDEO:\n{prompts['video_prompt']}\n\n")

                f.write("---\n\n")

    def export_higgsfield_format(
        self, screenplay: Screenplay, filename: str
    ) -> None:
        """Export in Higgsfield API-compatible format.

        Produces JSON ready for submission to the Higgsfield platform API.
        Each segment maps to a single API call to POST /{model_id}.
        """
        all_items = screenplay.get_all_storyboard_items()
        ss = getattr(screenplay, "story_settings", {}) or {}
        video_model = ss.get("higgsfield_model", "higgsfield-ai/dop/standard")
        image_model = ss.get("higgsfield_image_model", "higgsfield-ai/soul/standard")
        aspect_ratio = ss.get("aspect_ratio", "16:9")

        export_data = {
            "project_name": screenplay.title,
            "api_config": {
                "base_url": "https://platform.higgsfield.ai",
                "image_model": image_model,
                "video_model": video_model,
                "aspect_ratio": aspect_ratio,
            },
            "metadata": {
                "premise": screenplay.premise,
                "genre": screenplay.genre,
                "atmosphere": screenplay.atmosphere,
                "total_duration": screenplay.get_total_duration(),
                "segment_count": len(all_items),
            },
            "segments": [],
        }

        if screenplay.acts:
            export_data["metadata"]["framework"] = {
                "acts": len(screenplay.acts),
                "scenes": sum(len(act.scenes) for act in screenplay.acts),
                "story_structure": screenplay.story_structure,
            }

        for item in all_items:
            scene = self._find_scene_for_item(screenplay, item)
            prompts = compile_all_prompts(item, screenplay, scene)

            hero_path = (item.environment_start_image or "").strip()

            segment = {
                "segment_number": item.sequence_number,
                "image_model_id": image_model,
                "video_model_id": video_model,
                "duration": item.duration,
                "aspect_ratio": aspect_ratio,
                "image_path": hero_path or None,
                "image_url": None,
                "keyframe_prompt": prompts["keyframe_prompt"],
                "identity_prompt": prompts["identity_prompt"],
                "video_prompt": prompts["video_prompt"],
                "reference_images": {},
                "optics": {
                    "focal_length_mm": getattr(item, "focal_length", 35),
                    "aperture_style": getattr(item, "aperture_style", "cinematic_bokeh"),
                    "camera_motion": getattr(item, "camera_motion", "static"),
                    "shot_type": item.shot_type,
                },
            }

            # Map entity reference images
            assignments = getattr(item, "image_assignments", {}) or {}
            for slot in ("image_1", "image_2", "image_3"):
                info = assignments.get(slot)
                if not info:
                    continue
                entity_name = (info.get("entity_name") or "").strip()
                ref_path = (info.get("path") or "").strip()
                if entity_name:
                    segment["reference_images"][slot] = {
                        "entity_name": entity_name,
                        "entity_type": (info.get("entity_type") or "character"),
                        "image_path": ref_path or None,
                        "image_url": None,
                    }

            # End frame for start-to-end frame precision
            end_frame = (getattr(item, "environment_end_image", "") or "").strip()
            if end_frame:
                segment["end_frame_path"] = end_frame

            # Optional dialogue and audio metadata
            if (item.dialogue or "").strip():
                segment["dialogue"] = item.dialogue.strip()

            audio_intent = getattr(item, "audio_intent", "") or ""
            audio_notes = getattr(item, "audio_notes", "") or ""
            if audio_intent or audio_notes:
                segment["audio"] = {
                    "intent": audio_intent or None,
                    "notes": audio_notes or None,
                    "source": getattr(item, "audio_source", "none"),
                }

            export_data["segments"].append(segment)

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

    def get_export_summary(self, screenplay: Screenplay) -> Dict[str, Any]:
        """Get a summary of the screenplay for export preview."""
        all_items = screenplay.get_all_storyboard_items()

        summary = {
            "title": screenplay.title,
            "premise": screenplay.premise,
            "total_items": len(all_items),
            "total_duration": screenplay.get_total_duration_formatted(),
            "duration_breakdown": {
                "average_duration": round(
                    sum(item.duration for item in all_items) / max(len(all_items), 1),
                    1,
                ),
                "min_duration": min(
                    (item.duration for item in all_items), default=0
                ),
                "max_duration": max(
                    (item.duration for item in all_items), default=0
                ),
            },
        }

        if screenplay.acts:
            summary["framework"] = {
                "acts": len(screenplay.acts),
                "scenes": sum(len(act.scenes) for act in screenplay.acts),
                "complete_scenes": sum(
                    1
                    for act in screenplay.acts
                    for sc in act.scenes
                    if sc.is_complete
                ),
            }

        return summary

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _find_scene_for_item(
        screenplay: Screenplay, item: StoryboardItem
    ) -> Optional[object]:
        """Locate the StoryScene that owns the given item."""
        for act in getattr(screenplay, "acts", []):
            for sc in act.scenes:
                if item.item_id in [si.item_id for si in sc.storyboard_items]:
                    return sc
        return None
