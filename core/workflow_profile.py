"""
Workflow Profile system for conditional story creation workflows.
Determines wizard steps, required fields, and AI prompts based on story length and intent.
"""

from enum import Enum
from typing import Dict, Any, List, Optional


class WorkflowProfile(Enum):
    """Workflow profile types that determine the creation process."""
    NARRATIVE = "narrative"  # Traditional story with plot, characters, arcs
    PROMOTIONAL = "promotional"  # Advertisement, brand film, marketing content
    EXPERIMENTAL = "experimental"  # Abstract, non-linear, artistic


class WorkflowProfileManager:
    """Manages workflow profile determination and configuration."""
    
    INTENT_PROFILE_MAP = {
        "General Story": WorkflowProfile.NARRATIVE,
        "Advertisement / Brand Film": WorkflowProfile.PROMOTIONAL,
        "Social Media / Short-form": WorkflowProfile.NARRATIVE,
        "Visual Art / Abstract": WorkflowProfile.EXPERIMENTAL,
    }
    
    @classmethod
    def get_profile(cls, length: str, intent: str) -> WorkflowProfile:
        """Determine workflow profile from length and intent."""
        return cls.INTENT_PROFILE_MAP.get(intent, WorkflowProfile.NARRATIVE)
    
    @classmethod
    def requires_story_outline(cls, profile: WorkflowProfile) -> bool:
        """Determine if story outline step is required."""
        return profile == WorkflowProfile.NARRATIVE
    
    @classmethod
    def requires_characters(cls, profile: WorkflowProfile) -> bool:
        """Determine if character creation is required."""
        return profile == WorkflowProfile.NARRATIVE
    
    @classmethod
    def get_premise_prompt_type(cls, profile: WorkflowProfile) -> str:
        """Get the type of premise prompt to use."""
        if profile == WorkflowProfile.PROMOTIONAL:
            return "brand_concept"
        elif profile == WorkflowProfile.EXPERIMENTAL:
            return "experimental_concept"
        else:
            return "narrative_premise"
    
    @classmethod
    def get_outline_structure(cls, profile: WorkflowProfile) -> Dict[str, Any]:
        """Get the structure for outline step based on profile."""
        if profile == WorkflowProfile.PROMOTIONAL:
            return {
                "type": "promotional",
                "fields": ["core_message", "emotional_beats", "visual_motifs", "call_to_action"],
                "skip_subplots": True,
                "skip_characters": True,
                "skip_conclusion": True
            }
        elif profile == WorkflowProfile.EXPERIMENTAL:
            return {
                "type": "experimental",
                "fields": ["concept", "visual_themes", "mood_progression"],
                "skip_subplots": True,
                "skip_characters": True,
                "skip_conclusion": True
            }
        else:
            return {
                "type": "narrative",
                "fields": ["subplots", "characters", "conclusion"],
                "skip_subplots": False,
                "skip_characters": False,
                "skip_conclusion": False
            }
    
    @classmethod
    def get_framework_structure(cls, profile: WorkflowProfile, length: str) -> Dict[str, Any]:
        """Get framework structure requirements based on profile and length."""
        if profile == WorkflowProfile.PROMOTIONAL:
            return {
                "act_count": 1,
                "scene_type": "visual_beats",
                "focus": ["visual_action", "mood_progression", "brand_reveal"],
                "characters_optional": True
            }
        elif profile == WorkflowProfile.EXPERIMENTAL:
            return {
                "act_count": 1,
                "scene_type": "visual_themes",
                "focus": ["mood", "imagery", "abstract_concepts"],
                "characters_optional": True
            }
        else:
            length_map = {
                "micro": {"act_count": 1, "scenes_per_act": "1-5"},
                "short": {"act_count": 3, "scenes_per_act": "3-5"},
                "medium": {"act_count": 3, "scenes_per_act": "5-8"},
                "long": {"act_count": 5, "scenes_per_act": "6-10"}
            }
            base = length_map.get(length, length_map["medium"])
            return {
                "act_count": base["act_count"],
                "scene_type": "narrative_scenes",
                "focus": ["plot_progression", "character_development", "story_arcs"],
                "characters_optional": False
            }
    
    @classmethod
    def get_premise_ui_config(cls, profile: WorkflowProfile, intent: str = "") -> Dict[str, Any]:
        """Get UI configuration for premise step based on profile and intent."""
        if profile == WorkflowProfile.PROMOTIONAL:
            return {
                "genre_optional": True,
                "genre_visible": False,
                "genre_label": "Category (Optional)",
                "atmosphere_label": "Brand Tone",
                "character_count_optional": True,
                "character_count_max": 2,
                "character_count_default": 0
            }
        elif profile == WorkflowProfile.EXPERIMENTAL:
            return {
                "genre_optional": False,
                "genre_visible": True,
                "genre_label": "Themes",
                "atmosphere_label": "Mood/Tone",
                "character_count_optional": True,
                "character_count_max": 3,
                "character_count_default": 0
            }
        else:
            config = {
                "genre_optional": False,
                "genre_visible": True,
                "genre_label": "Genres",
                "atmosphere_label": "Atmosphere/Tone",
                "character_count_optional": False,
                "character_count_max": 10,
                "character_count_default": 4
            }
            if intent == "Social Media / Short-form":
                config["character_count_max"] = 4
                config["character_count_default"] = 2
            return config
