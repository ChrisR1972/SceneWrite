"""
Video Prompt Builder — three-layer prompt assembly for Higgsfield Cinema Studio 2.0.

Higgsfield uses a layered prompt system where each layer controls a separate
visual job.  Mixing layers causes drift, identity breaks, and camera jumps.

Layer 1 — KEYFRAME PROMPT (Popcorn)
    Static scene description: shot type, camera framing, lighting, environment,
    lens/film look, mood.  No motion verbs.  This generates the hero frame.

Layer 2 — IDENTITY PROMPT (Soul ID / Seedream / Seedance)
    Character identity locks, wardrobe overrides.  No camera, no lighting,
    no environment.  Keeps faces and clothing stable across frames.

Layer 3 — VIDEO PROMPT (Veo / Sora / Kling)
    Camera movement, acting, motion, dialogue, timing.  Specific camera verbs
    (dolly in, orbit, handheld) are encouraged here.  No identity details.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from .screenplay_engine import MultiShotCluster, Screenplay, StoryboardItem, StoryScene

from .screenplay_engine import (
    APERTURE_STYLE_OPTIONS,
    CAMERA_MOTION_OPTIONS,
    SHOT_TYPE_OPTIONS,
    VISUAL_STYLE_OPTIONS,
)


# ── Keywords forbidden in keyframe prompts (motion belongs in video layer) ──
_KEYFRAME_FORBIDDEN_VERBS = frozenset({
    "walks", "walking", "walk", "runs", "running", "run",
    "jumps", "jumping", "jump", "turns", "turning", "turn",
    "enters", "entering", "enter", "exits", "exiting", "exit",
    "approaches", "approaching", "approach", "speaks", "speaking", "speak",
    "pulls", "pulling", "pull", "pushes", "pushing", "push",
    "slides", "sliding", "slide", "opens", "opening", "open",
    "closes", "closing", "close", "grabs", "grabbing", "grab",
    "reaches", "reaching", "reach", "throws", "throwing", "throw",
    "kicks", "kicking", "kick", "hits", "hitting", "hit",
    "strikes", "striking", "strike", "fires", "firing", "fire",
    "swings", "swinging", "swing", "lifts", "lifting", "lift",
    "drops", "dropping", "drop", "falls", "falling", "fall",
    "rises", "rising", "rise", "climbs", "climbing", "climb",
    "crawls", "crawling", "crawl", "leaps", "leaping", "leap",
    "dives", "diving", "dive", "spins", "spinning", "spin",
    "rolls", "rolling", "roll", "ducks", "ducking", "duck",
    "dodges", "dodging", "dodge", "charges", "charging", "charge",
    "retreats", "retreating", "retreat", "flees", "fleeing", "flee",
    "chases", "chasing", "chase", "catches", "catching", "catch",
    "releases", "releasing", "release", "bursts", "bursting", "burst",
    "explodes", "exploding", "explode", "shatters", "shattering", "shatter",
    "crashes", "crashing", "crash", "collapses", "collapsing", "collapse",
    "emerges", "emerging", "emerge", "appears", "appearing", "appear",
    "vanishes", "vanishing", "vanish", "fades", "fading", "fade",
    "glows", "glowing", "glow", "flickers", "flickering", "flicker",
    "pours", "pouring", "pour", "spills", "spilling", "spill",
    "trips", "tripping", "trip", "stumbles", "stumbling", "stumble",
    "flips", "flipping", "flip", "activates", "activating", "activate",
})

# ── Pattern for *action* markup in storylines ──
_ACTION_MARKUP_RE = re.compile(r'\*([^*]+)\*')


def _extract_storyline_motion(storyline: str) -> str:
    """Extract motion-rich text from a storyline for the video/motion layer.

    Uses the *action* markup as the primary signal: sentences containing
    at least one *verb* are motion sentences and should drive the video
    prompt.  Returns the full storyline if no markup is found (fallback).
    """
    if not storyline:
        return ""
    if not _ACTION_MARKUP_RE.search(storyline):
        return storyline.strip()

    sentences = re.split(r'(?<=[.!?])\s+', storyline.strip())
    motion_sentences = [s for s in sentences if _ACTION_MARKUP_RE.search(s)]
    return " ".join(motion_sentences).strip() if motion_sentences else storyline.strip()


def _make_static_description(storyline: str) -> str:
    """Strip motion from a storyline, producing a static scene description.

    Splits into sentences and keeps only those that still carry meaningful
    composition info (characters, objects, environment) after removing
    *action* markup and motion verbs.  Pure-motion sentences are dropped
    entirely rather than left as awkward fragments.
    """
    if not storyline:
        return ""

    text = re.sub(r'\s*\([A-Z_]+[A-Z0-9_]*\)', '', storyline)
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())

    _ENTITY_SIGNAL = re.compile(
        r'[A-Z]{2,}(?:\s+[A-Z]{2,})*'
        r'|\[[^\]]+\]'
        r'|\{[^}]+\}'
        r'|(?<!\w)_[^_]+_(?!\w)'
    )

    kept: List[str] = []
    for sent in sentences:
        cleaned = _ACTION_MARKUP_RE.sub("", sent)
        words = cleaned.split()
        static_words = [
            w for w in words
            if w.lower().rstrip(".,;:!?") not in _KEYFRAME_FORBIDDEN_VERBS
        ]
        static_sent = " ".join(static_words).strip()
        static_sent = re.sub(r'\s{2,}', ' ', static_sent)
        static_sent = re.sub(r'\s+([.,;:!?])', r'\1', static_sent)

        if len(static_sent) < 8:
            continue
        if _ENTITY_SIGNAL.search(static_sent):
            kept.append(static_sent)

    return " ".join(kept).strip()


# =====================================================================
#  Image Auto-Bind Engine
# =====================================================================

class ImageAutoBindEngine:
    """Replace entity-name mentions in text with their Image N tag."""

    def __init__(self, image_assignments: Dict[str, Dict[str, str]]):
        self._map: Dict[str, str] = {}
        for slot, info in sorted(image_assignments.items()):
            name = (info.get("entity_name") or "").strip()
            if name:
                slot_label = slot.replace("_", " ").title()
                self._map[name.upper()] = slot_label

    def bind(self, text: str) -> str:
        if not text or not self._map:
            return text
        for name_upper, label in self._map.items():
            pattern = re.compile(re.escape(name_upper), re.IGNORECASE)
            text = pattern.sub(f"{label} ({name_upper})", text, count=1)
        return text


# =====================================================================
#  Validation
# =====================================================================

def validate_for_generation(item: "StoryboardItem") -> Tuple[bool, List[str]]:
    """Pre-generation validation.

    Returns (is_valid, error_messages).
    """
    errors: List[str] = []

    if not (item.environment_start_image or "").strip():
        errors.append("Hero Frame image is required (Environment Start Frame).")

    assignments = getattr(item, "image_assignments", {}) or {}
    for slot in ("image_1", "image_2", "image_3"):
        info = assignments.get(slot)
        if not info:
            continue
        path = (info.get("path") or "").strip()
        entity = (info.get("entity_name") or "").strip()
        if path and not entity:
            label = slot.replace("_", " ").title()
            errors.append(f"{label} has an uploaded image but no entity assignment.")

    return (len(errors) == 0, errors)


# ── Visual style prompt directives ───────────────────────────────────
_VISUAL_STYLE_DIRECTIVES: Dict[str, str] = {
    "photorealistic": "photorealistic rendering, natural textures, cinematic realism",
    "anime_cartoon": "anime-style cel shading, vibrant colors, clean line art",
    "vintage_retro": "vintage film grain, muted warm tones, light leaks, faded color palette",
    "film_noir": "high-contrast black and white, deep shadows, venetian blind lighting, dramatic chiaroscuro",
    "watercolor": "watercolor painting style, soft blended edges, visible brushstrokes, pigment textures",
    "comic_book": "comic book illustration, bold ink outlines, halftone dots, vivid flat colors",
    "cyberpunk_neon": "cyberpunk aesthetic, neon glow, holographic overlays, rain-slicked surfaces, dark urban",
    "fantasy_storybook": "fantasy storybook illustration, warm golden light, lush detail, slightly exaggerated proportions",
    "minimalist_flat": "minimalist flat design, clean geometric shapes, limited color palette, no texture",
    "dreamy_ethereal": "dreamy ethereal look, soft focus, lens flare, pastel tones, over-exposed highlights",
    "dark_gritty": "dark and gritty, desaturated palette, heavy grain, crushed blacks, harsh side-lighting",
    "art_deco": "art deco style, geometric patterns, gold and black palette, luxurious symmetry",
    "pencil_sketch": "pencil sketch style, rough line work, cross-hatching, unfinished storyboard feel",
    "oil_painting": "oil painting style, rich impasto texture, visible brushstrokes, classical composition",
    "vaporwave_synthwave": "vaporwave synthwave aesthetic, pink-purple-teal gradients, retro-futurist geometry, chrome reflections",
    "documentary_raw": "documentary raw look, natural available lighting, handheld feel, muted desaturated color grade",
}


def _resolve_visual_style(
    item: "StoryboardItem",
    screenplay: "Screenplay",
) -> str:
    """Return the effective visual style directive string.

    Item-level override wins; falls back to project story_settings default.
    Returns an empty string only for photorealistic (the implicit default).
    """
    style_key = (getattr(item, "visual_style", "") or "").strip()
    if not style_key:
        ss = getattr(screenplay, "story_settings", {}) or {}
        style_key = ss.get("visual_style", "photorealistic")
    return _VISUAL_STYLE_DIRECTIVES.get(style_key, "")


# =====================================================================
#  Layer 1 — KEYFRAME PROMPT (Popcorn)
# =====================================================================

def build_keyframe_prompt(
    item: "StoryboardItem",
    screenplay: "Screenplay",
    scene: Optional["StoryScene"] = None,
) -> str:
    """Build a structured Popcorn keyframe prompt for hero frame generation.

    Produces a static-only scene description with no motion verbs.
    Follows the Higgsfield Popcorn field structure:
      - Shot type and subject
      - Camera framing and angle
      - Lighting type and behavior
      - Environment and background
      - Lens / film look
      - Mood and tone
    """
    parts: List[str] = []

    # Shot type and subject
    shot_label = SHOT_TYPE_OPTIONS.get(
        getattr(item, "shot_type", "wide"), "Wide Establishing Shot"
    )
    storyline = (item.storyline or "").strip()
    static_storyline = _make_static_description(storyline)
    if static_storyline:
        parts.append(f"{shot_label} of {static_storyline}")
    else:
        parts.append(shot_label)

    # Camera framing (from shot type — already captured above)

    # Lighting
    lighting = (getattr(item, "lighting_description", "") or "").strip()
    if lighting:
        parts.append(f"Lighting: {lighting}")

    # Environment
    env_name = _get_environment_name(screenplay, scene)
    if env_name:
        parts.append(f"Setting: {env_name}")

    # Lens / film look
    focal = getattr(item, "focal_length", 35) or 35
    aperture_key = getattr(item, "aperture_style", "cinematic_bokeh") or "cinematic_bokeh"
    aperture_label = APERTURE_STYLE_OPTIONS.get(aperture_key, "Cinematic Bokeh")
    parts.append(f"{focal}mm lens, {aperture_label.lower()}")

    # Mood and tone
    mood = (getattr(item, "mood_tone", "") or "").strip()
    if mood:
        parts.append(f"Mood: {mood}")
    elif screenplay and screenplay.atmosphere:
        parts.append(f"Mood: {screenplay.atmosphere}")

    # Visual style
    style_directive = _resolve_visual_style(item, screenplay)
    if style_directive:
        parts.append(f"Style: {style_directive}")

    return ". ".join(parts)


def _get_environment_name(
    screenplay: "Screenplay", scene: Optional["StoryScene"]
) -> str:
    """Extract the environment name for the scene."""
    if not screenplay or not scene:
        return ""
    env_id = getattr(scene, "environment_id", None)
    if not env_id:
        return ""
    meta = getattr(screenplay, "identity_block_metadata", {}) or {}
    env_meta = meta.get(env_id, {})
    return (env_meta.get("name") or "").strip()


# =====================================================================
#  Layer 2 — IDENTITY PROMPT (Soul ID)
# =====================================================================

def build_identity_prompt(
    item: "StoryboardItem",
    screenplay: "Screenplay",
    scene: Optional["StoryScene"] = None,
) -> str:
    """Build the identity prompt layer for Soul ID / Seedream / Seedance.

    Contains character identity locks and wardrobe overrides only.
    No camera, lighting, or environment information.
    """
    assignments = getattr(item, "image_assignments", {}) or {}
    if not assignments:
        return ""

    sections: List[str] = []

    # Identity locks
    lock_section = _build_identity_lock_section(assignments, screenplay)
    if lock_section:
        sections.append(lock_section)

    # Wardrobe
    scene_id = getattr(scene, "scene_id", "") if scene else ""
    wardrobe_section = _build_wardrobe_section(assignments, screenplay, scene_id)
    if wardrobe_section:
        sections.append(wardrobe_section)

    return "\n\n".join(sections)


def _build_identity_lock_section(
    assignments: Dict[str, Dict[str, str]],
    screenplay: "Screenplay",
) -> str:
    """Identity locks — map image slots to entities with lock strength."""
    lock_strength = (
        screenplay.story_settings.get("identity_lock_strength", "standard")
        if hasattr(screenplay, "story_settings")
        else "standard"
    )

    strength_suffix = {
        "relaxed": "Maintain broad consistency but allow creative variation.",
        "standard": "Maintain identical facial features, body proportions, hairstyle, and skin tone.",
        "strict": "Reproduce identity VERBATIM. Zero creative deviation. Exact match required.",
    }
    suffix = strength_suffix.get(lock_strength, strength_suffix["standard"])

    lines: List[str] = ["IDENTITY LOCK:", ""]
    has_entries = False
    for slot in ("image_1", "image_2", "image_3"):
        info = assignments.get(slot)
        if not info:
            continue
        entity_name = (info.get("entity_name") or "").strip()
        entity_type = (info.get("entity_type") or "character").strip().lower()
        if not entity_name:
            continue
        label = slot.replace("_", " ").title()

        if entity_type == "character":
            lines.append(f"{label} represents {entity_name}.")
            lines.append(suffix)
        else:
            lines.append(f"{label} represents the {entity_name} {entity_type}.")
            lines.append("Do not reinterpret as a character.")
        lines.append("")
        has_entries = True

    if not has_entries:
        return ""
    return "\n".join(lines).rstrip()


def _build_wardrobe_section(
    assignments: Dict[str, Dict[str, str]],
    screenplay: "Screenplay",
    scene_id: str,
) -> str:
    """Wardrobe overrides for characters in this scene."""
    lines: List[str] = ["WARDROBE:", ""]
    has_entries = False

    scene = screenplay.get_scene(scene_id) if scene_id else None
    variant_ids = (
        (getattr(scene, "character_wardrobe_variant_ids", {}) or {}) if scene else {}
    )

    for slot in ("image_1", "image_2", "image_3"):
        info = assignments.get(slot)
        if not info:
            continue
        entity_type = (info.get("entity_type") or "").strip().lower()
        if entity_type != "character":
            continue
        entity_id = (info.get("entity_id") or "").strip()
        entity_name = (info.get("entity_name") or "").strip()
        if not entity_id or not entity_name:
            continue

        label = slot.replace("_", " ").title()
        vid = variant_ids.get(entity_id)
        variant = (
            screenplay.get_wardrobe_variant_by_id(entity_id, vid) if vid else None
        )

        if variant and variant.get("image_path"):
            var_label = variant.get("label") or "selected wardrobe"
            lines.append(
                f"{label} ({entity_name}): wearing the {var_label} wardrobe variant."
            )
            lines.append("Do not alter clothing from the wardrobe reference image.")
            lines.append("")
            has_entries = True
        else:
            wardrobe_text = screenplay.get_character_wardrobe_for_scene(
                scene_id, entity_id
            )
            if wardrobe_text:
                lines.append(f"{label} ({entity_name}) is wearing:")
                for wline in wardrobe_text.strip().splitlines():
                    wline = wline.strip()
                    if wline:
                        lines.append(
                            f"- {wline}" if not wline.startswith("-") else wline
                        )
                lines.append("")
                has_entries = True

    if not has_entries:
        return ""
    return "\n".join(lines).rstrip()


# =====================================================================
#  Layer 3 — VIDEO PROMPT (Motion / Camera / Dialogue)
# =====================================================================

def build_video_prompt(
    item: "StoryboardItem",
    screenplay: "Screenplay",
    scene: Optional["StoryScene"] = None,
) -> str:
    """Build the video/motion prompt layer for Veo / Sora / Kling.

    Contains camera movement, acting/action, dialogue, and timing.
    No identity details, no lighting, no static composition.
    Camera verbs are encouraged in this layer.
    """
    assignments = getattr(item, "image_assignments", {}) or {}
    binder = ImageAutoBindEngine(assignments)
    sections: List[str] = []

    # Camera movement
    camera_section = _build_camera_section(item)
    if camera_section:
        sections.append(camera_section)

    # Motion / Action
    motion_section = _build_motion_section(item, binder)
    sections.append(motion_section)

    # Dialogue
    dialogue_section = _build_dialogue_section(item, assignments)
    if dialogue_section:
        sections.append(dialogue_section)

    # Audio
    audio_section = _build_audio_section(screenplay, item=item)
    if audio_section:
        sections.append(audio_section)

    return "\n\n".join(sections)


def _build_camera_section(item: "StoryboardItem") -> str:
    """Camera movement directive using Cinema Studio 2.0 verbs."""
    camera_key = getattr(item, "camera_motion", "static") or "static"
    camera_label = CAMERA_MOTION_OPTIONS.get(camera_key, "Static (Locked-Off)")

    if camera_key == "static":
        return "CAMERA: Static, locked-off composition."

    lines: List[str] = [f"CAMERA: {camera_label}."]

    # If there's a camera_notes field with additional detail, include it
    notes = (getattr(item, "camera_notes", "") or "").strip()
    if notes:
        lines.append(notes)

    return "\n".join(lines)


def _build_motion_section(
    item: "StoryboardItem", binder: ImageAutoBindEngine
) -> str:
    """Action and movement layer — what characters/subjects do.

    Prefers detailed motion from the storyline's *action* markup.  If
    item.prompt is substantially richer than the storyline motion, it
    wins.  If item.prompt is vague (short / lacks action verbs) while the
    storyline has explicit motion, the storyline motion is used instead.
    """
    lines: List[str] = ["ACTION:", ""]

    storyline = (item.storyline or "").strip()
    prompt = (item.prompt or "").strip()
    storyline_motion = _extract_storyline_motion(storyline)

    _MOTION_VERB_SAMPLE = {
        "pulls", "pushes", "slides", "opens", "closes", "grabs",
        "lifts", "drops", "throws", "swings", "kicks", "hits",
        "runs", "walks", "jumps", "turns", "spins", "rolls",
        "bursts", "explodes", "crashes", "emerges", "falls", "rises",
        "releases", "reaches", "fires", "charges", "trips", "flips",
    }

    def _motion_richness(text: str) -> int:
        lower = text.lower()
        return sum(1 for v in _MOTION_VERB_SAMPLE if v in lower)

    if prompt and storyline_motion:
        prompt_richness = _motion_richness(prompt)
        storyline_richness = _motion_richness(storyline_motion)
        if prompt_richness >= storyline_richness and len(prompt) >= len(storyline_motion) * 0.6:
            action_text = prompt
        else:
            action_text = storyline_motion
    elif prompt:
        action_text = prompt
    elif storyline_motion:
        action_text = storyline_motion
    else:
        action_text = ""

    if action_text:
        lines.append(binder.bind(action_text))
    else:
        lines.append("Natural movement and realistic motion.")

    return "\n".join(lines).rstrip()


def _build_dialogue_section(
    item: "StoryboardItem",
    assignments: Dict[str, Dict[str, str]],
) -> str:
    """Dialogue layer with speaker-to-image-slot binding.

    Supported formats::

        CHARACTER_NAME: "dialogue text"
        CHARACTER_NAME: dialogue text
        "standalone dialogue"
    """
    dialogue = (item.dialogue or "").strip()
    if not dialogue:
        return ""

    name_to_label: Dict[str, str] = {}
    for slot in ("image_1", "image_2", "image_3"):
        info = assignments.get(slot)
        if not info:
            continue
        if (info.get("entity_type") or "").lower() == "character":
            ename = (info.get("entity_name") or "").strip()
            if ename:
                label = slot.replace("_", " ").title()
                name_to_label[ename.upper()] = f"{label} ({ename})"

    lines: List[str] = ["DIALOGUE:", ""]

    structured_pat = re.compile(
        r'^([A-Z][A-Z\s\'\-\.]+?)\s*:\s*["\u201c]?(.*?)["\u201d]?\s*$'
    )
    parsed_any = False
    for raw_line in dialogue.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        m = structured_pat.match(raw_line)
        if m:
            speaker = m.group(1).strip()
            text = m.group(2).strip()
            label = name_to_label.get(speaker.upper())
            if label:
                lines.append(f'{label} says: "{text}"')
            else:
                lines.append(f'{speaker} says: "{text}"')
            lines.append("")
            parsed_any = True
        else:
            clean = raw_line.strip('""\u201c\u201d')
            lines.append(f'"{clean}"')
            lines.append("")
            parsed_any = True

    if not parsed_any:
        first_label = next(iter(name_to_label.values()), None)
        if first_label:
            lines.append(f'{first_label} says:')
        lines.append(f'"{dialogue}"')

    return "\n".join(lines).rstrip()


_SFX_TAG_RE = re.compile(r'\(([a-z][a-z0-9_]+)\)')


def _extract_sfx_tags(item: Optional["StoryboardItem"]) -> List[str]:
    """Pull all ``(lowercase_tag)`` SFX markers from the item's text fields."""
    if item is None:
        return []
    blob = " ".join(
        filter(
            None,
            [
                getattr(item, "storyline", ""),
                getattr(item, "prompt", ""),
                getattr(item, "image_prompt", ""),
            ],
        )
    )
    seen: set = set()
    tags: List[str] = []
    for m in _SFX_TAG_RE.finditer(blob):
        tag = m.group(0)
        if tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


def _build_audio_section(
    screenplay: "Screenplay",
    item: Optional["StoryboardItem"] = None,
    items: Optional[List["StoryboardItem"]] = None,
) -> str:
    """Audio directive section."""
    ss = getattr(screenplay, "story_settings", {}) or {}
    audio = ss.get("audio_settings", {})

    dlg_mode = audio.get("dialogue_generation_mode", "generate")
    sfx_density = audio.get("sfx_density", "cinematic")
    music_strategy = audio.get("music_strategy", "ambient")

    all_off = (
        dlg_mode == "disabled"
        and sfx_density == "minimal"
        and music_strategy == "none"
    )
    if all_off:
        return ""

    lines: List[str] = ["AUDIO:", ""]

    if dlg_mode == "disabled":
        lines.append("No dialogue audio.")
    elif dlg_mode == "script_only":
        lines.append("Dialogue: script only (no audio cues).")

    sfx_tags: List[str] = []
    if sfx_density != "minimal":
        if items:
            for it in items:
                sfx_tags.extend(_extract_sfx_tags(it))
        elif item:
            sfx_tags = _extract_sfx_tags(item)

    if sfx_tags:
        lines.append(f"Sound Effects: {', '.join(dict.fromkeys(sfx_tags))}.")
    else:
        sfx_map = {
            "minimal": "SFX: Essential only.",
            "cinematic": "SFX: Cinematic layering — environmental ambience and interaction sounds.",
            "high_impact": "SFX: Dense, trailer-style layering.",
        }
        lines.append(sfx_map.get(sfx_density, sfx_map["cinematic"]))

    music_map = {
        "none": "Music: None.",
        "ambient": "Music: Low ambient tension score.",
        "thematic": "Music: Thematic recurring motif.",
        "full_cinematic": "Music: Full cinematic score with dynamic cue progression.",
    }
    lines.append(music_map.get(music_strategy, music_map["ambient"]))

    return "\n".join(lines).rstrip()


# =====================================================================
#  Output sanitisation
# =====================================================================

_ENTITY_ID_RE = re.compile(r"\b(?:CHARACTER|VEHICLE|OBJECT|ENVIRONMENT)_[A-F0-9]{4}\b")
_JSON_FRAGMENT_RE = re.compile(r"\{[^{}]{4,}\}")
_MARKDOWN_RE = re.compile(r"[*#`]{1,3}")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def _sanitize(text: str) -> str:
    """Remove internal metadata, markdown, JSON fragments, normalise whitespace."""
    text = _ENTITY_ID_RE.sub("", text)
    text = _JSON_FRAGMENT_RE.sub("", text)
    text = _MARKDOWN_RE.sub("", text)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    lines = [ln.rstrip() for ln in text.splitlines()]
    return "\n".join(lines).strip()


# =====================================================================
#  Compile All Prompts — public API
# =====================================================================

def compile_all_prompts(
    item: "StoryboardItem",
    screenplay: "Screenplay",
    scene: Optional["StoryScene"] = None,
) -> Dict[str, object]:
    """Validate and compile all three prompt layers.

    Returns::

        {
            "success": bool,
            "keyframe_prompt": str,
            "identity_prompt": str,
            "video_prompt": str,
            "errors": List[str],
        }
    """
    ok, errors = validate_for_generation(item)
    if errors:
        return {
            "success": False,
            "keyframe_prompt": "",
            "identity_prompt": "",
            "video_prompt": "",
            "errors": errors,
        }

    keyframe = _sanitize(build_keyframe_prompt(item, screenplay, scene))
    identity = _sanitize(build_identity_prompt(item, screenplay, scene))
    video = _sanitize(build_video_prompt(item, screenplay, scene))

    return {
        "success": True,
        "keyframe_prompt": keyframe,
        "identity_prompt": identity,
        "video_prompt": video,
        "errors": [],
    }


# =====================================================================
#  Legacy compile_master_prompt — backward compatibility
# =====================================================================

def compile_master_prompt(
    item: "StoryboardItem",
    screenplay: "Screenplay",
    scene: "StoryScene",
    cluster: Optional["MultiShotCluster"] = None,
    cluster_items: Optional[List["StoryboardItem"]] = None,
) -> Tuple[bool, str, List[str]]:
    """Legacy entry point — compiles all layers into a single text block.

    Returns ``(success, combined_prompt_string, error_messages)``.
    """
    result = compile_all_prompts(item, screenplay, scene)
    if not result["success"]:
        return (False, "", result["errors"])

    sections = []
    if result["keyframe_prompt"]:
        sections.append(f"--- KEYFRAME (Hero Frame) ---\n{result['keyframe_prompt']}")
    if result["identity_prompt"]:
        sections.append(f"--- IDENTITY ---\n{result['identity_prompt']}")
    if result["video_prompt"]:
        sections.append(f"--- VIDEO (Motion) ---\n{result['video_prompt']}")

    combined = "\n\n".join(sections) + "\n"
    return (True, combined, [])


# =====================================================================
#  Legacy single-shot builder (kept for backward compatibility)
# =====================================================================

def build_single_shot_prompt(
    item: "StoryboardItem",
    screenplay: "Screenplay",
    scene: "StoryScene",
) -> str:
    """Legacy: assemble a combined prompt for a single storyboard item."""
    result = compile_all_prompts(item, screenplay, scene)
    parts = filter(None, [
        result["keyframe_prompt"],
        result["identity_prompt"],
        result["video_prompt"],
    ])
    return "\n\n".join(parts) + "\n"


def build_multishot_cluster_prompt(
    cluster: "MultiShotCluster",
    screenplay: "Screenplay",
    scene: "StoryScene",
    items: Optional[List["StoryboardItem"]] = None,
) -> str:
    """Legacy: assemble a combined prompt for a multi-shot cluster.

    Compiles each item's 3 layers and combines with cluster metadata.
    """
    items = items or []
    sections: List[str] = []

    header = f"MULTI-SHOT CLUSTER — {len(cluster.shots)} shots, {cluster.total_duration}s total"
    sections.append(header)

    for it in items:
        result = compile_all_prompts(it, screenplay, scene)
        shot_num = getattr(it, "shot_number_in_cluster", None) or "?"
        block = f"Shot {shot_num} ({it.duration}s):"
        sub_parts = filter(None, [
            result["keyframe_prompt"],
            result["identity_prompt"],
            result["video_prompt"],
        ])
        block += "\n" + "\n".join(sub_parts)
        sections.append(block)

    return "\n\n".join(sections) + "\n"
