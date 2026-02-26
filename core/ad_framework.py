"""
Advertisement Framework for MoviePrompterAI.

Structured cinematic commercial mode for micro advertisement production.
Enforces a 6-beat template, escalation logic, hero shot requirements,
feature-to-visual conversion, brand personality integration, and
narrative complexity limits.

When story_length == "micro" and intent == "Advertisement / Brand Film",
this module governs the entire generation pipeline.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Beat types for micro advertisement structure (6 beats max)
# ---------------------------------------------------------------------------

AD_BEAT_TYPES = [
    "hook",
    "pain_desire",
    "product_reveal",
    "feature_demo",
    "emotional_payoff",
    "brand_moment",
]

AD_BEAT_LABELS: Dict[str, str] = {
    "hook": "Hook (Attention Grabber)",
    "pain_desire": "Audience Pain / Desire",
    "product_reveal": "Product Introduction",
    "feature_demo": "Feature Demonstration",
    "emotional_payoff": "Emotional Payoff",
    "brand_moment": "Brand Moment",
}

AD_BEAT_GUIDANCE: Dict[str, str] = {
    "hook": (
        "Visually compelling opening. No exposition. Immediate intrigue. "
        "Grab the viewer within the first 2 seconds. Use striking imagery, "
        "unexpected motion, or a bold visual statement."
    ),
    "pain_desire": (
        "Show a relatable problem or aspiration the audience identifies with. "
        "Do NOT introduce unrelated story arcs. Keep it focused on the core "
        "pain point or desire that the product resolves."
    ),
    "product_reveal": (
        "Clear reveal moment. The product is framed as the hero and solution. "
        "This is the first clean, unambiguous view of the product. "
        "Must feel intentional and cinematic — not incidental."
    ),
    "feature_demo": (
        "Each feature must be VISUALIZED through cinematic action, not narrated. "
        "Max 2-3 features in micro format. Show the feature in use with a "
        "specific camera angle, motion beat, and optional SFX."
    ),
    "emotional_payoff": (
        "Show transformation, empowerment, or satisfaction. Must escalate "
        "from earlier beats in visual scale, emotional intensity, or energy. "
        "The viewer should feel the benefit, not just see it."
    ),
    "brand_moment": (
        "Logo, tagline, or call-to-action. Clean framing, controlled lighting. "
        "This is the final impression — must feel polished and intentional. "
        "Reinforces the emotional anchor established throughout."
    ),
}

# ---------------------------------------------------------------------------
# Escalation dimensions — each subsequent beat must increase in at least one
# ---------------------------------------------------------------------------

ESCALATION_DIMENSIONS = [
    "visual_scale",
    "emotional_intensity",
    "energy",
    "motion",
    "product_dominance",
]

# ---------------------------------------------------------------------------
# Emotional anchors — advertisement must define exactly one
# ---------------------------------------------------------------------------

EMOTIONAL_ANCHORS = [
    "Freedom",
    "Confidence",
    "Innovation",
    "Control",
    "Escape",
    "Belonging",
    "Empowerment",
    "Joy",
    "Trust",
    "Discovery",
]

# ---------------------------------------------------------------------------
# Brand personality → visual style mapping
# ---------------------------------------------------------------------------

BRAND_PERSONALITY_VISUAL_MAP: Dict[str, Dict[str, str]] = {
    "innovative": {
        "color_tone": "Cool blues, electric accents, high contrast",
        "camera_movement": "Smooth tracking, slow reveal, drone sweeps",
        "editing_rhythm": "Sharp cuts, precise timing, rhythmic transitions",
        "lighting_mood": "Clean, bright key light with controlled shadows",
    },
    "sleek": {
        "color_tone": "Monochrome with metallic highlights, minimal palette",
        "camera_movement": "Gliding dolly, steady gimbal, minimal shaking",
        "editing_rhythm": "Slow dissolves, long takes, elegant transitions",
        "lighting_mood": "Studio-quality, rim lighting, specular highlights",
    },
    "energetic": {
        "color_tone": "Warm saturated tones, high vibrancy, bold accents",
        "camera_movement": "Dynamic tracking, handheld energy, whip pans",
        "editing_rhythm": "Fast cuts, beat-synced editing, jump cuts",
        "lighting_mood": "High-key natural light, lens flares, golden hour",
    },
    "playful": {
        "color_tone": "Bright pastels, warm tones, soft contrasts",
        "camera_movement": "Bouncy gimbal, tilts, casual pans",
        "editing_rhythm": "Snappy cuts, playful wipes, pop transitions",
        "lighting_mood": "Soft diffused light, warm fill, minimal shadows",
    },
    "trustworthy": {
        "color_tone": "Warm neutrals, earth tones, consistent palette",
        "camera_movement": "Steady tripod, slow push-ins, eye-level framing",
        "editing_rhythm": "Measured cuts, consistent pacing, smooth transitions",
        "lighting_mood": "Soft natural light, even exposure, warm tones",
    },
    "bold": {
        "color_tone": "High contrast, deep blacks, vivid accent colors",
        "camera_movement": "Low angle power shots, dramatic crane moves",
        "editing_rhythm": "Impact cuts, hard transitions, rhythmic builds",
        "lighting_mood": "Dramatic chiaroscuro, strong key with deep shadows",
    },
    "eco-conscious": {
        "color_tone": "Natural greens, earth tones, organic palette",
        "camera_movement": "Slow establishing shots, nature-integrated framing",
        "editing_rhythm": "Gentle transitions, dissolves, breathing room",
        "lighting_mood": "Natural daylight, soft golden hour, organic warmth",
    },
    "modern": {
        "color_tone": "Clean whites, geometric accents, minimal palette",
        "camera_movement": "Precise tracking, stabilized gimbal, clean lines",
        "editing_rhythm": "Crisp cuts, geometric wipes, structured timing",
        "lighting_mood": "Clean bright lighting, soft shadows, even exposure",
    },
    "confident": {
        "color_tone": "Deep saturated tones, navy and gold, rich palette",
        "camera_movement": "Steady controlled movement, hero-angle framing",
        "editing_rhythm": "Deliberate pacing, power cuts, controlled build",
        "lighting_mood": "Strong directional light, defined shadows, polish",
    },
    "urban": {
        "color_tone": "Cool desaturated tones, neon accents, city palette",
        "camera_movement": "Street-level tracking, through-traffic framing",
        "editing_rhythm": "Quick cuts synced to city rhythm, layered montage",
        "lighting_mood": "Mixed ambient, streetlight spill, reflective surfaces",
    },
    "intelligent": {
        "color_tone": "Cool neutrals, blue-gray tones, tech-inspired palette",
        "camera_movement": "Precise dolly, data-overlay framing, macro details",
        "editing_rhythm": "Measured pacing, info-reveals, layered transitions",
        "lighting_mood": "Cool balanced light, screen glow, subtle rim light",
    },
    "forward-thinking": {
        "color_tone": "Gradient futuristic tones, holographic accents",
        "camera_movement": "Sweeping reveals, parallax depth, futuristic angles",
        "editing_rhythm": "Progressive builds, escalating pace, forward momentum",
        "lighting_mood": "Ambient glow, edge lighting, volumetric atmosphere",
    },
    "empowering": {
        "color_tone": "Warm golds, sunrise tones, aspirational palette",
        "camera_movement": "Low-to-high reveals, hero-angle tracking",
        "editing_rhythm": "Building momentum, crescendo pacing, triumphant beats",
        "lighting_mood": "Dramatic backlight, golden rim, inspirational glow",
    },
}

# Fallback for unlisted personality traits
_DEFAULT_VISUAL_STYLE: Dict[str, str] = {
    "color_tone": "Balanced cinematic palette, natural tones",
    "camera_movement": "Smooth tracking, steady framing",
    "editing_rhythm": "Measured cuts, natural pacing",
    "lighting_mood": "Balanced natural lighting with cinematic quality",
}

# ---------------------------------------------------------------------------
# Distribution platform presets (preparation layer — structure only)
# ---------------------------------------------------------------------------

DISTRIBUTION_PLATFORMS = {
    "social": {
        "label": "Social (Vertical, Fast Hook)",
        "aspect_ratio": "9:16",
        "hook_duration_max": 2,
        "cta_placement": "end_overlay",
        "pacing_bias": "fast",
    },
    "youtube_preroll": {
        "label": "YouTube Pre-roll",
        "aspect_ratio": "16:9",
        "hook_duration_max": 5,
        "cta_placement": "end_card",
        "pacing_bias": "medium",
    },
    "tvc": {
        "label": "TVC (Television Commercial)",
        "aspect_ratio": "16:9",
        "hook_duration_max": 5,
        "cta_placement": "end_super",
        "pacing_bias": "medium",
    },
    "website_hero": {
        "label": "Website Hero",
        "aspect_ratio": "16:9",
        "hook_duration_max": 3,
        "cta_placement": "integrated",
        "pacing_bias": "slow",
    },
}

# ---------------------------------------------------------------------------
# Narrative complexity limits for advertisement mode
# ---------------------------------------------------------------------------

AD_NARRATIVE_LIMITS = {
    "max_primary_characters": 1,
    "max_environments": 2,
    "subplots_allowed": False,
    "character_growth_arcs_allowed": False,
    "multi_location_wandering_allowed": False,
    "max_secondary_characters": 0,
}


# ═══════════════════════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════════════════════

def is_advertisement_mode(story_length: str, intent: str) -> bool:
    """Return True when the project is in structured advertisement mode."""
    return (
        (story_length or "").lower() == "micro"
        and "advertisement" in (intent or "").lower()
    )


def get_brand_visual_style(brand_personality: List[str]) -> Dict[str, str]:
    """Derive visual style guidance from brand personality traits.

    Merges style directives from all matching personality keywords.
    Falls back to a balanced default when no matches are found.
    """
    if not brand_personality:
        return dict(_DEFAULT_VISUAL_STYLE)

    merged: Dict[str, List[str]] = {k: [] for k in _DEFAULT_VISUAL_STYLE}
    matched = False

    for trait in brand_personality:
        key = trait.strip().lower().rstrip(".")
        style = BRAND_PERSONALITY_VISUAL_MAP.get(key)
        if style:
            matched = True
            for field, value in style.items():
                if field in merged:
                    merged[field].append(value)

    if not matched:
        return dict(_DEFAULT_VISUAL_STYLE)

    return {k: "; ".join(dict.fromkeys(v)) for k, v in merged.items() if v}


def build_feature_visual_prompt(feature_text: str, product_name: str) -> str:
    """Convert a plain feature description into a cinematic visual beat.

    Returns a prompt fragment that describes the feature as a motion-based
    visual action suitable for storyboard generation.
    """
    return (
        f"Cinematic visual beat demonstrating the feature: {feature_text}. "
        f"Show the {product_name} in active use. Visualize the feature through "
        f"specific on-screen motion, a clear camera angle, and an observable "
        f"result. Do NOT narrate — SHOW the feature through action. "
        f"Include a suggested SFX cue and camera suggestion."
    )


# ═══════════════════════════════════════════════════════════════════════════
# Validation
# ═══════════════════════════════════════════════════════════════════════════

class AdValidationResult:
    """Result of advertisement structure validation."""

    def __init__(self) -> None:
        self.passed: bool = True
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def fail(self, msg: str) -> None:
        self.passed = False
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def __bool__(self) -> bool:
        return self.passed


def validate_ad_structure(scenes: List[Any]) -> AdValidationResult:
    """Validate that scenes follow the 6-beat micro advertisement template.

    Checks:
    - Required beats present (hook, product_reveal, brand_moment minimum)
    - Max 6 beats
    - Beat ordering logic
    """
    result = AdValidationResult()

    if not scenes:
        result.fail("No scenes/beats defined.")
        return result

    if len(scenes) > 6:
        result.fail(
            f"Micro advertisement allows max 6 beats, found {len(scenes)}."
        )

    beat_types = []
    for s in scenes:
        bt = None
        if hasattr(s, "ad_beat_type"):
            bt = s.ad_beat_type
        elif isinstance(s, dict):
            bt = s.get("ad_beat_type")
        beat_types.append(bt or "")

    has_hook = any(b == "hook" for b in beat_types)
    has_reveal = any(b == "product_reveal" for b in beat_types)
    has_brand = any(b == "brand_moment" for b in beat_types)
    has_pain = any(b == "pain_desire" for b in beat_types)
    has_feature = any(b == "feature_demo" for b in beat_types)
    has_payoff = any(b == "emotional_payoff" for b in beat_types)

    if not has_hook:
        result.fail("Missing required beat: Hook (Attention Grabber).")
    if not has_reveal:
        result.fail("Missing required beat: Product Introduction / Reveal.")
    if not has_brand:
        result.fail("Missing required beat: Brand Moment (logo/tagline/CTA).")
    if not has_pain:
        result.warn("No Audience Pain / Desire beat — consider adding one.")
    if not has_feature:
        result.warn("No Feature Demonstration beat — consider adding one.")
    if not has_payoff:
        result.warn("No Emotional Payoff beat — consider adding one.")

    # Ordering: hook should be first, brand_moment should be last
    if beat_types and beat_types[0] != "hook" and has_hook:
        result.warn("Hook beat should be the first scene for maximum impact.")
    if beat_types and beat_types[-1] != "brand_moment" and has_brand:
        result.warn("Brand Moment should be the final scene.")

    return result


def validate_hero_shot(storyboard_items: List[Any]) -> AdValidationResult:
    """Validate that at least one storyboard item is a product hero shot."""
    result = AdValidationResult()

    if not storyboard_items:
        result.fail("No storyboard items to check for hero shot.")
        return result

    has_hero = False
    for item in storyboard_items:
        flag = False
        if hasattr(item, "is_hero_shot"):
            flag = item.is_hero_shot
        elif isinstance(item, dict):
            flag = item.get("is_hero_shot", False)
        if flag:
            has_hero = True
            break

    if not has_hero:
        result.fail(
            "Missing product hero shot. At least one storyboard item must have "
            "is_hero_shot=true with: clean background, full product visible, "
            "controlled lighting, minimal distractions."
        )

    return result


def validate_escalation(scenes: List[Any]) -> AdValidationResult:
    """Warn if scene sequence appears flat (no escalation metadata)."""
    result = AdValidationResult()

    if len(scenes) < 2:
        return result

    # Escalation is enforced in the AI prompt; here we flag if all scenes
    # share the same pacing (a sign of flat stacking).
    pacings = []
    for s in scenes:
        p = getattr(s, "pacing", None) or (s.get("pacing") if isinstance(s, dict) else None) or "Medium"
        pacings.append(p)

    if len(set(pacings)) == 1 and len(pacings) >= 3:
        result.warn(
            "All beats share the same pacing — consider varying pacing to "
            "create escalation in energy and visual scale."
        )

    return result


def check_narrative_complexity(
    characters: List[Any],
    environments_count: int,
    story_outline: Optional[Dict[str, Any]] = None,
) -> AdValidationResult:
    """Check that narrative complexity stays within advertisement limits."""
    result = AdValidationResult()

    limits = AD_NARRATIVE_LIMITS

    if len(characters) > limits["max_primary_characters"]:
        result.warn(
            f"Advertisement mode recommends max {limits['max_primary_characters']} "
            f"primary character(s), found {len(characters)}. "
            f"Consider reducing to keep focus on the product."
        )

    if environments_count > limits["max_environments"]:
        result.warn(
            f"Advertisement mode recommends max {limits['max_environments']} "
            f"environment(s), found {environments_count}. "
            f"Too many locations dilutes product focus."
        )

    if story_outline and isinstance(story_outline, dict):
        subplots = story_outline.get("subplots", "")
        if subplots and str(subplots).strip():
            result.warn(
                "Subplots are disabled in advertisement mode. "
                "Remove subplots to maintain product-centric focus."
            )

        for char in story_outline.get("characters", []):
            if isinstance(char, dict) and char.get("growth_arc", "").strip():
                result.warn(
                    f"Character growth arc found for '{char.get('name', '?')}'. "
                    f"Growth arcs are disabled in advertisement mode."
                )
                break

    return result


def validate_pre_generation(
    scenes: List[Any],
    storyboard_items: Optional[List[Any]] = None,
) -> AdValidationResult:
    """Run full pre-generation validation for advertisement mode.

    Checks:
    1. Is there a hook?
    2. Is there a pain/desire?
    3. Is there a reveal?
    4. Is there feature visualization?
    5. Is there escalation?
    6. Is there a brand payoff?
    """
    result = AdValidationResult()

    struct = validate_ad_structure(scenes)
    if not struct:
        result.errors.extend(struct.errors)
        result.passed = False
    result.warnings.extend(struct.warnings)

    esc = validate_escalation(scenes)
    result.warnings.extend(esc.warnings)

    if storyboard_items:
        hero = validate_hero_shot(storyboard_items)
        if not hero:
            result.errors.extend(hero.errors)
            result.passed = False
        result.warnings.extend(hero.warnings)

    return result


# ═══════════════════════════════════════════════════════════════════════════
# Prompt builders
# ═══════════════════════════════════════════════════════════════════════════

def build_ad_framework_prompt(
    premise: str,
    title: str,
    atmosphere: str,
    brand_context: Any,
    emotional_anchor: str,
    visual_style: Dict[str, str],
    story_outline: Optional[Dict[str, Any]] = None,
) -> str:
    """Build the AI prompt for generating a micro advertisement framework.

    Returns the complete prompt string for the 6-beat structured template.
    """
    brand_info = ""
    if brand_context:
        bc = brand_context
        brand_name = getattr(bc, "brand_name", "") or ""
        product_name = getattr(bc, "product_name", "") or ""
        product_desc = getattr(bc, "product_description", "") or ""
        core_benefit = getattr(bc, "core_benefit", "") or ""
        target_audience = getattr(bc, "target_audience", "") or ""
        personality = getattr(bc, "brand_personality", []) or []
        mandatory = getattr(bc, "mandatory_elements", []) or []

        brand_info = "\n\nBRAND / PRODUCT CONTEXT (REQUIRED):\n"
        if brand_name:
            brand_info += f"Brand Name: {brand_name}\n"
        if product_name:
            brand_info += f"Product Name: {product_name}\n"
        if product_desc:
            brand_info += f"Product Description: {product_desc}\n"
        if core_benefit:
            brand_info += f"Core Benefit / Promise: {core_benefit}\n"
        if target_audience:
            brand_info += f"Target Audience: {target_audience}\n"
        if personality:
            brand_info += f"Brand Personality: {', '.join(personality)}\n"
        if mandatory:
            brand_info += f"Mandatory Inclusions: {', '.join(mandatory)}\n"

    # Feature list from core_benefit for feature-to-visual conversion
    features_section = ""
    if brand_context and getattr(brand_context, "core_benefit", ""):
        raw = brand_context.core_benefit
        features = [f.strip() for f in raw.replace("\n", ",").split(",") if f.strip()]
        if features:
            features_section = "\n\nPRODUCT FEATURES (each must become a CINEMATIC VISUAL ACTION):\n"
            for i, feat in enumerate(features[:3], 1):
                features_section += (
                    f"{i}. \"{feat}\" → Show this through on-screen motion, "
                    f"a specific camera angle, and observable result. "
                    f"NO abstract description allowed.\n"
                )

    visual_style_section = ""
    if visual_style:
        visual_style_section = "\n\nBRAND VISUAL STYLE (derived from brand personality):\n"
        for field, value in visual_style.items():
            label = field.replace("_", " ").title()
            visual_style_section += f"- {label}: {value}\n"
        visual_style_section += "Apply these visual directives to ALL beats.\n"

    anchor_section = ""
    if emotional_anchor:
        anchor_section = (
            f"\n\nEMOTIONAL ANCHOR: {emotional_anchor}\n"
            f"This emotional anchor MUST:\n"
            f"- Be present in the hook (implied or visual)\n"
            f"- Reinforce in the emotional payoff beat\n"
            f"- Echo in the final brand moment\n"
        )

    # Outline context (characters, visual motifs, etc.)
    outline_info = ""
    if story_outline and isinstance(story_outline, dict):
        chars = story_outline.get("characters", [])
        if chars:
            outline_info += "\n\nCHARACTER (max 1 primary):\n"
            for c in chars[:1]:
                if isinstance(c, dict):
                    outline_info += f"- {c.get('name', 'Unnamed')}: {c.get('outline', '')}\n"
        visual_motifs = story_outline.get("visual_motifs", "")
        if visual_motifs:
            outline_info += f"\nVisual Motifs: {visual_motifs}\n"
        cta = story_outline.get("call_to_action", "")
        if cta:
            outline_info += f"Call to Action: {cta}\n"

    prompt = f"""You are a professional commercial director and brand strategist.
Create a STRUCTURED MICRO ADVERTISEMENT framework — NOT a short film or narrative story.

Brand Concept: {premise}
Title: {title if title else "Untitled Commercial"}
Brand Tone: {atmosphere}
{brand_info}{features_section}{visual_style_section}{anchor_section}{outline_info}

═══════════════════════════════════════════════════════════════════════════════
MICRO ADVERTISEMENT STRUCTURE — 6 BEATS (MANDATORY TEMPLATE)
═══════════════════════════════════════════════════════════════════════════════

You MUST create EXACTLY these 6 beats in this order:

BEAT 1 — HOOK (Attention Grabber)
- Visually compelling, no exposition, immediate intrigue
- Grab attention in the first 2 seconds
- Pacing: Fast

BEAT 2 — AUDIENCE PAIN / DESIRE
- Show a relatable problem or aspiration
- Do NOT introduce unrelated story arcs
- Pacing: Medium

BEAT 3 — PRODUCT INTRODUCTION (Product Reveal)
- Clear reveal moment — product framed as the hero
- First clean, unambiguous view of the product
- Pacing: Medium
- Mark: is_product_reveal: true

BEAT 4 — FEATURE DEMONSTRATION
- Each feature VISUALIZED through cinematic action, NOT narrated
- Max 2-3 features for micro format
- Show features in use with specific camera angles and motion
- Pacing: Fast

BEAT 5 — EMOTIONAL PAYOFF
- Show transformation, empowerment, or satisfaction
- Must ESCALATE from earlier beats in visual scale and emotional intensity
- Pacing: Fast

BEAT 6 — BRAND MOMENT
- Logo, tagline, or call-to-action
- Clean framing, controlled lighting
- Mark: is_brand_hero_shot: true
- Pacing: Medium

═══════════════════════════════════════════════════════════════════════════════
ESCALATION RULE (MANDATORY)
═══════════════════════════════════════════════════════════════════════════════
Each subsequent beat MUST increase in at least one of:
- Visual scale
- Emotional intensity
- Energy / motion
- Cinematic dominance of the product

NO flat sequential feature stacking. Each beat must BUILD on the previous.

═══════════════════════════════════════════════════════════════════════════════
TONE RULES (MANDATORY — THIS IS A COMMERCIAL, NOT A SHORT FILM)
═══════════════════════════════════════════════════════════════════════════════
- Visually driven — every beat is a cinematic moment
- NO long exposition or unnecessary dialogue
- NO novelistic narration or literary prose
- Focus on CINEMATIC BEATS — camera, motion, light, product
- Dialogue must be minimal and purposeful (tagline or single line max)
- Output must feel like a PRODUCED COMMERCIAL, not a short story
- If output resembles narrative storytelling → it is WRONG

═══════════════════════════════════════════════════════════════════════════════
NARRATIVE LIMITS (MANDATORY)
═══════════════════════════════════════════════════════════════════════════════
- Maximum 1 primary character
- Maximum 1-2 environments
- NO subplots, NO character growth arcs, NO multi-location wandering
- NO unnecessary secondary characters
- Product is the true hero, character is the vehicle

CRITICAL: You MUST return ONLY valid JSON. No markdown, no explanations, no code blocks.

Format your response as a JSON object with this EXACT structure:
{{
    "title": "Commercial Title",
    "story_structure": {{
        "core_message": "The central brand value proposition",
        "visual_themes": ["Theme 1", "Theme 2"],
        "emotional_anchor": "{emotional_anchor or 'Confidence'}"
    }},
    "acts": [
        {{
            "act_number": 1,
            "title": "Act Title",
            "description": "Visual progression overview",
            "pacing_notes": "Escalating energy from hook to brand moment",
            "scenes": [
                {{
                    "scene_number": 1,
                    "title": "Beat Title",
                    "description": "2-3 sentence visual description of what the audience SEES — not a story summary. Describe camera, motion, light, product placement.",
                    "ad_beat_type": "hook",
                    "is_product_reveal": false,
                    "is_brand_hero_shot": false,
                    "plot_point": null,
                    "character_focus": [],
                    "pacing": "Fast",
                    "estimated_duration": 5
                }},
                {{
                    "scene_number": 2,
                    "title": "Beat Title",
                    "description": "Visual description...",
                    "ad_beat_type": "pain_desire",
                    "is_product_reveal": false,
                    "is_brand_hero_shot": false,
                    "plot_point": null,
                    "character_focus": [],
                    "pacing": "Medium",
                    "estimated_duration": 5
                }},
                {{
                    "scene_number": 3,
                    "title": "Beat Title",
                    "description": "Visual description...",
                    "ad_beat_type": "product_reveal",
                    "is_product_reveal": true,
                    "is_brand_hero_shot": false,
                    "plot_point": null,
                    "character_focus": [],
                    "pacing": "Medium",
                    "estimated_duration": 5
                }},
                {{
                    "scene_number": 4,
                    "title": "Beat Title",
                    "description": "Visual description...",
                    "ad_beat_type": "feature_demo",
                    "is_product_reveal": false,
                    "is_brand_hero_shot": false,
                    "plot_point": null,
                    "character_focus": [],
                    "pacing": "Fast",
                    "estimated_duration": 5
                }},
                {{
                    "scene_number": 5,
                    "title": "Beat Title",
                    "description": "Visual description...",
                    "ad_beat_type": "emotional_payoff",
                    "is_product_reveal": false,
                    "is_brand_hero_shot": false,
                    "plot_point": null,
                    "character_focus": [],
                    "pacing": "Fast",
                    "estimated_duration": 5
                }},
                {{
                    "scene_number": 6,
                    "title": "Beat Title",
                    "description": "Visual description...",
                    "ad_beat_type": "brand_moment",
                    "is_product_reveal": false,
                    "is_brand_hero_shot": true,
                    "plot_point": null,
                    "character_focus": [],
                    "pacing": "Medium",
                    "estimated_duration": 5
                }}
            ]
        }}
    ]
}}

IMPORTANT JSON RULES:
- Every property must be followed by a comma EXCEPT the last property in an object
- Every array item must be followed by a comma EXCEPT the last item
- All string values must be properly quoted and escaped
- No trailing commas before closing braces or brackets
- Use null (not "null") for optional fields
- estimated_duration for each beat should be 3-8 seconds (total ~30 seconds for micro)
"""
    return prompt


def build_ad_scene_content_guidance(
    brand_context: Any,
    emotional_anchor: str,
    visual_style: Dict[str, str],
    ad_beat_type: str,
) -> str:
    """Build advertisement-specific guidance to inject into scene content generation."""
    parts = []

    parts.append(
        "\n\n═══ ADVERTISEMENT MODE — COMMERCIAL SCRIPT RULES ═══\n"
        "This is a COMMERCIAL, not a short film. Write like a produced commercial script.\n"
        "- Visually driven: every paragraph is a cinematic beat\n"
        "- NO long exposition, NO unnecessary dialogue\n"
        "- NO novelistic narration, NO internal thoughts\n"
        "- Focus on: camera, motion, light, product presence\n"
        "- Dialogue: minimal and purposeful ONLY (tagline or single line max)\n"
        "- Each paragraph = one clear visual beat with observable action\n"
    )

    beat_guidance = AD_BEAT_GUIDANCE.get(ad_beat_type, "")
    if beat_guidance:
        label = AD_BEAT_LABELS.get(ad_beat_type, ad_beat_type)
        parts.append(
            f"\nBEAT TYPE: {label}\n{beat_guidance}\n"
        )

    if emotional_anchor:
        parts.append(
            f"\nEMOTIONAL ANCHOR: {emotional_anchor}\n"
            f"Reinforce this emotional thread through visual action, not words.\n"
        )

    if visual_style:
        parts.append("\nBRAND VISUAL STYLE:\n")
        for field, value in visual_style.items():
            label = field.replace("_", " ").title()
            parts.append(f"- {label}: {value}\n")

    if brand_context:
        product_name = getattr(brand_context, "product_name", "") or ""
        core_benefit = getattr(brand_context, "core_benefit", "") or ""
        if product_name:
            parts.append(f"\nProduct: {product_name}\n")
        if core_benefit:
            parts.append(f"Core Benefit: {core_benefit}\n")

    parts.append(
        "\nESCALATION: This beat must show HIGHER visual scale, energy, "
        "or product dominance than the previous beat.\n"
    )

    return "".join(parts)


def build_ad_storyboard_guidance(
    brand_context: Any,
    emotional_anchor: str,
    visual_style: Dict[str, str],
    ad_beat_type: str,
    is_product_reveal: bool = False,
    is_brand_hero_shot: bool = False,
) -> str:
    """Build advertisement-specific guidance for storyboard item generation."""
    parts = []

    parts.append(
        "\n\n═══ ADVERTISEMENT MODE — STORYBOARD RULES ═══\n"
        "Generate storyboard items as COMMERCIAL SHOTS, not story beats.\n"
    )

    if is_product_reveal:
        parts.append(
            "\nPRODUCT REVEAL SHOT: This is the product introduction moment.\n"
            "- Clean, unambiguous first view of the product\n"
            "- Product framed as hero and solution\n"
            "- Cinematic reveal — not incidental\n"
        )

    if is_brand_hero_shot:
        parts.append(
            "\nBRAND HERO SHOT: This is the final brand impression.\n"
            "- Clean background, controlled lighting\n"
            "- Logo and/or tagline visible\n"
            "- Polished, intentional framing\n"
        )

    parts.append(
        "\nHERO SHOT REQUIREMENT: At least one storyboard item in this commercial "
        "must be a clean product hero shot with:\n"
        "- Clean background\n"
        "- Full product visible\n"
        "- Controlled lighting\n"
        "- Minimal distractions\n"
        "- Mark this item with is_hero_shot: true in the output\n"
    )

    if visual_style:
        parts.append("\nApply brand visual style:\n")
        for field, value in visual_style.items():
            label = field.replace("_", " ").title()
            parts.append(f"- {label}: {value}\n")

    return "".join(parts)
