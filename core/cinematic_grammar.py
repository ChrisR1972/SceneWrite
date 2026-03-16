"""
Cinematic Grammar System for SceneWrite.

Unified validation pass that enforces:
- Action markup (*asterisks*) for all physical verbs
- SFX markup (parenthetical) for all sound events
- Intensity modifiers inside action markup
- Layered SFX (primary + ambient)
- No filler verbs
- No forbidden emotional verbs in markup
- No novel-style prose leakage

This module is the single entry point for the full cinematic grammar pipeline.
"""

import re
from typing import List, Tuple, Dict, Optional

from core.action_rules import (
    ACTION_VERB_WHITELIST,
    ACTION_VERB_FORBIDDEN,
    INTENSITY_MODIFIERS,
    get_effective_action_whitelist,
    enforce_action_grammar,
    fix_action_markup,
    rewrite_filler_verbs,
    normalize_intensity_modifiers,
    auto_wrap_action_verbs,
    get_action_rules_prompt_text,
    _FILLER_VERBS,
    _to_base_form,
)
from core.sfx_rules import (
    SFX_WHITELIST,
    SFX_FORBIDDEN,
    AMBIENT_SFX,
    get_effective_sfx_whitelist,
    enforce_sfx_grammar,
    expand_sfx_markup,
    fix_sfx_markup,
    validate_sfx_layers,
    is_sfx_valid,
    is_ambient_sfx,
    get_sfx_rules_prompt_text,
)


class CinematicGrammarReport:
    """Holds the results of a cinematic grammar validation pass."""
    
    def __init__(self):
        self.original_text: str = ""
        self.corrected_text: str = ""
        self.actions_wrapped: int = 0
        self.fillers_rewritten: int = 0
        self.sfx_expanded: int = 0
        self.sfx_fixed: int = 0
        self.modifiers_normalized: int = 0
        self.forbidden_stripped: int = 0
        self.sfx_warnings: List[str] = []
        self.violations: List[str] = []
        self.was_modified: bool = False
    
    def summary(self) -> str:
        parts = []
        if self.actions_wrapped:
            parts.append(f"{self.actions_wrapped} actions wrapped")
        if self.fillers_rewritten:
            parts.append(f"{self.fillers_rewritten} fillers rewritten")
        if self.sfx_expanded:
            parts.append(f"{self.sfx_expanded} SFX expanded")
        if self.sfx_fixed:
            parts.append(f"{self.sfx_fixed} SFX fixed")
        if self.modifiers_normalized:
            parts.append(f"{self.modifiers_normalized} modifiers normalized")
        if self.forbidden_stripped:
            parts.append(f"{self.forbidden_stripped} forbidden verbs stripped")
        if self.violations:
            parts.append(f"{len(self.violations)} violations")
        return "; ".join(parts) if parts else "No changes needed"


_ENV_MERGE_PREPS = re.compile(
    r'_\s*'                       # closing underscore of first env
    r'((?:of|at|in|inside|within|near|by|on|above|below|beneath|off|outside)\s+)'
    r'_',                         # opening underscore of second env
    re.IGNORECASE,
)


def merge_adjacent_environment_markup(text: str) -> str:
    """Merge adjacent _environment_ markup connected by prepositions.

    ``_Foyer_ of _Blackwood Manor_`` → ``_Foyer of Blackwood Manor_``

    This ensures compound location names produce a single environment entity
    rather than two separate ones.
    """
    if '_' not in text:
        return text
    # Replace  _A_ <prep> _B_  →  _A <prep> B_
    # The regex removes the inner closing/opening underscores, keeping the
    # outer ones intact so one continuous _..._ span results.
    return _ENV_MERGE_PREPS.sub(r' \1', text)


def _count_action_markup(text: str) -> int:
    """Count the number of *action* markup instances in text."""
    return len(re.findall(r'\*[^*]+\*', text))


def _count_sfx_markup(text: str) -> int:
    """Count the number of (sfx) markup instances in text."""
    return len(re.findall(r'\([^()]+\)', text))


def _count_filler_verbs(text: str) -> int:
    """Count filler verb occurrences in text."""
    count = 0
    text_lower = text.lower()
    for filler in _FILLER_VERBS:
        # Count occurrences followed by "to" (e.g. "begins to")
        count += len(re.findall(r'\b' + re.escape(filler) + r'\b', text_lower))
    return count


def _count_forbidden_in_markup(text: str) -> int:
    """Count forbidden verbs that are incorrectly inside *markup*."""
    count = 0
    for m in re.finditer(r'\*([^*]+)\*', text):
        inner = m.group(1).strip().lower()
        if inner in ACTION_VERB_FORBIDDEN:
            count += 1
    return count


def enforce_cinematic_grammar(text: str) -> Tuple[str, CinematicGrammarReport]:
    """
    Run the COMPLETE cinematic grammar pipeline on text.
    
    Pipeline order:
    1. Rewrite filler verbs (begins to walk → *walks*)
    2. Normalize intensity modifiers (slowly walks → *walks (slowly)*)
    3. Auto-wrap unmarked action verbs
    4. Validate existing *action* markup
    5. Expand prose sound descriptions to (sfx) markup
    6. Validate (sfx) markup
    7. Validate SFX layering rules
    8. Final cleanup
    
    Returns (corrected_text, report)
    """
    report = CinematicGrammarReport()
    report.original_text = text
    
    if not text or not text.strip():
        report.corrected_text = text
        return text, report
    
    # ── PHASE 0: ENVIRONMENT MARKUP MERGE ──
    # _Foyer_ of _Blackwood Manor_ → _Foyer of Blackwood Manor_
    result = merge_adjacent_environment_markup(text)
    
    # Measure before counts
    actions_before = _count_action_markup(result)
    sfx_before = _count_sfx_markup(result)
    fillers_before = _count_filler_verbs(result)
    forbidden_before = _count_forbidden_in_markup(result)
    
    # ── PHASE 1: SFX EXPANSION (run BEFORE action wrapping to avoid asterisk interference) ──
    result = expand_sfx_markup(result)
    
    # ── PHASE 2: ACTION GRAMMAR (filler rewrite → intensity modifiers → auto-wrap → validate) ──
    result = enforce_action_grammar(result)
    
    # ── PHASE 3: SFX VALIDATION (validate/fix any SFX tags, check layering) ──
    result = fix_sfx_markup(result)
    result, sfx_warnings = validate_sfx_layers(result)
    
    # ── PHASE 4: FINAL VALIDATION PASS ──
    violations = _final_validation(result)
    
    # ── PHASE 5: AUTO-CORRECT remaining violations ──
    if violations:
        result = _auto_correct_violations(result, violations)
        # Re-validate after corrections
        remaining = _final_validation(result)
        violations = remaining
    
    # ── PHASE 6: CLEANUP ──
    # Remove any double spaces created by corrections
    result = re.sub(r'  +', ' ', result)
    # Fix spacing around markup
    result = re.sub(r'\s+\.', '.', result)
    result = re.sub(r'\s+,', ',', result)
    # Fix lines that start/end with spaces
    result = '\n'.join(line.rstrip() for line in result.split('\n'))
    
    # Measure after counts
    actions_after = _count_action_markup(result)
    sfx_after = _count_sfx_markup(result)
    fillers_after = _count_filler_verbs(result)
    forbidden_after = _count_forbidden_in_markup(result)
    
    # Build report
    report.corrected_text = result
    report.actions_wrapped = max(0, actions_after - actions_before)
    report.fillers_rewritten = max(0, fillers_before - fillers_after)
    report.sfx_expanded = max(0, sfx_after - sfx_before)
    report.forbidden_stripped = max(0, forbidden_before - forbidden_after)
    report.sfx_warnings = sfx_warnings
    report.violations = violations
    report.was_modified = (result != text)
    
    return result, report


def _final_validation(text: str) -> List[str]:
    """
    Final validation pass — check for remaining violations.
    
    Checks:
    - Physical verbs not wrapped in *
    - Sound events not wrapped in ()
    - SFX not lowercase with underscores
    - Filler verbs remaining
    - Emotional verbs wrongly in *markup*
    - Sound words left unmarked
    """
    violations = []
    
    if not text or not text.strip():
        return violations
    
    # Check for remaining filler verbs
    for filler in _FILLER_VERBS:
        if re.search(r'\b' + re.escape(filler) + r'\s+(?:to\s+)?\w+', text, re.IGNORECASE):
            violations.append(f"FILLER_VERB: '{filler}' still present")
    
    # Check for forbidden verbs inside *markup*
    for m in re.finditer(r'\*([^*]+)\*', text):
        inner = m.group(1).strip().lower()
        # Strip intensity modifier if present
        mod_match = re.match(r'^(.+?)\s*\(\w+\)\s*$', inner)
        if mod_match:
            inner = mod_match.group(1).strip().lower()
        if inner in ACTION_VERB_FORBIDDEN:
            violations.append(f"FORBIDDEN_IN_MARKUP: '*{inner}*' is emotional/internal")
    
    # Check for SFX not in lowercase_underscore format
    for m in re.finditer(r'\(([^()]+)\)', text):
        inner = m.group(1).strip()
        if not inner:
            continue
        # Skip intensity modifiers
        if inner.lower() in INTENSITY_MODIFIERS:
            continue
        if inner != inner.lower() or ' ' in inner:
            if '_' not in inner.replace(' ', '_').lower():
                violations.append(f"SFX_FORMAT: '({inner})' not lowercase_underscore")
    
    # Check for forbidden SFX
    for m in re.finditer(r'\(([^()]+)\)', text):
        inner = m.group(1).strip().lower().replace(' ', '_')
        if inner in INTENSITY_MODIFIERS:
            continue
        if inner in SFX_FORBIDDEN:
            violations.append(f"FORBIDDEN_SFX: '({inner})' is abstract/emotional")
    
    return violations


def _auto_correct_violations(text: str, violations: List[str]) -> str:
    """Auto-correct detected violations."""
    result = text
    
    for v in violations:
        if v.startswith("FILLER_VERB:"):
            # Re-run filler rewrite
            result = rewrite_filler_verbs(result)
        elif v.startswith("FORBIDDEN_IN_MARKUP:"):
            # Strip markup from forbidden verbs
            result = fix_action_markup(result)
        elif v.startswith("SFX_FORMAT:"):
            # Re-run SFX fix
            result = fix_sfx_markup(result)
        elif v.startswith("FORBIDDEN_SFX:"):
            # Re-run SFX fix
            result = fix_sfx_markup(result)
    
    return result


def get_cinematic_grammar_prompt_text() -> str:
    """
    Return the complete cinematic grammar rules block for inclusion in AI prompts.
    Combines action rules + SFX rules + integration rules.
    """
    return f"""
========================================
CINEMATIC GRAMMAR SYSTEM (MANDATORY — SceneWrite)
========================================

{get_action_rules_prompt_text().strip()}

{get_sfx_rules_prompt_text().strip()}

INTEGRATION RULES:
- Every physical action MUST have *asterisk* markup. Every sound MUST have (sfx) markup.
- Filler verbs (begins, starts, continues, tries to) MUST be rewritten to direct action.
  "He begins to walk" → "He *walks*"
  "She starts turning the handle" → "She *turns* the handle"
- Intensity modifiers go INSIDE action markup: *walks (slowly)*, *slams (violently)*
  Only physical descriptors (slowly, quickly, forcefully, gently). NO emotional modifiers (sadly, angrily).
  "He slowly walks forward" → "He *walks (slowly)* forward"
- Forbidden internal verbs (feel, think, realize, decide, hope, fear, remember) are NEVER wrapped in *.
- Prose sound descriptions MUST be converted to (sfx) markup:
  "His boots crunch on broken glass" → "His [boots] *step* on broken glass (glass_crunch)"
- SFX must be lowercase_underscore: (glass_crunch), NOT (Glass Crunch) or (glass crunch).
- Max 1 primary SFX per action. Max 2 ambient SFX per paragraph.
- Ambient SFX use ambient_ prefix: (ambient_wind), (ambient_mill_creak).

COMPLETE EXAMPLE:
Original (incorrect):
MILO PENDERGAST adjusts the strap of his [headlamp] as he begins to step into the _Abandoned Mill_. His [boots] slowly crunch on broken glass and rotted wood. A cracked [tripod] stands in the corner, its [camera] dangling precariously.

Corrected:
MILO PENDERGAST *adjusts* the strap of his [headlamp] as he *steps* into the _Abandoned Mill_ (ambient_mill_creak). His [boots] *step (slowly)* on broken glass and rotted wood (glass_crunch). A cracked [tripod] *stands* in the corner, its [camera] *dangles* precariously.
"""
