# SceneWrite — Complete Application Documentation

A professional desktop application for creating screenplay storyboards with native support for 8 AI video generation platforms. SceneWrite bridges story ideation and AI video production with a structured workflow from premise to platform-ready prompts using a three-layer prompt architecture.

**Version:** 2.2  
**Python:** 3.10+  
**GUI:** PyQt6  
**AI Providers:** OpenAI, Anthropic, Together AI, OpenRouter, Hugging Face, Ollama Cloud, Local (Ollama, LM Studio), Custom  
**Video Platforms:** Higgsfield, Runway, Kling, Luma, Pika, OpenAI Sora, Google Veo, Minimax/Hailuo

---

## Table of Contents

1. [Architecture and Project Structure](#1-architecture-and-project-structure)
2. [Data Model Hierarchy](#2-data-model-hierarchy)
3. [Entity Markup Convention](#3-entity-markup-convention)
4. [Source-of-Truth Hierarchy](#4-source-of-truth-hierarchy)
5. [Complete Workflows](#5-complete-workflows)
6. [Character Identity vs Wardrobe](#6-character-identity-vs-wardrobe)
7. [Identity Blocks](#7-identity-blocks)
8. [Three-Layer Prompt Architecture](#8-three-layer-prompt-architecture)
9. [Multi-Shot Clustering](#9-multi-shot-clustering)
10. [Advertisement / Brand Film Mode](#10-advertisement--brand-film-mode)
11. [Episodic Series System](#11-episodic-series-system)
12. [Scene Pacing and Rhythm](#12-scene-pacing-and-rhythm)
13. [Environment Detection and Spatial Consistency](#13-environment-detection-and-spatial-consistency)
14. [Action Rules and SFX Rules](#14-action-rules-and-sfx-rules)
15. [Cinematic Grammar and Validation](#15-cinematic-grammar-and-validation)
16. [Workflow Profiles](#16-workflow-profiles)
17. [AI Integration](#17-ai-integration)
18. [Video Platform Integration](#18-video-platform-integration)
19. [UI Components](#19-ui-components)
20. [Export Formats](#20-export-formats)
21. [Configuration](#21-configuration)
22. [Update and Distribution](#22-update-and-distribution)
23. [Post-Generation Content Quality](#23-post-generation-content-quality)
24. [Known Limitations](#24-known-limitations)

---

## 1. Architecture and Project Structure

```
SceneWrite/
├── main.py                        # Application entry point (includes ScrollGuardFilter)
├── config.py                      # Configuration management (API keys, UI, platforms)
├── core/                          # Core business logic
│   ├── screenplay_engine.py       # Data models (Screenplay, StoryAct, StoryScene, StoryboardItem)
│   ├── ai_generator.py            # AI integration, prompt generation, entity extraction
│   ├── video_prompt_builder.py    # Three-layer prompt assembly (Keyframe/Identity/Video)
│   ├── platform_clients.py        # Platform-agnostic video generation API clients
│   ├── prompt_adapters.py         # Platform-specific prompt adapters and registry
│   ├── multishot_engine.py        # Multi-shot clustering, transitions, identity reinforcement
│   ├── higgsfield_exporter.py     # Export to JSON, CSV, Higgsfield API, Prompts
│   ├── cinematic_grammar.py       # Unified validation and auto-correction pipeline
│   ├── cinematic_token_detector.py # Real-time markup token detection for highlighting
│   ├── storyboard_validator.py    # Deterministic storyboard validation (entity mismatch, framing)
│   ├── sentence_integrity.py      # Broken sentence detection and AI-powered repair
│   ├── action_rules.py            # Action verb whitelist for *asterisk* markup
│   ├── sfx_rules.py               # SFX whitelist for (parenthetical) markup
│   ├── markup_whitelist.py        # Persistent user-extensible whitelist manager
│   ├── ad_framework.py            # Advertisement 6-beat template and validation
│   ├── series_bible.py            # Series Bible for episodic series (persistent characters, world, lore)
│   ├── series_manager.py          # Series lifecycle (create, load, episode generation)
│   ├── workflow_profile.py        # Wizard step and prompt structure by intent
│   └── __init__.py
├── ui/                            # User interface
│   ├── main_window.py             # Main window, menus, toolbar, dockable panels
│   ├── story_creation_wizard.py   # Multi-step story creation (Length/Intent → Premise → Outline → Framework)
│   ├── story_framework_view.py    # Tree view, tabs (Storyboard, Premise, Characters, Settings, Identity)
│   ├── storyboard_item_editor.py  # Full cinematic editor for individual storyboard items
│   ├── identity_block_manager.py  # Entity list, identity block editor, approval workflow
│   ├── story_settings_tab.py      # Per-project cinematic and platform settings
│   ├── series_bible_editor.py     # Series Bible editor (world context, episode duration, characters)
│   ├── higgsfield_panel.py        # Multi-platform video generation panel
│   ├── premise_dialog.py          # Premise creation (manual or AI-generated)
│   ├── settings_dialog.py         # AI config, UI config, platform API keys, whitelists
│   ├── help_dialogs.py            # Instructions, About, License dialogs
│   ├── ai_chat_panel.py           # AI Story Assistant — chat-driven editing, pacing analysis, toast feedback
│   └── __init__.py
├── ui/wizard_steps/               # Story Creation Wizard step pages
│   ├── length_intent_step.py      # Length, intent, and custom duration selection
│   ├── framework_generation_step.py # Framework generation with AI
│   └── ...
├── utils/
│   └── logger.py                  # Debug logging
└── config/                        # User whitelists (auto-created at install location)
    ├── ActionWhitelist.json
    └── SFXWhitelist.json
```

**Configuration files** (`config.json`) are stored in `%APPDATA%\SceneWrite` (Windows) / `~/.config/SceneWrite` (Linux) / `~/Library/Application Support/SceneWrite` (macOS) to survive application updates and reinstalls.

---

## 2. Data Model Hierarchy

```
Screenplay (Top Level)
├── title, premise, genre, atmosphere, story_length, intent, audio_strategy
├── custom_duration_seconds: Optional[int]     # User-specified total story duration
├── series_metadata: Optional[dict]            # Episodic series data (see §11)
│   ├── series_title, episode_number, episode_title, episode_premise
│   ├── series_bible_path, series_directory
│   └── previously_on (recap from previous episodes)
├── story_outline: { main_storyline, subplots, characters, conclusion }
├── story_structure
├── story_settings: {                       # Per-project platform and cinematic settings
│     generation_platform, video_model, image_model, aspect_ratio,
│     identity_lock_strength, visual_style, default_focal_length,
│     cinematic_beat_density, camera_movement_intensity,
│     prompt_output_format, max_clip_duration, enable_multishot, ...
│   }
├── character_registry: List[str]
├── character_registry_frozen: bool
├── identity_blocks: Dict[entity_id → identity_block_string]
├── identity_block_ids: Dict["type:name" → entity_id]
├── identity_block_metadata: Dict[entity_id → metadata]
├── brand_context: BrandContext              # For promotional workflows
├── acts: List[StoryAct]
│   └── StoryAct
│       ├── act_number, title, description, plot_points, character_arcs
│       └── scenes: List[StoryScene]
│           └── StoryScene
│               ├── scene_id, scene_number, title, description
│               ├── plot_point, character_focus, pacing, estimated_duration
│               ├── environment_id, environment_block
│               ├── compression_strategy    # "beat_by_beat", "montage", "atmospheric_hold"
│               ├── character_wardrobe      # Dict[entity_id → wardrobe description]
│               ├── multishot_clusters: List[MultiShotCluster]
│               ├── metadata: { generated_content, consistency_digest, ... }
│               └── storyboard_items: List[StoryboardItem]
│                   └── StoryboardItem
│                       ├── item_id, sequence_number, duration (1–30 sec)
│                       ├── storyline, image_prompt, prompt, visual_description
│                       ├── dialogue, camera_notes, scene_type
│                       ├── shot_type, camera_motion, focal_length, aperture_style
│                       ├── visual_style, mood, lighting
│                       ├── composition_blocking
│                       ├── cluster_id, shot_number_in_cluster
│                       ├── audio_intent, audio_notes, audio_source
│                       └── identity_drift_warnings
└── get_all_storyboard_items()  # Flat list of all items
```

### Identity Block Metadata (per entity)

```python
{
    "name": str,           # Entity name
    "type": str,           # "character" | "vehicle" | "object" | "environment" | "group"
    "scene_id": str,       # For environments (per-scene); "" for global entities
    "status": str,         # "placeholder" | "generating" | "approved" | "passive" | "referenced"
    "user_notes": str,     # Short description used for generation
    "identity_block": str, # Full 8-field block text
    "reference_image_prompt": str,
    "species": str,        # Character species (default "Human"); propagates to reference prompts
    # Environment-only:
    "extras_present", "extras_density", "extras_activities", "extras_depth",
    "foreground_zone", "is_primary_environment", "parent_vehicle",
    # Group-only:
    "member_count": int,           # Number of individuals in the group
    "individuality": str,          # "identical" | "slight" | "moderate" | "high"
    "uniform_description": str,    # Shared outfit/armor/equipment description
    "formation": str,              # How the group is arranged (e.g. "V-formation", "scattered")
    "linked_group_id": str,        # Links a character entity to its parent group
}
```

### Multi-Shot Cluster

```python
MultiShotCluster:
    cluster_id: str
    items: List[StoryboardItem]
    transitions: List[ShotTransition]
    total_duration: float
    generation_strategy: str  # "single_shot" | "multi_shot"

ShotTransition:
    from_item_id: str
    to_item_id: str
    transition_type: str      # "whip_pan", "match_cut", "dissolve", etc.
    overlap_seconds: float
```

### Wardrobe Variant

```python
WardrobeVariant:
    variant_id: str
    description: str
    reference_image_path: str
```

---

## 3. Entity Markup Convention

All generated and user-edited text must follow this markup:

| Entity Type   | Markup                | Example                                      |
|---------------|------------------------|----------------------------------------------|
| **Characters**| FULL CAPS             | MAYA RIVERA, ELIAS CROSS, REBECCA 'REX' STERN|
| **Locations** | _underlined_ Title Case | _Midnight Falls_, _City Hall_, _Common Area_ |
| **Objects**   | [brackets]            | [chair], [console], [weapon]                 |
| **Vehicles**  | {{braces}}            | {{motorcycle}}, {{Starfall Cruiser}}         |
| **Sound FX**  | (parentheses) lowercase | (metal_clang), (footsteps), (engine_fail)  |
| **Actions**   | *asterisks*           | *walks*, *reaches for*                       |

### Rules

- **Characters:** FULL CAPS only. Never underlined. Nicknames in single quotes: REBECCA 'REX' STERN.
- **Locations:** Title Case + underlined. Vehicle interiors (Bridge, Common Area) are locations, not vehicles.
- **Objects:** Only when a character directly interacts (sits on, holds, touches). Use [brackets].
- **Vehicles:** Exterior only. Interior spaces use _underscores_.
- **SFX:** Must match approved whitelist (see SFX Rules). Lowercase, underscore-separated.
- **Actions:** Must match approved action verb whitelist.

---

## 4. Source-of-Truth Hierarchy

Narrative consistency flows top-down. Lower layers must not contradict higher layers.

1. **Premise** — Core concept, genre, atmosphere
2. **Story Structure** — Scene summaries, plot points, character focus
3. **Scene Content** — Full prose with entity markup
4. **Storyboard** — Timed segments with three-layer prompts

If a conflict exists, the higher layer wins and lower content should be regenerated.

---

## 5. Complete Workflows

### 5.1 Workflow 1: AI-Generated Story (Story Creation Wizard)

**Step 1 — Length & Intent**

- Select story length: Micro | Short | Medium | Long | **Custom (specify duration)**
- Select story intent: General Story | Advertisement / Brand Film | Horror Short | Visual Art | Social Media | etc.
- Intent determines which wizard steps appear and how AI prompts are tuned
- Advertisement intent includes brand context fields
- **Custom duration:** When selected, the user enters a total target time (minutes and seconds). The AI automatically allocates appropriate durations to each scene and the per-scene duration selector is hidden. For episodic series, the custom duration persists across episodes via the Series Bible

**Step 2 — Premise (premise_step.py)**

- Select genres (checkboxes, 16 genres available)
- Select atmosphere/tone (dropdown, 15 options)
- Optional title
- Click "Generate Premise" → AI generates premise
- Edit if needed → Next

**Step 3 — Story Outline (story_outline_step.py)** (if required by workflow profile)

- AI generates: main_storyline, subplots, characters (name, outline, growth_arc), conclusion
- Edit or regenerate individual sections
- Character profiles auto-generated after conclusion
- Next

**Step 4 — Framework Generation (framework_generation_step.py)**

- AI creates acts and scenes from length spec (or from custom duration budget)
- Per scene: title, description, plot_point, character_focus, pacing, estimated_duration
- Pacing follows established filmmaking rhythm rules (see §12) with post-generation auto-correction
- When custom duration is active, scene durations are normalized to sum to the target total
- Finish → Screenplay with framework (no storyboard items yet)

### 5.2 Workflow 2: Manual Story Creation

- **File → New Story (Manual)**
- Enter title, premise, genres, atmosphere
- Set structure: number of characters, acts, scenes per act
- Creates empty framework with placeholders

### 5.3 Workflow 3: Quick Micro Story

- **File → Quick Micro Story** (Ctrl+M)
- Generates a complete micro-length story in one step
- Great for testing or rapid concept exploration

### 5.4 Workflow 4: Import from Text

- **File → Import Story from Text** (Ctrl+I)
- Load a novel or script from a text file
- AI analyzes the text and builds a screenplay structure

### 5.5 Workflow 5: Episodic Series

- **File → New Series** or convert an existing standalone story
- Creates a **Series Bible** (shared persistent data) and a series directory
- The Series Bible stores:
  - World context (setting, rules, lore)
  - Persistent characters (names, descriptions, identity blocks)
  - Recurring locations and props
  - Episode duration setting (for custom duration persistence)
  - Episode summaries and continuity notes
- **New Episode:** The wizard pre-fills series context (title, bible path, characters, duration)
- AI generation injects Series Bible data into prompts for continuity
- Episodes are saved as individual screenplay files within the series directory
- Standalone stories can be converted to series retroactively; the first story becomes episode 1
- The **Series Bible Editor** (UI) lets users edit world context, manage persistent characters, and set episode duration

### 5.6 Workflow 6: Scene Content Generation

- Select a scene in Framework View
- **Scene Content** tab: enter or edit scene description
- Click **Generate with AI** → AI generates full scene prose with entity markup
- Review and edit
- Click **Approve** → Triggers entity extraction and identity block creation

### 5.7 Workflow 7: Entity Extraction

When you **Approve** a scene or click **Re-extract Entities**:

1. **Characters:** Extract all FULL CAPS names (Wizard registry + scene-only)
   - Compound names are split at title boundary words (e.g., "MATTHEW COOPER MAYOR SARAH COOPER" → two characters)
   - Organization acronyms (NSA, FBI, BOLO, etc.) are filtered via a dedicated blocklist
   - Characters with shared title prefixes (MASTER REN, MASTER CHEN) are correctly deduplicated
2. **Groups:** FULL CAPS plural entities (e.g., IMPERIAL SOLDIERS) are classified as groups
   - Member count auto-extracted from scene content (e.g., "six soldiers" → 6)
   - Genre-aware uniform descriptions generated
   - Individuality setting determines physical variation among members
3. **Environments:** Extract _underlined_ locations
   - People-group phrases (e.g., _Temple Elders_) are filtered out using tail-word detection
   - Environments matching the scene description are prioritized as the primary environment
   - Descriptions are populated via rule-based extraction with AI-based fallback
   - Environments only mentioned in dialogue/visions/lore are marked as "Referenced" (no description extracted)
   - Outdoor environments exclude portable character props (tables, daggers, papers)
   - Substring filtering prevents environment name fragments from being extracted as separate entities (e.g., "Dying Light" is not extracted separately from "Temple of Dying Light")
4. **Objects:** Extract [brackets] (interactable only)
   - Recurring objects (appearing across multiple scenes) are flagged with 🔄 indicator
   - Notification shown to user listing recurring objects needing identity blocks
5. **Vehicles:** Extract {{braces}}
   - Vehicle interior detection from environment names (e.g., "Starfall Cruiser – Bridge")
   - Stale parent_vehicle relationships are cleared and re-validated
6. Create placeholder identity blocks for each
7. For characters: AI extracts physical appearance (user_notes) — **no clothing**
   - Species inference uses keyword maps with safeguards against false positives
   - For non-human characters (species ≠ Human): visual appearance extracted instead of wardrobe (translucent features, scales, wingspan, ethereal glow, etc.)
8. For characters: AI extracts **wardrobe** (clothing, accessories) → stored in `scene.character_wardrobe`
   - Regex fallback if AI extraction fails
   - Species passed to extraction for appropriate visual handling
9. For environments: Create MODE A (empty) or MODE B (with extras) based on scene

### 5.8 Workflow 8: Identity Blocks Management

- Go to **Identity Blocks** tab
- Left: Entity list (characters, vehicles, objects, environments) with status indicators
- Right: Editor for selected entity
- **User Notes:** Short description
- **Generate Identity Block** → AI expands to 8-field schema
- **Approve** → Mark as approved for use in prompts
- **Reference Image Prompt:** Generate or edit; upload reference images directly
- For environments: Configure extras (density, activities, depth, foreground zone)

### 5.9 Workflow 9: Storyboard Generation

- Select scene(s) in Framework View
- Click **Generate Storyboard for Scene**
- AI breaks scene into timed items with three-layer prompts
- Per item: keyframe prompt (static hero frame), identity prompt (auto-generated), video prompt (motion/action), dialogue, camera_notes
- Uses approved identity blocks + scene wardrobe in prompts
- If multi-shot clustering is enabled, compatible items are grouped into clusters

### 5.10 Workflow 10: Storyboard Editing

- Click item in the storyboard list
- **Storyboard Item Editor** opens with full cinematic controls
- Edit: duration, shot type, camera motion, focal length, aperture, visual style, mood, lighting
- Edit: storyline, composition/blocking, dialogue
- Manage image mapping: hero frame, end frame, entity reference slots
- View and edit three-layer prompts (Keyframe, Identity, Video, Platform)
- Regenerate individual prompt layers with AI
- View multi-shot cluster info if applicable

### 5.11 Workflow 11: Video Generation

- Open the Video Generation Panel (View → Show Higgsfield API)
- Panel syncs platform from Story Settings
- Enter API credentials for your platform
- Select model and duration
- Click **Generate All** or select specific items
- Monitor progress with real-time status tracking
- Retrieve image/video URLs when complete

### 5.12 Workflow 12: Export

- **File → Export**
- Formats: JSON, CSV, Higgsfield API, Prompts Only, Platform-Specific
- Exports all storyboard items with three-layer prompts, duration, metadata

---

## 6. Character Identity vs Wardrobe

SceneWrite separates **character identity** (global, immutable) from **wardrobe** (scene-level, mutable) to prevent visual drift.

### Character Identity (Global)

Stored in identity blocks. **Physical traits only** — no clothing.

- Face structure, hair color/style, eye color, skin tone
- Age range, build/body type
- Permanent features (scars, tattoos, glasses if permanent)

**Used for:** Canonical reference image (one per character) and Layer 2 (Identity Prompt).

### Character Wardrobe (Scene-Level)

Stored in `StoryScene.character_wardrobe` (entity_id → description).

- Clothing, accessories, armor, uniforms
- Condition (dirty, bloodstained, pristine)

**Used for:** Per-scene keyframe prompts ("Same character as reference; wearing [wardrobe]").

### Wardrobe Variants

Characters can have multiple wardrobe looks stored as `WardrobeVariant` objects, each with a description and optional reference image. The scene-level wardrobe selector picks which variant to use.

### Where to Edit

- **Identity Blocks tab:** Character identity (physical only)
- **Scene Content tab → Character Wardrobe:** Per-scene clothing for each character
- **Character Details tab:** Character profiles and growth arcs

### Validation

- Before storyboard generation: Warns if character identity contains clothing
- After generating identity block for character: Warns if output contains clothing

---

## 7. Identity Blocks

### 8-Field Universal Schema

Identity blocks are single flowing paragraphs with these 8 fields:

1. **Identity Lock Phrase** — Must start with "the same [entity_type] with..."
2. **Classification** — Type/category (adult human male, mid-size SUV, etc.)
3. **Physical Form & Silhouette** — Shape, proportions, size (for characters: exclude clothing)
4. **Surface & Material Behavior** — Color, texture, light reaction
5. **Key Identifying Features** — Distinct recognition elements
6. **Negative Constraints** — What is NOT present (no logos, no damage, etc.)
7. **Condition & State** — Clean, worn, pristine, etc.
8. **Style/Era/Design Language** — Modern, minimalist, utilitarian, etc.

### Entity Types

- **character** — Physical identity only; wardrobe in scene. Species-aware extraction for non-human characters.
- **group** — Collective characters sharing a visual identity (e.g. IMPERIAL SOLDIERS, TEMPLE GUARDS). Includes member count, individuality setting, uniform description, and formation. Genre-aware aesthetics (medieval for fantasy, tactical for sci-fi, etc.).
- **vehicle** — Exterior appearance
- **object** — Prop or interactable item. Recurring objects (appearing in multiple scenes) are flagged with 🔄 indicator.
- **environment** — Location/setting; supports extras (MODE B). Outdoor environments exclude portable character props.

### Environment Modes

- **MODE A:** Empty, no people
- **MODE B:** With extras (background figures) — extras_density, extras_activities, extras_depth, foreground_zone

### Environment Classification

- **Primary** — The scene takes place here; gets full description extraction
- **Referenced** — Mentioned in dialogue, carvings, visions, or lore but never physically visited. Marked with 👁 "Referenced" status. No description is extracted (prevents inheriting wrong environment descriptions).

### Status Workflow

Entities progress through: **Placeholder** → **Generating** → **Approved**

Additional statuses:
- **Passive** — Entity exists but is name-only (no identity block needed)
- **Referenced** — Environment mentioned but not visited (no description assigned)

### Reference Image Prompts

- **Characters:** Full body, neutral pose, plain background, "neutral generic clothing; clothing will vary by scene"
- **Vehicles:** 3/4 view, clean background
- **Objects:** Product-shot style
- **Environments:** Wide establishing, with or without extras

Reference images can be uploaded directly to entity slots in the Identity Block Manager or Storyboard Item Editor.

---

## 8. Three-Layer Prompt Architecture

SceneWrite generates prompts using a three-layer system designed for maximum quality and consistency:

### Layer 1: Keyframe Prompt (Hero Frame / "Popcorn")

Static first-frame description. No action verbs. Focuses on:
- Scene composition and character placement
- Character wardrobe (from scene-level wardrobe)
- Environment description
- Lighting and mood

### Layer 2: Identity Prompt (Soul ID)

Auto-generated from approved identity blocks. Provides:
- Character identity locks with 8-field descriptions
- Entity reference bindings (Image 1, Image 2, etc.)
- Identity lock strength (Relaxed / Standard / Strict)

This layer is read-only — it's automatically assembled from your approved identity blocks.

### Layer 3: Video Prompt (Motion / "Veo/Sora/Kling")

Camera movement and scene dynamics:
- Camera motion type and parameters
- Character actions and movements
- Dialogue delivery
- Scene transitions

### Platform Adaptation

The three layers are combined and reformatted by platform-specific adapters:

| Platform   | Adaptation Style                                          |
|------------|-----------------------------------------------------------|
| Higgsfield | Native three-layer pass-through                          |
| Runway     | Prose-style combined prompt, headers stripped             |
| Pika       | Concise comma-separated style tokens                     |
| Kling      | Natural-language scene description                       |
| Sora       | Cinematic description with shot type and focal length    |
| Veo        | Descriptive prose                                         |
| Minimax    | Keyword-rich single prompt                                |
| Luma       | Scene-focused prompt                                      |

### Visual Style Directives

Visual style (Photorealistic, Comic Book, Anime, etc.) injects style-specific instructions into the prompt assembly to ensure consistent visual language.

---

## 9. Multi-Shot Clustering

The multi-shot engine groups consecutive storyboard items into single video clips for AI platforms that support multi-shot generation.

### How It Works

1. **Strategy resolution:** Determines single-shot vs multi-shot per item
2. **Compatibility check:** Adjacent items must share the same environment and have overlapping characters
3. **Cluster building:** Compatible items are grouped into `MultiShotCluster` objects
4. **Transition generation:** `ShotTransition` objects created between shots (whip pan, match cut, dissolve, etc.)
5. **Identity reinforcement:** Identity-lock snippets built for all entities in the cluster
6. **Prompt formatting:** Consolidated multi-shot prompt generated for the cluster

### Configuration

- Enable in Story Settings → Multi-Shot Clustering (Higgsfield only)
- The engine respects `model_settings.supports_multishot`
- `calculate_multishot_render_cost()` estimates rendering complexity
- `validate_cluster()` ensures cluster integrity

### Fallback

If clustering fails validation, `_revert_to_single_shot()` resets the scene to individual items.

---

## 10. Advertisement / Brand Film Mode

Selecting "Advertisement / Brand Film" as the story intent activates a structured commercial workflow.

### 6-Beat Commercial Template

| Beat | Label            | Purpose                                      |
|------|------------------|----------------------------------------------|
| 1    | Hook             | Attention-grabbing opening                   |
| 2    | Pain/Desire      | Establish the problem or aspiration          |
| 3    | Product Reveal   | Introduce the product/brand                  |
| 4    | Feature Demo     | Show the product in action                   |
| 5    | Emotional Payoff | Deliver the emotional resolution             |
| 6    | Brand Moment     | Logo, tagline, call to action                |

### Brand Context

Configured in the wizard or Premise tab:
- Product description, core benefit
- Brand personality (maps to visual style guidance)
- Target audience
- Distribution platform presets (social media, TV, etc.)

### Validation

- `validate_ad_structure()` — Checks 6-beat sequence
- `validate_hero_shot()` — Ensures product hero shot is present
- `validate_escalation()` — Warns about flat pacing
- `check_narrative_complexity()` — Ensures narrative stays within ad-mode limits
- `validate_pre_generation()` — Full validation suite before generation

### Prompt Guidance

- `build_ad_framework_prompt()` — AI prompt for ad framework generation
- `build_ad_scene_content_guidance()` — Injects ad rules into scene content generation
- `build_ad_storyboard_guidance()` — Injects ad rules into storyboard generation

---

## 11. Episodic Series System

SceneWrite supports multi-episode stories that share persistent characters, world settings, and lore while allowing each episode to tell a self-contained storyline.

### Series Bible

The **Series Bible** (`core/series_bible.py`) is a JSON file that acts as the central data store for shared narrative elements:

| Field                    | Description                                                     |
|--------------------------|-----------------------------------------------------------------|
| `series_title`           | Title of the overall series                                    |
| `world_context`          | Setting description, rules, lore, and world-building notes     |
| `persistent_characters`  | Characters that appear across episodes (names, descriptions, identity blocks) |
| `recurring_locations`    | Locations that recur across episodes                           |
| `recurring_props`        | Objects/vehicles that recur across episodes                    |
| `episode_summaries`      | Per-episode summaries for continuity reference                 |
| `episode_duration_seconds` | Custom duration setting that persists across all episodes    |
| `continuity_notes`       | Free-form notes for maintaining consistency                    |

### Series Manager

The **Series Manager** (`core/series_manager.py`) orchestrates the series lifecycle:

- **Create Series:** Initialize a series directory and Series Bible from scratch
- **Convert Standalone:** Turn an existing standalone story into episode 1 of a new series
- **New Episode:** Create a new episode with pre-populated series context, characters, and duration
- **Load Series:** Open an existing series and browse its episodes

### Continuity in AI Generation

When generating content for an episode, the AI receives injected context from the Series Bible:
- Persistent character descriptions and identity blocks
- World context and lore
- "Previously on..." summaries from prior episodes
- Recurring location and prop references

This ensures narrative consistency across episodes while allowing fresh storylines.

### Backward Compatibility

Existing standalone stories work identically — the `series_metadata` field is `None` for non-series screenplays, and all series-aware code paths check for this before activating.

---

## 12. Scene Pacing and Rhythm

SceneWrite enforces established filmmaking pacing conventions to create natural story rhythm.

### Pacing Values

Each scene is assigned one of three pacing levels: **Fast**, **Medium**, or **Slow**.

### Framework Generation Rules

The AI follows these rules when generating story frameworks:

| Act        | Recommended Pattern                                    |
|------------|--------------------------------------------------------|
| Act 1 (Setup)       | Medium → Medium → Fast (build to inciting incident) |
| Act 2 (Confrontation) | Fast → Medium → Fast → Slow → Medium → Fast (alternation with breathers) |
| Act 3 (Climax)      | Medium → Fast → Fast → Medium/Slow (build, climax, resolution) |

**Hard limits:**
- Never more than 2 consecutive Fast scenes
- Never more than 2 consecutive Slow scenes
- Overall distribution target: 30–50% Medium, 25–40% Fast, 15–30% Slow

**Pacing by scene type:**
- Establishing/introduction → Medium or Slow
- Dialogue-heavy → Medium or Slow
- Action/chase/fight → Fast
- Emotional reveals → Medium
- Climax → Fast
- Resolution/denouement → Medium or Slow

### Post-Generation Validation

After the AI generates a framework, `_validate_and_fix_pacing()` automatically corrects violations:
- First scene forced to Medium/Slow (not Fast — setup needs room)
- Last scene forced to Medium/Slow (resolution needs room)
- Any run of 3+ consecutive same-pacing scenes is broken up

### AI Chat Panel — Full Capabilities

The AI Story Assistant is a context-aware conversational interface that can both discuss and directly modify every major element of a screenplay. It supports **14 change intents**:

| Intent | What it does |
|--------|-------------|
| `discuss` | Answer questions, give feedback — no changes |
| `regenerate_scene` | Replace or regenerate scene narrative content |
| `edit_scene` | Edit scene properties (title, description, duration, character focus) |
| `regenerate_items` | Regenerate selected storyboard items |
| `edit_items` | Edit selected storyboard item properties |
| `add_items` | Add new storyboard items to the current scene |
| `remove_items` | Remove selected storyboard items |
| `edit_character_outline` | Edit a character's outline and/or growth arc in the story outline |
| `edit_premise` | Edit the story's title, premise, genres, or atmosphere |
| `edit_story_outline` | Edit the main storyline, subplots, or conclusion |
| `regenerate_framework` | Regenerate the entire act/scene structure (destructive — double-confirmed) |
| `edit_series_bible` | Edit Series Bible world context (setting, time period, lore, tone) |
| `edit_identity_block` | Edit an entity's identity block description/notes |
| `approve_identity_block` | Approve an entity's identity block |

**Proactive analysis panel** detects:
- Consecutive runs of 3+ same-pacing scenes (with exact scene numbers)
- Overall distribution imbalances (>60% Fast or >50% Slow)
- Pending identity blocks that need review
- Characters missing outlines

**Visual feedback:** Every applied change triggers a toast notification overlay at the top of the main window (auto-dismisses after 4 seconds) in addition to the status bar message.

---

## 13. Environment Detection and Spatial Consistency

SceneWrite uses multiple layers to ensure environments are correctly detected, described, and respected during scene generation.

### Environment Change Detection

When generating scene content, the system determines whether the environment has changed from the previous scene:

1. **Primary check:** Compare `environment_id` between current and previous scene
2. **Description cross-check:** Extract `_underscored_` locations from both scene descriptions and compare — if descriptions name different locations, `environment_changed` is forced to `True` even if stale IDs match
3. **Regeneration handling:** `environment_id` is cleared at the start of entity extraction so regenerated scenes get a fresh assignment

### Environment Description Extraction

When a new environment is detected, its description is populated in three ways:
1. **Rule-based extraction** from scene content (regex patterns around the `_underscored_` location name)
2. **AI-based fallback** if rule-based extraction returns empty (uses `_extract_environment_from_content`)
3. **Scene description match priority:** Environments whose names appear in the scene description are prioritized as the primary environment

### Referenced vs Primary Environments

Environments are classified during entity extraction:
- **Primary:** Appears in the scene description, establishing paragraph, or non-dialogue action paragraphs. Gets full description extraction and MODE A/B assignment.
- **Referenced:** Only mentioned in dialogue, carvings, visions, or lore. Marked with `status="referenced"` and skipped for description extraction. This prevents referenced environments from inheriting the current scene's description (e.g., "Veil Between Worlds" mentioned in carvings doesn't get "Ashen Vale" description).

### Outdoor Environment Protection

Environment identity block generation distinguishes indoor from outdoor settings:
- **Indoor** environments include built-in furniture, fixtures, and architectural details
- **Outdoor** environments (fields, wastelands, ruins, plains, forests) describe only terrain, vegetation, sky, weather, and geological features
- Portable objects that characters carry (daggers, journals, papers, compasses) are excluded from outdoor environment descriptions

### Established Environment Injection

All environment identity blocks (descriptions, user notes) are injected into scene content prompts under an "ESTABLISHED ENVIRONMENTS" section. The AI receives the full physical description of every known location, with the current scene's location explicitly labeled.

### Spatial Consistency Rules

The scene content prompt includes strict spatial constraints:
- **No invented spaces:** The AI cannot add rooms, floors, levels, balconies, cliffs, or other areas not in the established environment description
- **No mid-scene relocation** unless the scene summary explicitly says characters move
- **Fight/action containment:** Action sequences must stay within the described physical boundaries
- **"Expanding descriptively"** means adding sensory detail (textures, sounds, smells) to *existing* spaces, not inventing new architecture

### Physical Access and Zone Logic

Characters are tracked by zone (inside/outside, specific room/area) paragraph by paragraph:
- A character can only interact with surfaces and features reachable from their current zone
- Moving between zones requires an explicit written transition (walks through door, steps inside, climbs through window, etc.)
- The AI cannot have a character interact with interior features while positioned outside, or vice versa

### Held-Object Continuity

Characters' hand-held objects are tracked throughout the scene:
- A character holding one object must visibly put it down before using another
- Two-handed objects require both hands
- Objects set down must be picked up again before reuse

---

## 14. Action Rules and SFX Rules

### Action Rules (action_rules.py)

- **Whitelist:** CHARACTER_ACTIONS, OBJECT_ACTIONS, VEHICLE_ACTIONS, ENVIRONMENTAL_ACTIONS, CAMERA_ACTIONS
- **Forbidden:** feel, think, realize, decide, hope, fear, etc. (internal/emotional)
- Used for *asterisk* action markup validation and normalization

### SFX Rules (sfx_rules.py)

- **Whitelist:** HUMAN_SFX, OBJECT_SFX, VEHICLE_SFX, ENVIRONMENTAL_SFX, WEAPON_SFX, ELECTRONIC_SFX
- **Forbidden:** silence, tension, drama, music, mood, etc.
- Format: (lowercase_underscore_separated)
- Used for (parenthetical) sound markup validation

### Custom Whitelists (markup_whitelist.py)

- User-added action verbs saved to `config/ActionWhitelist.json`
- User-added SFX saved to `config/SFXWhitelist.json`
- Merged at runtime with built-in frozensets
- Manageable via Settings → AI Config → Whitelists tab or right-click context menu in scene editor

### expand_sfx_markup / fix_sfx_markup

- Expands prose like "the hum of" → "(hum)"
- Validates and normalizes SFX to whitelist

---

## 15. Cinematic Grammar and Validation

### Cinematic Grammar Engine (cinematic_grammar.py)

Unified validation and auto-correction pipeline:

1. SFX expansion (prose → markup)
2. Action grammar validation
3. SFX whitelist validation
4. Final violation detection
5. Auto-correction of violations

`get_cinematic_grammar_prompt_text()` returns comprehensive rules for AI prompt injection.

### Cinematic Token Detector (cinematic_token_detector.py)

Real-time line-level detection for the QSyntaxHighlighter:

- **unknown_action:** Word matches action whitelist but isn't inside *...* markup
- **unknown_sfx:** Word matches SFX whitelist but isn't inside (...) markup
- **unknown_identity:** Capitalized phrase that looks like a proper noun but has no markup

Tokens are highlighted in the scene editor with suggestions to mark them up or add to whitelists.

### Storyboard Validator (storyboard_validator.py)

Deterministic, rule-based validation (no AI calls):

- Entity extraction from paragraphs and storyboard items using markup regex
- Entity set comparison: missing, extra, wrong environment, cross-paragraph contamination
- Dominant action verb extraction per paragraph
- Camera framing suggestions based on dominant action
- **Beat-aware shot and motion inference** (`infer_shot_and_motion_from_beat`) — analyses paragraph content to select `shot_type` and `camera_motion` keys based on action verbs, dialogue structure, character count, and environmental context
- Dialogue-aware validation: dialogue paragraphs only require the speaking character (close-up shots don't fail for missing nearby characters)
- Full validation pass across all paragraph/item pairs

### Sentence Integrity Validator (sentence_integrity.py)

Detects and repairs broken sentences from AI word-dropping artifacts:

- Missing verbs, subjects, or objects
- Truncated phrases and dangling articles
- Orphaned adverbs
- Heuristic detection + AI-powered repair

---

## 16. Workflow Profiles

**WorkflowProfileManager** determines wizard steps and prompts by intent:

| Intent                      | Profile      | Story Outline | Characters |
|-----------------------------|--------------|---------------|------------|
| General Story               | NARRATIVE    | Yes           | Yes        |
| Advertisement / Brand Film  | PROMOTIONAL  | Simplified    | Optional   |
| Social Media / Short-form   | NARRATIVE    | Yes           | Yes        |
| Visual Art / Abstract       | EXPERIMENTAL | Simplified    | Optional   |

**Promotional** workflows use brand_context (product_description, core_benefit, brand_personality, etc.).

---

## 17. AI Integration

### Providers (for story/content generation)

- OpenAI, Anthropic (Claude), Together AI, OpenRouter, Hugging Face
- Ollama Cloud (cloud-hosted Ollama instances)
- Local: Ollama, LM Studio (configurable base_url)
- Custom: Any OpenAI-compatible endpoint

All providers use the OpenAI Chat Completions API format (/v1/chat/completions).

### Key AI Operations

| Operation                            | Purpose                                              |
|--------------------------------------|------------------------------------------------------|
| generate_premise                     | Create premise from genre/atmosphere                |
| generate_story_outline               | Main storyline, subplots, characters, conclusion    |
| generate_story_framework             | Acts, scenes, descriptions (with pacing rhythm)     |
| generate_scene_content               | Full scene prose with entity markup, spatial rules  |
| generate_scene_storyboard            | Break scene into storyboard items with 3-layer prompts |
| generate_episode_summary             | Summarize an episode for Series Bible continuity    |
| generate_identity_block_from_notes   | Expand user notes to 8-field block                  |
| _generate_identity_block_from_scene  | Extract identity from scene text                    |
| extract_character_appearance_from_scene | Physical traits for user_notes (no clothing)      |
| extract_character_wardrobe_from_scene | Clothing/accessories (human) or visual appearance (non-human) |
| generate_reference_image_prompt      | Reference image prompt for any entity              |
| regenerate_image_prompt              | Regenerate composition prompt for item             |
| regenerate_storyboard_items          | Regenerate items based on chat discussion          |
| chat_about_story                     | AI Story Assistant — 14-intent chat engine (see AI Chat Panel) |
| _validate_and_fix_pacing             | Auto-correct pacing violations post-framework gen  |
| _normalize_scene_durations           | Scale scene durations to match custom total budget |
| _build_series_context_for_prompt     | Inject Series Bible data into AI prompts           |
| _validate_genre_compliance           | Ensure objects/descriptions match story genre      |
| _validate_no_invented_backstory      | Prevent AI from inventing backstory through dialogue |
| _validate_no_invented_abilities      | Catch unestablished character powers/abilities      |
| _fix_held_object_continuity          | Track and fix hand-held object logic per scene     |
| _deduplicate_dialogue                | Remove duplicated dialogue within paragraphs       |
| _strip_ai_preamble                   | Remove AI meta-text ("Here's the scene...")        |
| _detect_identity_drift               | Compare prompts against identity blocks for drift  |
| infer_shot_and_motion_from_beat      | Beat-aware shot type and camera motion selection   |

### Threading

- Long operations run in QThread to avoid UI blocking
- Progress dialogs shown during generation

---

## 18. Video Platform Integration

### Platform Clients (platform_clients.py)

Unified interface (`GenerationProvider` ABC) for submitting video generation requests:

| Platform   | Auth          | Models                                        | Max Duration | Special Features        |
|------------|---------------|-----------------------------------------------|--------------|-------------------------|
| Higgsfield | Key + Secret  | Default Higgsfield models                     | 30s          | Multi-shot, identity lock |
| Runway     | API Key       | gen4.5, gen4_turbo, gen4_aleph               | 10s          |                         |
| Sora       | API Key       | sora-2, sora-2-pro                           | 12s          | Duration presets        |
| Kling      | API Key       | o3-pro, o3-std, kling-3.0-pro/std, kling-2.6-pro | 10s     |                         |
| Luma       | API Key       | ray-2, ray-flash-2                           | 10s          | Loop mode               |
| Veo        | API Key       | veo-3.1-generate/fast, veo-3.0-generate/fast | 8s           | Duration presets        |
| Pika       | API Key (fal) | pika-2.5, pika-2.2                           | 10s          | Motion strength (1-5)   |
| Minimax    | API Key       | hailuo-2.3, hailuo-02                        | 10s          | Duration presets        |

Each provider supports:
- `submit_text_to_video()` — Text-to-video generation
- `submit_image_to_video()` — Image-to-video generation
- `poll_status()` — Check request status
- `cancel()` — Cancel pending requests (where supported)

### Prompt Adapters (prompt_adapters.py)

Each platform has a `PromptAdapter` subclass that converts three-layer prompts to platform-optimized format. Adapters expose capability metadata:

- `video_models`, `image_models`
- `supports_image_generation`, `supports_multishot`, `supports_identity_lock`
- `max_duration`, `duration_presets`, `supported_aspect_ratios`
- `api_base_url`, `api_auth_type`, `config_key`

### Video Generation Panel (higgsfield_panel.py)

Dockable panel for direct API submission:
- Dynamic platform sync from Story Settings
- Per-platform credential management
- Segment table with status tracking (Queued → Submitting → Polling → Completed/Failed)
- Background generation threads
- Cancel support
- Result URLs with copy-to-clipboard

---

## 19. UI Components

### Main Window

- **Menu:** File (New AI/Manual/Quick Micro, New Series, Open, Import from Text, Recent Stories, Save, Save As, Export, Exit), View (AI Chat, Higgsfield API), Settings (AI Config, UI Config, Story Settings), Help (Instructions, About, License)
- **Toolbar:** New, Open, Save, Export
- **Central:** Story Framework View (5 tabs)
- **Dock Panels:** AI Chat Panel, Video Generation Panel
- **Status Bar:** Story statistics
- **Scroll Guard:** Global event filter prevents accidental scroll-wheel changes on dropdowns (`QComboBox`) and spin boxes (`QAbstractSpinBox`) throughout the UI

### Story Framework View (5 tabs)

1. **Storyboard:** Acts/Scenes tree + scene editor + storyboard items list
2. **Premise:** Title, premise, genres, atmosphere, length, intent editing
3. **Character Details:** Character list, profiles, physical appearance, growth arc
4. **Story Settings:** Platform, cinematic controls, audio generation (StorySettingsTab)
5. **Identity Blocks:** Entity management (IdentityBlockManager)

### Storyboard Item Editor

Full-featured dialog with sections:
- **Scene Setup:** Duration, scene type, shot type (10 options), camera motion (16 options), focal length, aperture, visual style, mood, lighting. Shot type and camera motion are automatically set per beat based on paragraph content (dialogue → close-up, spatial action → tracking, tension → low angle push-in, etc.) and can be overridden via dropdowns.
- **Storyline:** Storyline text, composition/blocking, dialogue
- **Image Mapping:** Hero frame, end frame, 3 entity reference slots, entity tags, validation
- **Prompt Layers:** Keyframe, Identity (read-only), Video, Platform (read-only), with copy buttons
- **Audio:** Intent, notes, source
- **Multi-Shot:** Cluster info (if enabled)

### Identity Block Manager

- **Left panel:** Entity tree by type (Characters, Groups, Vehicles, Objects, Environments) with status icons (⚠ Pending, ✓ Approved, ⏳ Generating, 🔗 Linked, 👁 Referenced, ◇ Passive, 🔄 Recurring), search/filter, scene filter
- **Right panel:** Entity info, environment extras (if environment), group settings (if group: member count, individuality, formation), user notes, generated identity block, approval, reference image prompt, reference image upload

### Story Settings Tab

- Platform selector, video/image model
- Cinematic controls: multi-shot, clip duration, aspect ratio, visual style, focal length, identity lock strength, beat density, camera intensity, prompt format
- Platform-specific options (Pika motion strength, Luma loop, duration presets)
- Audio generation (dialogue mode, SFX density, music strategy)

### Settings Dialog

- **AI Settings tab:** Provider, base URL, API key, model, temperature, max tokens, platform API keys (8 platforms), connection test
- **UI Settings tab:** Theme, font size, line numbers, auto-save interval
- **Whitelists tab:** Custom action verbs, custom SFX (add/remove)

### Other UI

- **Story Creation Wizard:** 3-4 step wizard (Length/Intent → Premise → Outline → Framework) with custom duration input and episodic series support
- **Premise Dialog:** Manual entry or AI generation (16 genres, 15 atmospheres)
- **AI Chat Panel:** Full-featured AI Story Assistant supporting 14 change intents (see below); Apply/Preview/Dismiss suggestions; pacing and identity-block analysis; toast notifications on change application
- **Series Bible Editor:** Dedicated editor for managing world context, persistent characters, episode duration, and continuity notes
- **Help Dialogs:** Instructions, About, License

---

## 20. Export Formats

### JSON (Three-layer prompts)

- title, premise, genre, atmosphere
- total_duration_seconds, item_count
- storyboard: array of { sequence, duration_seconds, keyframe_prompt, identity_prompt, video_prompt, visual_description, scene_type, dialogue, camera_notes, shot_type, camera_motion, focal_length, audio_* }

### CSV

- One row per storyboard item
- Columns: Sequence, Duration, Keyframe Prompt, Video Prompt, Dialogue, Scene Type, etc.

### Prompts Only

- Text file: KEYFRAME: ... / IDENTITY: ... / VIDEO: ... per item

### Higgsfield API Format

- project_name, metadata, video_segments
- Each segment: segment_number, duration, image_prompt, video_prompt, model_id, settings

### Platform-Specific Export

- Uses the selected platform's prompt adapter to format prompts
- Includes platform-optimized prompt text per item

---

## 21. Configuration

### Config File Location

Configuration is stored in the user's platform-specific application data directory, **not** alongside the executable:

| Platform | Path                                          |
|----------|-----------------------------------------------|
| Windows  | `%APPDATA%\SceneWrite\config.json`            |
| macOS    | `~/Library/Application Support/SceneWrite/config.json` |
| Linux    | `~/.config/SceneWrite/config.json`            |

This ensures settings (API keys, model preferences, UI options) survive application updates and reinstalls.

**Migration:** On first launch after an update, if `config.json` exists in the old install directory but not yet in AppData, it is automatically copied over. The old file is left in place for rollback compatibility.

**config.json:**

```json
{
  "ai_provider": "OpenAI" | "Anthropic" | "Together AI" | "OpenRouter" | "Hugging Face" | "Ollama Cloud" | "Local" | "Custom",
  "api_key": "...",
  "base_url": "...",
  "model": "...",
  "temperature": 0.7,
  "max_tokens": 4000,
  "platform_api_keys": {
    "higgsfield_key": "...",
    "higgsfield_secret": "...",
    "runway_key": "...",
    "openai_sora_key": "...",
    "kling_key": "...",
    "luma_key": "...",
    "google_veo_key": "...",
    "pika_key": "...",
    "minimax_key": "..."
  },
  "ui_settings": {
    "theme": "light" | "dark",
    "font_size": 12,
    "show_line_numbers": true,
    "auto_save_interval": 300
  },
  "custom_species": [],
  "recent_files": []
}
```

**Environment:** `OPENAI_API_KEY` can override config.

**Per-Project Settings** (stored in screenplay file):

```json
{
  "generation_platform": "higgsfield",
  "video_model": "...",
  "image_model": "...",
  "aspect_ratio": "16:9",
  "visual_style": "photorealistic",
  "default_focal_length": 35,
  "identity_lock_strength": "standard",
  "enable_multishot": false,
  "max_clip_duration": 10,
  "cinematic_beat_density": "balanced",
  "camera_movement_intensity": "subtle",
  "prompt_output_format": "cinematic_script"
}
```

---

## 22. Update and Distribution

### In-Place Upgrades

The Inno Setup installer (`installer.iss`) supports seamless in-place upgrades:

- **`UsePreviousAppDir=yes`** — Installer reuses the previous installation directory
- **`CloseApplications=yes`** — Automatically closes the running app before overwriting files
- **`RestartApplications=no`** — User manually relaunches after update
- **Versioned installer filename** — `SceneWrite_Setup_{version}.exe` for clear version identification

Users run the new installer to update — no uninstall required. Configuration is preserved because it lives in AppData (see §21).

### Config Preservation

The config migration system (`_migrate_config_to_appdata()` in `config.py`) handles the transition:
1. On module import, checks if `config.json` exists in the install directory but not in AppData
2. If so, copies it to AppData (one-time migration)
3. All subsequent reads/writes use the AppData location
4. Old config file left in place so older versions still work if rolled back

### Default Stories Directory

Stories are saved to `~/Documents/SceneWrite Stories` by default via `get_stories_directory()`.

---

## 23. Post-Generation Content Quality

SceneWrite applies multiple automated validation and correction passes after AI generates scene content.

### Automated Post-Processing Pipeline

After scene content generation, these corrections run in order:

| Pass | Function | Purpose |
|------|----------|---------|
| 1 | `_strip_ai_preamble` | Remove AI meta-text ("Here's the scene...") and collapse `[N] [N]` tags |
| 2 | `_repair_sentence_integrity` | Detect and fix broken sentences from AI word-dropping |
| 3 | `_validate_genre_compliance` | Ensure objects/descriptions match the story's genre |
| 4 | `_validate_no_invented_abilities` | Catch characters displaying unestablished powers |
| 5 | `_validate_no_invented_backstory` | Prevent AI from inventing lore through dialogue |
| 6 | `_fix_held_object_continuity` | Track hand-held objects and fix continuity errors |
| 7 | `_deduplicate_dialogue` | Remove duplicated dialogue within quoted strings |
| 8 | `_sanitize_paragraph_tags` | Fix doubled tags, renumber sequentially |

### Identity Drift Detection

When storyboard items are generated, `_detect_identity_drift` compares each prompt against approved identity blocks:

- **Hair color:** Uses synonym groups (auburn/red/ginger/copper, grey/silver/white, blonde/blond, brown/brunette) and context awareness (only flags colors near hair-related words like "hair", "locks", "braid")
- **Clothing:** Basic check for wardrobe inconsistencies when identity blocks are present

### Cross-Scene Continuity

After all post-processing, `_check_cross_scene_continuity` warns if characters couldn't plausibly be in their current scene based on their last known location.

### Premise Variety

The `_generate_diverse_premise` mechanism tracks previously generated themes and includes an "AVOID THESE" instruction when regenerating premises, ensuring each regeneration produces a genuinely different concept.

### Prompt Length Management

Each video platform has maximum prompt lengths. The prompt adapter system (`prompt_adapters.py`) handles:
- Deduplication of repeated phrases across prompt layers
- Truncation to platform-specific limits while preserving key content
- Section header stripping for space efficiency

---

## 24. Known Limitations

- Windows-focused (PyInstaller builds .exe)
- Requires AI API key or local AI server for story generation
- Requires platform API keys for direct video generation
- Large frameworks (Long tier) can take significant time
- Single-user; no collaboration
- Multi-shot clustering currently Higgsfield-only
- Export formats are fixed; no custom templates

---

*End of Documentation*
