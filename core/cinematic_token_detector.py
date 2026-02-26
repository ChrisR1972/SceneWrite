"""
Cinematic Token Detector for MoviePrompterAI.

Scans scene text and classifies unmarked tokens for spellcheck-style highlighting.

Token types:
- unknown_action: word matches action whitelist but is NOT inside *...* markup
- unknown_sfx: word matches SFX whitelist but is NOT inside (...) markup
- unknown_identity: capitalized phrase that looks like a proper noun but has no markup

This module provides line-level detection for use by the QSyntaxHighlighter.
"""

import re
from typing import List, NamedTuple, Set, Optional

from core.markup_whitelist import get_merged_action_whitelist, get_merged_sfx_whitelist
from core.action_rules import ACTION_VERB_FORBIDDEN


class UnknownToken(NamedTuple):
    """A detected unmarked token within a single line of text."""
    start: int      # character offset within the line
    length: int     # character length
    word: str       # the raw word
    token_type: str # "unknown_action", "unknown_sfx", "unknown_identity"


# Pre-compiled patterns for identifying markup spans within a line
_MARKUP_SPANS = [
    re.compile(r'\*[^*]+\*'),           # *action*
    re.compile(r'\([^)]+\)'),           # (sfx)
    re.compile(r'\[[^\]]+\]'),          # [object]
    re.compile(r'\{[^}]+\}'),           # {vehicle}
    re.compile(r'(?<!\w)_[^_]+_(?!\w)'),# _environment_
    re.compile(r'"[^"]*"'),             # "dialogue"
]

_WORD_PATTERN = re.compile(r'\b[a-zA-Z][a-zA-Z\'-]*[a-zA-Z]\b|\b[a-zA-Z]\b')

# Words that look like proper nouns but are common English words (false-positive filter)
_COMMON_TITLE_CASE = frozenset({
    "The", "A", "An", "In", "On", "At", "To", "For", "Of", "And", "But", "Or",
    "He", "She", "It", "They", "We", "His", "Her", "Its", "Their", "My", "Your",
    "This", "That", "These", "Those", "With", "From", "Into", "Through",
    "Behind", "Under", "Over", "Between", "Before", "After", "During",
    "Not", "No", "Yes", "All", "Some", "Any", "Each", "Every",
})

# Nouns/adjectives that commonly appear after articles -- skip these for action detection
_NOUN_SIGNALS = frozenset({
    "the", "a", "an", "his", "her", "its", "their", "my", "your", "our",
    "this", "that", "these", "those", "some", "every", "each", "no", "any",
})


def _get_masked_positions(line: str) -> Set[int]:
    """Return set of character positions that are inside existing markup or dialogue."""
    masked = set()
    for pat in _MARKUP_SPANS:
        for m in pat.finditer(line):
            for i in range(m.start(), m.end()):
                masked.add(i)
    return masked


def _is_character_name_line(line: str) -> bool:
    """Return True if this line is just a character name (all caps, short)."""
    stripped = line.strip()
    if not stripped:
        return False
    # Character name line: all uppercase, 1-4 words, no punctuation except spaces
    if stripped == stripped.upper() and len(stripped.split()) <= 4:
        if all(c.isalpha() or c.isspace() or c == '-' or c == "'" for c in stripped):
            return True
    return False


def _build_inflection_lookup(whitelist: Set[str]) -> Set[str]:
    """Build a set of common inflections for action verbs in the whitelist."""
    inflections = set(whitelist)
    for verb in whitelist:
        if ' ' in verb:
            continue
        inflections.add(verb + "s")
        inflections.add(verb + "es")
        inflections.add(verb + "ed")
        inflections.add(verb + "ing")
        if verb.endswith("e"):
            inflections.add(verb[:-1] + "ing")
            inflections.add(verb + "d")
        if len(verb) >= 3 and verb[-1] not in "aeiouy" and verb[-2] in "aeiou" and verb[-3] not in "aeiou":
            inflections.add(verb + verb[-1] + "ing")
            inflections.add(verb + verb[-1] + "ed")
    return inflections


# Cached inflection sets (rebuilt when whitelists change)
_cached_action_inflections: Optional[Set[str]] = None
_cached_action_whitelist_size: int = -1


def _get_action_inflections() -> Set[str]:
    """Get the cached action inflection set, rebuilding if whitelist changed."""
    global _cached_action_inflections, _cached_action_whitelist_size
    merged = get_merged_action_whitelist()
    if _cached_action_inflections is None or len(merged) != _cached_action_whitelist_size:
        _cached_action_inflections = _build_inflection_lookup(merged)
        _cached_action_whitelist_size = len(merged)
    return _cached_action_inflections


def invalidate_cache():
    """Force rebuild of cached inflection sets (call after whitelist changes)."""
    global _cached_action_inflections, _cached_action_whitelist_size
    _cached_action_inflections = None
    _cached_action_whitelist_size = -1


def detect_line_tokens(line: str, ignore_words: Optional[Set[str]] = None) -> List[UnknownToken]:
    """Detect unmarked cinematic tokens in a single line of text.
    
    This is designed to be called from QSyntaxHighlighter.highlightBlock()
    which operates on one line at a time.
    
    Args:
        line: A single line of scene text.
        ignore_words: Set of words the user has chosen to ignore (instance-level).
    
    Returns:
        List of UnknownToken instances for words needing highlighting.
    """
    if not line or not line.strip():
        return []
    
    # Skip character name lines
    if _is_character_name_line(line):
        return []
    
    # Skip pure dialogue lines (entire line is a quote)
    stripped = line.strip()
    if stripped.startswith('"') and stripped.endswith('"'):
        return []
    
    ignore = ignore_words or set()
    masked = _get_masked_positions(line)
    action_inflections = _get_action_inflections()
    sfx_whitelist = get_merged_sfx_whitelist()
    
    tokens: List[UnknownToken] = []
    
    for m in _WORD_PATTERN.finditer(line):
        start, end = m.start(), m.end()
        word = m.group()
        word_lower = word.lower()
        
        # Skip if any part of the word is inside existing markup
        if any(i in masked for i in range(start, end)):
            continue
        
        # Skip ignored words
        if word_lower in ignore or word in ignore:
            continue
        
        # Check for unknown action
        if word_lower in action_inflections and word_lower not in ACTION_VERB_FORBIDDEN:
            # Context check: skip if preceded by article (likely a noun, not a verb)
            pre_text = line[:start].rstrip()
            if pre_text:
                prev_word = pre_text.split()[-1].lower().rstrip(".,;:!?") if pre_text.split() else ""
                if prev_word in _NOUN_SIGNALS:
                    continue
            tokens.append(UnknownToken(start, end - start, word, "unknown_action"))
            continue
        
        # Check for unknown SFX (underscore-separated words matching whitelist)
        if '_' in word_lower and word_lower in sfx_whitelist:
            tokens.append(UnknownToken(start, end - start, word, "unknown_sfx"))
            continue
    
    # Check for unknown identity tokens (consecutive Title-Case words)
    _detect_identity_tokens(line, masked, ignore, tokens)
    
    return tokens


def _detect_identity_tokens(line: str, masked: Set[int], ignore: Set[str],
                             tokens: List[UnknownToken]):
    """Detect potential character/entity names (consecutive Title Case words)."""
    # Match sequences of 2+ Title Case words (not inside markup)
    title_pattern = re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b')
    
    for m in title_pattern.finditer(line):
        start, end = m.start(), m.end()
        phrase = m.group()
        
        # Skip if any part is inside existing markup
        if any(i in masked for i in range(start, end)):
            continue
        
        # Skip if all words are common English title-case words
        words = phrase.split()
        if all(w in _COMMON_TITLE_CASE for w in words):
            continue
        
        # Skip if inside dialogue quotes
        # Simple check: count unmatched quotes before this position
        pre = line[:start]
        if pre.count('"') % 2 == 1:
            continue
        
        # Skip ignored
        if phrase in ignore or phrase.lower() in ignore:
            continue
        
        tokens.append(UnknownToken(start, end - start, phrase, "unknown_identity"))
