"""
Action Rules for SceneWrite / screenplay action markup.
Enforces strict Action Verb Whitelist for *asterisk* action markup.

CINEMATIC GRAMMAR SYSTEM:
- All visible physical movement MUST be wrapped in *asterisks*.
- Filler verbs (begins, starts, continues, tries to) are rewritten to direct action.
- Intensity modifiers are supported inside markup: *walks (slowly)*
- Forbidden emotional/internal verbs are NEVER wrapped.
"""

import re
from typing import Set, Optional, List, Tuple

# 1. CHARACTER ACTIONS (Physical, Visible)
CHARACTER_ACTIONS = frozenset({
    "walk", "run", "enter", "exit", "sit", "stand", "lean", "turn", "look", "reach",
    "grab", "hold", "release", "open", "close", "push", "pull", "pick up", "drop",
    "throw", "kneel", "rise", "step", "approach", "retreat", "brace", "gesture",
    "nod", "shake head", "aim", "fire", "strike", "fall", "collide", "crawl", "climb",
    "jump", "duck", "roll", "adjust", "wipe", "flip", "spin", "twist", "lift",
    "lower", "set down", "hand", "slide", "toss", "catch", "mount", "dismount",
    "crouch", "dodge", "lunge", "swing", "kick", "punch", "block", "parry",
    "draw", "sheathe", "load", "unload", "point", "wave", "beckon", "salute",
    "bow", "squeeze", "press", "tap", "knock", "slam", "yank", "tug",
    "peel", "unwrap", "wrap", "fold", "unfold", "strap", "unstrap",
    "stagger", "stumble", "limp", "sprint", "dash", "march", "creep",
    "sneak", "tiptoe", "pace", "wander", "halt", "freeze", "flinch",
    "jolt", "recoil", "sway", "wobble", "stretch", "shrug",
    "dangle", "drape", "prop", "perch", "balance", "hoist",
    "flick", "smack", "tuck", "poke", "burst", "zip", "bump",
    "swarm", "scatter", "squint", "give", "set down", "put down",
    "yell", "whisper", "glance", "peer", "stare", "gaze",
    "scratch", "rub", "stroke", "pat", "clutch", "grip",
    "stumble", "trip", "fumble", "grope", "lurch", "swallow",
    # Movement / locomotion
    "move", "fly", "soar", "swoop", "dive", "gallop", "trot", "canter", "ride",
    "swim", "wade", "float", "paddle", "row", "trudge", "plod", "bolt", "flee",
    "charge", "storm", "stride", "shuffle", "skid", "vault", "hurdle", "leap",
    # Whole-body expressive
    "dance", "waltz", "twirl", "pirouette", "curtsy", "kneel down", "rear",
    "heave", "raise", "writhe", "convulse", "thrash", "tremble", "shiver", "shudder",
    "cower", "cringe", "brace", "slump", "sag", "collapse",
    # Hand / arm interaction
    "pull out", "clamp", "grasp", "snatch", "wrench", "pry", "pluck",
    "pinch", "slap", "claw", "hammer", "chisel", "carve", "whittle",
    "dig", "shovel", "scoop", "pour", "stir", "mix", "chop", "slice", "saw",
    "type", "write", "scribble", "sketch", "paint",
    # Carrying / transferring
    "drag", "haul", "carry", "lug", "heave", "sling", "hurl", "shove",
    # Social / intimate
    "embrace", "hug", "caress", "kiss", "cradle", "rock",
    # Eating / drinking
    "sip", "drink", "gulp", "eat", "chew", "bite", "nibble", "devour",
    # Observation / subtle
    "scan", "inspect", "examine", "study", "survey", "peek", "spy",
    "wink", "blink", "narrow eyes", "cock head",
})

# 2. OBJECT ACTIONS (State Change or Interaction Result)
OBJECT_ACTIONS = frozenset({
    "open", "close", "lock", "unlock", "activate", "deactivate", "power on", "power off",
    "light up", "dim", "spark", "crack", "break", "shatter", "slide", "fall", "topple",
    "spill", "detach", "attach", "vibrate", "collapse", "snap", "split", "crumble",
    "unfurl", "retract", "extend", "rotate", "swing open", "swing shut",
    "glow", "pulse", "flash", "flare", "fade", "blink",
    "rattle", "clatter", "clang", "clank", "ring", "chime", "wobble", "teeter",
    "buckle", "warp", "melt", "dissolve", "freeze", "shudder", "hum", "whir",
    "ignite", "extinguish", "overflow", "drain", "fill", "empty",
})

# 3. VEHICLE ACTIONS (Motion, Control, Status)
VEHICLE_ACTIONS = frozenset({
    "start", "stop", "accelerate", "decelerate", "launch", "land", "dock", "undock",
    "ascend", "descend", "hover", "drift", "bank", "turn", "roll", "engage", "disengage",
    "power up", "power down", "tremble", "shake", "lurch", "stall", "glide", "cruise",
    "impact", "explode", "skid", "swerve", "brake", "reverse", "park",
    "sputter", "rumble", "rattle", "buck", "fishtail", "careen", "veer",
    "submerge", "surface", "capsize", "list", "pitch", "yaw",
})

# 4. ENVIRONMENTAL ACTIONS (Set / World Events)
ENVIRONMENTAL_ACTIONS = frozenset({
    "rumble", "collapse", "flood", "ignite", "burn", "smolder", "darken", "brighten",
    "flicker", "fill with smoke", "clear", "shake", "echo", "seal", "open", "close",
    "lock down", "power failure", "alarm sounds", "settle", "shift", "crumble",
    "crack", "groan", "sway", "bloom", "wilt", "erode", "freeze over",
    "rattle", "quake", "erupt", "subside", "recede", "surge", "churn",
    "howl", "gust", "billow", "cascade", "seep", "ooze", "drip",
    "thunder", "lightning strike", "cave in", "give way",
})

# 5. CAMERA / VISUAL ACTIONS (Optional)
CAMERA_ACTIONS = frozenset({
    "pan", "tilt", "zoom", "pull back", "push in", "cut", "fade in", "fade out",
    "hold", "shake", "track", "reveal", "whip pan",
})

# Combined whitelist (all approved built-in verbs)
ACTION_VERB_WHITELIST: Set[str] = (
    CHARACTER_ACTIONS | OBJECT_ACTIONS | VEHICLE_ACTIONS | ENVIRONMENTAL_ACTIONS | CAMERA_ACTIONS
)

# User-added verbs (populated at runtime from config/ActionWhitelist.json)
_user_action_whitelist: Set[str] = set()


def set_user_action_whitelist(verbs: Set[str]):
    """Set the user-added action whitelist (called by markup_whitelist at runtime)."""
    global _user_action_whitelist
    _user_action_whitelist = set(verbs)


def get_effective_action_whitelist() -> Set[str]:
    """Return built-in + user-added action verbs."""
    return ACTION_VERB_WHITELIST | _user_action_whitelist


# Forbidden — NEVER in action markup (internal/emotional/abstract)
ACTION_VERB_FORBIDDEN = frozenset({
    "feel", "think", "realize", "decide", "hope", "fear", "remember", "regret",
    "sense", "consider", "believe", "wonder", "hesitate", "feeling", "thinking",
    "realizing", "deciding", "hoping", "fearing", "remembering", "regretting",
    "sensing", "considering", "believing", "wondering", "hesitating",
    "know", "knowing", "understand", "understanding", "imagine", "imagining",
    "wish", "wishing", "suspect", "suspecting", "assume", "assuming",
    "ponder", "pondering", "reflect", "reflecting", "contemplate", "contemplating",
})

# Stative / descriptive — verbs that can describe a setting's spatial or
# ambient state rather than a physical action.  These receive action markup
# ONLY when the subject is clearly a character, object, or vehicle — NOT
# when they describe an environment or unrecognized scene element.
_STATIVE_CAPABLE_VERBS = frozenset({
    # Spatial / structural — how spaces or structures are arranged
    "stretch", "extend", "span", "sprawl", "spread",
    "wind", "curve", "spiral", "arch", "slope",
    # Vertical presence — height or dominance of structures
    "rise", "tower", "loom", "soar",
    # Hanging / suspended positioning
    "dangle", "drape", "hang", "sag",
    # Resting / situated positioning
    "perch", "rest", "nestle", "settle", "sit",
    # Angled positioning
    "lean", "tilt", "slant",
    # Layout around a space
    "line", "border", "frame", "flank", "surround",
    "jut", "protrude", "overhang",
    # Atmospheric / ambient presence
    "hover", "drift", "float", "sway",
    "glow", "flicker", "pulse", "shimmer", "fade",
    "burn", "smolder", "bloom", "crumble",
    # Visual prominence
    "dominate", "overlook", "overshadow",
    "blanket", "shroud", "cloak", "veil",
})

# Filler verbs that must be stripped (rewrite to clean cinematic verb)
_FILLER_VERBS = frozenset({
    "begins", "begin", "began", "beginning",
    "starts", "start", "started", "starting",
    "continues", "continue", "continued", "continuing",
    "tries", "try", "tried", "trying",
    "attempts", "attempt", "attempted", "attempting",
    "proceeds", "proceed", "proceeded", "proceeding",
    "manages", "manage", "managed", "managing",
})

# Approved physical intensity modifiers (visible or audible)
INTENSITY_MODIFIERS = frozenset({
    "slowly", "quickly", "rapidly", "gently", "forcefully", "violently",
    "cautiously", "carefully", "deliberately", "sharply", "abruptly",
    "heavily", "lightly", "firmly", "softly", "loudly", "silently",
    "steadily", "unsteadily", "frantically", "wildly", "calmly",
    "briskly", "sluggishly", "gracefully", "clumsily", "stiffly",
    "weakly", "powerfully", "vigorously", "lazily", "urgently",
    "reluctantly", "eagerly", "boldly", "timidly", "smoothly",
})

# Forbidden intensity modifiers (emotional, not physical)
_FORBIDDEN_MODIFIERS = frozenset({
    "sadly", "happily", "angrily", "fearfully", "nervously", "anxiously",
    "joyfully", "miserably", "hopefully", "desperately", "lovingly",
    "hatefully", "bitterly", "longingly", "wistfully",
})

# Common inflections → base form (for matching)
_INFLECTION_TO_BASE = {
    "walks": "walk", "walked": "walk", "walking": "walk",
    "runs": "run", "ran": "run", "running": "run",
    "enters": "enter", "entered": "enter", "entering": "enter",
    "exits": "exit", "exited": "exit", "exiting": "exit",
    "sits": "sit", "sat": "sit", "sitting": "sit",
    "stands": "stand", "stood": "stand", "standing": "stand",
    "leans": "lean", "leaned": "lean", "leaning": "lean",
    "turns": "turn", "turned": "turn", "turning": "turn",
    "looks": "look", "looked": "look", "looking": "look",
    "reaches": "reach", "reached": "reach", "reaching": "reach",
    "grabs": "grab", "grabbed": "grab", "grabbing": "grab",
    "holds": "hold", "held": "hold", "holding": "hold",
    "releases": "release", "released": "release", "releasing": "release",
    "opens": "open", "opened": "open", "opening": "open",
    "closes": "close", "closed": "close", "closing": "close",
    "pushes": "push", "pushed": "push", "pushing": "push",
    "pulls": "pull", "pulled": "pull", "pulling": "pull",
    "picks up": "pick up", "picked up": "pick up", "picking up": "pick up",
    "drops": "drop", "dropped": "drop", "dropping": "drop",
    "throws": "throw", "threw": "throw", "throwing": "throw",
    "kneels": "kneel", "knelt": "kneel", "kneeling": "kneel",
    "rises": "rise", "rose": "rise", "rising": "rise",
    "steps": "step", "stepped": "step", "stepping": "step",
    "approaches": "approach", "approached": "approach", "approaching": "approach",
    "retreats": "retreat", "retreated": "retreat", "retreating": "retreat",
    "braces": "brace", "braced": "brace", "bracing": "brace",
    "gestures": "gesture", "gestured": "gesture", "gesturing": "gesture",
    "nods": "nod", "nodded": "nod", "nodding": "nod",
    "aims": "aim", "aimed": "aim", "aiming": "aim",
    "fires": "fire", "fired": "fire", "firing": "fire",
    "strikes": "strike", "struck": "strike", "striking": "strike",
    "falls": "fall", "fell": "fall", "falling": "fall",
    "collides": "collide", "collided": "collide", "colliding": "collide",
    "crawls": "crawl", "crawled": "crawl", "crawling": "crawl",
    "climbs": "climb", "climbed": "climb", "climbing": "climb",
    "jumps": "jump", "jumped": "jump", "jumping": "jump",
    "ducks": "duck", "ducked": "duck", "ducking": "duck",
    "rolls": "roll", "rolled": "roll", "rolling": "roll",
    "trembles": "tremble", "trembled": "tremble", "trembling": "tremble",
    "shakes": "shake", "shook": "shake", "shaking": "shake",
    "flickers": "flicker", "flickered": "flicker", "flickering": "flicker",
    "brightens": "brighten", "brightened": "brighten", "brightening": "brighten",
    "darkens": "darken", "darkened": "darken", "darkening": "darken",
    "shakes head": "shake head", "shaking head": "shake head", "shook head": "shake head",
    "pulls back": "pull back", "pulling back": "pull back", "pulled back": "pull back",
    "pushes in": "push in", "pushing in": "push in", "pushed in": "push in",
    "fades in": "fade in", "fading in": "fade in", "faded in": "fade in",
    "fades out": "fade out", "fading out": "fade out", "faded out": "fade out",
    "adjusts": "adjust", "adjusted": "adjust", "adjusting": "adjust",
    "wipes": "wipe", "wiped": "wipe", "wiping": "wipe",
    "flips": "flip", "flipped": "flip", "flipping": "flip",
    "spins": "spin", "spun": "spin", "spinning": "spin",
    "twists": "twist", "twisted": "twist", "twisting": "twist",
    "lifts": "lift", "lifted": "lift", "lifting": "lift",
    "lowers": "lower", "lowered": "lower", "lowering": "lower",
    "slides": "slide", "slid": "slide", "sliding": "slide",
    "tosses": "toss", "tossed": "toss", "tossing": "toss",
    "catches": "catch", "caught": "catch", "catching": "catch",
    "crouches": "crouch", "crouched": "crouch", "crouching": "crouch",
    "dodges": "dodge", "dodged": "dodge", "dodging": "dodge",
    "lunges": "lunge", "lunged": "lunge", "lunging": "lunge",
    "swings": "swing", "swung": "swing", "swinging": "swing",
    "kicks": "kick", "kicked": "kick", "kicking": "kick",
    "punches": "punch", "punched": "punch", "punching": "punch",
    "blocks": "block", "blocked": "block", "blocking": "block",
    "draws": "draw", "drew": "draw", "drawing": "draw",
    "points": "point", "pointed": "point", "pointing": "point",
    "waves": "wave", "waved": "wave", "waving": "wave",
    "squeezes": "squeeze", "squeezed": "squeeze", "squeezing": "squeeze",
    "presses": "press", "pressed": "press", "pressing": "press",
    "taps": "tap", "tapped": "tap", "tapping": "tap",
    "knocks": "knock", "knocked": "knock", "knocking": "knock",
    "slams": "slam", "slammed": "slam", "slamming": "slam",
    "yanks": "yank", "yanked": "yank", "yanking": "yank",
    "tugs": "tug", "tugged": "tug", "tugging": "tug",
    "staggers": "stagger", "staggered": "stagger", "staggering": "stagger",
    "stumbles": "stumble", "stumbled": "stumble", "stumbling": "stumble",
    "limps": "limp", "limped": "limp", "limping": "limp",
    "sprints": "sprint", "sprinted": "sprint", "sprinting": "sprint",
    "dashes": "dash", "dashed": "dash", "dashing": "dash",
    "marches": "march", "marched": "march", "marching": "march",
    "creeps": "creep", "crept": "creep", "creeping": "creep",
    "sneaks": "sneak", "sneaked": "sneak", "sneaking": "sneak",
    "tiptoes": "tiptoe", "tiptoed": "tiptoe", "tiptoeing": "tiptoe",
    "paces": "pace", "paced": "pace", "pacing": "pace",
    "halts": "halt", "halted": "halt", "halting": "halt",
    "freezes": "freeze", "froze": "freeze", "freezing": "freeze",
    "flinches": "flinch", "flinched": "flinch", "flinching": "flinch",
    "jolts": "jolt", "jolted": "jolt", "jolting": "jolt",
    "recoils": "recoil", "recoiled": "recoil", "recoiling": "recoil",
    "sways": "sway", "swayed": "sway", "swaying": "sway",
    "wobbles": "wobble", "wobbled": "wobble", "wobbling": "wobble",
    "stretches": "stretch", "stretched": "stretch", "stretching": "stretch",
    "shrugs": "shrug", "shrugged": "shrug", "shrugging": "shrug",
    "dangles": "dangle", "dangled": "dangle", "dangling": "dangle",
    "drapes": "drape", "draped": "drape", "draping": "drape",
    "props": "prop", "propped": "prop", "propping": "prop",
    "perches": "perch", "perched": "perch", "perching": "perch",
    "balances": "balance", "balanced": "balance", "balancing": "balance",
    "hoists": "hoist", "hoisted": "hoist", "hoisting": "hoist",
    "glows": "glow", "glowed": "glow", "glowing": "glow",
    "pulses": "pulse", "pulsed": "pulse", "pulsing": "pulse",
    "flashes": "flash", "flashed": "flash", "flashing": "flash",
    "flares": "flare", "flared": "flare", "flaring": "flare",
    "blinks": "blink", "blinked": "blink", "blinking": "blink",
    "snaps": "snap", "snapped": "snap", "snapping": "snap",
    "cracks": "crack", "cracked": "crack", "cracking": "crack",
    "crumbles": "crumble", "crumbled": "crumble", "crumbling": "crumble",
    "settles": "settle", "settled": "settle", "settling": "settle",
    "shifts": "shift", "shifted": "shift", "shifting": "shift",
    "groans": "groan", "groaned": "groan", "groaning": "groan",
    "skids": "skid", "skidded": "skid", "skidding": "skid",
    "swerves": "swerve", "swerved": "swerve", "swerving": "swerve",
    "brakes": "brake", "braked": "brake", "braking": "brake",
    "reverses": "reverse", "reversed": "reverse", "reversing": "reverse",
    "parks": "park", "parked": "park", "parking": "park",
    "ignites": "ignite", "ignited": "ignite", "igniting": "ignite",
    "burns": "burn", "burned": "burn", "burning": "burn",
    "explodes": "explode", "exploded": "explode", "exploding": "explode",
    "collapses": "collapse", "collapsed": "collapse", "collapsing": "collapse",
    "rumbles": "rumble", "rumbled": "rumble", "rumbling": "rumble",
    "flicks": "flick", "flicked": "flick", "flicking": "flick",
    "smacks": "smack", "smacked": "smack", "smacking": "smack",
    "tucks": "tuck", "tucked": "tuck", "tucking": "tuck",
    "pokes": "poke", "poked": "poke", "poking": "poke",
    "bursts": "burst", "bursting": "burst",
    "zips": "zip", "zipped": "zip", "zipping": "zip",
    "bumps": "bump", "bumped": "bump", "bumping": "bump",
    "swarms": "swarm", "swarmed": "swarm", "swarming": "swarm",
    "scatters": "scatter", "scattered": "scatter", "scattering": "scatter",
    "squints": "squint", "squinted": "squint", "squinting": "squint",
    "gives": "give", "gave": "give", "giving": "give", "given": "give",
    "sets down": "set down", "setting down": "set down",
    "puts down": "put down", "putting down": "put down",
    "yells": "yell", "yelled": "yell", "yelling": "yell",
    "glances": "glance", "glanced": "glance", "glancing": "glance",
    "peers": "peer", "peered": "peer", "peering": "peer",
    "stares": "stare", "stared": "stare", "staring": "stare",
    "gazes": "gaze", "gazed": "gaze", "gazing": "gaze",
    "scratches": "scratch", "scratched": "scratch", "scratching": "scratch",
    "rubs": "rub", "rubbed": "rub", "rubbing": "rub",
    "pats": "pat", "patted": "pat", "patting": "pat",
    "clutches": "clutch", "clutched": "clutch", "clutching": "clutch",
    "grips": "grip", "gripped": "grip", "gripping": "grip",
    "trips": "trip", "tripped": "trip", "tripping": "trip",
    "fumbles": "fumble", "fumbled": "fumble", "fumbling": "fumble",
    "gropes": "grope", "groped": "grope", "groping": "grope",
    "lurches": "lurch", "lurched": "lurch", "lurching": "lurch",
    "swallows": "swallow", "swallowed": "swallow", "swallowing": "swallow",
}


def _normalize_verb(verb: str) -> str:
    """Return lowercase, stripped verb."""
    return verb.strip().lower()


def _to_base_form(verb: str) -> Optional[str]:
    """Return base form from whitelist if verb is an inflection, else None."""
    effective = get_effective_action_whitelist()
    v = _normalize_verb(verb)
    if v in effective:
        return v
    if v in _INFLECTION_TO_BASE:
        base = _INFLECTION_TO_BASE[v]
        return base if base in effective else None
    # Try common suffixes
    for suffix, repl in [("ing", ""), ("ed", ""), ("s", ""), ("es", "")]:
        if v.endswith(suffix) and len(v) > len(suffix) + 1:
            candidate = v[: -len(suffix)]
            if candidate in effective:
                return candidate
            candidate2 = candidate + "e" if suffix in ("ing", "ed") else candidate
            if candidate2 in effective:
                return candidate2
    # Phrase variants: "pulling back" -> "pull back", "pushed in" -> "push in"
    for phrase in effective:
        if " " in phrase:
            parts = phrase.split()
            if v.replace("ing", "").replace("ed", "").replace("s", "") == phrase.replace(" ", ""):
                return phrase
            if all(p in v or p + "ing" in v or p + "ed" in v for p in parts):
                return phrase
    return None


def is_action_valid(verb: str) -> bool:
    """Return True if verb is approved for action markup."""
    v = _normalize_verb(verb)
    if v in ACTION_VERB_FORBIDDEN:
        return False
    if v in get_effective_action_whitelist():
        return True
    return _to_base_form(verb) is not None


def get_valid_action(verb: str) -> Optional[str]:
    """
    Return approved action form for markup, or None if forbidden/invalid.
    - Forbidden → None
    - Exact/inflection match → return canonical whitelist form
    - No match → None
    """
    v = _normalize_verb(verb)
    if v in ACTION_VERB_FORBIDDEN:
        return None
    if v in get_effective_action_whitelist():
        return v
    base = _to_base_form(verb)
    return base


def fix_action_markup(text: str) -> str:
    """
    Scan all *action* markup in text. Validate verbs, remove markup for
    forbidden verbs. Preserve the ORIGINAL inflected form when valid.
    """
    if not text or not text.strip():
        return text

    # Match *content* — content may include intensity modifier like *walks (slowly)*
    pattern = re.compile(r'\*([^*]+)\*')

    def replacer(match: re.Match) -> str:
        inner = match.group(1).strip()
        if not inner:
            return match.group(0)
        
        # Check for intensity modifier: *verb (modifier)*
        mod_match = re.match(r'^(.+?)\s*\((\w+)\)\s*$', inner)
        if mod_match:
            verb_part = mod_match.group(1).strip()
            modifier = mod_match.group(2).strip().lower()
            valid = get_valid_action(verb_part)
            if valid is None:
                return inner  # Remove markup for forbidden verbs
            # Validate modifier
            if modifier in INTENSITY_MODIFIERS:
                # Preserve original verb form
                return f"*{verb_part} ({modifier})*"
            elif modifier in _FORBIDDEN_MODIFIERS:
                return f"*{verb_part}*"  # Drop emotional modifier
            else:
                return f"*{verb_part}*"  # Drop unknown modifier
        
        # No modifier — standard validation
        valid = get_valid_action(inner)
        if valid is None:
            # Remove markup, keep the word (no asterisks)
            return inner
        # Preserve original inflected form (e.g. *adjusts* stays *adjusts*, not *adjust*)
        return f"*{inner}*"

    return pattern.sub(replacer, text)


# ── FILLER VERB REWRITE ──────────────────────────────────────────────────

# Pattern: "begins/starts/continues/tries to VERB" → *VERB*
_FILLER_PATTERN = re.compile(
    r'\b(' + '|'.join(sorted(_FILLER_VERBS, key=len, reverse=True)) + r')\s+(?:to\s+)?(\w+)\b',
    re.IGNORECASE
)


def rewrite_filler_verbs(text: str) -> str:
    """
    Rewrite filler verb phrases to clean cinematic verbs.
    "He begins to walk forward" → "He *walks* forward"
    "She starts turning the handle" → "She *turns* the handle"
    Preserves subject-verb conjugation from the filler verb.
    """
    if not text or not text.strip():
        return text
    
    def replacer(match: re.Match) -> str:
        filler = match.group(1).strip().lower()
        action_word = match.group(2).strip()
        base = _to_base_form(action_word)
        if not base:
            # Not a known action — strip filler, keep word unmarked
            return action_word
        
        # Determine the conjugation from the filler verb
        # 3rd person singular fillers: begins, starts, continues, tries, attempts, proceeds, manages
        is_3rd_singular = filler.endswith('s') and not filler.endswith('ing')
        is_progressive = filler.endswith('ing')
        
        if is_3rd_singular:
            # Find the -s inflected form for the base verb
            for infl, b in _INFLECTION_TO_BASE.items():
                if b == base and infl.endswith('s') and not infl.endswith('ing') and not infl.endswith('ed'):
                    return f"*{infl}*"
            # Fallback: add 's' to base form
            if base.endswith(('s', 'sh', 'ch', 'x', 'z')):
                return f"*{base}es*"
            return f"*{base}s*"
        elif is_progressive:
            # Find the -ing form
            for infl, b in _INFLECTION_TO_BASE.items():
                if b == base and infl.endswith('ing'):
                    return f"*{infl}*"
            # Fallback: generate -ing form
            if base.endswith('e') and not base.endswith('ee'):
                return f"*{base[:-1]}ing*"
            return f"*{base}ing*"
        else:
            # Past tense fillers (began, started, continued, tried)
            # Find past tense form
            for infl, b in _INFLECTION_TO_BASE.items():
                if b == base and infl.endswith('ed'):
                    return f"*{infl}*"
            # Fallback: base form with -ed
            if base.endswith('e'):
                return f"*{base}d*"
            return f"*{base}ed*"
    
    return _FILLER_PATTERN.sub(replacer, text)


# ── INTENSITY MODIFIER NORMALIZATION ─────────────────────────────────────

# Pattern: "He slowly walks forward" → "He *walks (slowly)* forward"
# Matches: MODIFIER + VERB (when verb is a known action and modifier is before it)
def normalize_intensity_modifiers(text: str) -> str:
    """
    Move intensity modifiers inside action markup.
    "He slowly walks forward" → "He *walks (slowly)* forward"
    "She cautiously opens the door" → "She *opens (cautiously)* the door"
    """
    if not text or not text.strip():
        return text
    
    # Build a combined pattern for all known action inflections
    all_action_forms = set()
    all_action_forms.update(get_effective_action_whitelist())
    all_action_forms.update(_INFLECTION_TO_BASE.keys())
    
    # Sort by length (longest first) to avoid partial matches
    sorted_modifiers = sorted(INTENSITY_MODIFIERS, key=len, reverse=True)
    mod_pattern = '|'.join(re.escape(m) for m in sorted_modifiers)
    
    # Pattern: modifier + space + single action verb (not already in *markup*)
    # Only match single words as verbs to avoid capturing verb + next word
    pattern = re.compile(
        r'(?<!\*)\b(' + mod_pattern + r')\s+(\w+)\b(?!\*)',
        re.IGNORECASE
    )
    
    def replacer(match: re.Match) -> str:
        modifier = match.group(1).strip().lower()
        verb_text = match.group(2).strip()
        
        if modifier in _FORBIDDEN_MODIFIERS:
            # Remove emotional modifier, keep verb
            base = _to_base_form(verb_text)
            if base:
                return f"*{verb_text}*"
            return verb_text
        
        base = _to_base_form(verb_text)
        if base and modifier in INTENSITY_MODIFIERS:
            return f"*{verb_text} ({modifier})*"
        # Not a recognized action verb — leave as-is
        return match.group(0)
    
    return pattern.sub(replacer, text)


# ── AUTO-WRAP UNMARKED ACTION VERBS ──────────────────────────────────────

def auto_wrap_action_verbs(text: str) -> str:
    """
    Scan text for unmarked physical action verbs and wrap them in *asterisks*.
    Only wraps verbs that:
    - Are in the action whitelist (or inflection map)
    - Are NOT already inside *markup*
    - Are NOT forbidden (emotional/internal)
    - Are NOT inside [brackets], {braces}, _underscores_, or "quotes"
    - Are NOT used as nouns (after articles/possessives) or adjectives (before nouns)
    """
    if not text or not text.strip():
        return text
    
    # Words that are also common nouns/adjectives — require verb-position context
    _NOUN_ADJECTIVE_AMBIGUOUS = frozenset({
        "strap", "prop", "close", "open", "fire", "roll", "duck", "land", "park",
        "stop", "start", "clear", "seal", "drift", "bank", "block", "spring",
        "crack", "break", "slide", "fall", "draw", "lock", "balance", "brace",
        "aim", "cut", "hit", "snap", "flash", "flare", "pulse", "glow", "burn",
        "shake", "shift", "grip", "match", "bolt", "dash", "march", "limp",
        "wave", "point", "press", "tap", "knock", "slam", "tug", "bow",
        "light", "dim", "drop", "catch", "hold", "release", "turn",
        "step", "approach", "retreat", "gesture", "strike", "climb",
        "run", "sit", "stand", "lean", "reach", "grab",
    })
    
    # Articles and possessives that signal a noun follows
    _NOUN_SIGNALS = frozenset({
        "a", "an", "the", "his", "her", "its", "their", "my", "your", "our",
        "this", "that", "these", "those", "some", "any", "each", "every",
    })
    
    # Build regex for all known action verb forms (inflected + base)
    all_forms = set()
    all_forms.update(get_effective_action_whitelist())
    all_forms.update(_INFLECTION_TO_BASE.keys())
    
    # Remove very short words (2 chars or less) that almost always cause false positives
    all_forms = {f for f in all_forms if len(f) > 2}
    
    # Phase 1: wrap unambiguous multi-word phrases first (e.g. "pick up", "shake head")
    multi_word_forms = sorted(
        [f for f in all_forms if ' ' in f],
        key=len, reverse=True
    )
    for phrase in multi_word_forms:
        # Only wrap if not already inside *markup*
        pattern = re.compile(
            r'(?<!\*)\b(' + re.escape(phrase) + r')(?:s|ed|ing|es)?\b(?!\*)',
            re.IGNORECASE
        )
        text = pattern.sub(lambda m: f'*{m.group(1)}*', text)
    
    # Phase 2: wrap single-word action verbs
    sorted_forms = sorted(
        [f for f in all_forms if ' ' not in f],
        key=len, reverse=True
    )
    
    lines = text.split('\n')
    result_lines = []
    
    for line in lines:
        # Skip lines that are entirely dialogue (inside quotes)
        stripped = line.strip()
        if stripped.startswith('"') and stripped.endswith('"'):
            result_lines.append(line)
            continue
        
        # Find all existing *markup* spans to avoid double-wrapping
        markup_spans = []
        for m in re.finditer(r'\*[^*]+\*', line):
            markup_spans.append((m.start(), m.end()))
        
        # Find all bracket/brace/underscore/quote spans to avoid wrapping inside them
        protected_spans = list(markup_spans)
        for m in re.finditer(r'\[[^\]]*\]|\{[^}]*\}|_[^_]+_|"[^"]*"', line):
            protected_spans.append((m.start(), m.end()))
        
        def is_protected(pos: int, end: int) -> bool:
            return any(s <= pos and end <= e for s, e in protected_spans)
        
        def get_word_before(text_str: str, pos: int) -> str:
            """Get the word immediately before position pos (preserves case)."""
            before_text = text_str[:pos].rstrip()
            if not before_text:
                return ""
            # Strip any markup/bracket characters at the end
            before_text = re.sub(r'[\[\]{}*_\'"]+$', '', before_text).rstrip()
            words = before_text.split()
            return words[-1] if words else ""
        
        def get_word_after(text_str: str, pos: int) -> str:
            """Get the word immediately after position pos."""
            after_text = text_str[pos:].lstrip()
            if not after_text:
                return ""
            # Strip any markup/bracket characters at the start
            after_text = re.sub(r'^[\[\]{}*_\'"]+', '', after_text).lstrip()
            words = after_text.split()
            return words[0].lower().rstrip('.,;:!?') if words else ""
        
        # Process each known verb form
        for verb_form in sorted_forms:
            if len(verb_form) < 3:
                continue
            
            pat = re.compile(r'\b(' + re.escape(verb_form) + r')\b', re.IGNORECASE)
            
            new_line = []
            last_end = 0
            line_modified = False
            for m in pat.finditer(line):
                if is_protected(m.start(), m.end()):
                    continue
                # Check it's not already wrapped
                before_char = line[max(0, m.start()-1):m.start()]
                after_char = line[m.end():m.end()+1] if m.end() < len(line) else ''
                if before_char == '*' or after_char == '*':
                    continue
                # Check verb is not forbidden
                matched_word = m.group(1)
                base = matched_word.lower()
                resolved_base = _to_base_form(base)
                if base in ACTION_VERB_FORBIDDEN:
                    continue
                
                # ── CONTEXT CHECK: skip if used as noun or adjective ──
                word_before = get_word_before(line, m.start())
                word_after = get_word_after(line, m.end())
                
                # Skip if preceded by article/possessive (noun position)
                if word_before.lower() in _NOUN_SIGNALS:
                    continue
                
                # Skip past participles (-ed) before a noun (adjective position)
                # e.g. "cracked tripod", "damaged hull", "burned floor"
                if base.endswith('ed') and word_after:
                    # Check if word_after is not a preposition/conjunction
                    # (if it's a noun-like word, the -ed word is an adjective)
                    if word_after.lower() not in {'and', 'or', 'but', 'the', 'a', 'an', 'in',
                                          'on', 'at', 'to', 'from', 'with', 'by', 'into',
                                          'onto', 'over', 'under', 'through', 'across',
                                          'as', 'his', 'her', 'its', 'their', 'off', 'up',
                                          'down', 'out', 'away', 'back', 'around', 'about'}:
                        # Likely adjective use: "cracked [tripod]", "damaged hull"
                        continue
                
                # Skip present participles (-ing) after "is/was/are/were" (passive/progressive — keep)
                # But skip if used as adjective before noun: "the burning building"
                if base.endswith('ing') and word_before.lower() in _NOUN_SIGNALS:
                    continue
                
                # ── STATIVE CHECK: descriptive vs. action use ──
                # Verbs like "stretch", "rise", "glow" can describe a setting
                # rather than a physical action.  Only wrap when the subject is
                # clearly a character, object, or vehicle.
                stative_base = resolved_base if resolved_base else base
                if stative_base in _STATIVE_CAPABLE_VERBS or base in _STATIVE_CAPABLE_VERBS:
                    wb_st = word_before.lower().rstrip('.,;:!?')
                    is_active_subject = (
                        (word_before == word_before.upper() and len(word_before) > 1
                         and word_before.rstrip('.,;:!?').isalpha())
                        or wb_st in {'he', 'she', 'it', 'they', 'we', 'i', 'who'}
                        or wb_st in {'and', 'then', 'but', 'or'}
                        or word_before.endswith('.')
                        or word_before.endswith(',')
                        or m.start() == 0
                        or line[m.start()-1] in '.!?\n'
                    )
                    if not is_active_subject:
                        # No obvious character/pronoun/conjunction subject.
                        # Check whether the nearest entity markup is an
                        # object [brackets] or vehicle {braces} — those
                        # still receive action markup.
                        lookback_window = line[max(0, m.start()-40):m.start()]
                        last_obj = lookback_window.rfind(']')
                        last_veh = lookback_window.rfind('}')
                        obj_or_veh_pos = max(last_obj, last_veh)
                        if obj_or_veh_pos >= 0:
                            between = lookback_window[obj_or_veh_pos+1:]
                            if any(c in between for c in '.!?\n'):
                                continue  # sentence break — entity is unrelated
                            # object/vehicle entity is the subject → wrap
                        else:
                            continue  # environment entity or plain noun → stative
                
                # For highly ambiguous words, only wrap when in clear verb position
                # (after a subject: CAPS name, pronoun, entity markup, or after period/start of sentence)
                if base in _NOUN_ADJECTIVE_AMBIGUOUS or (resolved_base and resolved_base in _NOUN_ADJECTIVE_AMBIGUOUS):
                    lookback = line[max(0, m.start()-5):m.start()].rstrip()
                    preceded_by_entity = lookback.endswith(']') or lookback.endswith('}') or lookback.endswith('_')
                    wb_lower = word_before.lower()
                    if word_before and not (
                        preceded_by_entity
                        or (word_before == word_before.upper() and len(word_before) > 1)
                        or wb_lower in {'he', 'she', 'it', 'they', 'we', 'i', 'who'}
                        or wb_lower in {'and', 'then', 'but', 'or'}
                        or word_before.endswith('.')
                        or word_before.endswith(',')
                        or m.start() == 0
                        or line[m.start()-1] in '.!?\n'
                    ):
                        continue
                
                new_line.append(line[last_end:m.start()])
                new_line.append(f'*{matched_word}*')
                last_end = m.end()
                line_modified = True
            
            if line_modified:
                new_line.append(line[last_end:])
                line = ''.join(new_line)
                # Recompute protected spans for the modified line so the
                # next verb_form iteration uses accurate positions.
                protected_spans = []
                for pm in re.finditer(r'\*[^*]+\*', line):
                    protected_spans.append((pm.start(), pm.end()))
                for pm in re.finditer(r'\[[^\]]*\]|\{[^}]*\}|_[^_]+_|"[^"]*"', line):
                    protected_spans.append((pm.start(), pm.end()))
        
        result_lines.append(line)
    
    return '\n'.join(result_lines)


# ── FULL CINEMATIC ACTION PASS ───────────────────────────────────────────

def enforce_action_grammar(text: str) -> str:
    """
    Run the complete cinematic action grammar pipeline:
    1. Rewrite filler verbs (begins to walk → *walks*)
    2. Normalize intensity modifiers (slowly walks → *walks (slowly)*)
    3. Auto-wrap unmarked action verbs
    4. Validate all existing *markup*
    """
    if not text or not text.strip():
        return text
    
    # Step 1: Rewrite filler verbs
    text = rewrite_filler_verbs(text)
    
    # Step 2: Normalize intensity modifiers
    text = normalize_intensity_modifiers(text)
    
    # Step 3: Auto-wrap unmarked action verbs
    text = auto_wrap_action_verbs(text)
    
    # Step 4: Validate existing markup
    text = fix_action_markup(text)
    
    # Step 5: Clean up double-asterisk artifacts safely.
    # (a) Normalize AI markdown bold (**word**) → single-asterisk markup (*word*).
    text = re.sub(r'\*\*([^*]+)\*\*', r'*\1*', text)
    # (b) Adjacent markup like *walks**opens* must become *walks* *opens*
    #     (with a space), NOT *walksopens* which merges words.
    text = re.sub(r'\*\*', '* *', text)
    
    return text


def get_action_rules_prompt_text() -> str:
    """Return the Action Rules block for inclusion in AI prompts."""
    return """
ACTION MARKUP RULES (MANDATORY — SceneWrite):
- ALL visible physical movement MUST be wrapped in *asterisks*.
- This includes: character movement, object interaction, environmental movement, vehicle movement.
- Use ONLY approved action verbs. One primary action per markup.
- Intensity modifiers go INSIDE markup: *walks (slowly)*, *slams (violently)*, *turns (cautiously)*
- Only physical intensity descriptors (slowly, quickly, forcefully, gently, etc.) — NO emotional modifiers.
- NEVER use internal/emotional/abstract verbs: feel, think, realize, decide, hope, fear, remember, regret, sense, consider, believe, wonder, hesitate.
- Remove filler verbs: begins, starts, continues, tries to → rewrite to direct action.
  - "He begins to walk" → "He *walks*"
  - "She starts turning" → "She *turns*"
- Actions must be direct and visually concrete.

Approved verbs include: walk, run, enter, exit, sit, stand, lean, turn, look, reach, grab, hold, release, open, close, push, pull, pick up, drop, throw, kneel, rise, step, approach, retreat, brace, gesture, nod, adjust, wipe, flip, spin, twist, lift, lower, slide, toss, catch, crouch, dodge, lunge, swing, kick, punch, draw, point, wave, squeeze, press, tap, knock, slam, yank, tug, stagger, stumble, limp, sprint, dash, march, creep, sneak, tiptoe, pace, halt, freeze, flinch, recoil, sway, wobble, stretch, shrug, dangle, drape, prop, perch, balance, hoist; glow, pulse, flash, flare, fade, blink, snap, crack, crumble, settle, shift; tremble, shake, lurch, flicker, brighten, darken; start, stop, accelerate, launch, land, dock, hover, drift, skid, swerve, brake, reverse; rumble, collapse, flood, ignite, burn, smolder, echo, seal, lock down.

Example (correct): MILO *adjusts* the strap of his [headlamp] as he *steps* into the _Abandoned Mill_ (ambient_mill_creak). His [boots] *step* on broken glass (glass_crunch).
Example (incorrect): MILO adjusts the strap of his [headlamp] as he steps into the _Abandoned Mill_.
"""
