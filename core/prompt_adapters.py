"""
Platform-specific prompt adapters.

Each adapter takes the three-layer prompt dict produced by
``video_prompt_builder.compile_all_prompts`` and reshapes it into the
format expected by a specific AI video generation platform.

The base class provides common helpers; subclasses override ``adapt()``
to produce the platform-optimised output.
"""

from __future__ import annotations

import csv
import json
import os
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .screenplay_engine import Screenplay, StoryboardItem, StoryScene

from .video_prompt_builder import compile_all_prompts
from .screenplay_engine import (
    CAMERA_MOTION_OPTIONS,
    SHOT_TYPE_OPTIONS,
    VISUAL_STYLE_OPTIONS,
)


# =====================================================================
#  Registry
# =====================================================================

PLATFORM_REGISTRY: Dict[str, "type[PromptAdapter]"] = {}

def _register(cls: type[PromptAdapter]) -> type[PromptAdapter]:
    PLATFORM_REGISTRY[cls.platform_id] = cls
    return cls


# =====================================================================
#  Base class
# =====================================================================

class PromptAdapter(ABC):
    """Base class for platform prompt adapters."""

    platform_id: str = ""
    platform_name: str = ""
    file_extension: str = ".txt"
    description: str = ""

    # Platform capability metadata — overridden by subclasses
    video_models: Dict[str, str] = {}
    image_models: Dict[str, str] = {}
    supports_image_generation: bool = False
    supports_multishot: bool = False
    supports_identity_lock: bool = False
    max_duration: int = 10
    max_prompt_chars: int = 2000  # per-platform prompt character limit
    duration_presets: Optional[List[int]] = None
    supported_aspect_ratios: List[str] = [
        "16:9", "9:16", "1:1", "4:3", "21:9", "2.35:1",
    ]
    api_base_url: str = ""
    api_auth_type: str = "bearer"
    config_key: str = ""

    # -- Public API ---------------------------------------------------

    @abstractmethod
    def adapt(
        self,
        keyframe: str,
        identity: str,
        video: str,
        item: "StoryboardItem",
        screenplay: "Screenplay",
    ) -> str:
        """Return a single prompt string formatted for the target platform."""

    def export(
        self,
        screenplay: "Screenplay",
        filename: str,
    ) -> None:
        """Export all storyboard items to *filename* using this adapter."""
        items = screenplay.get_all_storyboard_items()
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"# {screenplay.title}\n")
            f.write(f"# Platform: {self.platform_name}\n")
            f.write(f"# Segments: {len(items)}\n\n")

            for item in items:
                scene = self._find_scene(screenplay, item)
                prompts = compile_all_prompts(item, screenplay, scene)

                adapted = self.adapt(
                    prompts["keyframe_prompt"],
                    prompts["identity_prompt"],
                    prompts["video_prompt"],
                    item,
                    screenplay,
                )

                f.write(
                    f"=== Segment #{item.sequence_number} "
                    f"({item.duration}s) ===\n\n"
                )
                f.write(adapted.strip())
                f.write("\n\n---\n\n")

    # -- Helpers ------------------------------------------------------

    @staticmethod
    def _find_scene(
        screenplay: "Screenplay", item: "StoryboardItem"
    ) -> Optional["StoryScene"]:
        for act in getattr(screenplay, "acts", []):
            for sc in act.scenes:
                if item.item_id in [si.item_id for si in sc.storyboard_items]:
                    return sc
        return None

    @staticmethod
    def _resolve_style(item: "StoryboardItem", screenplay: "Screenplay") -> str:
        key = (getattr(item, "visual_style", "") or "").strip()
        if not key:
            ss = getattr(screenplay, "story_settings", None) or {}
            key = ss.get("visual_style") or "photorealistic"
        return VISUAL_STYLE_OPTIONS.get(key, "Photorealistic")

    @staticmethod
    def _camera_label(item: "StoryboardItem") -> str:
        key = getattr(item, "camera_motion", "static") or "static"
        return CAMERA_MOTION_OPTIONS.get(key, "Static (Locked-Off)")

    @staticmethod
    def _shot_label(item: "StoryboardItem") -> str:
        key = getattr(item, "shot_type", "wide") or "wide"
        return SHOT_TYPE_OPTIONS.get(key, "Wide Establishing Shot")

    @staticmethod
    def _strip_section_headers(text: str) -> str:
        """Remove section headers like CAMERA:, ACTION:, AUDIO:, etc."""
        return re.sub(r"^[A-Z][A-Z /]+:\s*$", "", text, flags=re.MULTILINE).strip()

    @staticmethod
    def _flatten(text: str) -> str:
        """Collapse multi-line text into a comma-separated single line."""
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        return ", ".join(lines)

    @staticmethod
    def _strip_keyframe_suffixes(keyframe: str) -> str:
        """Remove Style:, Mood:, and lens specs from the keyframe text.

        These are already added separately by adapters that merge layers,
        so including them in the keyframe would be double-counting.
        """
        text = re.sub(r"\.\s*Style:[^.]*", "", keyframe)
        text = re.sub(r"\.\s*Mood:[^.]*", "", text)
        text = re.sub(r"\.\s*\d+mm lens,\s*[^.]*", "", text)
        return text.strip().rstrip(". ")

    @staticmethod
    def _strip_video_camera(video: str) -> str:
        """Remove CAMERA: lines and AUDIO: tail from video text."""
        text = re.sub(r"(?i)^CAMERA:.*$", "", video, flags=re.MULTILINE).strip()
        audio_idx = text.find("AUDIO:")
        if audio_idx > 0:
            text = text[:audio_idx].strip()
        return text

    @staticmethod
    def _smart_truncate(text: str, max_chars: int) -> str:
        """Truncate *text* to *max_chars* at a word boundary."""
        if not text or len(text) <= max_chars:
            return text
        truncated = text[:max_chars]
        last_space = truncated.rfind(" ")
        if last_space > max_chars * 0.5:
            truncated = truncated[:last_space]
        return truncated.rstrip(" .,;:|-")


# =====================================================================
#  Higgsfield (native — pass-through)
# =====================================================================

@_register
class HiggsfieldAdapter(PromptAdapter):
    platform_id = "higgsfield"
    platform_name = "Higgsfield"
    file_extension = ".txt"
    description = "Native three-layer format (Keyframe / Identity / Video)"
    video_models = {
        "higgsfield-ai/dop/standard": "DoP Standard — high-quality animation",
        "higgsfield-ai/dop/preview": "DoP Preview — fast preview generation",
        "kling-video/v2.1/pro/image-to-video": "Kling 2.1 Pro — realistic human motion",
        "kling-video/v3.0/pro/image-to-video": "Kling 3.0 Pro — faster generation",
        "bytedance/seedance/v1/pro/image-to-video": "Seedance Pro — character motion",
    }
    image_models = {
        "higgsfield-ai/soul/standard": "Soul Standard — creative character images",
        "higgsfield-ai/soul/2.0": "Soul 2.0 — fashion-forward, cultural fluency",
        "higgsfield-ai/nano-banana/pro": "Nano Banana Pro — 4K image generation",
    }
    supports_image_generation = True
    supports_multishot = True
    supports_identity_lock = True
    max_duration = 30
    api_base_url = "https://platform.higgsfield.ai"
    api_auth_type = "key_secret"
    config_key = "higgsfield_api"
    # Higgsfield accepts three separate prompts; per-layer limit is conservative
    # since exact API limit is undocumented but UI truncation suggests ~1500–2000
    max_prompt_chars = 2000

    def adapt(self, keyframe, identity, video, item, screenplay):
        sections = []
        if keyframe:
            kf = self._smart_truncate(keyframe, self.max_prompt_chars)
            sections.append(f"KEYFRAME:\n{kf}")
        if identity:
            ident = self._smart_truncate(identity, self.max_prompt_chars)
            sections.append(f"IDENTITY:\n{ident}")
        if video:
            vid = self._smart_truncate(video, self.max_prompt_chars)
            sections.append(f"VIDEO:\n{vid}")
        return "\n\n".join(sections)


# =====================================================================
#  Runway Gen-4
# =====================================================================

@_register
class RunwayAdapter(PromptAdapter):
    platform_id = "runway"
    platform_name = "Runway"
    file_extension = ".txt"
    description = "Combined prose prompt with inline camera direction"
    max_prompt_chars = 1000  # Gen-4/Gen-4 Turbo; Gen-4.5 allows 5000
    video_models = {
        "gen4.5": "Gen-4.5 — text/image to video",
        "gen4_turbo": "Gen-4 Turbo — fast image to video",
        "gen4_aleph": "Gen-4 Aleph — high fidelity",
    }
    image_models = {}
    supports_image_generation = False
    max_duration = 10
    supported_aspect_ratios = ["16:9", "9:16", "1:1"]
    api_base_url = "https://api.dev.runwayml.com/v1"
    config_key = "runway_api"

    def adapt(self, keyframe, identity, video, item, screenplay):
        parts: List[str] = []

        style = self._resolve_style(item, screenplay)
        parts.append(f"{style} style.")

        if keyframe:
            parts.append(self._strip_keyframe_suffixes(keyframe))

        if identity:
            clean = self._strip_section_headers(identity)
            if clean:
                parts.append(clean)

        camera = self._camera_label(item)
        if camera and "static" not in camera.lower():
            parts.append(f"Camera: {camera}.")

        if video:
            motion = self._strip_section_headers(video)
            motion = self._strip_video_camera(motion)
            if motion:
                parts.append(motion)

        parts.append(f"Duration: {item.duration} seconds.")
        result = " ".join(p.strip() for p in parts if p.strip())
        return self._smart_truncate(result, 1000)


# =====================================================================
#  Pika Labs
# =====================================================================

@_register
class PikaAdapter(PromptAdapter):
    platform_id = "pika"
    platform_name = "Pika"
    file_extension = ".txt"
    description = "Concise comma-separated style tokens"
    max_prompt_chars = 1500
    video_models = {
        "pika-2.5": "Pika 2.5 — latest generation",
        "pika-2.2": "Pika 2.2 — stable generation",
    }
    image_models = {}
    supports_image_generation = False
    max_duration = 5
    supported_aspect_ratios = ["16:9", "9:16", "1:1"]
    api_base_url = "https://fal.run/fal-ai/pika"
    api_auth_type = "bearer"
    config_key = "pika_api"

    def adapt(self, keyframe, identity, video, item, screenplay):
        tokens: List[str] = []

        tokens.append(self._resolve_style(item, screenplay).lower())
        tokens.append(self._shot_label(item).lower())

        if keyframe:
            clean = self._strip_keyframe_suffixes(keyframe)
            tokens.append(self._flatten(clean).lower())

        camera = self._camera_label(item)
        if "static" not in camera.lower():
            tokens.append(camera.lower())

        mood = (getattr(item, "mood_tone", "") or "").strip()
        if mood:
            tokens.append(mood.lower())

        lighting = (getattr(item, "lighting_description", "") or "").strip()
        if lighting:
            tokens.append(lighting.lower())

        focal = getattr(item, "focal_length", 35) or 35
        tokens.append(f"{focal}mm lens")

        seen: set = set()
        unique: List[str] = []
        for t in tokens:
            t = t.strip().rstrip(",. ")
            if t and t not in seen:
                seen.add(t)
                unique.append(t)
        result = ", ".join(unique)
        return self._smart_truncate(result, 1500)


# =====================================================================
#  Kling (direct — outside Higgsfield)
# =====================================================================

@_register
class KlingAdapter(PromptAdapter):
    platform_id = "kling"
    platform_name = "Kling"
    file_extension = ".txt"
    description = "Natural-language scene prompt optimised for Kling models"
    max_prompt_chars = 2500
    video_models = {
        "o3-pro": "O3 Pro — flagship quality",
        "o3-std": "O3 Standard — balanced",
        "kling-3.0-pro": "Kling 3.0 Pro — fast high quality",
        "kling-3.0-std": "Kling 3.0 Standard — everyday use",
        "kling-2.6-pro": "Kling 2.6 Pro — proven model",
    }
    image_models = {}
    supports_image_generation = False
    max_duration = 15
    supported_aspect_ratios = ["16:9", "9:16", "1:1"]
    api_base_url = "https://klingapi.com/v1"
    config_key = "kling_api"

    def adapt(self, keyframe, identity, video, item, screenplay):
        parts: List[str] = []

        style = self._resolve_style(item, screenplay)
        parts.append(f"{style}.")

        if keyframe:
            parts.append(self._strip_keyframe_suffixes(keyframe))

        if identity:
            clean = self._strip_section_headers(identity)
            id_lines = [
                ln for ln in clean.splitlines()
                if ln.strip() and "wardrobe" not in ln.lower()
            ]
            if id_lines:
                parts.append(" ".join(ln.strip() for ln in id_lines))

        if video:
            motion = self._strip_section_headers(video)
            motion = self._strip_video_camera(motion)
            if motion:
                parts.append(motion)

        result = " ".join(p.strip() for p in parts if p.strip())
        return self._smart_truncate(result, 2500)


# =====================================================================
#  Sora
# =====================================================================

@_register
class SoraAdapter(PromptAdapter):
    platform_id = "sora"
    platform_name = "Sora"
    file_extension = ".txt"
    description = "Natural-language cinematic description for OpenAI Sora"
    max_prompt_chars = 32000
    video_models = {
        "sora-2": "Sora 2 — standard generation",
        "sora-2-pro": "Sora 2 Pro — higher quality",
    }
    image_models = {}
    supports_image_generation = False
    max_duration = 12
    duration_presets = [4, 8, 12]
    supported_aspect_ratios = ["16:9", "9:16", "1:1"]
    api_base_url = "https://api.openai.com/v1"
    config_key = "openai_api"

    def adapt(self, keyframe, identity, video, item, screenplay):
        paragraphs: List[str] = []

        style = self._resolve_style(item, screenplay)
        shot = self._shot_label(item)
        focal = getattr(item, "focal_length", 35) or 35
        paragraphs.append(
            f"A {style.lower()}, cinematic {shot.lower()} "
            f"shot on a {focal}mm lens."
        )

        storyline = (item.storyline or "").strip()
        if storyline:
            paragraphs.append(storyline)
        elif keyframe:
            paragraphs.append(self._strip_keyframe_suffixes(keyframe))

        if identity:
            clean = self._strip_section_headers(identity)
            if clean:
                paragraphs.append(clean)

        camera = self._camera_label(item)
        if "static" not in camera.lower():
            paragraphs.append(f"The camera executes a {camera.lower()}.")

        if video:
            motion = self._strip_section_headers(video)
            motion = self._strip_video_camera(motion)
            if motion:
                paragraphs.append(motion)

        mood = (getattr(item, "mood_tone", "") or "").strip()
        if mood:
            paragraphs.append(f"The mood is {mood.lower()}.")

        lighting = (getattr(item, "lighting_description", "") or "").strip()
        if lighting:
            paragraphs.append(f"Lighting: {lighting.lower()}.")

        return "\n\n".join(p.strip() for p in paragraphs if p.strip())


# =====================================================================
#  Veo (Google)
# =====================================================================

@_register
class VeoAdapter(PromptAdapter):
    platform_id = "veo"
    platform_name = "Veo"
    file_extension = ".txt"
    description = "Descriptive prose prompt for Google Veo"
    max_prompt_chars = 1000
    video_models = {
        "veo-3.1-generate": "Veo 3.1 — latest generation",
        "veo-3.0-generate": "Veo 3.0 — stable generation",
        "veo-3.1-fast": "Veo 3.1 Fast — quick turnaround",
        "veo-3.0-fast": "Veo 3.0 Fast — quick turnaround",
    }
    image_models = {}
    supports_image_generation = False
    max_duration = 8
    duration_presets = [4, 6, 8]
    supported_aspect_ratios = ["16:9", "9:16"]
    api_base_url = "https://generativelanguage.googleapis.com/v1beta"
    api_auth_type = "google"
    config_key = "google_api"

    def adapt(self, keyframe, identity, video, item, screenplay):
        parts: List[str] = []

        style = self._resolve_style(item, screenplay)
        parts.append(f"{style} cinematic footage.")

        if keyframe:
            parts.append(self._strip_keyframe_suffixes(keyframe))

        if identity:
            clean = self._strip_section_headers(identity)
            if clean:
                parts.append(clean)

        camera = self._camera_label(item)
        if "static" not in camera.lower():
            parts.append(f"Camera movement: {camera.lower()}.")

        if video:
            motion = self._strip_section_headers(video)
            motion = self._strip_video_camera(motion)
            if motion:
                parts.append(motion)

        mood = (getattr(item, "mood_tone", "") or "").strip()
        if mood:
            parts.append(f"Mood: {mood.lower()}.")

        result = " ".join(p.strip() for p in parts if p.strip())
        return self._smart_truncate(result, 1000)


# =====================================================================
#  Minimax / Hailuo
# =====================================================================

@_register
class MinimaxAdapter(PromptAdapter):
    platform_id = "minimax"
    platform_name = "Minimax / Hailuo"
    file_extension = ".txt"
    description = "Keyword-rich single prompt for Minimax and Hailuo"
    max_prompt_chars = 2000
    video_models = {
        "hailuo-2.3": "Hailuo 2.3 — latest, multi-subject",
        "hailuo-02": "Hailuo 02 — stable generation",
    }
    image_models = {}
    supports_image_generation = False
    max_duration = 10
    duration_presets = [5, 10]
    supported_aspect_ratios = ["16:9", "9:16", "1:1"]
    api_base_url = "https://api.aimlapi.com/v2"
    config_key = "minimax_api"

    def adapt(self, keyframe, identity, video, item, screenplay):
        tokens: List[str] = []

        tokens.append(self._resolve_style(item, screenplay))
        tokens.append(self._shot_label(item))

        if keyframe:
            tokens.append(self._strip_keyframe_suffixes(keyframe))

        camera = self._camera_label(item)
        if "static" not in camera.lower():
            tokens.append(f"camera: {camera}")

        if video:
            motion = self._strip_section_headers(video)
            motion = self._strip_video_camera(motion)
            if motion:
                tokens.append(motion)

        mood = (getattr(item, "mood_tone", "") or "").strip()
        if mood:
            tokens.append(mood)

        lighting = (getattr(item, "lighting_description", "") or "").strip()
        if lighting:
            tokens.append(lighting)

        result = ". ".join(t.strip().rstrip(". ") for t in tokens if t.strip())
        return self._smart_truncate(result, 2000)


# =====================================================================
#  LumaLabs (Dream Machine)
# =====================================================================

@_register
class LumaAdapter(PromptAdapter):
    platform_id = "luma"
    platform_name = "Luma Dream Machine"
    file_extension = ".txt"
    description = "Scene-focused prompt for Luma Labs Dream Machine"
    max_prompt_chars = 2000
    video_models = {
        "ray-2": "Ray 2 — high quality generation",
        "ray-flash-2": "Ray Flash 2 — fast generation",
    }
    image_models = {}
    supports_image_generation = False
    max_duration = 10
    supported_aspect_ratios = ["16:9", "9:16", "1:1", "4:3", "3:4"]
    api_base_url = "https://api.lumalabs.ai/dream-machine/v1"
    config_key = "luma_api"

    def adapt(self, keyframe, identity, video, item, screenplay):
        parts: List[str] = []

        style = self._resolve_style(item, screenplay)
        shot = self._shot_label(item)
        parts.append(f"{style}, {shot.lower()}.")

        storyline = (item.storyline or "").strip()
        if storyline:
            parts.append(storyline)
        elif keyframe:
            parts.append(self._strip_keyframe_suffixes(keyframe))

        camera = self._camera_label(item)
        if "static" not in camera.lower():
            parts.append(f"Camera: {camera.lower()}.")

        mood = (getattr(item, "mood_tone", "") or "").strip()
        lighting = (getattr(item, "lighting_description", "") or "").strip()
        if mood and lighting:
            parts.append(f"{mood}, {lighting.lower()}.")
        elif mood:
            parts.append(f"{mood}.")
        elif lighting:
            parts.append(f"{lighting}.")

        result = " ".join(p.strip() for p in parts if p.strip())
        return self._smart_truncate(result, 2000)


# =====================================================================
#  Public helpers
# =====================================================================

def get_available_platforms() -> List[Dict[str, str]]:
    """Return list of registered platforms for UI display."""
    return [
        {
            "id": cls.platform_id,
            "name": cls.platform_name,
            "description": cls.description,
        }
        for cls in PLATFORM_REGISTRY.values()
    ]


def get_adapter(platform_id: str) -> Optional[PromptAdapter]:
    """Instantiate and return the adapter for *platform_id*, or None."""
    cls = PLATFORM_REGISTRY.get(platform_id)
    return cls() if cls else None


def get_adapter_class(platform_id: str) -> Optional[type[PromptAdapter]]:
    """Return the adapter *class* (not an instance) for *platform_id*."""
    return PLATFORM_REGISTRY.get(platform_id)
