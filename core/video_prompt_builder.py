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
    # Locomotion
    "walks", "walking", "walk", "runs", "running", "run",
    "steps", "stepping", "step", "sprints", "sprinting", "sprint",
    "dashes", "dashing", "dash", "marches", "marching", "march",
    "creeps", "creeping", "creep", "sneaks", "sneaking", "sneak",
    "tiptoes", "tiptoeing", "tiptoe", "paces", "pacing", "pace",
    "staggers", "staggering", "stagger", "limps", "limping", "limp",
    "enters", "entering", "enter", "exits", "exiting", "exit",
    "approaches", "approaching", "approach",
    # Jumping / climbing / falling
    "jumps", "jumping", "jump", "leaps", "leaping", "leap",
    "climbs", "climbing", "climb", "dives", "diving", "dive",
    "falls", "falling", "fall", "drops", "dropping", "drop",
    "rises", "rising", "rise", "launches", "launching", "launch",
    "lands", "landing", "land",
    # Turning / spinning / rolling
    "turns", "turning", "turn", "spins", "spinning", "spin",
    "rolls", "rolling", "roll", "twists", "twisting", "twist",
    "swerves", "swerving", "swerve",
    # Evasive / reactive
    "ducks", "ducking", "duck", "dodges", "dodging", "dodge",
    "flinches", "flinching", "flinch", "recoils", "recoiling", "recoil",
    "lurches", "lurching", "lurch", "wobbles", "wobbling", "wobble",
    "sways", "swaying", "sway", "trembles", "trembling", "tremble",
    "shakes", "shaking", "shake",
    # Combat / forceful
    "punches", "punching", "punch", "kicks", "kicking", "kick",
    "hits", "hitting", "hit", "strikes", "striking", "strike",
    "lunges", "lunging", "lunge", "swings", "swinging", "swing",
    "slams", "slamming", "slam", "charges", "charging", "charge",
    "fires", "firing", "fire",
    # Hand actions (transient motion)
    "grabs", "grabbing", "grab", "yanks", "yanking", "yank",
    "tugs", "tugging", "tug", "pulls", "pulling", "pull",
    "pushes", "pushing", "push", "throws", "throwing", "throw",
    "tosses", "tossing", "toss", "catches", "catching", "catch",
    "releases", "releasing", "release", "squeezes", "squeezing", "squeeze",
    "presses", "pressing", "press", "taps", "tapping", "tap",
    "knocks", "knocking", "knock", "flips", "flipping", "flip",
    "reaches", "reaching", "reach", "lifts", "lifting", "lift",
    "lowers", "lowering", "lower", "hoists", "hoisting", "hoist",
    "picks", "picking",
    # Opening / closing
    "opens", "opening", "open", "closes", "closing", "close",
    "slides", "sliding", "slide", "seals", "sealing", "seal",
    # Pursuit / retreat
    "retreats", "retreating", "retreat", "flees", "fleeing", "flee",
    "chases", "chasing", "chase",
    # Speaking (audio, not visual)
    "speaks", "speaking", "speak",
    # Destruction / impact
    "bursts", "bursting", "burst", "explodes", "exploding", "explode",
    "shatters", "shattering", "shatter", "crashes", "crashing", "crash",
    "collapses", "collapsing", "collapse", "crumbles", "crumbling", "crumble",
    "snaps", "snapping", "snap", "cracks", "cracking", "crack",
    # Appearing / vanishing
    "emerges", "emerging", "emerge", "appears", "appearing", "appear",
    "vanishes", "vanishing", "vanish", "fades", "fading", "fade",
    # Light effects (transient)
    "glows", "glowing", "glow", "flickers", "flickering", "flicker",
    "flashes", "flashing", "flash", "flares", "flaring", "flare",
    "blinks", "blinking", "blink", "brightens", "brightening", "brighten",
    "darkens", "darkening", "darken", "pulses", "pulsing", "pulse",
    "ignites", "igniting", "ignite",
    # Liquid / material
    "pours", "pouring", "pour", "spills", "spilling", "spill",
    "floods", "flooding", "flood",
    # Stumbling
    "trips", "tripping", "trip", "stumbles", "stumbling", "stumble",
    "crawls", "crawling", "crawl",
    # Vehicle motion
    "accelerates", "accelerating", "accelerate",
    "docks", "docking", "dock", "skids", "skidding", "skid",
    "brakes", "braking", "brake", "reverses", "reversing", "reverse",
    "starts", "starting", "start", "stops", "stopping", "stop",
    # Repetitive hand / interaction motion
    "types", "typing", "type", "scribbles", "scribbling", "scribble",
    "scrolls", "scrolling", "scroll", "dials", "dialing", "dial",
    "swipes", "swiping", "swipe", "writes", "writing", "write",
    "scratches", "scratching", "scratch", "stirs", "stirring", "stir",
    "wraps", "wrapping", "wrap", "unwraps", "unwrapping", "unwrap",
    "loads", "loading", "load", "unloads", "unloading", "unload",
    "plugs", "plugging", "plug", "unplugs", "unplugging", "unplug",
    # Misc motion
    "activates", "activating", "activate",
    "shifts", "shifting", "shift", "settles", "settling", "settle",
    "rumbles", "rumbling", "rumble", "echoes", "echoing", "echo",
})

# Pose / state verbs deliberately KEPT in keyframe prompts (not forbidden):
# sit, stand, lean, hold, kneel, crouch, look, brace, point, freeze, halt,
# hang, perch, prop, balance, dangle, drape, stretch, hover, drift, burn,
# smolder, wave, gesture, nod, shrug, wipe, adjust, draw

# ── Pose / state verb → participial form for image-gen friendliness ──
# Image models respond much better to "-ing" / "-ed" forms than present tense.
_POSE_VERB_TO_PARTICIPLE: Dict[str, str] = {
    "sits": "sitting", "sit": "sitting",
    "stands": "standing", "stand": "standing",
    "leans": "leaning", "lean": "leaning",
    "holds": "holding", "hold": "holding",
    "kneels": "kneeling", "kneel": "kneeling",
    "crouches": "crouching", "crouch": "crouching",
    "looks": "looking", "look": "looking",
    "braces": "bracing", "brace": "bracing",
    "points": "pointing", "point": "pointing",
    "freezes": "frozen", "freeze": "frozen",
    "halts": "halted", "halt": "halted",
    "hangs": "hanging", "hang": "hanging",
    "perches": "perched", "perch": "perched",
    "props": "propped", "prop": "propped",
    "balances": "balancing", "balance": "balancing",
    "dangles": "dangling", "dangle": "dangling",
    "drapes": "draped", "drape": "draped",
    "stretches": "stretching", "stretch": "stretching",
    "hovers": "hovering", "hover": "hovering",
    "drifts": "drifting", "drift": "drifting",
    "burns": "burning", "burn": "burning",
    "smolders": "smoldering", "smolder": "smoldering",
    "waves": "waving", "wave": "waving",
    "gestures": "gesturing", "gesture": "gesturing",
    "nods": "nodding", "nod": "nodding",
    "shrugs": "shrugging", "shrug": "shrugging",
    "wipes": "wiping", "wipe": "wiping",
    "adjusts": "adjusting", "adjust": "adjusting",
    "draws": "drawing", "draw": "drawing",
    "grips": "gripping", "grip": "gripping",
    "clutches": "clutching", "clutch": "clutching",
    "cradles": "cradling", "cradle": "cradling",
    "rests": "resting", "rest": "resting",
    "reclines": "reclining", "recline": "reclining",
    "squats": "squatting", "squat": "squatting",
    "straddles": "straddling", "straddle": "straddling",
    "lies": "lying", "lie": "lying",
    "lays": "laying", "lay": "laying",
}

# ── Motion-intensity adverbs to strip from keyframe prompts ──
_MOTION_ADVERBS = frozenset({
    "frantically", "desperately", "quickly", "rapidly", "hurriedly",
    "urgently", "furiously", "violently", "aggressively", "wildly",
    "hastily", "swiftly", "briskly", "fiercely", "forcefully",
    "abruptly", "sharply", "suddenly", "immediately", "nervously",
    "anxiously", "panicking", "recklessly", "feverishly", "breathlessly",
})

# ── Broken-sentence detection: pronoun/name + dangling particle after verb removal ──
_BROKEN_SENT_RE = re.compile(
    # "She up a [display]" — pronoun + orphaned preposition
    r'^(?:she|he|they|it|we|i|the\b\S*)\s+'
    r'(?:up|down|out|in|off|on|over|away|back|through|around|into|onto|across)\b'
    # "TALON his arrow" — CAPS name + possessive/article (verb was stripped)
    r'|^[A-Z][A-Z\s\']+\s+(?:his|her|its|their|the|a|an)\s+\w',
    re.IGNORECASE,
)

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
        cleaned = _ACTION_MARKUP_RE.sub(r'\1', sent)
        words = cleaned.split()
        static_words = []
        for w in words:
            bare = w.lower().rstrip(".,;:!?")
            if bare in _KEYFRAME_FORBIDDEN_VERBS:
                continue
            if bare in _MOTION_ADVERBS:
                continue
            participle = _POSE_VERB_TO_PARTICIPLE.get(bare)
            if participle:
                trailing = w[len(bare):]
                static_words.append(participle + trailing)
            else:
                static_words.append(w)
        static_sent = " ".join(static_words).strip()
        static_sent = re.sub(r'\s{2,}', ' ', static_sent)
        static_sent = re.sub(r'\s+([.,;:!?])', r'\1', static_sent)

        # Drop sentences broken by verb removal (e.g. "She up a [display]")
        if _BROKEN_SENT_RE.match(static_sent):
            continue

        if len(static_sent) < 8:
            continue
        if _ENTITY_SIGNAL.search(static_sent):
            kept.append(static_sent)

    return " ".join(kept).strip()


def _strip_character_descriptions(text: str) -> str:
    """Remove inline character descriptions, keeping only the name and action.

    Transforms patterns like:
        LUCY CHEN a woman in her late 20s wearing a paint-splattered
        denim jacket over a black t-shirt and practical cargo pants, kneels ...
    Into:
        LUCY CHEN kneels ...

    Also removes possessive appearance clauses like:
        , her dark hair pulled into a messy bun.
    """
    if not text:
        return ""

    # Pass 1: CAPS NAME + article + gender/age trigger word + description up
    # to the comma that precedes the action verb.
    result = re.sub(
        r'([A-Z]{2,}(?:\s+[A-Z]{2,})*)'
        r',?\s+(?:a |an |the )?'
        r'(?:woman|man|girl|boy|teen|teenager|child|person|figure|elderly|'
        r'young|old|mid-|middle-aged|late-|early-)'
        r'[^,]*,\s*',
        r'\1 ',
        text,
        flags=re.DOTALL,
    )

    # Pass 2: possessive appearance clauses — ", her dark hair pulled into..."
    result = re.sub(
        r',?\s+(?:her|his|their)\s+(?:\w+\s+){0,3}'
        r'(?:hair|eyes|skin|face|beard|brow|brows|lips|cheeks|complexion|'
        r'build|features|figure|freckles|dimples)'
        r'[^.,;]*[.,;]?\s*',
        ' ',
        result,
        flags=re.IGNORECASE,
    )

    return re.sub(r'\s{2,}', ' ', result).strip()


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
    Images are optional reference material — their absence never blocks
    prompt generation.
    """
    errors: List[str] = []

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


def get_image_warnings(item: "StoryboardItem") -> List[str]:
    """Return non-blocking warnings about missing reference images."""
    warnings: List[str] = []
    if not (item.environment_start_image or "").strip():
        warnings.append("No Hero Frame image assigned (Environment Start Frame).")
    assignments = getattr(item, "image_assignments", {}) or {}
    if not any((info.get("path") or "").strip() for info in assignments.values()):
        warnings.append("No entity reference images assigned.")
    return warnings


# ── Visual style prompt directives ───────────────────────────────────
_VISUAL_STYLE_DIRECTIVES: Dict[str, str] = {
    "photorealistic": "photorealistic rendering, natural textures, cinematic realism",
    "anime_cartoon": "anime-style cel shading, vibrant colors, clean line art",
    "3d_cartoon_pixar": "Pixar-style 3D cartoon rendering, smooth rounded forms, subsurface skin scattering, expressive oversized eyes, stylized proportions, rich saturated lighting, plastic-like material shaders",
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
    "grindhouse_70s": "1970s grindhouse exploitation film look, heavy film grain, washed-out saturated color, soft focus, scratched print artifacts, warm amber highlights, gritty low-budget cinematography",
}


def get_visual_style_directive(style_key: str) -> str:
    """Return the visual style directive string for a given style key.

    Public API so other modules (e.g. ai_generator) can resolve a style key
    to its prompt directive without duplicating the mapping.
    Returns empty string for unknown keys.
    """
    return _VISUAL_STYLE_DIRECTIVES.get(style_key, "")


def _resolve_visual_style(
    item: "StoryboardItem",
    screenplay: "Screenplay",
) -> str:
    """Return the effective visual style directive string.

    Item-level override wins; falls back to project story_settings default.
    """
    style_key = (getattr(item, "visual_style", "") or "").strip()
    if not style_key:
        ss = getattr(screenplay, "story_settings", None) or {}
        style_key = ss.get("visual_style") or "photorealistic"
    return _VISUAL_STYLE_DIRECTIVES.get(style_key, "")


# =====================================================================
#  Layer 1 — KEYFRAME PROMPT (Popcorn)
# =====================================================================

_FILL_FRAME_PATTERNS = re.compile(
    r'fills?\s+(?:the\s+)?frame'
    r'|dominates?\s+(?:the\s+)?frame'
    r'|frame[- ]filling'
    r'|takes?\s+up\s+(?:the\s+)?(?:entire|whole|full)\s+(?:frame|screen)'
    r'|covers?\s+(?:the\s+)?(?:entire|whole|full)\s+(?:frame|screen)'
    r'|(?:entire|whole|full)\s+frame',
    re.IGNORECASE,
)

_CLOSE_INTENT_PATTERNS = re.compile(
    r'close\s+on\b'
    r'|detail\s+of\b'
    r'|insert\s+(?:shot\s+)?of\b'
    r'|tight\s+on\b'
    r'|macro\s+(?:shot\s+)?of\b'
    r'|focus(?:ed)?\s+on\b',
    re.IGNORECASE,
)

_OTS_PATTERNS = re.compile(
    r'over\s+(?:\w+\s+)?shoulder'
    r'|behind\s+(?:\w+\s+){0,4}shoulder'
    r'|from\s+behind\b'
    r'|(?:camera|shot)\s+(?:positioned\s+)?behind\b',
    re.IGNORECASE,
)

_LOW_ANGLE_PATTERNS = re.compile(
    r'low\s+angle\b|from\s+below\b|looking\s+up\s+at\b|worm\'?s?\s+eye',
    re.IGNORECASE,
)

_HIGH_ANGLE_PATTERNS = re.compile(
    r'high\s+angle\b|from\s+above\b|looking\s+down\s+(?:at|on)\b|bird\'?s?\s+eye',
    re.IGNORECASE,
)

_SHOT_ESCALATION: Dict[str, str] = {
    "wide": "close_up",
    "medium": "close_up",
    "over_shoulder": "close_up",
    "two_shot": "close_up",
    "birds_eye": "close_up",
    "low_angle": "close_up",
    "high_angle": "close_up",
    "dutch_angle": "close_up",
    "close_up": "extreme_close_up",
}


def _detect_framing_override(composition: str, shot_key: str) -> Tuple[str, str]:
    """Detect if composition notes require a different framing than the shot type.

    Returns (effective_shot_key, framing_prefix).
    framing_prefix is an extra descriptor to front-load (e.g. "frame-filling").

    Priority: fill-frame > close-intent > camera-angle overrides.
    """
    if not composition:
        return shot_key, ""

    if _FILL_FRAME_PATTERNS.search(composition):
        escalated = _SHOT_ESCALATION.get(shot_key, shot_key)
        return escalated, "frame-filling"

    if _CLOSE_INTENT_PATTERNS.search(composition):
        escalated = _SHOT_ESCALATION.get(shot_key, shot_key)
        return escalated, "tight"

    if _OTS_PATTERNS.search(composition):
        return "over_shoulder", "over-the-shoulder"

    if _LOW_ANGLE_PATTERNS.search(composition):
        return "low_angle", "low-angle"

    if _HIGH_ANGLE_PATTERNS.search(composition):
        return "high_angle", "high-angle"

    return shot_key, ""


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

    composition = (getattr(item, "composition_notes", "") or "").strip()
    shot_key = getattr(item, "shot_type", "wide") or "wide"

    # Auto-escalate shot type when composition demands tighter framing
    effective_shot_key, framing_prefix = _detect_framing_override(
        composition, shot_key
    )
    shot_label = SHOT_TYPE_OPTIONS.get(effective_shot_key, "Wide Establishing Shot")

    storyline = (item.storyline or "").strip()
    static_storyline = _strip_character_descriptions(
        _make_static_description(storyline)
    )

    # Front-load framing descriptor when composition overrides shot type
    if framing_prefix and static_storyline:
        parts.append(f"{shot_label}, {framing_prefix} view of {static_storyline}")
    elif static_storyline:
        parts.append(f"{shot_label} of {static_storyline}")
    else:
        parts.append(shot_label)

    # Composition / blocking — integrated into the prompt
    if composition:
        cleaned_comp = _strip_character_descriptions(composition)
        if framing_prefix:
            parts.append(cleaned_comp)
        else:
            parts.append(f"Composition: {cleaned_comp}")

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


def _collect_scene_level_props(
    screenplay: "Screenplay", scene: Optional["StoryScene"]
) -> List[str]:
    """Return names of all objects, vehicles, and passive entities in the scene.

    Scans the scene's generated content for ``[bracket]`` objects and
    ``{brace}`` vehicles, plus any entities marked as passive in
    identity block metadata.  These are props that exist on set and
    should appear in every hero frame regardless of which paragraph
    interacts with them.
    """
    names: List[str] = []
    seen: set = set()

    if scene:
        content = ""
        if scene.metadata and isinstance(scene.metadata, dict):
            content = scene.metadata.get("generated_content", "")
        if not content:
            content = getattr(scene, "description", "") or ""

        for m in re.finditer(r'\[([^\]]+)\]', content):
            n = m.group(1).strip()
            if n and n.lower() not in seen:
                seen.add(n.lower())
                names.append(n)

        for m in re.finditer(r'\{([^{}]+)\}', content):
            n = m.group(1).strip()
            if n and len(n) >= 2 and n.lower() not in seen:
                seen.add(n.lower())
                names.append(n)

    if screenplay:
        meta = getattr(screenplay, "identity_block_metadata", {}) or {}
        for _eid, emeta in meta.items():
            if emeta.get("status") == "passive":
                ename = (emeta.get("name") or "").strip()
                if ename and ename.lower() not in seen:
                    seen.add(ename.lower())
                    names.append(ename)

    return names


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
        elif entity_type == "group":
            _gid = (info.get("entity_id") or "").strip()
            _gmeta = screenplay.identity_block_metadata.get(_gid, {}) if _gid else {}
            _individuality = _gmeta.get("individuality", "slight_variation")
            lines.append(f"{label} represents the group {entity_name}.")
            lines.append("All members must share identical uniform, armor, and insignia.")
            if _individuality == "identical":
                lines.append(
                    "All members are physically identical — same face, body, height, "
                    "and skin tone (clones/robots/duplicates)."
                )
            elif _individuality == "distinct":
                lines.append(
                    "Members share faction colours and insignia but vary noticeably in "
                    "gear, build, height, face, skin tone, and personal modifications."
                )
            else:
                lines.append(
                    "Members wear the same uniform but are physically diverse — each has "
                    "a unique face, skin tone, build, and height. They are different "
                    "people in matching outfits, NOT clones."
                )
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
        if entity_type not in ("character", "group"):
            continue
        entity_id = (info.get("entity_id") or "").strip()
        entity_name = (info.get("entity_name") or "").strip()
        if not entity_id or not entity_name:
            continue

        label = slot.replace("_", " ").title()

        if entity_type == "group":
            meta = screenplay.identity_block_metadata.get(entity_id, {})
            uniform = (meta.get("uniform_description") or "").strip()
            if uniform:
                lines.append(f"{label} ({entity_name}): {uniform}")
                lines.append("")
                has_entries = True
            continue

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

def _is_visual_art_intent(screenplay: "Screenplay") -> bool:
    """Return True if the screenplay targets a Visual Art / Abstract intent."""
    intent = (getattr(screenplay, "intent", "") or "").lower()
    return "visual art" in intent or "abstract" in intent


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

    # Seamless-loop directive (Visual Art looping mode)
    va_style = getattr(scene, "visual_art_style", "progressive") if scene else "progressive"
    if va_style == "looping" and _is_visual_art_intent(screenplay):
        sections.append(
            "SEAMLESS LOOP:\n"
            "This video must loop seamlessly — the final frame returns to the "
            "opening state so the clip repeats without a visible cut.\n"
            "Plan all motion as a cycle: environment, lighting, and atmosphere "
            "must transition back to their starting conditions by the end.\n"
            "Use circular or oscillating motion (e.g. light fading then returning, "
            "elements drifting then resettling, camera orbiting back to its origin).\n"
            "Explicitly show the return to the starting state."
        )

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

    # Strict consistency enforcement (compact — identity lock already has full details)
    has_characters = any(
        (info.get("entity_type") or "").lower() in ("character", "group")
        for info in assignments.values()
        if info
    )
    consistency_lines = [
        "CONSISTENCY: Match all reference images exactly — faces, proportions, "
        "clothing, setting. No invented characters, objects, or details.",
    ]
    if has_characters:
        consistency_lines.append(
            "No camera gaze unless storyline demands it."
        )
    sections.append(" ".join(consistency_lines))

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
        if (info.get("entity_type") or "").lower() in ("character", "group"):
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
#  Platform-adapted prompt compilation
# =====================================================================

def compile_platform_prompts(
    item: "StoryboardItem",
    screenplay: "Screenplay",
    scene: Optional["StoryScene"] = None,
) -> Dict[str, object]:
    """Compile prompts and adapt them for the project's selected platform.

    Returns::

        {
            "success": bool,
            "keyframe_prompt": str,
            "identity_prompt": str,
            "video_prompt": str,
            "platform_prompt": str,   # adapted for the target platform
            "platform_id": str,
            "platform_name": str,
            "errors": List[str],
        }
    """
    from .prompt_adapters import get_adapter

    result = compile_all_prompts(item, screenplay, scene)

    ss = getattr(screenplay, "story_settings", {}) or {}
    platform_id = ss.get("generation_platform", "higgsfield")

    adapter = get_adapter(platform_id)

    if not result["success"] or not adapter:
        return {
            **result,
            "platform_prompt": "",
            "platform_id": platform_id,
            "platform_name": adapter.platform_name if adapter else platform_id,
        }

    adapted = adapter.adapt(
        result["keyframe_prompt"],
        result["identity_prompt"],
        result["video_prompt"],
        item,
        screenplay,
    )

    return {
        **result,
        "platform_prompt": adapted,
        "platform_id": platform_id,
        "platform_name": adapter.platform_name,
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
