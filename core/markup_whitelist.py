"""
Persistent Whitelist Manager for MoviePrompterAI Cinematic Markup.

Manages user-added Action verbs and SFX stored in:
  config/ActionWhitelist.json
  config/SFXWhitelist.json

These are merged at runtime with the built-in frozensets in
action_rules.py and sfx_rules.py. The built-in lists are never modified.

Only Action and SFX support permanent whitelist addition.
Character, Object, Vehicle, and Environment are instance-level only.
"""

import json
import os
import re
import sys
from typing import Set, Optional

from core.action_rules import (
    ACTION_VERB_WHITELIST,
    ACTION_VERB_FORBIDDEN,
    _to_base_form,
    set_user_action_whitelist,
)
from core.sfx_rules import (
    SFX_WHITELIST,
    SFX_FORBIDDEN,
    set_user_sfx_whitelist,
)


def _get_config_dir() -> str:
    """Return the path to the config/ directory next to the app root."""
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "config")


def _ensure_config_dir():
    """Create the config/ directory if it does not exist."""
    config_dir = _get_config_dir()
    if not os.path.isdir(config_dir):
        os.makedirs(config_dir, exist_ok=True)


def _action_whitelist_path() -> str:
    return os.path.join(_get_config_dir(), "ActionWhitelist.json")


def _sfx_whitelist_path() -> str:
    return os.path.join(_get_config_dir(), "SFXWhitelist.json")


# ── LOAD ──────────────────────────────────────────────────────────────────

def load_action_whitelist() -> Set[str]:
    """Load user-added action verbs from config/ActionWhitelist.json."""
    path = _action_whitelist_path()
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return set(data)
    except Exception:
        pass
    return set()


def load_sfx_whitelist() -> Set[str]:
    """Load user-added SFX from config/SFXWhitelist.json."""
    path = _sfx_whitelist_path()
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return set(data)
    except Exception:
        pass
    return set()


# ── SAVE ──────────────────────────────────────────────────────────────────

def _save_action_whitelist(entries: Set[str]):
    """Write the user action whitelist to disk (sorted, deduplicated)."""
    _ensure_config_dir()
    path = _action_whitelist_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(entries), f, indent=2, ensure_ascii=False)


def _save_sfx_whitelist(entries: Set[str]):
    """Write the user SFX whitelist to disk (sorted, deduplicated)."""
    _ensure_config_dir()
    path = _sfx_whitelist_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(entries), f, indent=2, ensure_ascii=False)


# ── NORMALIZE ─────────────────────────────────────────────────────────────

def normalize_action_verb(verb: str) -> str:
    """Normalize a verb to its base form for whitelist storage.
    
    If the verb is already recognized by action_rules, return its base form.
    Otherwise return the lowercased verb as-is (user is adding a new one).
    """
    v = verb.strip().lower()
    base = _to_base_form(v)
    if base:
        return base
    # Try stripping common suffixes for a clean base form
    for suffix in ("ing", "ed", "es", "s"):
        if v.endswith(suffix) and len(v) > len(suffix) + 2:
            candidate = v[:-len(suffix)]
            if suffix in ("ing", "ed") and not candidate.endswith("e"):
                candidate_e = candidate + "e"
                return candidate_e
            return candidate
    return v


def normalize_sfx(sfx: str) -> str:
    """Normalize SFX to lowercase_underscore format for whitelist storage."""
    s = sfx.strip().lower()
    s = re.sub(r'[^a-z0-9_]', '_', s)
    s = re.sub(r'_+', '_', s)
    s = s.strip('_')
    return s


# ── SAFETY FILTERS ────────────────────────────────────────────────────────

_ABSTRACT_NOUNS = frozenset({
    "silence", "tension", "drama", "mood", "emotion", "mystery",
    "suspense", "dread", "anticipation", "relief", "confusion",
    "excitement", "sadness", "anger", "joy", "surprise", "love",
    "hate", "guilt", "shame", "pride", "envy", "jealousy",
})

_DIALOGUE_WORDS = frozenset({
    "said", "says", "asked", "replied", "answered", "whispered",
    "shouted", "exclaimed", "muttered", "murmured", "stammered",
    "stuttered", "remarked", "noted", "added", "continued",
    "explained", "insisted", "demanded", "pleaded", "begged",
})


def is_valid_action_candidate(word: str) -> tuple:
    """Check if a word is a valid candidate for the Action whitelist.
    
    Returns (is_valid: bool, rejection_reason: str or None).
    """
    w = word.strip().lower()
    base = normalize_action_verb(w)
    
    if base in ACTION_VERB_FORBIDDEN or w in ACTION_VERB_FORBIDDEN:
        return False, "Emotional, internal, or abstract verbs cannot be added to the Action whitelist."
    
    if w in _ABSTRACT_NOUNS or base in _ABSTRACT_NOUNS:
        return False, "Abstract nouns cannot be added to the Action whitelist."
    
    if w in _DIALOGUE_WORDS or base in _DIALOGUE_WORDS:
        return False, "Dialogue attribution words cannot be added to the Action whitelist."
    
    return True, None


def is_valid_sfx_candidate(sfx: str) -> tuple:
    """Check if a word is a valid candidate for the SFX whitelist.
    
    Returns (is_valid: bool, rejection_reason: str or None).
    """
    norm = normalize_sfx(sfx)
    
    if norm in SFX_FORBIDDEN:
        return False, "This word does not qualify as a physical sound effect."
    
    if norm in _ABSTRACT_NOUNS:
        return False, "Abstract nouns cannot be added as SFX."
    
    return True, None


# ── ADD / REMOVE ──────────────────────────────────────────────────────────

def add_to_action_whitelist(verb: str) -> bool:
    """Add a verb to the persistent action whitelist.
    
    Normalizes to base form, deduplicates, and saves.
    Returns True if the verb was newly added, False if already present or invalid.
    """
    valid, _ = is_valid_action_candidate(verb)
    if not valid:
        return False
    
    base = normalize_action_verb(verb)
    if not base:
        return False
    
    # Skip if already in built-in whitelist
    if base in ACTION_VERB_WHITELIST:
        return False
    
    current = load_action_whitelist()
    if base in current:
        return False
    
    current.add(base)
    _save_action_whitelist(current)
    sync_runtime_whitelists()
    return True


def add_to_sfx_whitelist(sfx: str) -> bool:
    """Add an SFX to the persistent SFX whitelist.
    
    Normalizes to lowercase_underscore, deduplicates, and saves.
    Returns True if newly added, False if already present or invalid.
    """
    valid, _ = is_valid_sfx_candidate(sfx)
    if not valid:
        return False
    
    norm = normalize_sfx(sfx)
    if not norm:
        return False
    
    # Skip if already in built-in whitelist
    if norm in SFX_WHITELIST:
        return False
    
    current = load_sfx_whitelist()
    if norm in current:
        return False
    
    current.add(norm)
    _save_sfx_whitelist(current)
    sync_runtime_whitelists()
    return True


def remove_from_action_whitelist(verb: str) -> bool:
    """Remove a verb from the persistent action whitelist.
    
    Returns True if removed, False if not found.
    """
    base = normalize_action_verb(verb)
    current = load_action_whitelist()
    if base in current:
        current.discard(base)
        _save_action_whitelist(current)
        sync_runtime_whitelists()
        return True
    return False


def remove_from_sfx_whitelist(sfx: str) -> bool:
    """Remove an SFX from the persistent SFX whitelist.
    
    Returns True if removed, False if not found.
    """
    norm = normalize_sfx(sfx)
    current = load_sfx_whitelist()
    if norm in current:
        current.discard(norm)
        _save_sfx_whitelist(current)
        sync_runtime_whitelists()
        return True
    return False


# ── MERGED WHITELISTS ─────────────────────────────────────────────────────

def get_merged_action_whitelist() -> Set[str]:
    """Return the union of built-in + user-added action verbs."""
    return ACTION_VERB_WHITELIST | load_action_whitelist()


def get_merged_sfx_whitelist() -> Set[str]:
    """Return the union of built-in + user-added SFX."""
    return SFX_WHITELIST | load_sfx_whitelist()


def sync_runtime_whitelists():
    """Push user whitelist entries into the runtime sets in action_rules and sfx_rules.
    
    Call this at startup and after any whitelist modification to ensure the
    auto-validation engine (cinematic grammar pass) sees user-added entries.
    """
    set_user_action_whitelist(load_action_whitelist())
    set_user_sfx_whitelist(load_sfx_whitelist())
