"""
Sentence Integrity Validator for MoviePrompterAI.

Detects and repairs incomplete/broken sentences caused by AI word-dropping artifacts.

Common patterns:
- Missing verbs: "The beam before steadying." (missing flickers/stutters)
- Missing subjects: "It erratically." (missing verb between subject and adverb)
- Missing objects: "falls off with a." (missing noun after article)
- Truncated phrases: "The Ecto-Detector to life" (missing "springs/comes")
- Dangling articles: "The only sound is the of water" (missing noun)
- Orphaned adverbs: "seem to faintly in the dim light" (missing verb after "to")

This module provides:
1. Heuristic detection of broken sentences
2. AI-powered repair of detected issues
3. A validation pass for the post-generation pipeline
"""

import re
from typing import List, Tuple, Optional, Dict


class SentenceIssue:
    """Represents a detected sentence integrity issue."""
    
    def __init__(self, sentence: str, issue_type: str, description: str,
                 paragraph_idx: int = -1, sentence_idx: int = -1):
        self.sentence = sentence
        self.issue_type = issue_type
        self.description = description
        self.paragraph_idx = paragraph_idx
        self.sentence_idx = sentence_idx
    
    def __repr__(self):
        return f"SentenceIssue({self.issue_type}: {self.description!r})"


# ── DETECTION PATTERNS ────────────────────────────────────────────────────

# Pattern: article/possessive followed by a preposition or period (missing noun)
# "the of water", "a.", "his from the"
_DANGLING_ARTICLE = re.compile(
    r'\b(the|a|an|his|her|its|their|my|your|our)\s+'
    r'(of|from|in|on|at|to|with|by|into|through|across|around|about|over|under)\b',
    re.IGNORECASE
)

# Pattern: pronoun + adverb/preposition with no verb between
# "It erratically.", "It faster", "It with feedback"
_SUBJECT_NO_VERB = re.compile(
    r'\b(It|He|She|They|We)\s+'
    r'(erratically|faster|slower|quickly|slowly|suddenly|with|without|before|after|'
    r'to|from|in|on|at|near|into|through|across|around)\b',
    re.IGNORECASE
)

# Pattern: possessive noun + verb (missing the noun being possessed)
# "The Ecto-Detector's intensifies" (missing "beeping" or "signal")
_POSSESSIVE_NO_NOUN = re.compile(
    r"\b(\w+(?:'s|s'))\s+(intensifies|grows|fades|increases|decreases|"
    r"changes|shifts|rises|falls|drops|stops|starts|begins|continues|"
    r"flickers|pulses|glows|dims|brightens|weakens|strengthens)\b",
    re.IGNORECASE
)

# Pattern: "begins to" / "starts to" / "seem to" + non-verb (adverb, preposition, etc.)
# "seem to faintly in", "begins to on its own"
_INFINITIVE_NO_VERB = re.compile(
    r'\b(begins?|starts?|seems?|tries?|attempts?|continues?|manages?)\s+to\s+'
    r'(faintly|slowly|quickly|quietly|loudly|softly|gently|suddenly|gradually|'
    r'on|in|at|from|with|through|across|around|over|under)\b',
    re.IGNORECASE
)

# Pattern: noun/subject + "to life" / "to a halt" without a verb
# "The Ecto-Detector to life" (missing "springs/comes")
_MISSING_MOTION_VERB = re.compile(
    r'\b(The\s+\w[\w\s-]*?)\s+(to life|to a halt|to a stop|to rest|to pieces|'
    r'to the ground|to the floor|in a shower|in a burst|in a flash|into view|'
    r'into focus|into action|into place|apart|open|shut)\b',
    re.IGNORECASE
)

# Pattern: verb + "with a" at end of sentence (missing noun)
# "falls off with a." / "crashes with a."
_TRAILING_ARTICLE = re.compile(
    r'\b(with|like|as|into|from|of|for|about)\s+(a|an|the)\s*[.!?]',
    re.IGNORECASE
)

# Pattern: "The" + noun + "and" + verb (missing verb for first clause)
# "The headlamp and dies" (missing "flickers" or "stutters")
_COMPOUND_MISSING_VERB = re.compile(
    r'\bThe\s+(\w[\w\s]*?)\s+and\s+(dies?|stops?|falls?|breaks?|fades?|'
    r'goes|comes|drops|cracks|snaps|pops|bursts|shatters|collapses)\b',
    re.IGNORECASE
)

# Pattern: "A" + adjective + verb (missing noun)
# "A soft echoes" → "A soft [sound] echoes"
# Also handles action markup: "A sudden *echoes*" → "A sudden (sound) *echoes*"
_ADJECTIVE_AS_NOUN = re.compile(
    r'\bAn?\s+(soft|loud|faint|bright|dim|sharp|low|high|deep|quiet|gentle|'
    r'sudden|distant|muffled|harsh|warm|cold|strange|eerie|familiar|'
    r'ominous|heavy|light|hollow|metallic|wet|dry|dull|piercing)\s+'
    r'\*?'  # optional opening asterisk from action markup
    r'(echoes?|sounds?|rings?|fills?|spreads?|washes?|hits?|reaches?|'
    r'grows?|fades?|rises?|falls?|breaks?|crashes?|rumbles?|hums?|'
    r'booms?|cracks?|creaks?|thuds?|clangs?|rattles?|whines?|buzzes?|'
    r'clicks?|snaps?|pops?|bangs?|thumps?|whistles?|groans?|shrieks?)'
    r'\*?',  # optional closing asterisk from action markup
    re.IGNORECASE
)

# Pattern: "The/A NOUN before/after/without VERB-ing" (missing verb between subject and preposition)
# "The beam before steadying" (missing "flickers/stutters")
_NOUN_PREP_GERUND = re.compile(
    r'\b(The|A|An|His|Her|Its|Their)\s+(\w+)\s+'
    r'(before|after|without|while|until|despite)\s+(\w+ing)\b',
    re.IGNORECASE
)

# Pattern: sentence that's too short (less than 3 words) and not dialogue or character name
_TOO_SHORT = re.compile(r'^[A-Z][\w\s]{0,8}[.!?]$')


def detect_sentence_issues(text: str) -> List[SentenceIssue]:
    """
    Scan text for incomplete/broken sentences.
    
    Returns a list of SentenceIssue objects describing each detected problem.
    """
    if not text or not text.strip():
        return []
    
    issues = []
    paragraphs = text.split('\n\n')
    
    for p_idx, paragraph in enumerate(paragraphs):
        lines = paragraph.split('\n')
        
        for l_idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            
            # Skip dialogue lines (inside quotes)
            if stripped.startswith('"') and stripped.endswith('"'):
                continue
            
            # Skip character name lines (all caps, standalone)
            if stripped == stripped.upper() and len(stripped.split()) <= 4 and not any(c in stripped for c in '.*()[]{}'):
                continue
            
            # Split into sentences for more precise detection
            sentences = re.split(r'(?<=[.!?])\s+', stripped)
            
            for s_idx, sentence in enumerate(sentences):
                sent_stripped = sentence.strip()
                if not sent_stripped or len(sent_stripped) < 3:
                    continue
                
                # Check each pattern
                _check_dangling_article(sent_stripped, p_idx, s_idx, issues)
                _check_subject_no_verb(sent_stripped, p_idx, s_idx, issues)
                _check_possessive_no_noun(sent_stripped, p_idx, s_idx, issues)
                _check_infinitive_no_verb(sent_stripped, p_idx, s_idx, issues)
                _check_missing_motion_verb(sent_stripped, p_idx, s_idx, issues)
                _check_trailing_article(sent_stripped, p_idx, s_idx, issues)
                _check_compound_missing_verb(sent_stripped, p_idx, s_idx, issues)
                _check_adjective_as_noun(sent_stripped, p_idx, s_idx, issues)
                _check_noun_prep_gerund(sent_stripped, p_idx, s_idx, issues)
    
    return issues


def _check_dangling_article(sentence: str, p_idx: int, s_idx: int,
                             issues: List[SentenceIssue]):
    """Detect dangling articles: 'the of water', 'a.', 'his from'."""
    for m in _DANGLING_ARTICLE.finditer(sentence):
        article = m.group(1)
        prep = m.group(2)
        # Exclude false positives
        before = sentence[:m.start()].strip()
        if before.endswith(('because', 'instead', 'part', 'most', 'all', 'some', 'none')):
            continue
        # Exclude if there's SFX markup or other content between article and preposition
        between_text = sentence[m.start() + len(article):m.start() + len(article) + len(prep) + 5]
        if '(' in between_text or '*' in between_text or '[' in between_text:
            continue
        # Exclude "the only" — "only" is an adjective, not a preposition target
        after_article = sentence[m.start() + len(article):].strip()
        if after_article.lower().startswith('only'):
            continue
        # Verify the article + preposition are truly adjacent (no noun between)
        gap = sentence[m.start() + len(article):m.start() + len(m.group(0))].strip()
        if gap and gap != prep:
            continue
        issues.append(SentenceIssue(
            sentence=sentence,
            issue_type="DANGLING_ARTICLE",
            description=f"Missing noun after '{article}' — found '{article} {prep}'",
            paragraph_idx=p_idx,
            sentence_idx=s_idx
        ))


def _check_subject_no_verb(sentence: str, p_idx: int, s_idx: int,
                            issues: List[SentenceIssue]):
    """Detect subject followed directly by adverb/preposition: 'It erratically.'"""
    for m in _SUBJECT_NO_VERB.finditer(sentence):
        # Only flag if there's no verb between subject and the matched word
        between = sentence[m.start():m.end()]
        # Check for any existing *verb* markup between
        if '*' in between:
            continue
        issues.append(SentenceIssue(
            sentence=sentence,
            issue_type="SUBJECT_NO_VERB",
            description=f"'{m.group(1)}' has no verb before '{m.group(2)}'",
            paragraph_idx=p_idx,
            sentence_idx=s_idx
        ))


def _check_possessive_no_noun(sentence: str, p_idx: int, s_idx: int,
                               issues: List[SentenceIssue]):
    """Detect possessive + verb with missing noun: 'Detector's intensifies'."""
    for m in _POSSESSIVE_NO_NOUN.finditer(sentence):
        issues.append(SentenceIssue(
            sentence=sentence,
            issue_type="POSSESSIVE_NO_NOUN",
            description=f"Missing noun between '{m.group(1)}' and '{m.group(2)}'",
            paragraph_idx=p_idx,
            sentence_idx=s_idx
        ))


def _check_infinitive_no_verb(sentence: str, p_idx: int, s_idx: int,
                               issues: List[SentenceIssue]):
    """Detect 'begins/seems to' + non-verb: 'seem to faintly in'."""
    for m in _INFINITIVE_NO_VERB.finditer(sentence):
        issues.append(SentenceIssue(
            sentence=sentence,
            issue_type="INFINITIVE_NO_VERB",
            description=f"Missing verb after '{m.group(1)} to' — found '{m.group(2)}' instead",
            paragraph_idx=p_idx,
            sentence_idx=s_idx
        ))


def _check_missing_motion_verb(sentence: str, p_idx: int, s_idx: int,
                                issues: List[SentenceIssue]):
    """Detect missing motion verb: 'The Ecto-Detector to life'."""
    for m in _MISSING_MOTION_VERB.finditer(sentence):
        subject = m.group(1).strip()
        # Verify there's no verb between subject and the phrase
        # Check if the word right before the matched phrase is a verb (if so, skip)
        pre_match = sentence[:m.start() + len(m.group(1))].strip()
        last_word = pre_match.split()[-1] if pre_match.split() else ""
        # If last word looks like a verb (ends in s/ed/ing), skip
        if last_word and any(last_word.lower().endswith(s) for s in ['es', 'ed', 'ing', 'ts']):
            continue
        # Also skip if there's a *verb* markup
        between = sentence[m.start():m.end()]
        if '*' in between:
            continue
        issues.append(SentenceIssue(
            sentence=sentence,
            issue_type="MISSING_MOTION_VERB",
            description=f"'{subject}' missing verb before '{m.group(2)}'",
            paragraph_idx=p_idx,
            sentence_idx=s_idx
        ))


def _check_trailing_article(sentence: str, p_idx: int, s_idx: int,
                             issues: List[SentenceIssue]):
    """Detect trailing article at end of sentence: 'with a.'"""
    for m in _TRAILING_ARTICLE.finditer(sentence):
        issues.append(SentenceIssue(
            sentence=sentence,
            issue_type="TRAILING_ARTICLE",
            description=f"Sentence ends with '{m.group(1)} {m.group(2)}' — missing noun",
            paragraph_idx=p_idx,
            sentence_idx=s_idx
        ))


def _check_compound_missing_verb(sentence: str, p_idx: int, s_idx: int,
                                  issues: List[SentenceIssue]):
    """Detect compound with missing first verb: 'The headlamp and dies.'"""
    for m in _COMPOUND_MISSING_VERB.finditer(sentence):
        subject = m.group(1).strip()
        # Check the subject doesn't already contain a verb
        words = subject.split()
        if len(words) > 3:
            continue  # Too complex, might be a false positive
        # Verify no *verb* between "The X" and "and"
        between = sentence[m.start():m.end()]
        if '*' in between:
            continue
        issues.append(SentenceIssue(
            sentence=sentence,
            issue_type="COMPOUND_MISSING_VERB",
            description=f"'The {subject} and {m.group(2)}' — missing first verb",
            paragraph_idx=p_idx,
            sentence_idx=s_idx
        ))


def _check_adjective_as_noun(sentence: str, p_idx: int, s_idx: int,
                              issues: List[SentenceIssue]):
    """Detect adjective used as noun: 'A soft echoes through', 'A sudden *echoes*'."""
    for m in _ADJECTIVE_AS_NOUN.finditer(sentence):
        adj = m.group(1)
        verb = m.group(2)
        # Suggest context-appropriate nouns based on the verb
        sound_verbs = {'echoes', 'echo', 'sounds', 'sound', 'rings', 'ring',
                       'rumbles', 'rumble', 'hums', 'hum', 'booms', 'boom',
                       'cracks', 'crack', 'creaks', 'creak', 'thuds', 'thud',
                       'clangs', 'clang', 'rattles', 'rattle', 'whines', 'whine',
                       'buzzes', 'buzz', 'clicks', 'click', 'snaps', 'snap',
                       'pops', 'pop', 'bangs', 'bang', 'thumps', 'thump',
                       'whistles', 'whistle', 'groans', 'groan', 'shrieks', 'shriek'}
        light_verbs = {'glows', 'glow', 'fills', 'fill', 'spreads', 'spread',
                       'washes', 'wash', 'flashes', 'flash', 'flickers', 'flicker'}
        if verb.lower() in sound_verbs:
            noun_hint = "sound, creak, thud, crash, noise"
        elif verb.lower() in light_verbs:
            noun_hint = "light, glow, beam, flash"
        else:
            noun_hint = "sound, glow, light, force"
        issues.append(SentenceIssue(
            sentence=sentence,
            issue_type="ADJECTIVE_AS_NOUN",
            description=f"'A {adj} *{verb}*' — adjective used as noun, missing noun between '{adj}' and '{verb}' (e.g. {noun_hint})",
            paragraph_idx=p_idx,
            sentence_idx=s_idx
        ))


def _check_noun_prep_gerund(sentence: str, p_idx: int, s_idx: int,
                             issues: List[SentenceIssue]):
    """Detect missing verb: 'The beam before steadying' (noun + preposition + gerund with no verb)."""
    for m in _NOUN_PREP_GERUND.finditer(sentence):
        subject_noun = m.group(2).strip()
        prep = m.group(3).strip()
        gerund = m.group(4).strip()
        # Check there's no *verb* between the subject and the preposition
        between = sentence[m.start():m.end()]
        if '*' in between:
            continue
        # Verify the noun isn't a verb itself (e.g. "The running before stopping")
        if subject_noun.lower().endswith('ing'):
            continue
        issues.append(SentenceIssue(
            sentence=sentence,
            issue_type="NOUN_PREP_GERUND",
            description=f"'{m.group(1)} {subject_noun}' missing verb before '{prep} {gerund}'",
            paragraph_idx=p_idx,
            sentence_idx=s_idx
        ))


# ── AI-POWERED REPAIR ────────────────────────────────────────────────────

def build_repair_prompt(content: str, issues: List[SentenceIssue]) -> str:
    """
    Build an AI prompt to repair detected sentence issues.
    
    The prompt instructs the AI to fix ONLY the broken sentences,
    preserving all existing markup, dialogue, and structure.
    """
    issue_descriptions = []
    for i, issue in enumerate(issues, 1):
        issue_descriptions.append(
            f"{i}. [{issue.issue_type}] \"{issue.sentence}\"\n"
            f"   Problem: {issue.description}"
        )
    
    issues_block = "\n".join(issue_descriptions)
    
    prompt = f"""You are a screenplay content repair tool. The following scene content has broken/incomplete sentences caused by word-dropping during AI generation.

DETECTED ISSUES:
{issues_block}

FULL SCENE CONTENT:
{content}

REPAIR RULES (STRICT):
1. Fix ONLY the sentences listed above. Do NOT modify any other text.
2. Add the MINIMUM number of words needed to make each sentence grammatically complete and cinematically coherent.
3. Preserve ALL existing markup exactly as-is:
   - *action* markup (asterisks around verbs)
   - (sfx) markup (sound effects in parentheses)
   - [object] markup (brackets around objects)
   - _location_ markup (underscores around locations)
   - {{vehicle}} markup (braces around vehicles)
   - "dialogue" (quoted text)
   - CHARACTER NAMES in FULL CAPS
4. When adding missing verbs, use the cinematic grammar style: wrap in *asterisks*.
5. When adding missing nouns, determine from context what makes sense.
6. When adding missing sound effects, use (lowercase_underscore) SFX format.
7. Keep the screenplay tone: short, direct, visual, concrete.
8. Do NOT add new sentences, paragraphs, or change the story.
9. Do NOT rewrite sentences that are already complete.
10. The repaired content must have EXACTLY the same structure (paragraphs, line breaks, dialogue placement).

Return ONLY the full corrected scene content. No explanations, no labels, no markdown formatting."""

    return prompt


def format_issues_summary(issues: List[SentenceIssue]) -> str:
    """Format issues into a human-readable summary string."""
    if not issues:
        return "No sentence integrity issues detected."
    
    lines = [f"Found {len(issues)} sentence integrity issue(s):"]
    for i, issue in enumerate(issues, 1):
        lines.append(f"  {i}. [{issue.issue_type}] {issue.description}")
        # Truncate long sentences for display
        sent_display = issue.sentence[:80] + "..." if len(issue.sentence) > 80 else issue.sentence
        lines.append(f"     In: \"{sent_display}\"")
    return "\n".join(lines)
