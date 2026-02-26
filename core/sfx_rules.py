"""
SFX Rules for MoviePrompterAI / screenplay sound effects.
Enforces strict SFX Whitelist for (parenthetical) sound markup.

CINEMATIC GRAMMAR SYSTEM:
- Lower-case only
- Underscore-separated tokens
- Must match approved SFX Whitelist
- Represents audible sound only
- Supports LAYERED SFX: primary (action-caused) + ambient (environmental)
- Maximum 1 primary SFX per action
- Maximum 2 ambient SFX per scene paragraph
"""

import re
from typing import Set, Optional, List, Tuple

# 1. HUMAN / PHYSICAL SFX
HUMAN_SFX = frozenset({
    "footsteps", "running_footsteps", "breathing", "heavy_breathing", "grunt", "gasp",
    "cough", "scream", "shout", "whisper", "laugh", "cry", "panting", "struggle",
    "body_fall", "impact_body", "snap_fingers", "clap", "heartbeat",
    "sigh", "yawn", "choking", "sobbing", "hiccup",
    "roar", "growl", "moan", "groan", "wheeze", "snore", "snoring",
    "splutter", "retch", "hiss", "sniff", "sniffle", "gulp",
    "teeth_chatter", "knuckle_crack", "bone_crack", "joint_pop",
    "slurp", "chewing", "swallow", "belch",
})

# 2. OBJECT / PROP SFX
OBJECT_SFX = frozenset({
    "metal_clang", "metal_scrape", "wood_creak", "chair_scrape", "door_open", "door_close",
    "door_slam", "lock_click", "unlock_click", "button_press", "lever_pull", "glass_shatter",
    "object_drop", "object_slide", "chain_rattle", "key_jingle", "paper_rustle",
    "zipper_pull", "switch_click", "glass_crunch", "rope_snap", "metal_snap",
    "cloth_tear", "wood_snap", "book_close", "book_open", "drawer_open", "drawer_close",
    "lid_open", "lid_close", "cork_pop", "bottle_clink",
    "metal_clank", "light_clank", "metal_rattle", "metal_creak", "metal_ping",
    "wood_thud", "wood_crack", "wood_splinter",
    "glass_clink", "glass_crack", "ceramic_break", "ceramic_clink",
    "cloth_rustle", "cloth_rip", "leather_creak", "leather_snap",
    "rope_creak", "chain_clink", "latch_click", "hinge_squeak",
    "pot_clang", "pan_sizzle", "knife_chop", "liquid_pour", "liquid_splash",
    "coin_clink", "coin_drop", "bell_ring", "bell_chime",
    "shatter", "thud", "clank", "clang", "clatter", "creak", "squeak",
    "rattle", "jingle", "clink", "rustle", "snap", "crack", "crunch",
    "buzz", "whir", "hiss", "pop", "fizz", "sizzle", "gurgle", "drip",
})

# 3. VEHICLE SFX
VEHICLE_SFX = frozenset({
    "engine_start", "engine_idle", "engine_rev", "engine_shutdown", "engine_roar",
    "engine_whine", "engine_fail", "thrust_engage", "thrust_disengage", "landing_gear_deploy",
    "landing_gear_retract", "docking_clamp", "metal_groan", "hull_stress",
    "tire_screech", "brakes_squeal", "horn_honk", "engine_sputter", "engine_hum",
    "propeller_whir", "helicopter_rotor",
    "engine_rumble", "engine_cough", "engine_knock", "engine_purr",
    "exhaust_pop", "exhaust_backfire", "gear_shift", "gear_grind",
    "tire_pop", "tire_squeal", "tire_crunch", "wheel_spin",
    "horn_blast", "horn_beep", "siren_wail",
    "hull_creak", "hull_breach", "anchor_drop", "anchor_chain",
    "sail_flap", "rigging_creak", "oar_splash", "paddle_splash",
    "sputter", "roar",
})

# 4. ENVIRONMENTAL / ATMOSPHERIC SFX
ENVIRONMENTAL_SFX = frozenset({
    "rumble", "distant_rumble", "shake", "creaking_structure", "wind_howl", "air_vent",
    "steam_hiss", "alarm", "siren", "warning_tone", "electric_buzz", "power_down",
    "power_up", "lights_flicker", "hum", "whirr", "thunder", "rain", "rain_heavy",
    "dripping_water", "water_splash", "water_flow", "fire_crackle", "ice_crack",
    "gravel_crunch", "leaves_rustle", "branch_snap", "bird_call", "insect_buzz",
    "wolf_howl", "crow_call", "church_bell", "clock_tick", "clock_chime",
    "whir", "thunder_crack", "thunder_roll", "lightning_strike",
    "wind_gust", "wind_whistle", "wind_moan",
    "rain_patter", "rain_drizzle", "hail", "hailstones",
    "snow_crunch", "ice_crack", "ice_shatter", "icicle_snap",
    "water_drip", "water_gurgle", "water_rush", "wave_crash", "waterfall_roar",
    "fire_roar", "fire_pop", "fire_hiss", "ember_pop", "wood_fire_crackle",
    "earth_rumble", "rock_slide", "rock_fall", "gravel_shift", "sand_shift",
    "door_creak", "floor_creak", "stair_creak", "wall_crack",
    "pipe_clang", "pipe_hiss", "vent_rattle",
    "distant_explosion", "distant_gunfire", "distant_sirens",
    "crowd_murmur", "crowd_cheer", "crowd_gasp",
})

# 5. WEAPONS / COMBAT SFX
WEAPON_SFX = frozenset({
    "gunshot", "laser_fire", "energy_blast", "explosion", "impact_metal", "impact_concrete",
    "ricochet", "reload_click", "weapon_charge", "weapon_overheat",
    "blade_ring", "blade_impact", "arrow_loose", "arrow_impact",
    "shield_clang", "whip_crack", "fist_impact",
    "gunshot_echo", "gunshot_suppressed", "automatic_fire", "shotgun_blast",
    "bullet_impact", "bullet_whiz", "shell_casing", "magazine_click",
    "blade_draw", "blade_slash", "blade_scrape", "blade_clang",
    "sword_clash", "dagger_thrust", "axe_chop", "mace_impact",
    "arrow_whiz", "arrow_thud", "crossbow_release",
    "shield_bash", "armor_clank", "armor_scrape",
    "punch_impact", "kick_impact", "body_slam",
    "staff_strike", "club_impact", "hammer_strike",
    "energy_hum", "energy_pulse", "energy_discharge",
    "explosion_distant", "explosion_small", "detonation",
})

# 6. ELECTRONIC / UI SFX
ELECTRONIC_SFX = frozenset({
    "beep", "double_beep", "error_tone", "confirmation_tone", "scanner_ping",
    "hologram_activate", "hologram_deactivate", "data_stream", "signal_lost", "signal_restored",
    "radio_static", "radio_click", "phone_ring", "phone_buzz", "camera_shutter",
    "keyboard_clack", "typing",
})

# 7. ANIMAL / CREATURE SFX
ANIMAL_SFX = frozenset({
    "horse_whinny", "horse_neigh", "horse_snort", "horse_gallop", "hooves_cobblestone",
    "hooves_dirt", "hooves_clatter", "saddle_creak", "bridle_jingle",
    "dog_bark", "dog_growl", "dog_whimper", "dog_howl", "dog_pant",
    "cat_meow", "cat_hiss", "cat_purr", "cat_yowl",
    "bird_song", "bird_chirp", "bird_screech", "bird_flutter", "wings_flap",
    "eagle_cry", "hawk_screech", "owl_hoot", "raven_croak",
    "snake_hiss", "snake_rattle",
    "bear_growl", "bear_roar", "lion_roar", "tiger_growl",
    "elephant_trumpet", "monkey_screech",
    "cattle_moo", "sheep_bleat", "goat_bleat", "pig_squeal", "chicken_cluck",
    "rooster_crow", "donkey_bray",
    "frog_croak", "cricket_chirp", "cicada_buzz", "bee_buzz",
    "fly_buzz", "mosquito_whine",
    "whale_song", "dolphin_click", "seal_bark",
    "creature_screech", "creature_growl", "creature_roar", "creature_hiss",
    "whinny",
})

# 8. IMPACT / COLLISION SFX
IMPACT_SFX = frozenset({
    "thud", "thump", "crash", "bang", "slam", "smash", "bash",
    "crunch", "crack", "snap", "pop", "splat", "squelch",
    "clunk", "bonk", "thwack", "whack", "smack",
    "impact_wood", "impact_glass", "impact_stone", "impact_dirt",
    "impact_water", "impact_flesh", "impact_bone",
    "collision", "crash_metal", "crash_wood", "crash_glass",
    "shatter", "splinter", "crumble",
})

# 9. AMBIENT SFX (Environmental layers — use with ambient_ prefix)
AMBIENT_SFX = frozenset({
    "ambient_wind", "ambient_rain", "ambient_thunder", "ambient_crickets",
    "ambient_forest", "ambient_city", "ambient_traffic", "ambient_crowd",
    "ambient_ocean", "ambient_waves", "ambient_river", "ambient_waterfall",
    "ambient_fire", "ambient_campfire", "ambient_machinery", "ambient_factory",
    "ambient_engine", "ambient_hum", "ambient_buzz", "ambient_static",
    "ambient_cave", "ambient_dungeon", "ambient_spaceship", "ambient_station",
    "ambient_hospital", "ambient_office", "ambient_classroom", "ambient_church",
    "ambient_bar", "ambient_restaurant", "ambient_kitchen", "ambient_market",
    "ambient_battlefield", "ambient_storm", "ambient_blizzard", "ambient_desert",
    "ambient_jungle", "ambient_swamp", "ambient_mine", "ambient_sewer",
    "ambient_attic", "ambient_basement", "ambient_dust_rattle",
    "ambient_mill_creak", "ambient_warehouse", "ambient_docks",
    "ambient_night", "ambient_dawn", "ambient_dusk",
})

# Combined whitelist (all approved)
SFX_WHITELIST: Set[str] = (
    HUMAN_SFX | OBJECT_SFX | VEHICLE_SFX | ENVIRONMENTAL_SFX | WEAPON_SFX
    | ELECTRONIC_SFX | ANIMAL_SFX | IMPACT_SFX | AMBIENT_SFX
)

# User-added SFX (populated at runtime from config/SFXWhitelist.json)
_user_sfx_whitelist: Set[str] = set()


def set_user_sfx_whitelist(sfx_set: Set[str]):
    """Set the user-added SFX whitelist (called by markup_whitelist at runtime)."""
    global _user_sfx_whitelist
    _user_sfx_whitelist = set(sfx_set)


def get_effective_sfx_whitelist() -> Set[str]:
    """Return built-in + user-added SFX."""
    return SFX_WHITELIST | _user_sfx_whitelist


# Forbidden — NEVER as SFX (abstract/emotion/narrative)
SFX_FORBIDDEN = frozenset({
    "silence", "tension", "drama", "fear", "anticipation", "relief", "music", "score",
    "mood", "emotion", "meanwhile", "pause", "beat", "sadly", "angrily", "quietly",
    "loudly", "softly", "tension_builds", "dramatic_pause", "sadness", "anger",
    "joy", "surprise", "confusion", "excitement", "dread", "suspense",
})

# Common variants → whitelist form (e.g. verb forms, slight spelling)
_SFX_NORMALIZE = {
    "creak": "wood_creak", "creaks": "wood_creak", "creaking": "wood_creak",
    "moan": "grunt", "moans": "grunt",
    "thud": "body_fall", "thuds": "body_fall",
    "crack": "impact_metal", "cracks": "impact_metal",
    "splash": "water_splash", "splashes": "water_splash",
    "whispering": "whisper", "whispers": "whisper",
    "footstep": "footsteps", "foot steps": "footsteps", "running footsteps": "running_footsteps",
    "engine revs": "engine_rev", "metal groans": "metal_groan",
    "crunch": "glass_crunch", "crunches": "glass_crunch", "crunching": "glass_crunch",
    "clang": "metal_clang", "clanging": "metal_clang",
    "click": "lock_click", "clicking": "lock_click",
    "boom": "explosion", "booms": "explosion",
    "bang": "gunshot", "bangs": "gunshot",
    "hiss": "steam_hiss", "hissing": "steam_hiss",
    "scrape": "metal_scrape", "scrapes": "metal_scrape", "scraping": "metal_scrape",
    "rattle": "chain_rattle", "rattles": "chain_rattle", "rattling": "chain_rattle",
    "shatter": "glass_shatter", "shatters": "glass_shatter", "shattering": "glass_shatter",
    "squeal": "brakes_squeal", "squealing": "brakes_squeal",
    "drip": "dripping_water", "drips": "dripping_water",
    "crackle": "fire_crackle", "crackling": "fire_crackle",
    "rustle": "leaves_rustle", "rustling": "leaves_rustle",
    "buzz": "electric_buzz", "buzzing": "electric_buzz",
    "whine": "engine_whine", "whining": "engine_whine",
    "roar": "engine_roar", "roaring": "engine_roar",
    "howl": "wind_howl", "howling": "wind_howl",
    "groan": "metal_groan", "groaning": "metal_groan",
    "snap": "wood_snap", "snaps": "wood_snap", "snapping": "wood_snap",
    "patter": "rain", "pattering": "rain",
    "thunder_crack": "thunder", "thunder_boom": "thunder",
}


def _normalize_sfx(text: str) -> str:
    """Lowercase, strip, replace spaces with underscores."""
    return text.strip().lower().replace(" ", "_")


def is_sfx_valid(sfx: str) -> bool:
    """Return True if SFX is approved."""
    norm = _normalize_sfx(sfx)
    if norm in SFX_FORBIDDEN:
        return False
    if norm in get_effective_sfx_whitelist():
        return True
    return get_valid_sfx(sfx) is not None


def is_ambient_sfx(sfx: str) -> bool:
    """Return True if this SFX is an ambient layer sound."""
    norm = _normalize_sfx(sfx)
    return norm in AMBIENT_SFX or norm.startswith("ambient_")


def get_valid_sfx(sfx: str) -> Optional[str]:
    """
    Return approved SFX form for markup, or None if forbidden/invalid.
    """
    norm = _normalize_sfx(sfx)
    if norm in SFX_FORBIDDEN:
        return None
    if norm in get_effective_sfx_whitelist():
        return norm
    if norm in _SFX_NORMALIZE:
        return _SFX_NORMALIZE[norm]
    # Check if it starts with "ambient_" and the base part matches something
    if norm.startswith("ambient_"):
        # Allow custom ambient_ prefixed SFX that follow the pattern
        base = norm[8:]  # strip "ambient_"
        if base and re.match(r'^[a-z][a-z_]*$', base) and len(base) > 1:
            return norm  # Accept well-formed ambient SFX
    return None


# Prose patterns: when these phrases appear (describing sounds), replace with (sfx) markup.
# Order matters: longer phrases first. Use word boundaries to avoid false hits (e.g. "human").
_SFX_EXPAND_PATTERNS = [
    # Compound sound descriptions first (handle optional [brackets] around nouns)
    # These patterns APPEND the SFX tag; they don't replace the prose
    (re.compile(r'((?:\[?boots?\]?)\s+crunch(?:es|ing)?\s+(?:on|through|across)\s+[^.!?]+)', re.IGNORECASE),
     lambda m: f'{m.group(0)} (glass_crunch)'),
    (re.compile(r'((?:\[?feet\]?)\s+crunch(?:es|ing)?\s+(?:on|through|across)\s+[^.!?]+)', re.IGNORECASE),
     lambda m: f'{m.group(0)} (gravel_crunch)'),
    (re.compile(r'(glass\s+(?:crunches?|cracking|breaking))', re.IGNORECASE),
     lambda m: f'{m.group(0)} (glass_crunch)'),
    (re.compile(r'(gravel\s+crunch(?:es|ing)?)', re.IGNORECASE),
     lambda m: f'{m.group(0)} (gravel_crunch)'),
    (re.compile(r'(\bwood(?:en)?\s+(?:creaks?|creaking|groans?|groaning))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (wood_creak)'),
    (re.compile(r'(\bfloor(?:boards?)?\s+(?:creaks?|creaking|groans?))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (wood_creak)'),
    (re.compile(r'(\bdoor\s+(?:slams?|slamming))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (door_slam)'),
    (re.compile(r'(\bdoor\s+(?:opens?|opening))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (door_open)'),
    (re.compile(r'(\bdoor\s+(?:closes?|closing|shuts?|shutting))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (door_close)'),
    (re.compile(r'(\bmetal\s+(?:clangs?|clanging|clanks?|clanking))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (metal_clang)'),
    (re.compile(r'(\bmetal\s+(?:scrapes?|scraping|scratches?|scratching))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (metal_scrape)'),
    (re.compile(r'(\bmetal\s+(?:groans?|groaning|creaks?|creaking))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (metal_groan)'),
    (re.compile(r'(\bchain(?:s)?\s+(?:rattles?|rattling|jingle|jingling))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (chain_rattle)'),
    (re.compile(r'(\bengine\s+(?:roars?|roaring))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (engine_roar)'),
    (re.compile(r'(\bengine\s+(?:sputters?|sputtering|coughs?|coughing))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (engine_sputter)'),
    (re.compile(r'(\bengine\s+(?:starts?|starting|fires?\s+up|firing\s+up))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (engine_start)'),
    (re.compile(r'(\bengine\s+(?:dies?|dying|stalls?|stalling|fails?|failing))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (engine_fail)'),
    (re.compile(r'(\bengine\s+(?:idles?|idling|purrs?|purring))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (engine_idle)'),
    (re.compile(r'(\btires?\s+(?:screech(?:es|ing)?|squeal(?:s|ing)?))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (tire_screech)'),
    (re.compile(r'(\bbrakes?\s+(?:screech(?:es|ing)?|squeal(?:s|ing)?))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (brakes_squeal)'),
    (re.compile(r'(\bwind\s+(?:howls?|howling|whistles?|whistling))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (wind_howl)'),
    (re.compile(r'(\bthunder(?:\s+(?:cracks?|booms?|rolls?|rumbles?)))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (thunder)'),
    (re.compile(r'(\brain\s+(?:pounds?|pounding|hammers?|hammering|lashes?|lashing|pelts?|pelting))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (rain_heavy)'),
    (re.compile(r'(\brain\s+(?:patters?|pattering|falls?|falling|drizzles?|drizzling))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (rain)'),
    (re.compile(r'(\bwater\s+(?:drips?|dripping|drops?))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (dripping_water)'),
    (re.compile(r'(\bwater\s+(?:splash(?:es|ing)?))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (water_splash)'),
    (re.compile(r'(\bfire\s+(?:crackles?|crackling))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (fire_crackle)'),
    (re.compile(r'(\bleaves?\s+(?:rustles?|rustling))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (leaves_rustle)'),
    (re.compile(r'(\bbranch(?:es)?\s+(?:snaps?|snapping|cracks?|cracking))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (branch_snap)'),
    (re.compile(r'(\bglass\s+(?:shatters?|shattering|breaks?|breaking))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (glass_shatter)'),
    
    # Simple sound word patterns
    # hum (avoid "human", "humility")
    (re.compile(r'\bthe hum of\b', re.IGNORECASE), '(hum) of'),
    (re.compile(r'\bwith the hum\b', re.IGNORECASE), 'with (hum)'),
    (re.compile(r'\ba (?:low |soft |faint |constant |steady )?hum\b(?!\w)', re.IGNORECASE), '(hum)'),
    (re.compile(r'\bthe hum\b(?!\w)', re.IGNORECASE), '(hum)'),
    # whirr
    (re.compile(r'\bthe whirr of\b', re.IGNORECASE), '(whirr) of'),
    (re.compile(r'\bthe whirr\b', re.IGNORECASE), '(whirr)'),
    (re.compile(r'\ba whirr\b', re.IGNORECASE), '(whirr)'),
    # rumble
    (re.compile(r'\bthe rumble of\b', re.IGNORECASE), '(rumble) of'),
    (re.compile(r'\bdistant rumble\b', re.IGNORECASE), '(distant_rumble)'),
    (re.compile(r'\bthe rumble\b', re.IGNORECASE), '(rumble)'),
    (re.compile(r'\ba (?:low |deep |distant )?rumble\b', re.IGNORECASE), '(rumble)'),
    # creak -> wood_creak
    (re.compile(r'\bthe creak of\b', re.IGNORECASE), '(wood_creak) of'),
    (re.compile(r'\bthe creak\b', re.IGNORECASE), '(wood_creak)'),
    (re.compile(r'\ba creak\b', re.IGNORECASE), '(wood_creak)'),
    # buzz -> electric_buzz
    (re.compile(r'\bthe buzz of\b', re.IGNORECASE), '(electric_buzz) of'),
    (re.compile(r'\bthe buzz\b', re.IGNORECASE), '(electric_buzz)'),
    (re.compile(r'\ba buzz\b', re.IGNORECASE), '(electric_buzz)'),
    # footsteps
    (re.compile(r'\bthe sound of footsteps\b', re.IGNORECASE), '(footsteps)'),
    (re.compile(r'\bfootsteps (echo|sound|pound|fade)\b', re.IGNORECASE), r'(footsteps) \1'),
    (re.compile(r'\bhis footsteps\b', re.IGNORECASE), '(footsteps)'),
    (re.compile(r'\bher footsteps\b', re.IGNORECASE), '(footsteps)'),
    # alarm, siren
    (re.compile(r'\bthe alarm (?:sounds?|blares?|rings?)\b', re.IGNORECASE), '(alarm)'),
    (re.compile(r'\bthe siren (?:wails?|blares?|sounds?)\b', re.IGNORECASE), '(siren)'),
    (re.compile(r'\ban alarm (?:sounds?|blares?|rings?)\b', re.IGNORECASE), '(alarm)'),
    # engine sounds
    (re.compile(r'\bengine hum\b', re.IGNORECASE), '(engine_hum)'),
    (re.compile(r'\bengine whirr\b', re.IGNORECASE), '(whirr)'),
    # beep
    (re.compile(r'\bthe beep of\b', re.IGNORECASE), '(beep) of'),
    (re.compile(r'\ba beep\b', re.IGNORECASE), '(beep)'),
    (re.compile(r'\b(?:soft |faint |loud )?beep(?:ing)?\b', re.IGNORECASE), '(beep)'),
    # hiss
    (re.compile(r'\bthe hiss of\b', re.IGNORECASE), '(steam_hiss) of'),
    (re.compile(r'\bsteam hiss(?:es|ing)?\b', re.IGNORECASE), '(steam_hiss)'),
    (re.compile(r'\ba hiss\b', re.IGNORECASE), '(steam_hiss)'),
    # flicker (lights)
    (re.compile(r'\bthe flickering of (?:the )?lights\b', re.IGNORECASE), '(lights_flicker)'),
    (re.compile(r'\blights flicker\b', re.IGNORECASE), '(lights_flicker)'),
    # gunshot / explosion
    (re.compile(r'(\ba (?:loud |sharp )?(?:gunshot|gun shot))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (gunshot)'),
    (re.compile(r'(\ban? (?:massive |huge |loud |distant )?explosion)\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (explosion)'),
    # screech
    (re.compile(r'(\bscreech(?:es|ing)? of (?:tires?|brakes?|wheels?))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (tire_screech)'),
    # heartbeat
    (re.compile(r'(\bheart(?:beat)?\s+(?:pounds?|pounding|thumps?|thumping))\b', re.IGNORECASE),
     lambda m: f'{m.group(0)} (heartbeat)'),
]


def expand_sfx_markup(text: str) -> str:
    """
    Auto-correct: find unmarked sound descriptions in prose and wrap them in (sfx) markup.
    E.g. "the hum of an old computer" -> "(hum) of an old computer"
    E.g. "His boots crunch on broken glass" -> "(glass_crunch)"
    Run BEFORE fix_sfx_markup so new parens get validated.
    """
    if not text or not text.strip():
        return text
    result = text
    for entry in _SFX_EXPAND_PATTERNS:
        pattern = entry[0]
        replacement = entry[1]
        if callable(replacement):
            result = pattern.sub(replacement, result)
        else:
            result = pattern.sub(replacement, result)
    return result


def fix_sfx_markup(text: str) -> str:
    """
    Scan all (parenthetical) content. Replace invalid SFX with valid form or remove.
    - Forbidden (silence, tension, etc.) → remove entirely
    - Not in whitelist, no mapping → remove
    - Valid or mappable → ensure correct format (lowercase, underscores)
    """
    if not text or not text.strip():
        return text

    # Match (content) - non-greedy, one level (no nested parens)
    pattern = re.compile(r'\(([^()]*)\)')

    def replacer(match: re.Match) -> str:
        inner = match.group(1).strip()
        if not inner:
            return match.group(0)
        # Check for intensity modifier format: (modifier) inside *action*
        # These are handled by action_rules, not SFX — skip them
        if inner.lower() in _get_all_intensity_words():
            return match.group(0)
        valid = get_valid_sfx(inner)
        if valid is None:
            # Remove invalid SFX entirely
            return ""
        return f"({valid})"

    result = pattern.sub(replacer, text)
    # Clean up double spaces or spacing left by removed parens
    result = re.sub(r'  +', ' ', result)
    result = re.sub(r' \.', '.', result)
    result = re.sub(r' ,', ',', result)
    return result


def _get_all_intensity_words() -> Set[str]:
    """Return set of intensity modifier words so fix_sfx_markup doesn't strip them."""
    # Import here to avoid circular imports
    try:
        from core.action_rules import INTENSITY_MODIFIERS
        return INTENSITY_MODIFIERS
    except ImportError:
        # Fallback list
        return {"slowly", "quickly", "gently", "forcefully", "violently", "cautiously",
                "carefully", "deliberately", "sharply", "abruptly", "heavily", "lightly",
                "firmly", "softly", "loudly", "silently", "steadily", "frantically",
                "wildly", "calmly", "briskly", "gracefully", "urgently"}


# ── LAYERED SFX VALIDATION ───────────────────────────────────────────────

def validate_sfx_layers(text: str) -> Tuple[str, List[str]]:
    """
    Validate SFX layering rules:
    - Max 1 primary SFX per action/sentence
    - Max 2 ambient SFX per paragraph
    
    Returns (corrected_text, list_of_warnings)
    """
    if not text or not text.strip():
        return text, []
    
    warnings = []
    paragraphs = text.split('\n\n')
    corrected_paragraphs = []
    
    for para in paragraphs:
        # Find all SFX in this paragraph
        sfx_matches = list(re.finditer(r'\(([^()]+)\)', para))
        
        ambient_count = 0
        primary_in_sentence = {}  # sentence_idx -> count
        
        # Split paragraph into sentences for primary SFX counting
        sentences = re.split(r'(?<=[.!?])\s+', para)
        
        for sfx_match in sfx_matches:
            sfx_text = sfx_match.group(1).strip()
            if sfx_text.lower() in _get_all_intensity_words():
                continue  # Skip intensity modifiers
            
            valid = get_valid_sfx(sfx_text)
            if valid is None:
                continue
            
            if is_ambient_sfx(valid):
                ambient_count += 1
            else:
                # Find which sentence this SFX belongs to
                pos = sfx_match.start()
                char_count = 0
                for sent_idx, sent in enumerate(sentences):
                    char_count += len(sent) + 1  # +1 for space
                    if pos < char_count:
                        primary_in_sentence[sent_idx] = primary_in_sentence.get(sent_idx, 0) + 1
                        break
        
        if ambient_count > 2:
            warnings.append(f"Paragraph has {ambient_count} ambient SFX (max 2)")
        
        for sent_idx, count in primary_in_sentence.items():
            if count > 1:
                warnings.append(f"Sentence has {count} primary SFX (max 1)")
        
        corrected_paragraphs.append(para)
    
    return '\n\n'.join(corrected_paragraphs), warnings


# ── FULL CINEMATIC SFX PASS ──────────────────────────────────────────────

def enforce_sfx_grammar(text: str) -> Tuple[str, List[str]]:
    """
    Run the complete cinematic SFX grammar pipeline:
    1. Expand prose sound descriptions to (sfx) markup
    2. Validate and fix all (parenthetical) SFX
    3. Validate SFX layering rules
    
    Returns (corrected_text, list_of_warnings)
    """
    if not text or not text.strip():
        return text, []
    
    # Step 1: Expand prose to SFX markup
    text = expand_sfx_markup(text)
    
    # Step 2: Validate SFX markup
    text = fix_sfx_markup(text)
    
    # Step 3: Validate layering
    text, warnings = validate_sfx_layers(text)
    
    return text, warnings


def get_sfx_rules_prompt_text() -> str:
    """Return the SFX Rules block for inclusion in AI prompts."""
    return """
SFX RULES (MANDATORY — MoviePrompterAI):
- ALL audible events MUST use (lowercase_underscore_format) markup.
- Use ONLY approved SFX from the whitelist. 
- NEVER use: character names, locations, dialogue, narrative phrases, emotions (silence, tension, drama, fear, anticipation, relief, music, score, mood, emotion).
- If sound is described in prose, convert to SFX markup:
  - Incorrect: "His boots crunch on broken glass."
  - Correct: "His [boots] *step* on broken glass (glass_crunch)."

LAYERED SFX SYSTEM:
- Primary SFX: Caused directly by character or object action. Max 1 per action.
  Examples: (glass_crunch), (metal_clang), (door_slam), (gunshot)
- Ambient SFX: Continuous environmental sound. Max 2 per paragraph. Use ambient_ prefix.
  Examples: (ambient_wind), (ambient_rain), (ambient_mill_creak), (ambient_dust_rattle)
- Ambient SFX must not dominate foreground action.

Approved SFX include: footsteps, running_footsteps, breathing, heavy_breathing, grunt, gasp, scream, whisper, metal_clang, metal_scrape, wood_creak, door_slam, glass_shatter, glass_crunch, chain_rattle, engine_start, engine_idle, engine_roar, engine_fail, rumble, alarm, siren, wind_howl, thunder, rain, fire_crackle, gravel_crunch, gunshot, explosion, impact_metal, blade_ring, beep, error_tone, heartbeat, water_splash, dripping_water, leaves_rustle, branch_snap, tire_screech, brakes_squeal, etc.
Ambient: ambient_wind, ambient_rain, ambient_forest, ambient_city, ambient_ocean, ambient_fire, ambient_machinery, ambient_cave, ambient_spaceship, ambient_storm, ambient_night, ambient_mill_creak, ambient_dust_rattle, etc.

Example (correct): (ambient_mill_creak) MILO *adjusts* the strap of his [headlamp] as he *steps* into the _Abandoned Mill_. His [boots] *step* on broken glass (glass_crunch). A cracked [tripod] *stands* in the corner (ambient_dust_rattle).
Example (incorrect): His boots crunch on broken glass. The mill creaks. A low hum fills the air.
"""
