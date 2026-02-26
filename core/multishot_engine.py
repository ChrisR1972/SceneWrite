"""
Multi-shot clustering engine for MoviePrompterAI.

Provides model-agnostic multi-shot video generation support.  When the video
model advertises ``supports_multishot``, consecutive storyboard items that
share environment, characters, and vehicles are grouped into clusters.  Each
cluster produces a single structured cinematic sequence prompt rather than
individual single-shot prompts.

Single-shot generation remains the default and fallback.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from core.screenplay_engine import (
    ALLOWED_TRANSITION_TYPES,
    MultiShotCluster,
    Screenplay,
    ShotTransition,
    StoryScene,
    StoryboardItem,
)


# ---------------------------------------------------------------------------
# Entity extraction helpers (lightweight, markup-based)
# ---------------------------------------------------------------------------

_ENV_PATTERN = re.compile(r'_([^_]+)_')
_OBJ_PATTERN = re.compile(r'\[([^\]]+)\]')
_VEH_PATTERN = re.compile(r'\{([^}]+)\}')
_HONORIFIC = r"(?:(?:MRS?|MS|DR|MME|PROF|SGT|CPT|LT|GEN|COL|REV|CMDR|CAPT)\.\s+)?"
_NAME_WORD = r"[A-Z](?:[A-Z]+|'[A-Z]+)"
_CHAR_PATTERN = re.compile(rf"\b({_HONORIFIC}{_NAME_WORD}(?:[ \t]+{_NAME_WORD})*)\b")

# Identity block ID tags injected by the pipeline
_ID_TAG = re.compile(r'\((CHARACTER|OBJECT|VEHICLE|ENVIRONMENT)_[A-F0-9]+\)')


def _strip_id_tags(text: str) -> str:
    """Remove identity block ID tags before entity extraction."""
    return _ID_TAG.sub('', text)


def _extract_characters_from_text(text: str,
                                   registry: Optional[List[str]] = None) -> Set[str]:
    cleaned = _strip_id_tags(text)

    if registry:
        return _match_characters_from_registry(cleaned, registry)

    raw = set(_CHAR_PATTERN.findall(cleaned))
    stop_words = {
        'THE', 'AND', 'BUT', 'FOR', 'WITH', 'FROM', 'INTO', 'ONTO',
        'HIS', 'HER', 'ITS', 'OUR', 'CUT', 'FADE', 'INT', 'EXT',
        'PAN', 'ZOOM', 'CLOSE', 'WIDE', 'SHOT', 'ANGLE', 'POV',
        'MR', 'MRS', 'MS', 'DR', 'MME', 'PROF', 'SGT', 'CPT', 'LT',
        'GEN', 'COL', 'REV', 'CMDR', 'CAPT',
    }
    return {n for n in raw if n not in stop_words and len(n) > 1}


def _match_characters_from_registry(text: str,
                                     registry: List[str]) -> Set[str]:
    """Match characters by scanning for known registry names (longest first).

    Handles garbled/repeated names by checking if any registered name appears
    as a substring of the uppercase text.  Longest names are checked first so
    "MAESTRO ORVILLE STONE" matches before "STONE" can.
    """
    text_upper = text.upper()
    sorted_names = sorted(registry, key=len, reverse=True)
    found: Set[str] = set()
    for name in sorted_names:
        if not name:
            continue
        if name.upper() in text_upper:
            found.add(name)
    return found


def _extract_environments_from_text(text: str) -> Set[str]:
    return set(_ENV_PATTERN.findall(_strip_id_tags(text)))


def _extract_objects_from_text(text: str) -> Set[str]:
    return set(_OBJ_PATTERN.findall(_strip_id_tags(text)))


def _extract_vehicles_from_text(text: str) -> Set[str]:
    return set(_VEH_PATTERN.findall(_strip_id_tags(text)))


def _item_text(item: StoryboardItem) -> str:
    return " ".join(filter(None, [item.storyline, item.prompt, item.camera_notes]))


# ---------------------------------------------------------------------------
# Strategy resolution
# ---------------------------------------------------------------------------

def resolve_generation_strategy(scene: StoryScene,
                                model_settings: Dict[str, Any],
                                screenplay: Optional['Screenplay'] = None) -> str:
    """Determine the generation strategy for *scene* based on model capabilities.

    Returns ``"single_shot"`` or ``"multi_shot_cluster"``.
    Prefers per-project ``screenplay.story_settings`` when available,
    falling back to *model_settings* for backward compatibility.
    """
    ss = getattr(screenplay, "story_settings", None) if screenplay else None
    supports = ss.get("supports_multishot", False) if ss else model_settings.get("supports_multishot", False)
    if not supports:
        return "single_shot"
    if len(scene.storyboard_items) < 2:
        return "single_shot"
    return "multi_shot_cluster"


# ---------------------------------------------------------------------------
# Cluster building
# ---------------------------------------------------------------------------

def _get_item_environment(item: StoryboardItem,
                          scene: StoryScene) -> str:
    """Return the environment id for *item*, falling back to the scene env."""
    text = _item_text(item)
    envs = _extract_environments_from_text(text)
    if envs:
        return sorted(envs)[0]
    return scene.environment_id or ""


def _normalize_env_set(env: str, scene: StoryScene,
                       screenplay: Optional['Screenplay'] = None) -> Set[str]:
    """Build a set of equivalent identifiers for *env* so that an extracted
    name like ``"haunted basement"`` matches the scene fallback
    ``"ENVIRONMENT_1FDB"`` when they refer to the same location."""
    equivalents: Set[str] = set()
    if env:
        equivalents.add(env.lower().strip())
    scene_env_id = (scene.environment_id or "").strip()
    if scene_env_id:
        equivalents.add(scene_env_id.lower())
    if screenplay:
        meta = getattr(screenplay, "identity_block_metadata", {}) or {}
        if scene_env_id and scene_env_id in meta:
            name = (meta[scene_env_id].get("name") or "").strip()
            if name:
                equivalents.add(name.lower())
    return equivalents


def _envs_compatible(env_a: str, env_b: str, scene: StoryScene,
                     screenplay: Optional['Screenplay'] = None) -> bool:
    """Return True when two environment identifiers refer to the same place."""
    if env_a == env_b:
        return True
    set_a = _normalize_env_set(env_a, scene, screenplay)
    set_b = _normalize_env_set(env_b, scene, screenplay)
    return bool(set_a & set_b)


def _items_compatible(anchor_chars: Set[str],
                      anchor_vehicles: Set[str],
                      anchor_env: str,
                      anchor_identity_ids: Set[str],
                      candidate: StoryboardItem,
                      scene: StoryScene,
                      screenplay: Screenplay,
                      cumulative_duration: int,
                      max_duration: int) -> bool:
    """Return True when *candidate* can join the current cluster."""
    if cumulative_duration + candidate.duration > max_duration:
        return False

    text = _item_text(candidate)
    cand_env = _get_item_environment(candidate, scene)
    if not _envs_compatible(anchor_env, cand_env, scene, screenplay):
        return False

    registry = getattr(screenplay, 'character_registry', None) or None
    cand_chars = _extract_characters_from_text(text, registry=registry)
    if cand_chars and anchor_chars and not cand_chars.issubset(anchor_chars):
        return False

    cand_vehicles = _extract_vehicles_from_text(text)
    if cand_vehicles and anchor_vehicles and not cand_vehicles.issubset(anchor_vehicles):
        return False

    # Reject if a genuinely new identity block appears that was not in the
    # anchor set.  When the anchor has no tags (first item didn't use them)
    # we skip this check -- character/vehicle/environment name matching above
    # is sufficient.
    if anchor_identity_ids:
        cand_ids: Set[str] = set()
        for tag_match in _ID_TAG.finditer(text):
            cand_ids.add(tag_match.group(0))
        if cand_ids - anchor_identity_ids:
            return False

    return True


def _ad_blocks_cluster(scene: StoryScene,
                       item_a: StoryboardItem,
                       item_b: StoryboardItem) -> bool:
    """Advertisement-mode guard: return False if clustering would violate ad rules."""
    beat = getattr(scene, "ad_beat_type", "")
    if not beat:
        return True
    # Brand hero and product reveal shots must stay isolated
    if getattr(scene, "is_brand_hero_shot", False):
        return False
    if getattr(scene, "is_product_reveal", False):
        return False
    if getattr(item_a, "is_hero_shot", False) or getattr(item_b, "is_hero_shot", False):
        return False
    return True


def build_clusters(scene: StoryScene,
                   screenplay: Screenplay,
                   max_duration: int,
                   is_ad_mode: bool = False) -> List[MultiShotCluster]:
    """Group consecutive storyboard items into multi-shot clusters.

    Items that cannot be grouped remain in single-item clusters (effectively
    single-shot).
    """
    items = sorted(scene.storyboard_items, key=lambda i: i.sequence_number)
    if not items:
        return []

    registry = getattr(screenplay, 'character_registry', None) or None

    clusters: List[MultiShotCluster] = []
    current_ids: List[str] = []
    current_items: List[StoryboardItem] = []
    anchor_chars: Set[str] = set()
    anchor_vehicles: Set[str] = set()
    anchor_env: str = ""
    anchor_identity_ids: Set[str] = set()
    cumulative_dur = 0

    def _flush() -> None:
        nonlocal current_ids, current_items, anchor_chars, anchor_vehicles
        nonlocal anchor_env, anchor_identity_ids, cumulative_dur
        if current_items:
            cluster = _make_cluster(current_items, scene, screenplay,
                                    anchor_chars, anchor_vehicles, anchor_env)
            clusters.append(cluster)
        current_ids = []
        current_items = []
        anchor_chars = set()
        anchor_vehicles = set()
        anchor_env = ""
        anchor_identity_ids = set()
        cumulative_dur = 0

    for item in items:
        if not current_items:
            # Start a new cluster
            text = _item_text(item)
            anchor_chars = _extract_characters_from_text(text, registry=registry)
            anchor_vehicles = _extract_vehicles_from_text(text)
            anchor_env = _get_item_environment(item, scene)
            anchor_identity_ids = {m.group(0) for m in _ID_TAG.finditer(text)}
            current_items.append(item)
            current_ids.append(item.item_id)
            cumulative_dur = item.duration
            continue

        # Ad-mode guard
        if is_ad_mode and not _ad_blocks_cluster(scene, current_items[-1], item):
            _flush()
            # Re-seed with this item
            text = _item_text(item)
            anchor_chars = _extract_characters_from_text(text, registry=registry)
            anchor_vehicles = _extract_vehicles_from_text(text)
            anchor_env = _get_item_environment(item, scene)
            anchor_identity_ids = {m.group(0) for m in _ID_TAG.finditer(text)}
            current_items.append(item)
            current_ids.append(item.item_id)
            cumulative_dur = item.duration
            continue

        if _items_compatible(anchor_chars, anchor_vehicles, anchor_env,
                             anchor_identity_ids, item, scene, screenplay,
                             cumulative_dur, max_duration):
            current_items.append(item)
            current_ids.append(item.item_id)
            cumulative_dur += item.duration
            # Grow identity id set
            text = _item_text(item)
            anchor_identity_ids |= {m.group(0) for m in _ID_TAG.finditer(text)}
        else:
            _flush()
            text = _item_text(item)
            anchor_chars = _extract_characters_from_text(text, registry=registry)
            anchor_vehicles = _extract_vehicles_from_text(text)
            anchor_env = _get_item_environment(item, scene)
            anchor_identity_ids = {m.group(0) for m in _ID_TAG.finditer(text)}
            current_items.append(item)
            current_ids.append(item.item_id)
            cumulative_dur = item.duration

    _flush()
    return clusters


def _make_cluster(items: List[StoryboardItem],
                  scene: StoryScene,
                  screenplay: Screenplay,
                  chars: Set[str],
                  vehicles: Set[str],
                  env: str) -> MultiShotCluster:
    shots: List[Dict[str, Any]] = []
    for idx, it in enumerate(items, 1):
        shots.append({
            "shot_number": idx,
            "duration": it.duration,
            "description": it.storyline,
            "camera": it.camera_notes,
            "action": it.prompt,
        })
    return MultiShotCluster(
        cluster_id=f"CLUSTER_{uuid.uuid4().hex[:8].upper()}",
        scene_id=scene.scene_id,
        item_ids=[it.item_id for it in items],
        total_duration=sum(it.duration for it in items),
        environment_id=env,
        primary_characters=sorted(chars),
        vehicles=sorted(vehicles),
        shots=shots,
        transitions=[],
        identity_lock_refs={},
    )


# ---------------------------------------------------------------------------
# Transition generation
# ---------------------------------------------------------------------------

_WHIP_KEYWORDS = re.compile(
    r'\b(whip|snap|jerk|spin|swivel|swipe)\b', re.IGNORECASE)
_PUSH_KEYWORDS = re.compile(
    r'\b(push\s*in|dolly\s*in|move\s*closer|advancing)\b', re.IGNORECASE)
_RACK_KEYWORDS = re.compile(
    r'\b(rack\s*focus|shift\s*focus|focus\s*pull)\b', re.IGNORECASE)
_OCCLUSION_KEYWORDS = re.compile(
    r'\b(behind|occlude|block|pass\s*in\s*front|obscure|silhouette)\b', re.IGNORECASE)
_MATCH_KEYWORDS = re.compile(
    r'\b(match|mirror|echo|reflect|parallel)\b', re.IGNORECASE)


def _choose_transition_type(from_item: StoryboardItem,
                            to_item: StoryboardItem) -> str:
    from_cam = (from_item.camera_notes or "").lower()
    to_cam = (to_item.camera_notes or "").lower()
    combined = from_cam + " " + to_cam

    if _WHIP_KEYWORDS.search(combined):
        return "whip_pan"
    if _PUSH_KEYWORDS.search(combined):
        return "push_in_continuation"
    if _RACK_KEYWORDS.search(combined):
        return "rack_focus"
    if _OCCLUSION_KEYWORDS.search(combined):
        return "environmental_occlusion_cut"
    if _MATCH_KEYWORDS.search(combined):
        return "match_cut"

    from_chars = _extract_characters_from_text(_item_text(from_item))
    to_chars = _extract_characters_from_text(_item_text(to_item))
    if from_chars and to_chars and from_chars != to_chars:
        return "match_cut"

    # Camera movement changes suggest motivated move
    if from_cam and to_cam and from_cam != to_cam:
        return "motivated_camera_move"

    return "seamless_cut"


def generate_transitions(cluster: MultiShotCluster,
                         items_lookup: Dict[str, StoryboardItem]) -> List[ShotTransition]:
    """Produce transitions between consecutive shots in *cluster*."""
    transitions: List[ShotTransition] = []
    for i in range(len(cluster.item_ids) - 1):
        from_item = items_lookup.get(cluster.item_ids[i])
        to_item = items_lookup.get(cluster.item_ids[i + 1])
        if not from_item or not to_item:
            transitions.append(ShotTransition(
                from_shot=i + 1, to_shot=i + 2,
                transition_type="seamless_cut"))
            continue
        t_type = _choose_transition_type(from_item, to_item)
        transitions.append(ShotTransition(
            from_shot=i + 1,
            to_shot=i + 2,
            transition_type=t_type,
            description=f"{t_type.replace('_', ' ').title()} from shot {i+1} to shot {i+2}",
        ))
    return transitions


# ---------------------------------------------------------------------------
# Identity lock reinforcement
# ---------------------------------------------------------------------------

def reinforce_identity_locks(cluster: MultiShotCluster,
                             screenplay: Screenplay) -> Dict[str, str]:
    """Build concise identity-lock snippets for every entity in *cluster*.

    Returns a mapping of ``entity_id -> lock_snippet``.  If a new identity is
    detected that was not present in the first shot, the cluster should be
    split (handled by the caller via ``validate_cluster``).
    """
    refs: Dict[str, str] = {}
    meta = screenplay.identity_block_metadata or {}

    all_text = " ".join(
        s.get("description", "") + " " + s.get("action", "")
        for s in cluster.shots
    )

    for entity_id, entity_meta in meta.items():
        name = entity_meta.get("name", "")
        if not name:
            continue
        # Only lock entities that are actually referenced in the cluster text
        if name.upper() not in all_text.upper() and name not in all_text:
            continue
        e_type = entity_meta.get("type", "")
        user_notes = entity_meta.get("user_notes", "")
        snippet_parts = [f"{e_type.upper()}: {name}"]
        if user_notes:
            snippet_parts.append(user_notes[:120])
        refs[entity_id] = " | ".join(snippet_parts)

    return refs


# ---------------------------------------------------------------------------
# Prompt formatting
# ---------------------------------------------------------------------------

_TRANSITION_LABELS = {
    "seamless_cut": "Seamless Cut",
    "match_cut": "Match Cut",
    "whip_pan": "Whip Pan",
    "motivated_camera_move": "Motivated Camera Move",
    "push_in_continuation": "Push-In Continuation",
    "rack_focus": "Rack Focus",
    "environmental_occlusion_cut": "Environmental Occlusion Cut",
}


def format_multishot_prompt(
    cluster: MultiShotCluster,
    screenplay: Optional[Screenplay] = None,
    scene=None,
    items: Optional[List] = None,
) -> str:
    """Produce a clean cinematic-sequence prompt (no JSON).

    When *screenplay* and *scene* are provided the new structured Video Prompt
    Builder is used.  Otherwise falls back to the legacy flat format.
    """
    if screenplay is not None and scene is not None:
        try:
            from .video_prompt_builder import build_multishot_cluster_prompt
            return build_multishot_cluster_prompt(cluster, screenplay, scene, items or [])
        except Exception:
            pass

    # Legacy fallback
    lines: List[str] = []

    if cluster.identity_lock_refs:
        lines.append("--- Identity Lock ---")
        for eid, snippet in cluster.identity_lock_refs.items():
            lines.append(f"  {snippet}")
        lines.append("--- Sequence ---")
        lines.append("")

    for idx, shot in enumerate(cluster.shots):
        dur = shot.get("duration", 5)
        desc = shot.get("description", "").strip()
        camera = shot.get("camera", "").strip()
        lines.append(f"Shot {shot.get('shot_number', idx + 1)} ({dur}s): {desc}")
        if camera:
            lines.append(f"Camera: {camera}")

        if idx < len(cluster.transitions):
            t = cluster.transitions[idx]
            label = _TRANSITION_LABELS.get(t.transition_type, t.transition_type)
            lines.append(f"Transition: {label}")
        if idx < len(cluster.shots) - 1:
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Render-cost calculation (multi-shot specific)
# ---------------------------------------------------------------------------

_CAMERA_INTENSITY_WORDS = re.compile(
    r'\b(crane|jib|steadicam|dolly|tracking|whip|pan|tilt|zoom|push|pull|orbit|arc|fly|aerial)\b',
    re.IGNORECASE,
)

TRANSITION_COMPLEXITY_MAP: Dict[str, int] = {
    "seamless_cut": 1,
    "match_cut": 4,
    "whip_pan": 6,
    "motivated_camera_move": 5,
    "push_in_continuation": 4,
    "rack_focus": 3,
    "environmental_occlusion_cut": 7,
}


def calculate_multishot_render_cost(
        cluster: MultiShotCluster) -> Tuple[str, Dict[str, Any]]:
    """Return ``(cost_level, factors)`` for a multi-shot cluster."""
    num_shots = len(cluster.shots)

    # Camera movement intensity
    all_camera = " ".join(s.get("camera", "") for s in cluster.shots)
    cam_hits = len(_CAMERA_INTENSITY_WORDS.findall(all_camera))
    camera_intensity = min(cam_hits * 2, 10)

    # Transition complexity (average)
    t_scores = [TRANSITION_COMPLEXITY_MAP.get(t.transition_type, 2)
                for t in cluster.transitions]
    transition_complexity = int(round(sum(t_scores) / max(len(t_scores), 1)))

    # Motion continuity (rough heuristic: more shots = more continuity burden)
    motion_continuity = min(num_shots * 2, 10)

    # Character persistence
    char_persistence = min(len(cluster.primary_characters) * 2, 10)

    factors: Dict[str, Any] = {
        "number_of_internal_shots": num_shots,
        "camera_movement_intensity": camera_intensity,
        "transition_complexity": transition_complexity,
        "motion_continuity": motion_continuity,
        "character_persistence": char_persistence,
    }

    total = sum(v for v in factors.values() if isinstance(v, (int, float)))
    if total <= 12:
        level = "easy"
    elif total <= 28:
        level = "moderate"
    else:
        level = "expensive"

    return level, factors


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_cluster(cluster: MultiShotCluster,
                     screenplay: Screenplay,
                     max_duration: int) -> bool:
    """Return True when *cluster* passes all integrity checks."""
    if cluster.total_duration > max_duration:
        return False

    if len(cluster.item_ids) < 1:
        return False

    # Verify identity lock consistency: first shot's entities must be a
    # superset of (or equal to) all entities in subsequent shots.
    first_text = ""
    if cluster.shots:
        s = cluster.shots[0]
        first_text = s.get("description", "") + " " + s.get("action", "")
    first_chars = _extract_characters_from_text(first_text)
    first_vehicles = _extract_vehicles_from_text(first_text)

    for shot in cluster.shots[1:]:
        text = shot.get("description", "") + " " + shot.get("action", "")
        chars = _extract_characters_from_text(text)
        vehicles = _extract_vehicles_from_text(text)
        # New characters or vehicles mid-cluster → invalid
        if chars - first_chars:
            return False
        if vehicles - first_vehicles:
            return False

    # Verify transitions reference valid shot numbers
    shot_numbers = {s.get("shot_number", i + 1) for i, s in enumerate(cluster.shots)}
    for t in cluster.transitions:
        if t.from_shot not in shot_numbers or t.to_shot not in shot_numbers:
            return False
        if t.transition_type not in ALLOWED_TRANSITION_TYPES:
            return False

    return True


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

def apply_multishot_clustering(
        scene: StoryScene,
        screenplay: Screenplay,
        model_settings: Dict[str, Any],
) -> None:
    """Run the full multi-shot clustering pipeline on *scene*.

    Mutates *scene* in-place: sets ``generation_strategy``,
    ``multishot_clusters``, and per-item ``cluster_id`` /
    ``shot_number_in_cluster``.

    On any failure the scene reverts to single-shot.
    """
    strategy = resolve_generation_strategy(scene, model_settings, screenplay)
    scene.generation_strategy = strategy
    if strategy != "multi_shot_cluster":
        _revert_to_single_shot(scene)
        return

    ss = getattr(screenplay, "story_settings", None)
    max_dur = (ss.get("max_generation_duration_seconds", 15) if ss
               else model_settings.get("max_generation_duration_seconds", 15))
    is_ad = screenplay.is_advertisement_mode()

    try:
        clusters = build_clusters(scene, screenplay, max_dur, is_ad_mode=is_ad)
    except Exception:
        _revert_to_single_shot(scene)
        return

    items_lookup = {it.item_id: it for it in scene.storyboard_items}
    valid_clusters: List[MultiShotCluster] = []

    for cluster in clusters:
        # Single-item clusters are effectively single-shot; skip enrichment
        if len(cluster.item_ids) <= 1:
            valid_clusters.append(cluster)
            continue

        try:
            cluster.identity_lock_refs = reinforce_identity_locks(cluster, screenplay)
            cluster.transitions = generate_transitions(cluster, items_lookup)
            cluster_items = [items_lookup[iid] for iid in cluster.item_ids if iid in items_lookup]
            cluster.generation_prompt = format_multishot_prompt(
                cluster, screenplay=screenplay, scene=scene, items=cluster_items)
            cost_level, cost_factors = calculate_multishot_render_cost(cluster)
            cluster.transition_complexity = cost_factors.get("transition_complexity", 0)
            cluster.metadata["render_cost"] = cost_level
            cluster.metadata["render_cost_factors"] = cost_factors

            if not validate_cluster(cluster, screenplay, max_dur):
                # Revert items in this cluster to unclustered
                for iid in cluster.item_ids:
                    it = items_lookup.get(iid)
                    if it:
                        it.cluster_id = None
                        it.shot_number_in_cluster = None
                continue

            valid_clusters.append(cluster)
        except Exception:
            # Safety: revert this cluster to single-shot
            for iid in cluster.item_ids:
                it = items_lookup.get(iid)
                if it:
                    it.cluster_id = None
                    it.shot_number_in_cluster = None
            continue

    # Assign cluster IDs to items
    for cluster in valid_clusters:
        if len(cluster.item_ids) <= 1:
            continue
        for shot_idx, iid in enumerate(cluster.item_ids, 1):
            it = items_lookup.get(iid)
            if it:
                it.cluster_id = cluster.cluster_id
                it.shot_number_in_cluster = shot_idx

    scene.multishot_clusters = valid_clusters


def _revert_to_single_shot(scene: StoryScene) -> None:
    scene.generation_strategy = "single_shot"
    scene.multishot_clusters = []
    for item in scene.storyboard_items:
        item.cluster_id = None
        item.shot_number_in_cluster = None
