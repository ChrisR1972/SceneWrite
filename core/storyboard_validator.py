"""
Storyboard Validator for MoviePrompterAI.

Deterministic, rule-based validation of storyboard items against their source
paragraphs.  Pure functions only — no AI calls.

Responsibilities:
- Extract entities (characters, objects, vehicles, environments) from paragraphs
  and storyboard items using cinematic markup regex.
- Compare entity sets to detect mismatches (missing, extra, wrong environment,
  cross-paragraph contamination).
- Extract the dominant action verb from a paragraph.
- Suggest camera framing based on the dominant action.
- Run a full validation pass across all paragraph/item pairs.
"""

import re
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

from core.action_rules import get_effective_action_whitelist

# ---------------------------------------------------------------------------
# Entity extraction patterns (cinematic markup conventions)
# ---------------------------------------------------------------------------

# FULL CAPS names — supports apostrophes (O'MALLEY) and honorifics (MRS., DR.)
_HONORIFIC = r"(?:(?:MRS?|MS|DR|MME|PROF|SGT|CPT|LT|GEN|COL|REV|CMDR|CAPT)\.\s+)?"
_NAME_WORD_V = r"[A-Z](?:[A-Z']+|'[A-Z]+)"
CHARACTER_PATTERN = re.compile(rf"\b({_HONORIFIC}{_NAME_WORD_V}(?:\s+{_NAME_WORD_V})*)\b")

# [object]
OBJECT_PATTERN = re.compile(r'\[([^\]]+)\]')

# {vehicle}
VEHICLE_PATTERN = re.compile(r'\{([^}]+)\}')

# _environment_
ENV_PATTERN = re.compile(r'(?<!\w)_([^_]+)_(?!\w)')

# *action* markup
ACTION_PATTERN = re.compile(r'\*([^*]+)\*')

# (sfx) markup
SFX_PATTERN = re.compile(r'\(([^)]+)\)')

# Identity block ID tags injected by the storyboard generator, e.g.
# (CHARACTER_7634), (VEHICLE_41D1), (OBJECT_8DF0), (ENVIRONMENT_CB1A)
_IDENTITY_ID_TAG = re.compile(r'\s*\([A-Z]+_[A-F0-9]{4,}\)')

# Common uppercase words that are NOT character names
_CAPS_STOPWORDS = frozenset({
    "INT", "EXT", "CUT", "FADE", "SMASH", "MATCH", "DISSOLVE",
    "THE", "A", "AN", "AND", "OR", "BUT", "NOT", "TO", "IN", "ON",
    "AT", "BY", "FOR", "OF", "WITH", "FROM", "AS", "IS", "IT",
    "HIS", "HER", "HE", "SHE", "THEY", "WE", "MY", "YOUR",
    "BEAT", "CONT", "CONTINUED", "MORE", "END", "SCENE",
    "SFX", "VO", "OS", "OC",
})


# ---------------------------------------------------------------------------
# Named tuples
# ---------------------------------------------------------------------------

class EntitySet(NamedTuple):
    """Extracted entity sets from a text block."""
    characters: Set[str]
    objects: Set[str]
    vehicles: Set[str]
    environments: Set[str]


class EntityMismatch(NamedTuple):
    """Mismatch report between paragraph and storyboard item entities."""
    missing_characters: Set[str]
    extra_characters: Set[str]
    missing_objects: Set[str]
    extra_objects: Set[str]
    missing_vehicles: Set[str]
    extra_vehicles: Set[str]
    wrong_environment: bool
    expected_environments: Set[str]
    actual_environments: Set[str]
    is_match: bool
    errors: List[str]


class ValidationResult(NamedTuple):
    """Validation result for a single paragraph/item pair."""
    paragraph_index: int
    is_valid: bool
    mismatch: Optional[EntityMismatch]
    dominant_action: str
    suggested_framing: str
    errors: List[str]


# ---------------------------------------------------------------------------
# Entity extraction
# ---------------------------------------------------------------------------

def _normalize_name(name: str) -> str:
    """Normalize an entity name for comparison.

    - Strip leading/trailing whitespace and collapse internal whitespace.
    - Remove identity block ID tags, e.g. "(VEHICLE_41D1)", that the
      storyboard generator injects inside markup like {Smart Electric Bike (VEHICLE_41D1)}.
    - Strip trailing apostrophes left over from possessives (THE RIDER's),
      where the regex captures "THE RIDER'" but not the lowercase "s".
    """
    name = _IDENTITY_ID_TAG.sub("", name)
    name = " ".join(name.split()).strip()
    name = name.rstrip("'")
    return name


def _filter_caps_stopwords(names: Set[str]) -> Set[str]:
    """Remove common uppercase stopwords from character name candidates."""
    filtered = set()
    for name in names:
        words = name.split()
        # Keep only if at least one word is NOT a stopword
        if any(w not in _CAPS_STOPWORDS for w in words):
            filtered.add(name)
    return filtered


def extract_entities(text: str, screenplay=None) -> EntitySet:
    """Extract characters, objects, vehicles, and environments from text.

    Uses cinematic markup regex patterns:
    - Characters: FULL CAPS names (2+ uppercase-letter words)
    - Objects: [brackets]
    - Vehicles: {braces}
    - Environments: _underscores_

    Also recognises identity block ID tags like (CHARACTER_5DF3),
    (OBJECT_7A9B), (VEHICLE_41D1), (ENVIRONMENT_C5AC) and resolves
    them back to entity names via the screenplay's metadata.

    If *screenplay* is provided, cross-references extracted names against
    known identity block metadata for improved accuracy.
    """
    if not text:
        return EntitySet(set(), set(), set(), set())

    # Objects, vehicles, environments — straightforward markup extraction
    objects = {_normalize_name(m) for m in OBJECT_PATTERN.findall(text)}
    vehicles = {_normalize_name(m) for m in VEHICLE_PATTERN.findall(text)}
    environments = {_normalize_name(m) for m in ENV_PATTERN.findall(text)}

    # Characters — FULL CAPS words, filtered for stopwords
    raw_chars = {_normalize_name(m) for m in CHARACTER_PATTERN.findall(text)}
    characters = _filter_caps_stopwords(raw_chars)

    # Cross-reference with screenplay identity blocks for better accuracy
    if screenplay and hasattr(screenplay, 'identity_block_metadata'):
        known_chars = set()
        known_objects = set()
        known_vehicles = set()
        known_envs = set()

        # Build lookup: entity_id -> (type, name)
        id_to_entity = {}
        for _eid, meta in screenplay.identity_block_metadata.items():
            etype = (meta.get("type") or "").lower()
            ename = (meta.get("name") or "").strip()
            if not ename:
                continue
            id_to_entity[_eid] = (etype, ename)
            if etype == "character":
                known_chars.add(ename.upper())
            elif etype == "object":
                known_objects.add(ename.lower())
            elif etype == "vehicle":
                known_vehicles.add(ename.lower())
            elif etype == "environment":
                known_envs.add(ename.lower())

        # Add characters found by known-name lookup even if regex missed them
        text_upper = text.upper()
        for kc in known_chars:
            if kc in text_upper:
                characters.add(kc)

        # ── PARTIAL CHARACTER NAME MATCHING ──
        # If the full name (e.g. "DETECTIVE JUDE FLECK") isn't found but a
        # significant word from it (e.g. "Fleck") appears in the text,
        # count the character as present.  This handles storyboard items
        # that use mixed-case last names or abbreviated names.
        _CHAR_NAME_STOPWORDS = frozenset({
            "DR", "MR", "MRS", "MS", "DETECTIVE", "OFFICER", "SERGEANT",
            "CAPTAIN", "GENERAL", "PRIVATE", "CORPORAL", "MAJOR",
            "COLONEL", "LIEUTENANT", "COMMANDER", "AGENT", "INSPECTOR",
            "PROFESSOR", "CHIEF", "DUKE", "PRINCE", "PRINCESS", "KING",
            "QUEEN", "LORD", "LADY", "SIR", "BARON", "COUNT",
        })
        for kc in known_chars:
            if kc in characters:
                continue
            words = kc.split()
            significant_words = [w for w in words
                                 if w not in _CHAR_NAME_STOPWORDS and len(w) >= 3]
            for word in significant_words:
                # Check case-insensitively as a whole word
                if re.search(r'\b' + re.escape(word) + r'\b', text, re.IGNORECASE):
                    characters.add(kc)
                    break

        # ── BARE OBJECT / VEHICLE / ENVIRONMENT NAME MATCHING ──
        # If a known entity name appears in the text without its markup
        # (e.g. "notebook" without [brackets]), count it as present.
        # This handles storyboard items where the markup was dropped.
        text_lower = text.lower()
        for ko in known_objects:
            if ko not in {o.lower() for o in objects}:
                if re.search(r'\b' + re.escape(ko) + r'\b', text_lower):
                    objects.add(ko)
        for kv in known_vehicles:
            if kv not in {v.lower() for v in vehicles}:
                if re.search(r'\b' + re.escape(kv) + r'\b', text_lower):
                    vehicles.add(kv)
        for ke in known_envs:
            if ke not in {e.lower() for e in environments}:
                if re.search(r'\b' + re.escape(ke) + r'\b', text_lower):
                    environments.add(ke)

        # ── IDENTITY BLOCK ID TAG RESOLUTION ──
        # Recognise (CHARACTER_XXXX), (OBJECT_XXXX), etc. in the text and
        # resolve them to the canonical entity names so validation can match.
        id_tag_pattern = re.compile(r'\(([A-Z]+_[A-F0-9]{4,})\)')
        for m in id_tag_pattern.finditer(text):
            tag_id = m.group(1)
            if tag_id in id_to_entity:
                etype, ename = id_to_entity[tag_id]
                if etype == "character":
                    characters.add(ename.upper())
                elif etype == "object":
                    objects.add(_normalize_name(ename))
                elif etype == "vehicle":
                    vehicles.add(_normalize_name(ename))
                elif etype == "environment":
                    environments.add(_normalize_name(ename))

        # ── FILTER CHARACTERS TO KNOWN NAMES ──
        # The CAPS regex can produce spurious matches when character names
        # contain apostrophes/quotes (e.g. PARIS 'PARI' PARKER) because
        # the pattern's [A-Z'] class spans across name boundaries.
        # When identity blocks are available, keep only characters that
        # are recognised canonical names.
        if known_chars:
            characters = {c for c in characters if c in known_chars}

    return EntitySet(
        characters=characters,
        objects=objects,
        vehicles=vehicles,
        environments=environments,
    )


def extract_paragraph_entities(paragraph: str, screenplay=None) -> EntitySet:
    """Extract entities from a single scene paragraph."""
    return extract_entities(paragraph, screenplay)


def extract_storyboard_entities(item, screenplay=None) -> EntitySet:
    """Extract entities from a storyboard item's text fields.

    Combines storyline, image_prompt, and prompt for comprehensive coverage.
    """
    combined = " ".join(filter(None, [
        getattr(item, "storyline", ""),
        getattr(item, "image_prompt", ""),
        getattr(item, "prompt", ""),
    ]))
    return extract_entities(combined, screenplay)


# ---------------------------------------------------------------------------
# Entity comparison
# ---------------------------------------------------------------------------

def _ci_set(s: Set[str]) -> Set[str]:
    """Return a case-insensitive (lowered) copy of a string set."""
    return {x.lower() for x in s}


def _fuzzy_match_sets(expected: Set[str], actual: Set[str]) -> Tuple[Set[str], Set[str]]:
    """Compare two entity name sets with substring-aware matching.

    Returns (truly_missing, truly_extra) after removing pairs where one name
    is a case-insensitive substring of the other (e.g. "camera" matches
    "Sony FX6 camera" because the storyboard may abbreviate entity names).
    """
    missing = set(expected)
    extra = set(actual)

    # Try to pair up missing ↔ extra via substring relationship
    paired_missing: Set[str] = set()
    paired_extra: Set[str] = set()
    for m in missing:
        m_lower = m.lower()
        for e in extra:
            if e in paired_extra:
                continue
            e_lower = e.lower()
            # Exact match already handled by set difference, so check substring
            if m_lower in e_lower or e_lower in m_lower:
                paired_missing.add(m)
                paired_extra.add(e)
                break

    return missing - paired_missing, extra - paired_extra


def compare_entity_sets(
    paragraph_entities: EntitySet,
    item_entities: EntitySet,
    item_raw_text: str = "",
    screenplay=None,
) -> EntityMismatch:
    """Compare entities from paragraph vs storyboard item.

    Returns a structured mismatch report indicating missing/extra entities
    and whether the overall match passes.

    Character names are compared in uppercase (already FULL CAPS).
    Objects, vehicles, and environments are compared case-insensitively
    and with substring-aware matching to handle abbreviated names
    (e.g. "camera" matches "Sony FX6 camera").

    If *item_raw_text* is supplied, a final bare-text sweep removes any
    "missing" entity whose name appears as plain text in the storyboard
    item (handles cases where markup was dropped but the entity name is
    still present in the storyline, image_prompt, or prompt).

    If *screenplay* is supplied, entities that have been deleted from the
    identity blocks (i.e. have no metadata entry) are excluded from the
    "expected" set so they don't cause false validation failures.
    """
    p_raw = paragraph_entities
    s = item_entities

    # ── FILTER DELETED ENTITIES ──
    # If an entity appears in the paragraph markup but has no identity block,
    # the user deliberately removed it — exclude it from the "expected" set
    # so the storyboard isn't required to include it (prevents false
    # "missing" errors).  However, the *unfiltered* paragraph (p_raw) is
    # kept for the "extra" comparison: if the storyboard references an
    # entity that IS in the paragraph markup (even without an identity
    # block), it should NOT be flagged as "extra".
    p_required = p_raw
    if screenplay and hasattr(screenplay, 'identity_block_metadata'):
        known_names: Dict[str, Set[str]] = {
            "character": set(),
            "object": set(),
            "vehicle": set(),
            "environment": set(),
        }
        for _meta in screenplay.identity_block_metadata.values():
            etype = (_meta.get("type") or "").lower()
            ename = (_meta.get("name") or "").strip()
            if etype in known_names and ename:
                known_names[etype].add(ename.lower())

        def _exists(name: str, etype: str) -> bool:
            return name.lower() in known_names.get(etype, set())

        p_required = EntitySet(
            characters={c for c in p_raw.characters if _exists(c, "character")},
            objects={o for o in p_raw.objects if _exists(o, "object")},
            vehicles={v for v in p_raw.vehicles if _exists(v, "vehicle")},
            environments={e for e in p_raw.environments if _exists(e, "environment")},
        )

    # Characters: already uppercase, direct set comparison
    # "missing" = required by paragraph but absent from storyboard (filtered)
    # "extra"   = in storyboard but not anywhere in the paragraph (unfiltered)
    missing_chars = p_required.characters - s.characters
    extra_chars = s.characters - p_raw.characters

    # Objects / vehicles / environments: case-insensitive comparison
    # Missing uses the filtered (required) set; extra uses the raw set.
    p_objs_req_ci = _ci_set(p_required.objects)
    p_objs_raw_ci = _ci_set(p_raw.objects)
    s_objs_ci = _ci_set(s.objects)
    missing_objs_ci = p_objs_req_ci - s_objs_ci
    extra_objs_ci = s_objs_ci - p_objs_raw_ci
    missing_objs_ci, extra_objs_ci = _fuzzy_match_sets(missing_objs_ci, extra_objs_ci)
    missing_objs = {o for o in p_required.objects if o.lower() in missing_objs_ci}
    extra_objs = {o for o in s.objects if o.lower() in extra_objs_ci}

    p_vehs_req_ci = _ci_set(p_required.vehicles)
    p_vehs_raw_ci = _ci_set(p_raw.vehicles)
    s_vehs_ci = _ci_set(s.vehicles)
    missing_vehs_ci = p_vehs_req_ci - s_vehs_ci
    extra_vehs_ci = s_vehs_ci - p_vehs_raw_ci
    missing_vehs_ci, extra_vehs_ci = _fuzzy_match_sets(missing_vehs_ci, extra_vehs_ci)
    missing_vehs = {v for v in p_required.vehicles if v.lower() in missing_vehs_ci}
    extra_vehs = {v for v in s.vehicles if v.lower() in extra_vehs_ci}

    wrong_env = False
    p_envs_req_ci = _ci_set(p_required.environments)
    s_envs_ci = _ci_set(s.environments)
    if p_envs_req_ci and s_envs_ci:
        env_missing = p_envs_req_ci - s_envs_ci
        if env_missing:
            for em in list(env_missing):
                for se in s_envs_ci:
                    if em in se or se in em:
                        env_missing.discard(em)
                        break
        wrong_env = bool(env_missing)
    elif p_envs_req_ci and not s_envs_ci:
        wrong_env = True

    # ── BARE-TEXT FALLBACK ──
    # If an entity is "missing" but its name appears as plain text in the
    # storyboard item's combined text, remove it from the missing set.
    # This handles cases where cinematic markup was dropped.
    if item_raw_text:
        raw_lower = item_raw_text.lower()

        still_missing_objs = set()
        for obj in missing_objs:
            if not re.search(r'\b' + re.escape(obj.lower()) + r'\b', raw_lower):
                still_missing_objs.add(obj)
        missing_objs = still_missing_objs

        still_missing_vehs = set()
        for veh in missing_vehs:
            if not re.search(r'\b' + re.escape(veh.lower()) + r'\b', raw_lower):
                still_missing_vehs.add(veh)
        missing_vehs = still_missing_vehs

        still_missing_chars = set()
        for char in missing_chars:
            # Check if any significant word from the character name appears
            words = char.split()
            found = False
            for w in words:
                if len(w) >= 3 and re.search(r'\b' + re.escape(w) + r'\b', item_raw_text, re.IGNORECASE):
                    found = True
                    break
            if not found:
                still_missing_chars.add(char)
        missing_chars = still_missing_chars

    errors: List[str] = []
    if missing_chars:
        errors.append(f"Missing characters: {', '.join(sorted(missing_chars))}")
    if extra_chars:
        errors.append(f"Extra characters (not in paragraph): {', '.join(sorted(extra_chars))}")
    if missing_objs:
        errors.append(f"Missing objects: {', '.join(sorted(missing_objs))}")
    if extra_objs:
        errors.append(f"Extra objects (not in paragraph): {', '.join(sorted(extra_objs))}")
    if missing_vehs:
        errors.append(f"Missing vehicles: {', '.join(sorted(missing_vehs))}")
    if extra_vehs:
        errors.append(f"Extra vehicles (not in paragraph): {', '.join(sorted(extra_vehs))}")
    if wrong_env:
        errors.append(
            f"Wrong environment: expected {sorted(p_required.environments)}, "
            f"got {sorted(s.environments)}"
        )

    is_match = not errors

    return EntityMismatch(
        missing_characters=missing_chars,
        extra_characters=extra_chars,
        missing_objects=missing_objs,
        extra_objects=extra_objs,
        missing_vehicles=missing_vehs,
        extra_vehicles=extra_vehs,
        wrong_environment=wrong_env,
        expected_environments=p_required.environments,
        actual_environments=s.environments,
        is_match=is_match,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Dominant action extraction
# ---------------------------------------------------------------------------

# Action verbs that imply spatial movement (wide shot appropriate)
_SPATIAL_ACTIONS = frozenset({
    "walk", "walks", "run", "runs", "enter", "enters",
    "exit", "exits", "step", "steps", "sprint", "sprints",
    "dash", "dashes", "leap", "leaps", "charge", "charges",
    "climb", "climbs", "descend", "descends", "cross", "crosses",
    "approach", "approaches", "retreat", "retreats", "stumble", "stumbles",
    "flee", "flees", "crawl", "crawls", "drive", "drives",
})

# Action verbs that imply subtle/intimate motion (close/medium shot)
_SUBTLE_ACTIONS = frozenset({
    "adjust", "adjusts", "examine", "examines", "inspect", "inspects",
    "read", "reads", "whisper", "whispers", "touch", "touches",
    "grip", "grips", "squeeze", "squeezes", "press", "presses",
    "type", "types", "write", "writes", "glance", "glances",
    "nod", "nods", "blink", "blinks", "sigh", "sighs",
    "breathe", "breathes", "swallow", "swallows", "wince", "winces",
    "flinch", "flinches", "smirk", "smirks", "narrow", "narrows",
})

# Action verbs that imply tension (low angle / slow push appropriate)
_TENSION_ACTIONS = frozenset({
    "freeze", "freezes", "stare", "stares", "clench", "clenches",
    "tighten", "tightens", "aim", "aims", "point", "points",
    "raise", "raises", "draw", "draws", "load", "loads",
    "cock", "cocks", "brace", "braces", "crouch", "crouches",
    "tense", "tenses", "coil", "coils", "ready", "readies",
})


def extract_dominant_action(paragraph: str) -> str:
    """Find the dominant *action* verb from a paragraph.

    Looks for the first action-marked verb (*verb*) that exists in the
    Action Whitelist.  Falls back to the first *action* found.
    """
    if not paragraph:
        return ""

    actions = ACTION_PATTERN.findall(paragraph)
    if not actions:
        return ""

    whitelist = get_effective_action_whitelist()

    # Try to find one that matches the whitelist
    for action in actions:
        # Strip intensity modifier if present: "verb (modifier)" -> "verb"
        base = action.split("(")[0].strip().lower()
        if base in whitelist:
            return base

    # Fallback: return the first marked action
    return actions[0].split("(")[0].strip().lower()


def suggest_camera_framing(dominant_action: str, paragraph: str) -> str:
    """Suggest camera framing based on the dominant action.

    Rules:
    - Spatial shift actions -> wide shot
    - Subtle / intimate actions -> medium or close-up shot
    - Tension actions -> slow push or low angle
    - Purely environmental (no character action) -> wide establishing shot
    - Default -> medium shot
    """
    if not dominant_action:
        # Check if paragraph is purely environmental
        chars = _filter_caps_stopwords(
            {_normalize_name(m) for m in CHARACTER_PATTERN.findall(paragraph)}
        )
        if not chars:
            return "Wide establishing shot, static camera"
        return "Medium shot, eye level"

    action_lower = dominant_action.lower()

    if action_lower in _SPATIAL_ACTIONS:
        return "Wide shot, tracking camera following movement"

    if action_lower in _SUBTLE_ACTIONS:
        return "Medium close-up, steady camera, shallow depth of field"

    if action_lower in _TENSION_ACTIONS:
        return "Low angle, slow push-in, building tension"

    return "Medium shot, eye level"


# ---------------------------------------------------------------------------
# Full validation pass
# ---------------------------------------------------------------------------

def validate_storyboard_against_paragraphs(
    scene_beats: List[str],
    items: list,
    screenplay=None,
) -> List[ValidationResult]:
    """Run validation for each paragraph/item pair.

    Args:
        scene_beats: List of paragraph strings (source of truth).
        items: List of StoryboardItem objects.
        screenplay: Optional Screenplay for identity cross-referencing.

    Returns:
        List of ValidationResult, one per paragraph.  If there are fewer
        items than paragraphs, extra paragraphs are flagged as invalid
        with a "missing storyboard item" error.
    """
    results: List[ValidationResult] = []

    for idx, beat in enumerate(scene_beats):
        dominant = extract_dominant_action(beat)
        framing = suggest_camera_framing(dominant, beat)

        if idx < len(items):
            item = items[idx]
            p_entities = extract_paragraph_entities(beat, screenplay)
            s_entities = extract_storyboard_entities(item, screenplay)
            # Build combined raw text for bare-text fallback matching
            raw_text = " ".join(filter(None, [
                getattr(item, "storyline", ""),
                getattr(item, "image_prompt", ""),
                getattr(item, "prompt", ""),
            ]))
            mismatch = compare_entity_sets(p_entities, s_entities, item_raw_text=raw_text, screenplay=screenplay)

            results.append(ValidationResult(
                paragraph_index=idx,
                is_valid=mismatch.is_match,
                mismatch=mismatch,
                dominant_action=dominant,
                suggested_framing=framing,
                errors=list(mismatch.errors),
            ))
        else:
            results.append(ValidationResult(
                paragraph_index=idx,
                is_valid=False,
                mismatch=None,
                dominant_action=dominant,
                suggested_framing=framing,
                errors=[f"Missing storyboard item for paragraph {idx + 1}"],
            ))

    # Flag extra items beyond paragraph count
    for extra_idx in range(len(scene_beats), len(items)):
        results.append(ValidationResult(
            paragraph_index=extra_idx,
            is_valid=False,
            mismatch=None,
            dominant_action="",
            suggested_framing="",
            errors=[f"Extra storyboard item {extra_idx + 1} has no corresponding paragraph"],
        ))

    return results
