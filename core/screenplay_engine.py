"""
Core screenplay data models and engine for SceneWrite.

Source-of-truth hierarchy (narrative consistency): (1) Premise, (2) Story Structure
(scene summaries), (3) Scene Content, (4) Storyboard. Lower layers must not contradict
higher layers; if conflict, higher layer wins and content must be regenerated.
"""

from __future__ import annotations

from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
import datetime
from enum import Enum
import json


def _safe_print(*args, **kwargs):
    """Route output through debug_log instead of stdout (hidden in production)."""
    try:
        from debug_log import debug_log as _dl
        _dl(" ".join(str(a) for a in args))
    except Exception:
        pass
import os
import uuid

def get_default_story_settings() -> Dict[str, Any]:
    """Return the default per-project story settings dict.

    Used both for new projects and for backward-compatible migration of
    projects saved before story_settings existed.
    """
    return {
        "generation_platform": "higgsfield",
        "supports_multishot": False,
        "max_generation_duration_seconds": 15,
        "aspect_ratio": "16:9",
        "visual_style": "photorealistic",
        "identity_lock_strength": "standard",
        "cinematic_beat_density": "balanced",
        "camera_movement_intensity": "subtle",
        "prompt_output_format": "cinematic_script",
        "video_model": "higgsfield-ai/dop/standard",
        "image_model": "higgsfield-ai/soul/standard",
        "default_focal_length": 35,
        "platform_config": {},
        "content_rating": "unrestricted",
        "audio_settings": {
            "dialogue_generation_mode": "generate",
            "sfx_density": "cinematic",
            "music_strategy": "ambient",
        },
    }


class SceneType(Enum):
    """Types of storyboard scenes."""
    ACTION = "action"
    DIALOGUE = "dialogue"
    TRANSITION = "transition"
    ESTABLISHING = "establishing"
    CLOSEUP = "closeup"
    WIDE_SHOT = "wide_shot"
    MONTAGE = "montage"

SHOT_TYPE_OPTIONS = {
    "wide": "Wide Establishing Shot",
    "medium": "Medium Shot",
    "close_up": "Close-Up",
    "extreme_close_up": "Extreme Close-Up",
    "over_shoulder": "Over the Shoulder",
    "two_shot": "Two Shot",
    "birds_eye": "Bird's Eye View",
    "low_angle": "Low Angle",
    "high_angle": "High Angle",
    "dutch_angle": "Dutch Angle",
}

CAMERA_MOTION_OPTIONS = {
    "static": "Static (Locked-Off)",
    "slow_dolly_in": "Slow Dolly In",
    "slow_dolly_out": "Slow Dolly Out",
    "orbit": "Orbit Around Subject",
    "tracking": "Tracking Shot",
    "handheld": "Handheld Shake",
    "crash_zoom": "Crash Zoom",
    "fpv_drone": "FPV / Drone",
    "slow_pan_left": "Slow Pan Left",
    "slow_pan_right": "Slow Pan Right",
    "tilt_up": "Tilt Up",
    "tilt_down": "Tilt Down",
    "crane_up": "Crane Up",
    "crane_down": "Crane Down",
    "push_in": "Push In",
    "pull_out": "Pull Out",
}

APERTURE_STYLE_OPTIONS = {
    "shallow": "Shallow Depth of Field",
    "deep": "Deep Focus (Everything Sharp)",
    "cinematic_bokeh": "Cinematic Bokeh",
    "natural": "Natural",
}

VISUAL_STYLE_OPTIONS = {
    "photorealistic": "Photorealistic",
    "anime_cartoon": "Anime / Cartoon",
    "3d_cartoon_pixar": "3D Cartoon",
    "vintage_retro": "Vintage / Retro",
    "film_noir": "Film Noir",
    "watercolor": "Watercolor / Painted",
    "comic_book": "Comic Book / Graphic Novel",
    "cyberpunk_neon": "Cyberpunk / Neon",
    "fantasy_storybook": "Fantasy / Storybook",
    "minimalist_flat": "Minimalist / Flat Design",
    "dreamy_ethereal": "Dreamy / Ethereal",
    "dark_gritty": "Dark & Gritty",
    "art_deco": "Art Deco",
    "pencil_sketch": "Pencil Sketch / Storyboard",
    "oil_painting": "Oil Painting",
    "vaporwave_synthwave": "Vaporwave / Synthwave",
    "documentary_raw": "Documentary / Raw",
    "grindhouse_70s": "70s Grindhouse",
}

CONTENT_RATING_OPTIONS = {
    "unrestricted": "Unrestricted",
    "teen": "Teen (PG-13)",
    "family_friendly": "Family Friendly (PG)",
    "child_safe": "Child Safe (G)",
}

FOCAL_LENGTH_RANGE = (8, 50)  # mm — matches Cinema Studio 2.0 optics

@dataclass
class BrandContext:
    """Brand and product context for promotional workflows."""
    brand_name: str = ""
    product_name: str = ""
    product_description: str = ""  # Required for promotional workflows
    core_benefit: str = ""  # Required for promotional workflows
    target_audience: str = ""
    brand_personality: List[str] = field(default_factory=list)  # e.g., ["Innovative", "Trustworthy", "Playful"]
    mandatory_elements: List[str] = field(default_factory=list)  # e.g., ["logo reveal", "product shot", "tagline text"]
    emotional_anchor: str = ""  # e.g., "Freedom", "Confidence", "Innovation"
    distribution_platform: str = ""  # "social", "youtube_preroll", "tvc", "website_hero" (preparation layer)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert brand context to dictionary."""
        return {
            "brand_name": self.brand_name,
            "product_name": self.product_name,
            "product_description": self.product_description,
            "core_benefit": self.core_benefit,
            "target_audience": self.target_audience,
            "brand_personality": self.brand_personality,
            "mandatory_elements": self.mandatory_elements,
            "emotional_anchor": self.emotional_anchor,
            "distribution_platform": self.distribution_platform,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BrandContext':
        """Create brand context from dictionary."""
        return cls(
            brand_name=data.get("brand_name", ""),
            product_name=data.get("product_name", ""),
            product_description=data.get("product_description", ""),
            core_benefit=data.get("core_benefit", ""),
            target_audience=data.get("target_audience", ""),
            brand_personality=data.get("brand_personality", []),
            mandatory_elements=data.get("mandatory_elements", []),
            emotional_anchor=data.get("emotional_anchor", ""),
            distribution_platform=data.get("distribution_platform", ""),
        )
    
    def is_valid(self) -> bool:
        """Check if brand context has required fields for promotional workflows."""
        return bool(self.product_description.strip() and self.core_benefit.strip())

@dataclass
class ShotTransition:
    """Describes the transition between two consecutive shots in a multi-shot cluster."""
    from_shot: int
    to_shot: int
    transition_type: str  # seamless_cut, match_cut, whip_pan, motivated_camera_move, push_in_continuation, rack_focus, environmental_occlusion_cut
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_shot": self.from_shot,
            "to_shot": self.to_shot,
            "transition_type": self.transition_type,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ShotTransition':
        return cls(
            from_shot=data["from_shot"],
            to_shot=data["to_shot"],
            transition_type=data.get("transition_type", "seamless_cut"),
            description=data.get("description", ""),
        )


ALLOWED_TRANSITION_TYPES = frozenset({
    "seamless_cut",
    "match_cut",
    "whip_pan",
    "motivated_camera_move",
    "push_in_continuation",
    "rack_focus",
    "environmental_occlusion_cut",
})


@dataclass
class MultiShotCluster:
    """A group of consecutive storyboard items rendered as one multi-shot video clip."""
    cluster_id: str
    scene_id: str
    item_ids: List[str]
    total_duration: int
    environment_id: str
    primary_characters: List[str]
    vehicles: List[str]
    shots: List[Dict[str, Any]]
    transitions: List[ShotTransition]
    identity_lock_refs: Dict[str, str]
    generation_prompt: str = ""
    transition_complexity: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "scene_id": self.scene_id,
            "item_ids": self.item_ids,
            "total_duration": self.total_duration,
            "environment_id": self.environment_id,
            "primary_characters": self.primary_characters,
            "vehicles": self.vehicles,
            "shots": self.shots,
            "transitions": [t.to_dict() for t in self.transitions],
            "identity_lock_refs": self.identity_lock_refs,
            "generation_prompt": self.generation_prompt,
            "transition_complexity": self.transition_complexity,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MultiShotCluster':
        return cls(
            cluster_id=data["cluster_id"],
            scene_id=data["scene_id"],
            item_ids=data.get("item_ids", []),
            total_duration=data.get("total_duration", 0),
            environment_id=data.get("environment_id", ""),
            primary_characters=data.get("primary_characters", []),
            vehicles=data.get("vehicles", []),
            shots=data.get("shots", []),
            transitions=[ShotTransition.from_dict(t) for t in data.get("transitions", [])],
            identity_lock_refs=data.get("identity_lock_refs", {}),
            generation_prompt=data.get("generation_prompt", ""),
            transition_complexity=data.get("transition_complexity", 0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class StoryAct:
    """Represents an act in the screenplay (Act 1, Act 2, Act 3, etc.)."""
    act_number: int
    title: str
    description: str = ""
    plot_points: List[str] = field(default_factory=list)  # e.g., "Inciting Incident", "Midpoint", "Climax"
    character_arcs: Dict[str, str] = field(default_factory=dict)  # character name -> arc description
    scenes: List['StoryScene'] = field(default_factory=list)
    pacing_notes: str = ""
    created_at: str = ""
    updated_at: str = ""
    
    def __post_init__(self):
        """Initialize timestamps if not provided."""
        if not self.created_at:
            self.created_at = datetime.datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = datetime.datetime.now().isoformat()
    
    def add_scene(self, scene: 'StoryScene') -> None:
        """Add a scene to this act."""
        self.scenes.append(scene)
        self.scenes.sort(key=lambda x: x.scene_number)
        self.updated_at = datetime.datetime.now().isoformat()
    
    def get_scene(self, scene_id: str) -> Optional['StoryScene']:
        """Get a scene by ID."""
        for scene in self.scenes:
            if scene.scene_id == scene_id:
                return scene
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert act to dictionary."""
        return {
            "act_number": self.act_number,
            "title": self.title,
            "description": self.description,
            "plot_points": self.plot_points,
            "character_arcs": self.character_arcs,
            "scenes": [scene.to_dict() for scene in self.scenes],
            "pacing_notes": self.pacing_notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StoryAct':
        """Create act from dictionary."""
        act = cls(
            act_number=data["act_number"],
            title=data["title"],
            description=data.get("description", ""),
            plot_points=data.get("plot_points", []),
            character_arcs=data.get("character_arcs", {}),
            pacing_notes=data.get("pacing_notes", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", "")
        )
        # Load scenes
        for scene_data in data.get("scenes", []):
            act.add_scene(StoryScene.from_dict(scene_data))
        return act

@dataclass
class WardrobeVariant:
    """A single wardrobe look for a character, backed by a reference image."""
    variant_id: str
    label: str = ""              # e.g. "Mill Outfit", "Night Coat"
    description: str = ""        # Clothing notes (auto-filled from scene extraction)
    wardrobe_prompt: str = ""    # Legacy field kept for backward compatibility
    identity_block: str = ""     # Generated identity block for this wardrobe variant
    reference_image_prompt: str = ""  # Approved reference image prompt for this variant
    image_path: str = ""         # Absolute path to uploaded wardrobe image
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "variant_id": self.variant_id,
            "label": self.label,
            "description": self.description,
            "wardrobe_prompt": self.wardrobe_prompt,
            "identity_block": self.identity_block,
            "reference_image_prompt": self.reference_image_prompt,
            "image_path": self.image_path,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WardrobeVariant':
        return cls(
            variant_id=data.get("variant_id", str(uuid.uuid4())[:8]),
            label=data.get("label", ""),
            description=data.get("description", ""),
            wardrobe_prompt=data.get("wardrobe_prompt", ""),
            identity_block=data.get("identity_block", ""),
            reference_image_prompt=data.get("reference_image_prompt", ""),
            image_path=data.get("image_path", ""),
            created_at=data.get("created_at", ""),
        )


@dataclass
class StoryScene:
    """Represents a scene within an act."""
    scene_id: str
    scene_number: int  # Within act
    title: str
    description: str = ""  # 3-5 sentences: plot progression, character development
    plot_point: Optional[str] = None  # e.g., "Inciting Incident", "First Plot Point", "Midpoint"
    character_focus: List[str] = field(default_factory=list)  # Characters featured in this scene
    pacing: str = "Medium"  # "Fast", "Medium", "Slow"
    estimated_duration: int = 0  # seconds
    storyboard_items: List['StoryboardItem'] = field(default_factory=list)  # Detailed prompts created in Phase 2
    is_complete: bool = False  # Whether Phase 2 is done
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    environment_block: Optional[str] = None  # Static environment description for Higgsfield first-frame prompts
    environment_id: Optional[str] = None  # Unique ID for environment tracking
    compression_strategy: str = "beat_by_beat"  # "montage", "beat_by_beat", or "atmospheric_hold"
    character_wardrobe: Dict[str, str] = field(default_factory=dict)  # entity_id -> wardrobe description (legacy text)
    # Wardrobe variant system
    character_wardrobe_variant_ids: Dict[str, str] = field(default_factory=dict)   # entity_id -> selected variant_id
    character_wardrobe_selector: Dict[str, str] = field(default_factory=dict)      # entity_id -> "same"|"change"|"change_in_scene"
    # Advertisement mode fields
    ad_beat_type: str = ""  # "hook", "pain_desire", "product_reveal", "feature_demo", "emotional_payoff", "brand_moment"
    is_product_reveal: bool = False  # True if this scene is the product introduction moment
    is_brand_hero_shot: bool = False  # True if this scene is the brand moment (logo/tagline/CTA)
    # Multi-shot clustering
    generation_strategy: str = "auto"  # "auto", "single_shot", "multi_shot_cluster"
    multishot_clusters: List['MultiShotCluster'] = field(default_factory=list)
    # Visual Art mode style
    visual_art_style: str = "progressive"  # "progressive" (evolving) or "looping" (seamless loop)
    
    def __post_init__(self):
        """Initialize timestamps if not provided."""
        if not self.created_at:
            self.created_at = datetime.datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = datetime.datetime.now().isoformat()
    
    def add_storyboard_item(self, item: StoryboardItem) -> None:
        """Add a storyboard item to this scene."""
        self.storyboard_items.append(item)
        self.storyboard_items.sort(key=lambda x: x.sequence_number)
        self.updated_at = datetime.datetime.now().isoformat()
        # Mark as complete if has items
        if self.storyboard_items:
            self.is_complete = True
    
    def get_storyboard_item(self, item_id: str) -> Optional[StoryboardItem]:
        """Get a storyboard item by ID."""
        for item in self.storyboard_items:
            if item.item_id == item_id:
                return item
        return None
    
    def get_total_duration(self) -> int:
        """Get total duration of all storyboard items in seconds."""
        return sum(item.duration for item in self.storyboard_items)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert scene to dictionary."""
        return {
            "scene_id": self.scene_id,
            "scene_number": self.scene_number,
            "title": self.title,
            "description": self.description,
            "plot_point": self.plot_point,
            "character_focus": self.character_focus,
            "pacing": self.pacing,
            "estimated_duration": self.estimated_duration,
            "storyboard_items": [item.to_dict() for item in self.storyboard_items],
            "is_complete": self.is_complete,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "environment_block": self.environment_block,
            "environment_id": self.environment_id,
            "compression_strategy": getattr(self, "compression_strategy", "beat_by_beat"),  # Backward compatible
            "character_wardrobe": getattr(self, "character_wardrobe", {}),
            "character_wardrobe_variant_ids": getattr(self, "character_wardrobe_variant_ids", {}),
            "character_wardrobe_selector": getattr(self, "character_wardrobe_selector", {}),
            "ad_beat_type": getattr(self, "ad_beat_type", ""),
            "is_product_reveal": getattr(self, "is_product_reveal", False),
            "is_brand_hero_shot": getattr(self, "is_brand_hero_shot", False),
            "generation_strategy": getattr(self, "generation_strategy", "auto"),
            "multishot_clusters": [c.to_dict() for c in getattr(self, "multishot_clusters", [])],
            "visual_art_style": getattr(self, "visual_art_style", "progressive"),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StoryScene':
        """Create scene from dictionary."""
        scene = cls(
            scene_id=data["scene_id"],
            scene_number=data["scene_number"],
            title=data["title"],
            description=data.get("description", ""),
            plot_point=data.get("plot_point"),
            character_focus=data.get("character_focus", []),
            pacing=data.get("pacing", "Medium"),
            estimated_duration=data.get("estimated_duration", 0),
            is_complete=data.get("is_complete", False),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            environment_block=data.get("environment_block"),
            environment_id=data.get("environment_id")
        )
        # Set optional compression_strategy field
        if "compression_strategy" in data:
            scene.compression_strategy = data["compression_strategy"]
        # Load character wardrobe (scene-level clothing per character)
        if "character_wardrobe" in data and isinstance(data["character_wardrobe"], dict):
            scene.character_wardrobe = dict(data["character_wardrobe"])
        if "character_wardrobe_variant_ids" in data and isinstance(data["character_wardrobe_variant_ids"], dict):
            scene.character_wardrobe_variant_ids = dict(data["character_wardrobe_variant_ids"])
        if "character_wardrobe_selector" in data and isinstance(data["character_wardrobe_selector"], dict):
            scene.character_wardrobe_selector = dict(data["character_wardrobe_selector"])
        # Advertisement mode fields
        if "ad_beat_type" in data:
            scene.ad_beat_type = data["ad_beat_type"]
        if "is_product_reveal" in data:
            scene.is_product_reveal = bool(data["is_product_reveal"])
        if "is_brand_hero_shot" in data:
            scene.is_brand_hero_shot = bool(data["is_brand_hero_shot"])
        if "generation_strategy" in data:
            scene.generation_strategy = data["generation_strategy"]
        if "visual_art_style" in data:
            scene.visual_art_style = data["visual_art_style"]
        for cluster_data in data.get("multishot_clusters", []):
            scene.multishot_clusters.append(MultiShotCluster.from_dict(cluster_data))
        # Load storyboard items
        for item_data in data.get("storyboard_items", []):
            scene.add_storyboard_item(StoryboardItem.from_dict(item_data))
        return scene

@dataclass
class StoryboardItem:
    """Represents a single storyboard item (video segment)."""
    item_id: str
    sequence_number: int
    duration: int  # seconds (1-30, AI-determined optimal value)
    storyline: str = ""  # Narrative description of what happens in this item (for user reference)
    image_prompt: str = ""  # Prompt for generating the establishing image (photorealistic)
    prompt: str = ""  # Video generation prompt for higgsfield.ai
    visual_description: str = ""
    dialogue: str = ""
    scene_type: SceneType = SceneType.ACTION
    camera_notes: str = ""
    # Optional audio layer (decoupled from visual)
    audio_intent: str = ""  # Short description of intended audio/sound design
    audio_notes: str = ""  # Free-form notes for post or generation
    audio_source: str = "none"  # "generated", "post", "none"
    render_cost: str = "unknown"  # "easy", "moderate", "expensive" - render complexity indicator
    render_cost_factors: Dict[str, Any] = field(default_factory=dict)  # Breakdown of cost factors
    identity_drift_warnings: List[str] = field(default_factory=list)  # Warnings about identity inconsistencies
    validation_status: str = ""  # "", "passed", "validation_failed"
    validation_errors: List[str] = field(default_factory=list)
    source_paragraph_index: int = -1  # Which paragraph [#] this item maps to
    is_hero_shot: bool = False  # Advertisement mode: clean product hero shot
    # Multi-shot clustering
    cluster_id: Optional[str] = None
    shot_number_in_cluster: Optional[int] = None
    # Video Prompt Builder — image mapping
    environment_start_image: str = ""
    environment_end_image: str = ""
    hero_frame_entity_id: str = ""
    end_frame_entity_id: str = ""
    image_assignments: Dict[str, Dict[str, str]] = field(default_factory=dict)
    shot_type: str = "wide"
    visual_style: str = ""  # Per-item override; empty = use project default
    # Cinema Studio 2.0 optics
    focal_length: int = 35
    aperture_style: str = "cinematic_bokeh"
    camera_motion: str = "static"
    mood_tone: str = ""
    lighting_description: str = ""
    composition_notes: str = ""  # Blocking: entity positions, facing directions, spatial relationships
    prompts_generated: bool = False  # True after user clicks "Generate All Prompts"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    
    def __post_init__(self):
        """Initialize timestamps if not provided."""
        if not self.created_at:
            self.created_at = datetime.datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = datetime.datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert storyboard item to dictionary."""
        return {
            "item_id": self.item_id,
            "sequence_number": self.sequence_number,
            "duration": self.duration,
            "storyline": self.storyline,
            "image_prompt": self.image_prompt,
            "prompt": self.prompt,
            "visual_description": self.visual_description,
            "dialogue": self.dialogue,
            "scene_type": self.scene_type.value,
            "camera_notes": self.camera_notes,
            "audio_intent": getattr(self, "audio_intent", ""),
            "audio_notes": getattr(self, "audio_notes", ""),
            "audio_source": getattr(self, "audio_source", "none"),
            "render_cost": getattr(self, "render_cost", "unknown"),  # Backward compatible
            "render_cost_factors": getattr(self, "render_cost_factors", {}),  # Backward compatible
            "identity_drift_warnings": getattr(self, "identity_drift_warnings", []),  # Backward compatible
            "validation_status": getattr(self, "validation_status", ""),
            "validation_errors": getattr(self, "validation_errors", []),
            "source_paragraph_index": getattr(self, "source_paragraph_index", -1),
            "is_hero_shot": getattr(self, "is_hero_shot", False),
            "cluster_id": getattr(self, "cluster_id", None),
            "shot_number_in_cluster": getattr(self, "shot_number_in_cluster", None),
            "environment_start_image": getattr(self, "environment_start_image", ""),
            "environment_end_image": getattr(self, "environment_end_image", ""),
            "hero_frame_entity_id": getattr(self, "hero_frame_entity_id", ""),
            "end_frame_entity_id": getattr(self, "end_frame_entity_id", ""),
            "image_assignments": getattr(self, "image_assignments", {}),
            "shot_type": getattr(self, "shot_type", "wide"),
            "visual_style": getattr(self, "visual_style", ""),
            "focal_length": getattr(self, "focal_length", 35),
            "aperture_style": getattr(self, "aperture_style", "cinematic_bokeh"),
            "camera_motion": getattr(self, "camera_motion", "static"),
            "mood_tone": getattr(self, "mood_tone", ""),
            "lighting_description": getattr(self, "lighting_description", ""),
            "composition_notes": getattr(self, "composition_notes", ""),
            "prompts_generated": getattr(self, "prompts_generated", False),
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StoryboardItem':
        """Create storyboard item from dictionary."""
        item = cls(
            item_id=data["item_id"],
            sequence_number=data["sequence_number"],
            duration=data["duration"],
            storyline=data.get("storyline", ""),
            image_prompt=data.get("image_prompt", ""),
            prompt=data.get("prompt", ""),
            visual_description=data.get("visual_description", ""),
            dialogue=data.get("dialogue", ""),
            scene_type=SceneType(data.get("scene_type", "action")),
            camera_notes=data.get("camera_notes", ""),
            audio_intent=data.get("audio_intent", ""),
            audio_notes=data.get("audio_notes", ""),
            audio_source=data.get("audio_source", "none"),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", "")
        )
        if "render_cost" in data:
            item.render_cost = data["render_cost"]
        if "render_cost_factors" in data:
            item.render_cost_factors = data["render_cost_factors"]
        if "identity_drift_warnings" in data:
            item.identity_drift_warnings = data["identity_drift_warnings"]
        if "validation_status" in data:
            item.validation_status = data["validation_status"]
        if "validation_errors" in data:
            item.validation_errors = data["validation_errors"]
        if "source_paragraph_index" in data:
            item.source_paragraph_index = data["source_paragraph_index"]
        if "is_hero_shot" in data:
            item.is_hero_shot = bool(data["is_hero_shot"])
        if "cluster_id" in data:
            item.cluster_id = data["cluster_id"]
        if "shot_number_in_cluster" in data:
            item.shot_number_in_cluster = data["shot_number_in_cluster"]
        if "environment_start_image" in data:
            item.environment_start_image = data["environment_start_image"]
        if "environment_end_image" in data:
            item.environment_end_image = data["environment_end_image"]
        if "hero_frame_entity_id" in data:
            item.hero_frame_entity_id = data["hero_frame_entity_id"]
        if "end_frame_entity_id" in data:
            item.end_frame_entity_id = data["end_frame_entity_id"]
        if "image_assignments" in data:
            item.image_assignments = data["image_assignments"]
        if "shot_type" in data:
            item.shot_type = data["shot_type"]
        if "visual_style" in data:
            item.visual_style = data["visual_style"]
        if "focal_length" in data:
            item.focal_length = data["focal_length"]
        if "aperture_style" in data:
            item.aperture_style = data["aperture_style"]
        if "camera_motion" in data:
            item.camera_motion = data["camera_motion"]
        if "mood_tone" in data:
            item.mood_tone = data["mood_tone"]
        if "lighting_description" in data:
            item.lighting_description = data["lighting_description"]
        if "composition_notes" in data:
            item.composition_notes = data["composition_notes"]
        if "prompts_generated" in data:
            item.prompts_generated = bool(data["prompts_generated"])
        return item

class Screenplay:
    """Main screenplay class managing the storyboard."""
    
    def __init__(self, title: str = "", premise: str = ""):
        self.title = title
        self.premise = premise
        self.genre: List[str] = []
        self.atmosphere: str = ""
        self.story_length: str = "medium"  # micro, short, medium, long, custom (from wizard)
        self.custom_duration_seconds: int = 0  # 0 = not custom; >0 = target total duration in seconds
        self.intent: str = "General Story"  # Story intent (General Story, Advertisement, Social Media, Visual Art)
        self.audio_strategy: str = "generated_with_video"  # "generated_with_video", "added_in_post", "no_audio"
        self.story_settings: Dict[str, Any] = get_default_story_settings()
        # Story outline (from wizard Step 2)
        self.story_outline: Dict[str, Any] = {}  # subplots, characters, conclusion
        # New structure: acts and scenes
        self.acts: List[StoryAct] = []
        self.story_structure: Dict[str, Any] = {}  # Overall plot structure, character arcs, themes
        self.framework_complete: bool = False  # Phase 1 done
        # Legacy: keep for backward compatibility
        self.storyboard_items: List[StoryboardItem] = []
        self.metadata: Dict[str, Any] = {}
        self.version: str = "2.0"  # Bump version for new structure
        self.created_at: str = ""
        self.updated_at: str = ""
        
        # Identity blocks for consistent entity descriptions (Higgsfield)
        self.identity_blocks: Dict[str, str] = {}  # Maps entity_id -> identity_block_string
        self.identity_block_ids: Dict[str, str] = {}  # Maps entity_name/type -> entity_id (e.g., "SUV_7A3F")
        
        # New identity block management system
        self.identity_block_metadata: Dict[str, Dict[str, Any]] = {}
        # Maps entity_id -> {
        #     "name": str,
        #     "type": str (character/vehicle/object/environment/group),
        #     "scene_id": str (for per-scene environments),
        #     "status": str ("placeholder", "generating", "approved"),
        #     "user_notes": str (short description from user),
        #     "identity_block": str (full 8-field generated block),
        #     "reference_image_prompt": str (prompt for generating Higgsfield reference image),
        #     "created_at": str,
        #     "updated_at": str
        # }
        # For type "environment" only: extras are background-only people (guests, crowd, passersby).
        # extras_present: bool, extras_density, extras_activities, extras_depth, foreground_zone.
        # parent_vehicle: str (when this environment is an interior of a vehicle, the vehicle name;
        # must match an existing VEHICLE identity. Camera inside craft → ENVIRONMENT; outside → VEHICLE.)
        
        # Snapshot manager for version history
        self.snapshot_manager = None  # Will be initialized when needed
        
        # Brand context for promotional workflows
        self.brand_context: Optional[BrandContext] = None
        
        # Character Registry (Wizard): single source of truth for characters. Identity blocks must
        # consume this registry and must NOT discover or invent characters. When frozen, downstream
        # must not add new character identities; only registry names may get character identity blocks.
        self.character_registry: List[str] = []  # Canonical character names only
        self.character_registry_frozen: bool = False
        
        # Wardrobe variant system
        self.character_wardrobe_variants: Dict[str, List[Dict[str, Any]]] = {}  # entity_id -> list of variant dicts
        self.character_last_wardrobe_variant: Dict[str, str] = {}  # entity_id -> last used variant_id
        
        # Episodic series metadata (None for standalone stories)
        self.series_metadata: Optional[Dict[str, Any]] = None
        
        # Initialize timestamps
        self.created_at = datetime.datetime.now().isoformat()
        self.updated_at = datetime.datetime.now().isoformat()
    
    def is_advertisement_mode(self) -> bool:
        """Return True when this screenplay is in structured advertisement mode.
        
        Advertisement mode is active when story_length is 'micro' and
        intent is 'Advertisement / Brand Film'.
        """
        from core.ad_framework import is_advertisement_mode
        return is_advertisement_mode(self.story_length, self.intent)
    
    def add_identity_block(self, entity_id: str, entity_type: str, identity_block: str) -> None:
        """Store an identity block for a recurring entity."""
        self.identity_blocks[entity_id] = identity_block
        self.updated_at = datetime.datetime.now().isoformat()
    
    def get_identity_block(self, entity_id: str) -> Optional[str]:
        """Retrieve a stored identity block by entity ID."""
        return self.identity_blocks.get(entity_id)
    
    def get_identity_block_by_name(self, entity_name: str, entity_type: str) -> Optional[str]:
        """Retrieve an identity block by entity name and type."""
        lookup_key = f"{entity_type}:{entity_name}"
        entity_id = self.identity_block_ids.get(lookup_key.lower())
        if entity_id:
            return self.identity_blocks.get(entity_id)
        # Fallback: check identity_block_metadata for a name match (handles
        # blocks created before the id-registry entry existed).
        name_lower = entity_name.strip().lower()
        for eid, meta in self.identity_block_metadata.items():
            if meta.get("type") == entity_type and (meta.get("name") or "").strip().lower() == name_lower:
                return self.identity_blocks.get(eid)
        return None
    
    def register_identity_block_id(self, entity_name: str, entity_type: str, entity_id: str) -> None:
        """Register a mapping from entity name/type to entity ID."""
        if not entity_name or not isinstance(entity_name, str):
            return
        # Never register malformed keys (dialogue blocks, paragraph text)
        if '\n' in entity_name or '"' in entity_name or len(entity_name.strip()) > 80:
            return
        lookup_key = f"{entity_type}:{entity_name}"
        self.identity_block_ids[lookup_key.lower()] = entity_id
        self.updated_at = datetime.datetime.now().isoformat()
    
    def find_or_create_identity_block(self, entity_name: str, entity_type: str, description: str) -> Optional[str]:
        """Find existing identity block or return None if not found (creation happens in AI generator)."""
        return self.get_identity_block_by_name(entity_name, entity_type)
    
    # Words that indicate a location/building/place — never part of a person name.
    # Used to reject extracted names like "PENDERGAST MANSION" from matching a character.
    _LOCATION_INDICATOR_WORDS = frozenset({
        "mansion", "house", "building", "mill", "library", "emporium", "store", "shop",
        "lab", "laboratory", "warehouse", "station", "hub", "apartment", "room", "office",
        "facility", "corridor", "hallway", "lobby", "street", "avenue", "alley", "plaza",
        "square", "park", "bridge", "dock", "port", "terminal", "tower", "castle", "palace",
        "temple", "church", "cathedral", "hospital", "school", "university", "museum",
        "restaurant", "bar", "tavern", "inn", "hotel", "motel", "ranch", "farm", "mine",
        "cave", "forest", "woods", "lake", "river", "mountain", "valley", "island",
        "carnival", "festival", "arena", "stadium", "theater", "theatre", "cinema",
        "garage", "barn", "shed", "cottage", "cabin", "lodge", "resort", "prison",
        "jail", "cemetery", "graveyard", "ruins", "bunker", "base", "camp",
        "night", "day", "morning", "evening", "dawn", "dusk", "noon", "midnight",
    })

    def resolve_character_to_canonical(self, name: str) -> Optional[str]:
        """Resolve a character name (or alias) to the canonical registry name, or None if not in registry.
        
        Used when registry is frozen: scene-extracted names (e.g. 'Hank', 'Henry', 'Thompson',
        'As Hank') must map to a single canonical entry (e.g. "Henry 'Hank' Thompson") if present.
        Returns names with nicknames in single quotes (normalizes "Nick" -> 'Nick').
        
        Rejects names containing location/building indicator words (e.g. "PENDERGAST MANSION",
        "NIGHT") even if they share a surname with a character in the registry.
        """
        if not name or not isinstance(name, str):
            return None
        registry = getattr(self, "character_registry", None) or []
        if not registry:
            return None
        n = name.strip()
        if not n:
            return None
        import re
        n_lower = n.lower()

        # Reject if name contains a location/time-of-day indicator word
        n_words = set(n_lower.split())
        if n_words & self._LOCATION_INDICATOR_WORDS:
            return None

        # Strip narrative prefixes for matching
        n_norm = re.sub(r"^\s*As\s+", "", n, flags=re.IGNORECASE).strip()
        n_norm = re.sub(r"^\s*The\s+", "", n_norm, flags=re.IGNORECASE).strip()
        n_norm_lower = n_norm.lower()
        
        def _normalize_nickname_quotes(s: str) -> str:
            """Convert "Nickname" to 'Nickname' for consistency."""
            return re.sub(r'"([^"]*)"', r"'\1'", s) if s else s
        
        # For matching: treat both " and ' as nickname delimiters when splitting
        def _parts(txt: str) -> set:
            return set(re.split(r"[\s'\"]+", re.sub(r'"([^"]*)"', r" \1 ", txt or ""))) - {""}
        
        # Exact match
        for canonical in registry:
            if not canonical:
                continue
            c = canonical.strip()
            if c.lower() == n_lower or c.lower() == n_norm_lower:
                return _normalize_nickname_quotes(c)
        # First name, last name, or nickname match (case-insensitive)
        parts_n = {p.lower() for p in _parts(n_norm)}
        _TITLE_WORDS = {
            "captain", "cpt", "capt", "detective", "det", "professor", "prof",
            "doctor", "dr", "sergeant", "sgt", "lieutenant", "lt", "colonel",
            "col", "general", "gen", "commander", "cmdr", "reverend", "rev",
            "officer", "agent", "inspector", "constable", "marshal", "sheriff",
            "king", "queen", "prince", "princess", "lord", "lady", "sir",
            "dame", "duke", "duchess", "baron", "baroness", "count", "countess",
            "chief", "corporal", "cpl", "private", "pvt", "admiral", "adm",
            "major", "maj", "mister", "mr", "mrs", "ms", "mme", "miss",
            "maestro", "madame", "monsieur",
        }
        for canonical in registry:
            if not canonical:
                continue
            c = canonical.strip()
            c_lower = c.lower()
            c_parts = {p.lower() for p in _parts(c_lower)}
            if parts_n and parts_n <= c_parts:
                return _normalize_nickname_quotes(c)
            # Superset match: input has ALL canonical words plus extra title/rank words
            if c_parts and len(c_parts) >= 2 and c_parts <= parts_n:
                extra = parts_n - c_parts
                if extra and extra <= _TITLE_WORDS:
                    return _normalize_nickname_quotes(c)
            if len(parts_n) == 1:
                (word,) = parts_n
                if word in c_lower or any(seg == word for seg in c_parts if seg):
                    return _normalize_nickname_quotes(c)
        return None
    
    def is_canonical_character(self, name: str) -> bool:
        """Return True if the name resolves to a Wizard (canonical) character when registry is frozen.
        Use this to avoid misclassifying Wizard characters as environment/object/vehicle."""
        if not getattr(self, "character_registry_frozen", False):
            return False
        return self.resolve_character_to_canonical(name) is not None

    def has_overlapping_registry_name(self, name: str, min_shared_words: int = 2) -> Optional[str]:
        """Check if *name* shares significant word overlap with an existing registry entry.

        Returns the existing registry name if overlap is found, else None.
        Used to prevent confusing entries like "MAESTRO ORVILLE PRIMROSE STONE"
        when "MAESTRO ORVILLE STONE" and "PRIMROSE STONE" already exist.
        """
        if not name or not isinstance(name, str):
            return None
        registry = getattr(self, "character_registry", None) or []
        if not registry:
            return None
        name_words = set(name.upper().split())
        if len(name_words) < min_shared_words:
            return None
        for existing in registry:
            if not existing:
                continue
            if existing.upper() == name.upper():
                return None  # exact match is fine (not an overlap issue)
            existing_words = set(existing.upper().split())
            shared = name_words & existing_words
            if len(shared) >= min_shared_words:
                return existing
        return None
    
    _BUILDING_VENUE_WORDS = frozenset({
        "club", "bar", "pub", "tavern", "inn", "restaurant", "cafe", "diner",
        "shop", "store", "market", "mall", "theater", "theatre", "cinema",
        "church", "temple", "mosque", "cathedral", "chapel", "shrine",
        "school", "university", "college", "academy", "library", "museum",
        "hospital", "clinic", "office", "building", "tower", "house", "home",
        "apartment", "flat", "mansion", "palace", "castle", "fortress", "fort",
        "hotel", "motel", "hostel", "lodge", "resort", "gym", "arena", "stadium",
        "park", "garden", "zoo", "gallery", "salon", "studio", "warehouse",
        "factory", "plant", "station", "garage", "barn", "shed", "bunker",
        "basement", "attic", "cellar", "lab", "laboratory", "morgue", "prison",
        "jail", "precinct", "headquarters", "hq", "base", "compound",
    })

    def _is_valid_entity_name(self, entity_name: str, entity_type: str) -> bool:
        """Reject malformed entity names (dialogue blocks, compound text, common words, etc.)."""
        if not entity_name or not isinstance(entity_name, str):
            return False
        n = entity_name.strip()
        if not n or len(n) < 2:
            return False
        # Reject common English words (e.g. "the" mistakenly extracted as vehicle/object)
        invalid_words = {"the", "a", "an", "this", "that", "it", "his", "her", "their"}
        if n.lower() in invalid_words:
            return False
        # Reject names containing newlines (indicates dialogue block or paragraph text)
        if '\n' in n:
            return False
        # Reject names with double quotes (dialogue uses "; nicknames use ' and are allowed)
        if '"' in n:
            return False
        # Reject overly long names (likely paragraph content, not a single entity)
        if len(n) > 80:
            return False
        # For vehicles: reject building/venue words that are never vehicles
        if entity_type == "vehicle":
            import re
            core = re.sub(r'^(?:the|a|an)\s+', '', n, flags=re.IGNORECASE).strip().lower()
            if core in self._BUILDING_VENUE_WORDS:
                return False
        # For characters: reject if it looks like multiple names/dialogue concatenated
        if entity_type == "character":
            # Pattern like "NAME1\n\"dialogue\"\n\nNAME2" would have been caught by newline/quote
            # Also reject comma-separated multiple names (e.g. "Captain, Pilot")
            if n.count(',') > 1:
                return False
        return True
    
    def create_placeholder_identity_block(self, entity_name: str, entity_type: str, scene_id: str = "") -> str:
        """Create a placeholder identity block that needs user review.
        
        Args:
            entity_name: Name of the entity
            entity_type: Type (character/vehicle/object/environment/group)
            scene_id: Scene ID for environment blocks
            
        Returns:
            entity_id: The generated entity ID, or "" if character registry is frozen and name not in registry
        """
        import hashlib
        import re
        
        # Normalize nickname quotes: "Nickname" -> 'Nickname' (dialogue uses "; nicknames use ')
        if entity_type == "character" and entity_name:
            entity_name = re.sub(r'"([^"]*)"', r"'\1'", entity_name)
        
        # Reject malformed entity names (dialogue blocks, paragraph text passed as entity name)
        if not self._is_valid_entity_name(entity_name, entity_type):
            return ""
        
        # Wizard character list is absolute authority: never create environment/object/vehicle for a canonical character
        if entity_type in ("environment", "object", "vehicle") and getattr(self, "character_registry_frozen", False):
            canonical = self.resolve_character_to_canonical(entity_name)
            if canonical is not None:
                entity_type = "character"
                entity_name = re.sub(r'"([^"]*)"', r"'\1'", canonical)  # Normalize "Nick" -> 'Nick'
        
        # Character Registry (frozen): prefer canonical name if in registry. Scene-named characters
        # (named in scene content but not in registry) are still allowed — they get identity blocks
        # for visual consistency but do not have character outlines or growth arcs.
        if entity_type == "character" and getattr(self, "character_registry_frozen", False):
            canonical = self.resolve_character_to_canonical(entity_name)
            if canonical is not None:
                entity_name = re.sub(r'"([^"]*)"', r"'\1'", canonical)  # Normalize "Nick" -> 'Nick'
        
        # Normalize entity name to prevent duplicates from title/prefix variations
        normalized_name = entity_name
        if entity_type == "character":
            # Strip prefixes "As ", "The " and titles — one human = one CHARACTER identity
            normalized_name = re.sub(r'^\s*As\s+', '', entity_name, flags=re.IGNORECASE).strip()
            normalized_name = re.sub(r'^\s*The\s+', '', normalized_name, flags=re.IGNORECASE).strip()
            normalized_name = re.sub(r'^(Dr\.|Mr\.|Mrs\.|Ms\.|Miss|Captain|Professor|Prof\.|Lieutenant|Lt\.|Sergeant|Sgt\.|General|Gen\.|Colonel|Col\.|Major|Commander|Admiral)\s+', '', normalized_name, flags=re.IGNORECASE).strip()
            
            # Also dedupe minor spelling variations (e.g., "Jasmin" vs "Jasmine")
            try:
                import difflib
                best_id = None
                best_ratio = 0.0
                for existing_id, meta in self.identity_block_metadata.items():
                    if meta.get("type") != "character":
                        continue
                    existing_name = (meta.get("name") or "").strip()
                    if not existing_name:
                        continue
                    existing_norm = re.sub(r'^\s*As\s+', '', existing_name, flags=re.IGNORECASE).strip()
                    existing_norm = re.sub(r'^\s*The\s+', '', existing_norm, flags=re.IGNORECASE).strip()
                    existing_norm = re.sub(r'^(Dr\.|Mr\.|Mrs\.|Ms\.|Miss|Captain|Professor|Prof\.|Lieutenant|Lt\.|Sergeant|Sgt\.|General|Gen\.|Colonel|Col\.|Major|Commander|Admiral)\s+', '', existing_norm, flags=re.IGNORECASE).strip()
                    ratio = difflib.SequenceMatcher(None, normalized_name.lower(), existing_norm.lower()).ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_id = existing_id
                    # Full-name matching: if shortened name is a whole word in existing (e.g. "Victor" vs "Victor Kane")
                    if not best_id or best_ratio < 0.88:
                        first_word = (normalized_name.split() or [""])[0].lower()
                        existing_first = (existing_norm.split() or [""])[0].lower()
                        existing_words = set(existing_norm.lower().split())
                        new_words = set(normalized_name.lower().split())
                        if first_word == existing_first or first_word in existing_words or existing_first in new_words:
                            if len(existing_norm) >= len(normalized_name):
                                best_ratio = max(best_ratio, 0.90)
                                best_id = existing_id
                    # Nickname match: REX vs REBECCA 'REX' STERN — same character, reuse existing ID
                    if not best_id or best_ratio < 0.88:
                        nick_match = re.search(r'["\']([^"\']+)["\']', existing_name)
                        if nick_match and len(normalized_name.split()) == 1:
                            if nick_match.group(1).lower() == normalized_name.lower():
                                best_ratio = 0.95
                                best_id = existing_id
                # If it's a strong near-match or first-name match, reuse the existing character ID (prevents identity drift)
                if best_id and best_ratio >= 0.88:
                    self.register_identity_block_id(entity_name, entity_type, best_id)
                    if normalized_name != entity_name:
                        self.register_identity_block_id(normalized_name, entity_type, best_id)
                    return best_id
            except Exception:
                pass
        
        entity_key = f"{entity_type}:{normalized_name}".lower()
        entity_hash = hashlib.md5(entity_key.encode()).hexdigest()[:4].upper()
        entity_id = f"{entity_type.upper()}_{entity_hash}"
        
        # Check if already exists
        if entity_id in self.identity_block_metadata:
            # Update the name to use the most complete version (with title if available)
            existing_name = self.identity_block_metadata[entity_id]["name"]
            # Prefer the version with a title
            if len(entity_name) > len(existing_name):
                self.identity_block_metadata[entity_id]["name"] = entity_name
            return entity_id
        
        # Create placeholder metadata
        base_metadata = {
            "name": entity_name,
            "type": entity_type,
            "scene_id": scene_id,
            "status": "placeholder",
            "user_notes": "",
            "identity_block": "",
            "reference_image_prompt": "",  # Prompt for Higgsfield reference image
            "image_path": "",  # Path to uploaded reference image
            # Optional linking/grouping (used by Identity Blocks Merge feature)
            "linked_group_id": "",
            "linked_role": "",
            # Character alias system: links multiple entity IDs as the same
            # person under different names (e.g. HOODED FIGURE → TALON → LYRA).
            # alias_of: entity_id of the canonical identity this is an alias for
            # aliases: list of entity_ids that are aliases OF this entity
            "alias_of": "",
            "aliases": [],
            "created_at": datetime.datetime.now().isoformat(),
            "updated_at": datetime.datetime.now().isoformat()
        }
        # Character-only: species field for non-human characters
        if entity_type == "character":
            base_metadata["species"] = "Human"  # Default; updated from story_outline data when available
        # Environment-only: extras fields (MODE A = empty, MODE B = with extras). Backward compat: defaults.
        # parent_vehicle: when this environment is an interior of a vehicle, the vehicle name (exact match to VEHICLE identity).
        if entity_type == "environment":
            base_metadata["extras_present"] = False
            base_metadata["extras_density"] = "sparse"
            base_metadata["extras_activities"] = ""
            base_metadata["extras_depth"] = "background_only"
            base_metadata["foreground_zone"] = "clear"
            base_metadata["is_primary_environment"] = True  # Default to primary; user can change
            base_metadata["parent_vehicle"] = ""  # Vehicle name when this is a vehicle interior; must match existing VEHICLE identity
        # Group-only: collective entity fields (e.g. IMPERIAL SOLDIERS, CITY GUARDS).
        # Groups share a uniform visual identity but represent multiple individuals.
        if entity_type == "group":
            base_metadata["member_count"] = 3
            base_metadata["member_count_visible"] = 0  # 0 = same as member_count
            base_metadata["uniform_description"] = ""
            base_metadata["formation"] = "scattered"  # scattered / line / wedge / cluster / surrounding / flanking
            base_metadata["individuality"] = "slight_variation"  # identical / slight_variation / distinct
        self.identity_block_metadata[entity_id] = base_metadata
        
        # Register the ID mapping using BOTH the original name and normalized name
        # This allows lookups with either "Dr. Elara Vex" or "Elara Vex" to find the same entity
        self.register_identity_block_id(entity_name, entity_type, entity_id)
        if normalized_name != entity_name:
            # Also register the normalized version
            self.register_identity_block_id(normalized_name, entity_type, entity_id)
        self.updated_at = datetime.datetime.now().isoformat()
        
        return entity_id
    
    # Environment extras keys (allowed when updating even if not previously in dict, for backward compat)
    _ENVIRONMENT_EXTRAS_KEYS = frozenset({"extras_present", "extras_density", "extras_activities", "extras_depth", "foreground_zone", "is_primary_environment", "parent_vehicle"})
    # Group entity keys (member count, formation, individuality, uniform)
    _GROUP_KEYS = frozenset({"member_count", "member_count_visible", "uniform_description", "formation", "individuality"})
    _ALWAYS_ALLOWED_KEYS = frozenset({"image_path", "reference_image_prompt"})
    # Alias keys (allowed on any entity type)
    _ALIAS_KEYS = frozenset({"alias_of", "aliases"})

    # ── Character Alias System ────────────────────────────────────────

    def link_entity_alias(self, alias_entity_id: str, canonical_entity_id: str) -> bool:
        """Link *alias_entity_id* as an alias of *canonical_entity_id*.

        Both entities keep their own identity blocks (the alias may have a
        disguise appearance), but the system knows they are the same person.
        The canonical entity's ``aliases`` list is updated, and the alias
        entity's ``alias_of`` field is set.

        Returns True on success, False if either ID is unknown.
        """
        if alias_entity_id not in self.identity_block_metadata:
            return False
        if canonical_entity_id not in self.identity_block_metadata:
            return False
        if alias_entity_id == canonical_entity_id:
            return False

        alias_meta = self.identity_block_metadata[alias_entity_id]
        canon_meta = self.identity_block_metadata[canonical_entity_id]

        alias_meta["alias_of"] = canonical_entity_id
        existing = canon_meta.get("aliases") or []
        if alias_entity_id not in existing:
            existing.append(alias_entity_id)
        canon_meta["aliases"] = existing

        self.updated_at = datetime.datetime.now().isoformat()
        return True

    def unlink_entity_alias(self, alias_entity_id: str) -> bool:
        """Remove the alias link from *alias_entity_id*."""
        if alias_entity_id not in self.identity_block_metadata:
            return False
        alias_meta = self.identity_block_metadata[alias_entity_id]
        canon_id = alias_meta.get("alias_of", "")
        if not canon_id:
            return False
        alias_meta["alias_of"] = ""
        if canon_id in self.identity_block_metadata:
            canon_meta = self.identity_block_metadata[canon_id]
            existing = canon_meta.get("aliases") or []
            canon_meta["aliases"] = [a for a in existing if a != alias_entity_id]
        self.updated_at = datetime.datetime.now().isoformat()
        return True

    def get_canonical_entity(self, entity_id: str) -> str:
        """Return the canonical entity ID for *entity_id*.

        If the entity is an alias, returns the ``alias_of`` target.
        Otherwise returns *entity_id* itself.
        """
        meta = self.identity_block_metadata.get(entity_id, {})
        canon = meta.get("alias_of", "")
        return canon if canon and canon in self.identity_block_metadata else entity_id

    def get_all_aliases(self, canonical_entity_id: str) -> List[str]:
        """Return all alias entity IDs for a canonical entity."""
        meta = self.identity_block_metadata.get(canonical_entity_id, {})
        return list(meta.get("aliases") or [])

    def update_identity_block_metadata(self, entity_id: str, **kwargs) -> None:
        """Update identity block metadata fields.
        
        Args:
            entity_id: The entity ID
            **kwargs: Fields to update (status, user_notes, identity_block, extras_present, etc.)
        """
        if entity_id not in self.identity_block_metadata:
            return
        meta = self.identity_block_metadata[entity_id]
        for key, value in kwargs.items():
            if key in meta or key in self._ALWAYS_ALLOWED_KEYS or key in self._ALIAS_KEYS or (meta.get("type") == "environment" and key in self._ENVIRONMENT_EXTRAS_KEYS) or (meta.get("type") == "group" and key in self._GROUP_KEYS):
                meta[key] = value if (key != "parent_vehicle") else (str(value).strip() if value else "")
        meta["updated_at"] = datetime.datetime.now().isoformat()
        
        # If identity_block is updated, also update the legacy storage
        if "identity_block" in kwargs and kwargs["identity_block"]:
            self.identity_blocks[entity_id] = kwargs["identity_block"]
        
        self.updated_at = datetime.datetime.now().isoformat()
    
    def get_pending_identity_blocks(self) -> List[Dict[str, Any]]:
        """Get all identity blocks that need user review (status not approved/passive).
        
        Returns:
            List of identity block metadata dicts with entity_id included
        """
        pending = []
        for entity_id, metadata in self.identity_block_metadata.items():
            status = metadata.get("status", "")
            if status not in ("approved", "passive", "referenced"):
                block_data = metadata.copy()
                block_data["entity_id"] = entity_id
                pending.append(block_data)
        return pending
    
    def get_approved_identity_blocks(self) -> List[Dict[str, Any]]:
        """Get all approved identity blocks.
        
        Returns:
            List of identity block metadata dicts with entity_id included
        """
        approved = []
        for entity_id, metadata in self.identity_block_metadata.items():
            if metadata.get("status") == "approved":
                block_data = metadata.copy()
                block_data["entity_id"] = entity_id
                approved.append(block_data)
        return approved

    def get_passive_entity_names(self) -> List[str]:
        """Return names of all entities marked as passive (name-only, no identity block)."""
        names: List[str] = []
        for _entity_id, metadata in self.identity_block_metadata.items():
            if metadata.get("status") == "passive":
                name = (metadata.get("name") or "").strip()
                if name:
                    names.append(name)
        return names

    def get_identity_blocks_for_scene(self, scene_id: str) -> Dict[str, List[str]]:
        """Get environment and entity identity blocks for a specific scene.
        
        Args:
            scene_id: The scene ID
            
        Returns:
            Dict with "environment" and "entities" keys containing approved identity blocks
        """
        result = {
            "environment": [],
            "entities": []
        }
        
        for entity_id, metadata in self.identity_block_metadata.items():
            if metadata.get("status") != "approved":
                continue
            
            identity_block = metadata.get("identity_block", "")
            if not identity_block:
                continue
            
            entity_type = metadata.get("type", "")
            entity_scene_id = metadata.get("scene_id", "")
            
            if entity_type == "environment" and entity_scene_id == scene_id:
                result["environment"].append(identity_block)
            elif entity_type in ["character", "vehicle", "object"]:
                # Entity blocks are global (not scene-specific)
                result["entities"].append(identity_block)
        
        return result
    
    def remove_identity_blocks_for_scene(self, scene_id: str) -> int:
        """Remove all identity blocks created for a given scene (for re-extraction).
        Returns the number of blocks removed."""
        if not scene_id:
            return 0
        to_remove = [
            entity_id for entity_id, meta in self.identity_block_metadata.items()
            if meta.get("scene_id") == scene_id
        ]
        for entity_id in to_remove:
            self.identity_block_metadata.pop(entity_id, None)
            self.identity_blocks.pop(entity_id, None)
            # Remove from identity_block_ids (keys that point to this entity_id)
            keys_to_del = [k for k, eid in self.identity_block_ids.items() if eid == entity_id]
            for k in keys_to_del:
                del self.identity_block_ids[k]
        if to_remove:
            self.updated_at = datetime.datetime.now().isoformat()
        return len(to_remove)
    
    def get_character_wardrobe_for_scene(self, scene_id: str, entity_id: str) -> str:
        """Get wardrobe description for a character in a specific scene.

        Falls back to the wardrobe variant description when the scene's
        ``character_wardrobe`` dict is missing an entry but a variant ID is
        recorded for this scene.
        
        Args:
            scene_id: The scene ID
            entity_id: The character's entity ID (e.g., CHARACTER_7A3F)
            
        Returns:
            Wardrobe description string, or "" if not set
        """
        scene = self.get_scene(scene_id)
        if not scene:
            return ""
        wardrobe = getattr(scene, "character_wardrobe", None) or {}
        desc = wardrobe.get(entity_id, "")
        if desc:
            return desc

        # Fallback: resolve via the variant ID stored on this scene
        variant_ids = getattr(scene, "character_wardrobe_variant_ids", None) or {}
        vid = variant_ids.get(entity_id)
        if vid:
            variants = getattr(self, "character_wardrobe_variants", {}).get(entity_id, [])
            for v in variants:
                if v.get("variant_id") == vid:
                    return v.get("description", "")
        return ""
    
    def set_character_wardrobe_for_scene(self, scene_id: str, entity_id: str, wardrobe: str) -> None:
        """Set wardrobe description for a character in a specific scene.
        
        Args:
            scene_id: The scene ID
            entity_id: The character's entity ID
            wardrobe: Wardrobe description (clothing, accessories, etc.)
        """
        scene = self.get_scene(scene_id)
        if not scene:
            return
        if not hasattr(scene, "character_wardrobe") or scene.character_wardrobe is None:
            scene.character_wardrobe = {}
        scene.character_wardrobe[entity_id] = (wardrobe or "").strip()
        self.updated_at = datetime.datetime.now().isoformat()

    # ── Wardrobe Variant helpers ──────────────────────────────────────

    def get_wardrobe_variants(self, entity_id: str) -> List[Dict[str, Any]]:
        """Return the list of wardrobe variant dicts for *entity_id*."""
        variants = getattr(self, "character_wardrobe_variants", {})
        return variants.get(entity_id, [])

    def add_wardrobe_variant(self, entity_id: str, variant: Dict[str, Any]) -> None:
        if not hasattr(self, "character_wardrobe_variants"):
            self.character_wardrobe_variants = {}
        self.character_wardrobe_variants.setdefault(entity_id, []).append(variant)
        self.updated_at = datetime.datetime.now().isoformat()

    def update_wardrobe_variant(self, entity_id: str, variant_id: str, **kwargs) -> None:
        for v in self.get_wardrobe_variants(entity_id):
            if v.get("variant_id") == variant_id:
                v.update(kwargs)
                self.updated_at = datetime.datetime.now().isoformat()
                return

    def delete_wardrobe_variant(self, entity_id: str, variant_id: str) -> None:
        variants = self.get_wardrobe_variants(entity_id)
        self.character_wardrobe_variants[entity_id] = [
            v for v in variants if v.get("variant_id") != variant_id
        ]
        self.updated_at = datetime.datetime.now().isoformat()

    def get_wardrobe_variant_by_id(self, entity_id: str, variant_id: str) -> Optional[Dict[str, Any]]:
        for v in self.get_wardrobe_variants(entity_id):
            if v.get("variant_id") == variant_id:
                return v
        return None

    def get_scene_wardrobe_variant(self, scene_id: str, entity_id: str) -> Optional[Dict[str, Any]]:
        """Return the wardrobe variant assigned to *entity_id* in *scene_id*, or None."""
        scene = self.get_scene(scene_id)
        if not scene:
            return None
        vid = getattr(scene, "character_wardrobe_variant_ids", {}).get(entity_id)
        if not vid:
            return None
        return self.get_wardrobe_variant_by_id(entity_id, vid)

    def get_vehicle_names(self) -> List[str]:
        """Return list of entity names that are type VEHICLE (exterior). Used for parent_vehicle validation."""
        names = []
        for metadata in self.identity_block_metadata.values():
            if (metadata.get("type") or "").lower() == "vehicle":
                name = (metadata.get("name") or "").strip()
                if name:
                    names.append(name)
        return names

    def validate_parent_vehicle_relationships(self) -> tuple:
        """Validate parent_vehicle rules: environments with parent_vehicle reference existing VEHICLE;
        no VEHICLE has parent_vehicle; interiors (names implying vehicle interior) have parent_vehicle.
        Returns (passed: bool, issues: List[str])."""
        issues = []
        vehicle_names = {n.lower() for n in self.get_vehicle_names()}
        for entity_id, meta in self.identity_block_metadata.items():
            etype = (meta.get("type") or "").lower()
            name = (meta.get("name") or "").strip()
            parent = (meta.get("parent_vehicle") or "").strip()
            # No VEHICLE may have a parent_vehicle field (vehicles are exterior only)
            if etype == "vehicle" and parent:
                issues.append(f"VEHICLE '{name}' must not have parent_vehicle (vehicles are exterior only)")
            # ENVIRONMENT with parent_vehicle must reference an existing VEHICLE identity
            if etype == "environment" and parent:
                if parent.lower() not in vehicle_names:
                    issues.append(f"ENVIRONMENT '{name}' has parent_vehicle '{parent}' but no VEHICLE identity named '{parent}' exists")
        return (len(issues) == 0, issues)

    def validate_outline_entity_names(self) -> List[str]:
        """Compare entity names referenced in ``story_outline`` (main_storyline,
        conclusion) against the actual identity block registry.

        Returns a list of human-readable warnings for mismatches — e.g. the
        outline says ``{The Wayfarer}`` but all scenes use ``{Stormchaser}``.
        """
        import re as _re
        warnings: List[str] = []
        outline = getattr(self, "story_outline", None) or {}
        if not isinstance(outline, dict):
            return warnings

        text_fields = [
            ("main_storyline", outline.get("main_storyline", "")),
            ("conclusion", outline.get("conclusion", "")),
        ]
        for subplot in outline.get("subplots", []) or []:
            if isinstance(subplot, dict):
                text_fields.append(("subplot", subplot.get("description", "")))
            elif isinstance(subplot, str):
                text_fields.append(("subplot", subplot))

        # Collect all known entity names by type
        known: Dict[str, set] = {"vehicle": set(), "environment": set(), "object": set()}
        for _eid, m in self.identity_block_metadata.items():
            etype = (m.get("type") or "").lower()
            ename = (m.get("name") or "").strip().lower()
            if etype in known and ename:
                known[etype].add(ename)

        for field_label, text in text_fields:
            if not text:
                continue
            # {vehicle names}
            for m in _re.finditer(r'\{+([^{}]+)\}+', text):
                vname = m.group(1).strip().lower()
                if vname and vname not in known["vehicle"]:
                    closest = self._find_closest_entity_name(vname, known["vehicle"])
                    hint = f" (did you mean '{closest}'?)" if closest else ""
                    warnings.append(
                        f"Outline {field_label} references vehicle '{m.group(1).strip()}' "
                        f"but no VEHICLE identity block matches{hint}"
                    )
            # _environment names_
            for m in _re.finditer(r'(?<!\w)_([^_]+)_(?!\w)', text):
                ename = m.group(1).strip().lower()
                if ename and ename not in known["environment"]:
                    closest = self._find_closest_entity_name(ename, known["environment"])
                    hint = f" (did you mean '{closest}'?)" if closest else ""
                    warnings.append(
                        f"Outline {field_label} references environment '{m.group(1).strip()}' "
                        f"but no ENVIRONMENT identity block matches{hint}"
                    )

        return warnings

    @staticmethod
    def _find_closest_entity_name(target: str, candidates: set) -> str:
        """Return the candidate with the highest word-overlap to *target*, or ''."""
        if not candidates:
            return ""
        target_words = set(target.lower().split())
        best, best_score = "", 0
        for c in candidates:
            score = len(target_words & set(c.lower().split()))
            if score > best_score:
                best, best_score = c, score
        return best.title() if best_score > 0 else ""

    def validate_environment_name_content(self) -> List[str]:
        """Detect environments whose name doesn't match their identity block text.

        For example, an environment named 'Cockpit' whose block describes a
        'stone observatory atop the Shattered Spire'.  Returns warnings.
        """
        import re as _re
        warnings: List[str] = []
        for eid, m in self.identity_block_metadata.items():
            if (m.get("type") or "").lower() != "environment":
                continue
            name = (m.get("name") or "").strip()
            block_text = (self.identity_blocks.get(eid, "") or "").lower()
            if not name or not block_text or len(block_text) < 40:
                continue
            # Check if any significant word from the name appears in the block
            name_words = [w for w in name.lower().split() if len(w) > 3
                          and w not in ("the", "with", "from", "this", "that", "same")]
            if not name_words:
                continue
            hits = sum(1 for w in name_words if w in block_text)
            if hits == 0:
                warnings.append(
                    f"ENVIRONMENT '{name}' ({eid}): name doesn't appear in its "
                    f"identity block text — possible mismatch"
                )
        return warnings

    def detect_unused_placeholder_entities(self) -> List[str]:
        """Find identity blocks that are still 'placeholder' status and have
        no scene content reference.  These are likely orphans from story
        generation that were created but never used.

        Returns a list of human-readable descriptions.
        """
        all_scenes = self.get_all_scenes()
        # Build a set of entity names mentioned across all scene content
        all_content = ""
        for scene in all_scenes:
            all_content += " " + (getattr(scene, "description", "") or "")
            meta = getattr(scene, "metadata", None) or {}
            all_content += " " + (meta.get("generated_content", "") or "")
        all_content_upper = all_content.upper()

        unused: List[str] = []
        for eid, m in self.identity_block_metadata.items():
            status = (m.get("status") or "").lower()
            if status not in ("placeholder",):
                continue
            ename = (m.get("name") or "").strip()
            etype = (m.get("type") or "").lower()
            if not ename:
                continue
            # Check if this entity appears in any scene content
            if ename.upper() not in all_content_upper:
                unused.append(
                    f"{etype.upper()} '{ename}' ({eid}) is placeholder and "
                    f"not referenced in any scene content"
                )
        return unused

    # Generic set-dressing objects that don't need their own identity blocks
    # even when they recur across scenes (they're part of the environment).
    _GENERIC_SET_DRESSING: frozenset = frozenset({
        "door", "doors", "table", "tables", "chair", "chairs", "wall", "walls",
        "floor", "floors", "ceiling", "window", "windows", "staircase", "stairs",
        "steps", "railing", "railings", "bench", "benches", "shelf", "shelves",
        "lamp", "lamps", "lantern", "lanterns", "torch", "torches", "candle",
        "candles", "rug", "rugs", "carpet", "curtain", "curtains", "drape",
        "drapes", "pillar", "pillars", "column", "columns", "beam", "beams",
        "fence", "gate", "archway", "corridor", "hallway", "passage",
        "bed", "cot", "mattress", "blanket", "pillow", "barrel", "barrels",
        "crate", "crates", "box", "boxes", "bucket", "rope", "ladder",
        "sign", "banner", "flag", "rock", "rocks", "boulder", "tree", "trees",
        "bush", "bushes", "grass", "vine", "vines", "path", "trail",
    })

    def detect_recurring_objects_needing_identity(self) -> List[str]:
        """Find [bracketed] objects that appear across multiple scenes but lack
        an identity block.  These recurring props need dedicated identity blocks
        so they look visually consistent across scenes.

        Returns a list of human-readable warning strings sorted by scene count
        (most recurring first).
        """
        import re as _re

        all_scenes = self.get_all_scenes()
        _safe_print(f"  [recurring-objects] Scanning {len(all_scenes)} scene(s)...")
        if len(all_scenes) < 2:
            _safe_print("  [recurring-objects] < 2 scenes — skipping")
            return []

        # Map: normalised object name → set of (scene_id, scene_title)
        object_scenes: Dict[str, set] = {}
        # Keep the original casing for display
        object_display_name: Dict[str, str] = {}

        scenes_with_content = 0
        for scene in all_scenes:
            meta = getattr(scene, "metadata", None) or {}
            # Combine generated content AND scene description to catch objects
            # mentioned in the story outline even before content is generated
            parts = []
            gc = meta.get("generated_content", "") or ""
            if gc:
                parts.append(gc)
            desc = getattr(scene, "description", "") or ""
            if desc:
                parts.append(desc)
            content = " ".join(parts)
            if not content.strip():
                continue
            scenes_with_content += 1

            # Extract all [bracketed] names from this scene
            for m in _re.finditer(r'\[([^\]\[]+)\]', content):
                raw = m.group(1).strip()
                if not raw or len(raw) < 2:
                    continue
                # Skip paragraph numbers like [1], [2]
                if _re.match(r'^\d+$', raw):
                    continue
                key = raw.lower()
                # Skip generic set dressing
                if key in self._GENERIC_SET_DRESSING:
                    continue
                if key not in object_scenes:
                    object_scenes[key] = set()
                    object_display_name[key] = raw
                object_scenes[key].add((scene.scene_id, scene.title or f"Scene {scene.scene_number}"))

        _safe_print(f"  [recurring-objects] {scenes_with_content} scene(s) have content, found {len(object_scenes)} unique object(s)")

        # Filter to objects appearing in 2+ scenes
        recurring = {k: v for k, v in object_scenes.items() if len(v) >= 2}
        if recurring:
            _safe_print(f"  [recurring-objects] {len(recurring)} object(s) appear in 2+ scenes: {list(recurring.keys())[:10]}")
        else:
            _safe_print(f"  [recurring-objects] No objects appear in 2+ scenes")
            # Also list all objects and their scene counts for debugging
            if object_scenes:
                for k, v in sorted(object_scenes.items(), key=lambda x: -len(x[1]))[:10]:
                    _safe_print(f"    [{object_display_name[k]}] → {len(v)} scene(s)")
            return []

        # Check which recurring objects need attention
        warnings: List[str] = []
        for key, scene_set in sorted(recurring.items(), key=lambda x: -len(x[1])):
            display = object_display_name[key]

            # Look up the object's identity block status (if any)
            obj_status = ""
            obj_has_content = False
            name_lower = display.strip().lower()
            lookup_id = self.identity_block_ids.get(f"object:{name_lower}")
            if not lookup_id:
                for eid, m in self.identity_block_metadata.items():
                    if (m.get("type") or "").lower() == "object" and (m.get("name") or "").strip().lower() == name_lower:
                        lookup_id = eid
                        break
            if lookup_id:
                obj_meta = self.identity_block_metadata.get(lookup_id, {})
                obj_status = (obj_meta.get("status") or "").lower()
                obj_has_content = bool((self.identity_blocks.get(lookup_id) or "").strip())

            # Skip objects with approved/generated identity blocks that have real content
            if obj_status in ("approved", "generated") and obj_has_content:
                continue

            # Check if this object is baked into an environment identity block
            baked_env_id = None
            for eid, meta in self.identity_block_metadata.items():
                if (meta.get("type") or "").lower() != "environment":
                    continue
                env_text = (
                    (self.identity_blocks.get(eid) or "")
                    + " " + (meta.get("user_notes") or "")
                ).lower()
                if key in env_text:
                    baked_env_id = eid
                    break

            # Determine which environments the object appears in
            env_ids = set()
            scenes_without_env = 0
            for sid, _ in scene_set:
                for s in all_scenes:
                    if s.scene_id == sid:
                        if s.environment_id:
                            env_ids.add(s.environment_id)
                        else:
                            scenes_without_env += 1
                        break

            scene_names = sorted(title for _, title in scene_set)
            scene_list = ", ".join(scene_names[:5])
            if len(scene_names) > 5:
                scene_list += f" (+{len(scene_names) - 5} more)"

            count = len(scene_set)

            # Only suppress baked-in objects if ALL scenes share the same
            # environment and that environment is the one the object is baked into.
            # Scenes without an assigned environment are treated as unknown
            # (the object may travel there).
            all_same_baked_env = (
                baked_env_id
                and len(env_ids) == 1
                and baked_env_id in env_ids
                and scenes_without_env == 0
            )
            if all_same_baked_env:
                continue

            if len(env_ids) > 1 or (env_ids and scenes_without_env > 0):
                priority = "HIGH"
                reason = "travels across different environments"
            elif scenes_without_env > 0:
                priority = "HIGH"
                reason = "appears in multiple scenes (environments not yet assigned)"
            else:
                priority = "MEDIUM"
                reason = "recurs in same environment"

            has_block_note = ""
            if lookup_id and obj_status == "placeholder":
                has_block_note = " (has placeholder — generate identity)"

            warnings.append(
                f"[{priority}] [{display}] appears in {count} scenes "
                f"({scene_list}) — {reason}.{has_block_note}"
            )

        return warnings

    def get_identity_block_metadata_by_id(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Get identity block metadata by entity ID.
        
        Args:
            entity_id: The entity ID
            
        Returns:
            Metadata dict with entity_id included, or None if not found
        """
        if entity_id not in self.identity_block_metadata:
            return None
        
        metadata = self.identity_block_metadata[entity_id].copy()
        metadata["entity_id"] = entity_id
        return metadata
    
    def add_act(self, act: StoryAct) -> None:
        """Add an act to the screenplay."""
        self.acts.append(act)
        self.acts.sort(key=lambda x: x.act_number)
        self.updated_at = datetime.datetime.now().isoformat()
    
    def get_act(self, act_number: int) -> Optional[StoryAct]:
        """Get an act by number."""
        for act in self.acts:
            if act.act_number == act_number:
                return act
        return None
    
    def get_scene(self, scene_id: str) -> Optional[StoryScene]:
        """Get a scene by ID across all acts."""
        for act in self.acts:
            scene = act.get_scene(scene_id)
            if scene:
                return scene
        return None
    
    def get_entity_ids_for_scene(self, scene: 'StoryScene') -> set:
        """Return the set of entity IDs that belong to a given scene.

        Characters are matched through authoritative scene-level links
        (character_focus, wardrobe, wardrobe_variant_ids, image_assignments)
        — never through ``metadata["scene_id"]`` which can be set on wizard
        characters that aren't actually present in the scene.

        Environments, objects, and vehicles use ``metadata["scene_id"]``
        plus the scene's ``environment_id`` and storyboard references.
        Objects/vehicles with no ``scene_id`` are matched by scanning
        storyboard item text for entity name mentions.
        """
        ids: set = set()
        sid = scene.scene_id

        # Characters: authoritative links only
        for eid in getattr(scene, "character_wardrobe", {}):
            ids.add(eid)
        for eid in getattr(scene, "character_wardrobe_variant_ids", {}):
            ids.add(eid)

        # Characters listed in character_focus (populated during story creation)
        for char_name in getattr(scene, "character_focus", []) or []:
            stripped = char_name.strip()
            if not stripped:
                continue
            lookup = f"character:{stripped}".lower()
            eid = self.identity_block_ids.get(lookup)
            if not eid and getattr(self, "character_registry_frozen", False):
                canonical = self.resolve_character_to_canonical(stripped)
                if canonical:
                    eid = self.identity_block_ids.get(f"character:{canonical}".lower())
            if eid:
                ids.add(eid)

        # Environment assigned to the scene
        env_id = getattr(scene, "environment_id", None)
        if env_id:
            ids.add(env_id)

        # Entities referenced in storyboard item image_assignments
        for item in getattr(scene, "storyboard_items", []):
            for eid in getattr(item, "image_assignments", {}):
                ids.add(eid)

        # Non-character entities whose metadata scene_id matches
        for eid, meta in self.identity_block_metadata.items():
            etype = (meta.get("type") or "").lower()
            if etype == "character":
                continue
            if meta.get("scene_id") == sid:
                ids.add(eid)

        # Objects/vehicles with empty scene_id: match by name in scene text
        # Build a combined text corpus from all scene text sources
        text_parts = []
        for item in getattr(scene, "storyboard_items", []):
            text_parts.append(getattr(item, "image_prompt", "") or "")
            text_parts.append(getattr(item, "prompt", "") or "")
            text_parts.append(getattr(item, "visual_description", "") or "")
            text_parts.append(getattr(item, "storyline", "") or "")
        text_parts.append(getattr(scene, "description", "") or "")
        scene_meta = getattr(scene, "metadata", None) or {}
        text_parts.append(scene_meta.get("generated_content", "") or "")
        scene_text_lower = " ".join(text_parts).lower()

        if scene_text_lower.strip():
            for eid, meta in self.identity_block_metadata.items():
                if eid in ids:
                    continue
                etype = (meta.get("type") or "").lower()
                if etype not in ("object", "vehicle"):
                    continue
                if meta.get("scene_id"):
                    continue
                name = (meta.get("name") or "").strip().lower()
                if name and name in scene_text_lower:
                    ids.add(eid)

        return ids

    def auto_populate_image_assignments(self, scene: 'StoryScene') -> int:
        """Auto-fill ``image_assignments`` on every storyboard item in *scene*.

        Uses the same priority logic as the UI editor:
          1. Characters/entities named in the item's text
          2. Characters in the scene's ``character_focus``
          3. Scene-level objects/vehicles mentioned anywhere in the scene

        Returns the number of items that received assignments.
        """
        meta = self.identity_block_metadata or {}
        scene_entity_ids = self.get_entity_ids_for_scene(scene)

        scene_char_focus: set = set()
        for name in getattr(scene, "character_focus", []) or []:
            stripped = name.strip()
            if stripped:
                scene_char_focus.add(stripped.upper())

        scene_text_upper = ""
        parts = []
        for si in getattr(scene, "storyboard_items", []):
            parts.append(getattr(si, "storyline", "") or "")
            parts.append(getattr(si, "image_prompt", "") or "")
            parts.append(getattr(si, "visual_description", "") or "")
        parts.append(getattr(scene, "description", "") or "")
        scene_meta = getattr(scene, "metadata", None) or {}
        parts.append(scene_meta.get("generated_content", "") or "")
        scene_text_upper = " ".join(parts).upper()

        count = 0
        for item in getattr(scene, "storyboard_items", []):
            if getattr(item, "image_assignments", None):
                continue
            item_text = " ".join([
                getattr(item, "storyline", "") or "",
                getattr(item, "image_prompt", "") or "",
                getattr(item, "prompt", "") or "",
                getattr(item, "visual_description", "") or "",
                getattr(item, "dialogue", "") or "",
            ]).upper()

            tier1, tier2, tier3 = [], [], []
            for eid, m in meta.items():
                if scene_entity_ids and eid not in scene_entity_ids:
                    continue
                etype = (m.get("type") or "").lower()
                status = m.get("status", "")
                if etype not in ("character", "object", "vehicle", "group"):
                    continue
                if status == "passive":
                    continue
                img = (m.get("image_path") or "").strip()
                if not img:
                    continue
                ename = (m.get("name") or "").strip()
                entry = {
                    "path": img,
                    "entity_id": eid,
                    "entity_name": ename,
                    "entity_type": etype,
                }
                if ename and ename.upper() in item_text:
                    tier1.append(entry)
                elif etype in ("character", "group") and ename.upper() in scene_char_focus:
                    tier2.append(entry)
                elif etype in ("object", "vehicle") and ename and ename.upper() in scene_text_upper:
                    tier3.append(entry)

            ranked = tier1 + tier2 + tier3
            slots = ("image_1", "image_2", "image_3")
            assignments = {}
            for i, entry in enumerate(ranked[:len(slots)]):
                assignments[slots[i]] = entry
            if assignments:
                item.image_assignments = assignments
                count += 1

            # Environment start image
            if not (getattr(item, "environment_start_image", "") or "").strip():
                env_id = getattr(scene, "environment_id", None)
                if env_id and env_id in meta:
                    env_path = (meta[env_id].get("image_path") or "").strip()
                    if env_path:
                        item.environment_start_image = env_path

        return count

    def get_all_scenes(self) -> List[StoryScene]:
        """Get all scenes from all acts in order."""
        all_scenes = []
        for act in sorted(self.acts, key=lambda x: x.act_number):
            all_scenes.extend(act.scenes)
        return all_scenes
    
    def get_all_storyboard_items(self) -> List[StoryboardItem]:
        """Get all storyboard items from all scenes, or legacy items if using old structure."""
        if self.acts:
            # New structure: collect from scenes
            all_items = []
            for scene in self.get_all_scenes():
                all_items.extend(scene.storyboard_items)
            return all_items
        else:
            # Legacy structure: return old storyboard_items
            return self.storyboard_items
    
    def add_item(self, item: StoryboardItem) -> None:
        """Add a storyboard item to the screenplay."""
        # Ensure sequence numbers are correct
        if item.sequence_number <= 0:
            item.sequence_number = len(self.storyboard_items) + 1
        
        self.storyboard_items.append(item)
        # Sort by sequence number
        self.storyboard_items.sort(key=lambda x: x.sequence_number)
        self.updated_at = datetime.datetime.now().isoformat()
    
    def remove_item(self, item_id: str) -> bool:
        """Remove a storyboard item by ID."""
        for i, item in enumerate(self.storyboard_items):
            if item.item_id == item_id:
                del self.storyboard_items[i]
                # Renumber remaining items
                for j, remaining_item in enumerate(self.storyboard_items, start=1):
                    remaining_item.sequence_number = j
                self.updated_at = datetime.datetime.now().isoformat()
                return True
        return False
    
    def get_item(self, item_id: str) -> Optional[StoryboardItem]:
        """Get a storyboard item by ID."""
        # Check new structure first
        if self.acts:
            for scene in self.get_all_scenes():
                item = scene.get_storyboard_item(item_id)
                if item:
                    return item
        # Fall back to legacy structure
        for item in self.storyboard_items:
            if item.item_id == item_id:
                return item
        return None
    
    def get_total_duration(self) -> int:
        """Get total duration of all storyboard items in seconds."""
        return sum(item.duration for item in self.get_all_storyboard_items())
    
    def get_total_duration_formatted(self) -> str:
        """Get total duration formatted as MM:SS."""
        total_seconds = self.get_total_duration()
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes:02d}:{seconds:02d}"
    
    def reorder_items(self, new_order: List[str]) -> None:
        """Reorder items based on list of item IDs."""
        item_dict = {item.item_id: item for item in self.storyboard_items}
        self.storyboard_items = [item_dict[item_id] for item_id in new_order if item_id in item_dict]
        # Renumber items
        for i, item in enumerate(self.storyboard_items, start=1):
            item.sequence_number = i
        self.updated_at = datetime.datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert screenplay to dictionary."""
        result = {
            "title": self.title,
            "premise": self.premise,
            "genre": self.genre,
            "atmosphere": self.atmosphere,
            "story_length": getattr(self, "story_length", "medium"),
            "intent": getattr(self, "intent", "General Story"),  # Backward compatible
            "audio_strategy": getattr(self, "audio_strategy", "generated_with_video"),
            "story_outline": self.story_outline,
            "metadata": self.metadata,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "identity_blocks": self.identity_blocks,
            "identity_block_ids": self.identity_block_ids,
            "identity_block_metadata": self.identity_block_metadata,
            "character_registry": getattr(self, "character_registry", []),
            "character_registry_frozen": getattr(self, "character_registry_frozen", False),
            "brand_context": self.brand_context.to_dict() if self.brand_context else None,
            "story_settings": getattr(self, "story_settings", get_default_story_settings()),
            "character_wardrobe_variants": getattr(self, "character_wardrobe_variants", {}),
            "character_last_wardrobe_variant": getattr(self, "character_last_wardrobe_variant", {}),
        }
        
        # Only write series_metadata when present (backward compatible)
        if getattr(self, "series_metadata", None):
            result["series_metadata"] = self.series_metadata
        
        # Only write custom_duration_seconds when active (backward compatible)
        if getattr(self, "custom_duration_seconds", 0) > 0:
            result["custom_duration_seconds"] = self.custom_duration_seconds
        
        # New structure
        if self.acts:
            result["acts"] = [act.to_dict() for act in self.acts]
            result["story_structure"] = self.story_structure
            result["framework_complete"] = self.framework_complete
        
        # Legacy structure (for backward compatibility)
        if self.storyboard_items:
            result["storyboard_items"] = [item.to_dict() for item in self.storyboard_items]
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Screenplay':
        """Create screenplay from dictionary."""
        screenplay = cls(
            title=data.get("title", ""),
            premise=data.get("premise", "")
        )
        
        screenplay.genre = data.get("genre", [])
        screenplay.atmosphere = data.get("atmosphere", "")
        screenplay.story_length = data.get("story_length", "medium")
        screenplay.custom_duration_seconds = data.get("custom_duration_seconds", 0)
        _LEGACY_INTENT_MAP = {
            "Horror Short": "General Story",
            "Trailer / Teaser": "General Story",
            "Episodic Pilot": "General Story",
            "Looping Visual": "Visual Art / Abstract",
            "Music Video": "Visual Art / Abstract",
            "Proof of Concept": "General Story",
            "Experimental / Abstract": "Visual Art / Abstract",
        }
        raw_intent = data.get("intent", "General Story")
        screenplay.intent = _LEGACY_INTENT_MAP.get(raw_intent, raw_intent)
        screenplay.audio_strategy = data.get("audio_strategy", "generated_with_video")
        screenplay.story_outline = data.get("story_outline", {})
        screenplay.metadata = data.get("metadata", {})
        screenplay.version = data.get("version", "1.0")
        screenplay.created_at = data.get("created_at", "")
        screenplay.updated_at = data.get("updated_at", "")
        # Load identity blocks (backward compatible - initialize empty dict if missing)
        screenplay.identity_blocks = data.get("identity_blocks", {})
        screenplay.identity_block_ids = data.get("identity_block_ids", {})
        screenplay.identity_block_metadata = data.get("identity_block_metadata", {})
        # Backward-compat: ensure all entities have required keys
        for _eid, _meta in screenplay.identity_block_metadata.items():
            if "image_path" not in _meta:
                _meta["image_path"] = ""
            if "reference_image_prompt" not in _meta:
                _meta["reference_image_prompt"] = ""
            if "alias_of" not in _meta:
                _meta["alias_of"] = ""
            if "aliases" not in _meta:
                _meta["aliases"] = []
        screenplay.character_registry = data.get("character_registry", [])
        screenplay.character_registry_frozen = data.get("character_registry_frozen", False)
        # Load story settings with backward-compatible merge
        saved_ss = data.get("story_settings") or {}
        defaults_ss = get_default_story_settings()
        defaults_ss.update(saved_ss)
        if "audio_settings" in saved_ss:
            merged_audio = get_default_story_settings()["audio_settings"]
            merged_audio.update(saved_ss["audio_settings"])
            defaults_ss["audio_settings"] = merged_audio
        # Backward compat: migrate old higgsfield_model / higgsfield_image_model keys
        if "higgsfield_model" in defaults_ss and "video_model" not in saved_ss:
            defaults_ss["video_model"] = defaults_ss.pop("higgsfield_model")
        elif "higgsfield_model" in defaults_ss:
            defaults_ss.pop("higgsfield_model", None)
        if "higgsfield_image_model" in defaults_ss and "image_model" not in saved_ss:
            defaults_ss["image_model"] = defaults_ss.pop("higgsfield_image_model")
        elif "higgsfield_image_model" in defaults_ss:
            defaults_ss.pop("higgsfield_image_model", None)
        defaults_ss.setdefault("generation_platform", "higgsfield")
        defaults_ss.setdefault("platform_config", {})
        screenplay.story_settings = defaults_ss
        # Backward-compat: normalize characters to list and infer species
        if screenplay.story_outline and isinstance(screenplay.story_outline, dict):
            chars = screenplay.story_outline.get("characters", [])
            # Old manual stories stored characters as a dict — convert to list
            if isinstance(chars, dict):
                converted = []
                for key, val in chars.items():
                    if isinstance(val, dict):
                        if "name" not in val:
                            val["name"] = key
                        if "role" in val and val["role"] in ("Main Character", "Supporting Character"):
                            val["role"] = "main" if val["role"] == "Main Character" else "minor"
                        for field in ("outline", "growth_arc", "physical_appearance", "species"):
                            val.setdefault(field, "Human" if field == "species" else "")
                        converted.append(val)
                chars = converted
                screenplay.story_outline["characters"] = chars
            main_sl = str(screenplay.story_outline.get("main_storyline", "") or "")
            if isinstance(chars, list):
                from core.ai_generator import infer_species_from_text, normalize_species_label
                for ch in chars:
                    if not isinstance(ch, dict):
                        continue
                    # Normalize legacy field names from old manual stories
                    if "description" in ch and "outline" not in ch:
                        ch["outline"] = ch.pop("description", "")
                    if "character_arc" in ch and "growth_arc" not in ch:
                        ch["growth_arc"] = ch.pop("character_arc", "")
                    ch.setdefault("physical_appearance", "")
                    has_explicit_species = "species" in ch
                    ch.setdefault("species", "Human")
                    if "role" in ch and ch["role"] in ("Main Character", "Supporting Character"):
                        ch["role"] = "main" if ch["role"] == "Main Character" else "minor"
                    raw_sp = str(ch.get("species", "") or "").strip()
                    if raw_sp and raw_sp != "Human":
                        ch["species"] = normalize_species_label(raw_sp)
                        continue
                    if has_explicit_species:
                        continue
                    char_name = str(ch.get("name", "")).strip()
                    char_ctx = ""
                    for seg in main_sl.split(". "):
                        if char_name.upper() in seg.upper():
                            char_ctx += seg + ". "
                    inferred = infer_species_from_text(
                        str(ch.get("outline", "") or ""),
                        str(ch.get("physical_appearance", "") or ""),
                        char_ctx,
                        char_name
                    )
                    ch["species"] = inferred
            # Build registry from characters if it's empty (old manual stories)
            if not screenplay.character_registry:
                reg = []
                for ch in chars:
                    if isinstance(ch, dict):
                        n = str(ch.get("name", "")).strip()
                        if n and n.lower() not in {r.lower() for r in reg}:
                            reg.append(n)
                if reg:
                    screenplay.character_registry = reg
                    screenplay.character_registry_frozen = True
        # Wardrobe variant system
        screenplay.character_wardrobe_variants = data.get("character_wardrobe_variants", {})
        screenplay.character_last_wardrobe_variant = data.get("character_last_wardrobe_variant", {})
        # Episodic series metadata (None for standalone stories)
        screenplay.series_metadata = data.get("series_metadata", None)
        # Load brand context if present
        brand_context_data = data.get("brand_context")
        if brand_context_data:
            screenplay.brand_context = BrandContext.from_dict(brand_context_data)
        
        # Load new structure (acts/scenes) if available
        if "acts" in data:
            screenplay.story_structure = data.get("story_structure", {})
            screenplay.framework_complete = data.get("framework_complete", False)
            for act_data in data.get("acts", []):
                screenplay.add_act(StoryAct.from_dict(act_data))
        
        # Load legacy structure (storyboard_items) for backward compatibility
        if "storyboard_items" in data and not screenplay.acts:
            for item_data in data.get("storyboard_items", []):
                screenplay.add_item(StoryboardItem.from_dict(item_data))
        
        return screenplay
    
    def _json_default(self, obj):
        """Handle non-JSON-serializable types (datetime, etc.)."""
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    def save_to_file(self, filename: str) -> None:
        """Save screenplay to JSON file."""
        filename = os.path.abspath(filename)
        dirname = os.path.dirname(filename)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False, default=self._json_default)
            f.flush()
            try:
                if hasattr(f, 'fileno'):
                    os.fsync(f.fileno())
            except (OSError, AttributeError):
                pass
    
    @classmethod
    def load_from_file(cls, filename: str) -> 'Screenplay':
        """Load screenplay from JSON file."""
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)

