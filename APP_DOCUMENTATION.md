# MoviePrompterAI — Complete Application Documentation

A professional desktop application for creating screenplay storyboards optimized for higgsfield.ai video generation. MoviePrompterAI bridges story ideation and AI video production with a structured workflow from premise to detailed video prompts.

**Version:** 2.0  
**Python:** 3.10+  
**GUI:** PyQt6  
**AI Providers:** OpenAI, Together AI, OpenRouter, Hugging Face, Local (Ollama, LM Studio)

---

## Table of Contents

1. [Architecture and Project Structure](#1-architecture-and-project-structure)
2. [Data Model Hierarchy](#2-data-model-hierarchy)
3. [Entity Markup Convention](#3-entity-markup-convention)
4. [Source-of-Truth Hierarchy](#4-source-of-truth-hierarchy)
5. [Complete Workflows](#5-complete-workflows)
6. [Character Identity vs Wardrobe](#6-character-identity-vs-wardrobe)
7. [Identity Blocks](#7-identity-blocks)
8. [Action Rules and SFX Rules](#8-action-rules-and-sfx-rules)
9. [Workflow Profiles](#9-workflow-profiles)
10. [AI Integration](#10-ai-integration)
11. [UI Components](#11-ui-components)
12. [Export Formats](#12-export-formats)
13. [Configuration](#13-configuration)
14. [Higgsfield.ai Integration](#14-higgsfieldai-integration)

---

## 1. Architecture and Project Structure

```
MoviePrompterAI/
├── main.py                 # Application entry point
├── config.py               # Configuration management
├── config.json             # API keys, AI provider, UI settings
├── core/                   # Core business logic
│   ├── screenplay_engine.py   # Data models (Screenplay, StoryAct, StoryScene, StoryboardItem)
│   ├── ai_generator.py        # AI integration, prompt generation, entity extraction
│   ├── higgsfield_exporter.py # Export to JSON, CSV, prompts
│   ├── action_rules.py        # Action verb whitelist for *asterisk* markup
│   ├── sfx_rules.py           # SFX whitelist for (parenthetical) markup
│   ├── spell_checker.py       # Spell checking for text fields
│   ├── snapshot_manager.py    # Version history snapshots
│   └── workflow_profile.py    # Conditional workflows (narrative, promotional, etc.)
├── ui/                     # User interface
│   ├── main_window.py         # Main window, menus, central widget
│   ├── story_creation_wizard.py  # Multi-step story creation
│   ├── story_framework_view.py   # Tree view, tabs, scene content, wardrobe
│   ├── storyboard_timeline.py    # Card-based storyboard view
│   ├── storyboard_item_editor.py # Edit individual storyboard items
│   ├── identity_block_manager.py # Manage entity identity blocks
│   ├── premise_dialog.py        # Premise creation/generation
│   ├── settings_dialog.py       # AI config, theme, font
│   ├── ai_chat_panel.py         # Context-aware AI chat
│   ├── scene_framework_editor.py
│   ├── help_dialogs.py
│   └── wizard_steps/
│       ├── premise_step.py          # Step 1: Premise
│       ├── story_outline_step.py    # Step 2: Story outline
│       ├── length_intent_step.py
│       └── framework_generation_step.py  # Step 3: Framework
└── utils/
    └── logger.py
```

---

## 2. Data Model Hierarchy

```
Screenplay (Top Level)
├── title, premise, genre, atmosphere, story_length, intent, audio_strategy
├── story_outline: { main_storyline, subplots, characters, conclusion }
├── story_structure
├── character_registry: List[str]       # Canonical character names (Wizard)
├── character_registry_frozen: bool     # When true, only registry names get identity blocks
├── identity_blocks: Dict[entity_id -> identity_block_string]
├── identity_block_ids: Dict["type:name" -> entity_id]
├── identity_block_metadata: Dict[entity_id -> metadata]
├── brand_context: BrandContext        # For promotional workflows
├── acts: List[StoryAct]
│   └── StoryAct
│       ├── act_number, title, description, plot_points, character_arcs
│       └── scenes: List[StoryScene]
│           └── StoryScene
│               ├── scene_id, scene_number, title, description
│               ├── plot_point, character_focus, pacing, estimated_duration
│               ├── environment_id, environment_block
│               ├── compression_strategy    # "beat_by_beat", "montage", "atmospheric_hold"
│               ├── character_wardrobe      # Dict[entity_id -> wardrobe description] (scene-level)
│               ├── metadata: { generated_content, consistency_digest, ... }
│               └── storyboard_items: List[StoryboardItem]
│                   └── StoryboardItem
│                       ├── item_id, sequence_number, duration (1-30 sec, AI-optimized)
│                       ├── storyline, image_prompt, prompt, visual_description
│                       ├── dialogue, camera_notes, scene_type
│                       ├── audio_intent, audio_notes, audio_source
│                       └── identity_drift_warnings
└── get_all_storyboard_items()  # Flat list of all items
```

### Identity Block Metadata (per entity)

```python
{
    "name": str,           # Entity name
    "type": str,           # "character" | "vehicle" | "object" | "environment"
    "scene_id": str,       # For environments (per-scene); "" for global entities
    "status": str,         # "placeholder" | "generating" | "approved"
    "user_notes": str,     # Short description used for generation
    "identity_block": str, # Full 8-field block text
    "reference_image_prompt": str,
    # Environment-only:
    "extras_present", "extras_density", "extras_activities", "extras_depth",
    "foreground_zone", "is_primary_environment", "parent_vehicle"
}
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
4. **Storyboard** — 5–10 second segments, prompts

If a conflict exists, the higher layer wins and lower content should be regenerated.

---

## 5. Complete Workflows

### 5.1 Workflow 1: AI-Generated Story (Story Creation Wizard)

**Step 1 — Premise (premise_step.py)**

- Select genres (checkboxes)
- Select atmosphere/tone (dropdown)
- Select story length: Micro | Short | Medium | Long
- Set character count (2–10)
- Optional title
- Click "Generate Premise" → AI generates premise
- Edit if needed → Next

**Step 2 — Story Outline (story_outline_step.py)**

- AI generates: main_storyline, subplots, characters (name, outline, growth_arc), conclusion
- Edit or regenerate individual sections
- Next

**Step 3 — Framework Generation (framework_generation_step.py)**

- AI creates acts and scenes from length spec
- Per scene: title, description, plot_point, character_focus, pacing, estimated_duration
- Finish → Screenplay with framework (no storyboard items yet)

### 5.2 Workflow 2: Manual Story Creation

- **File → New Story (Manual)**
- Enter title, premise, genres, atmosphere
- Set structure: number of characters, acts, scenes per act
- Creates empty framework with placeholders

### 5.3 Workflow 3: Scene Content Generation

- Select a scene in Framework View
- **Scene Content** tab: enter or edit scene description
- Click **Generate with AI** → AI generates full scene prose with entity markup
- Review and edit
- Click **Approve** → Triggers entity extraction and identity block creation

### 5.4 Workflow 4: Entity Extraction

When you **Approve** a scene or click **Re-extract Entities**:

1. **Characters:** Extract all FULL CAPS names (Wizard registry + scene-only)
2. **Environments:** Extract _underlined_ locations
3. **Objects:** Extract [brackets] (interactable only)
4. **Vehicles:** Extract {{braces}}
5. Create placeholder identity blocks for each
6. For characters: AI extracts physical appearance (user_notes) — **no clothing**
7. For characters: AI extracts **wardrobe** (clothing, accessories) → stored in `scene.character_wardrobe`
8. For environments: Create MODE A (empty) or MODE B (with extras) based on scene

### 5.5 Workflow 5: Identity Blocks Management

- Go to **Identity Blocks** tab
- Left: Entity list (characters, vehicles, objects, environments)
- Right: Editor for selected entity
- **User Notes:** Short description
- **Generate Identity Block** → AI expands to 8-field schema
- **Approve** → Mark as approved for use in prompts
- **Reference Image Prompt:** Generate or edit prompt for Higgsfield reference image

### 5.6 Workflow 6: Storyboard Generation

- Select scene(s) in Framework View
- Click **Generate Storyboard for Scene**
- AI breaks scene into 5–10 second items (1:1 with paragraphs when available)
- Per item: image_prompt (static first frame), prompt (video action), dialogue, camera_notes
- Uses approved identity blocks + scene wardrobe in image prompts

### 5.7 Workflow 7: Storyboard Editing

- Click item in timeline or list
- **Storyboard Item Editor** opens
- Edit duration, storyline, image_prompt, prompt, dialogue, camera_notes
- **Regenerate Composition Prompt** / **Regenerate Motion Prompt** with AI
- Identity drift warnings shown if inconsistencies detected

### 5.8 Workflow 8: Export

- **File → Export**
- Formats: JSON, CSV, Higgsfield.ai, Prompts Only
- Exports all storyboard items with prompts, duration, metadata

---

## 6. Character Identity vs Wardrobe

MoviePrompterAI separates **character identity** (global, immutable) from **wardrobe** (scene-level, mutable) to prevent visual drift.

### Character Identity (Global)

Stored in identity blocks. **Physical traits only** — no clothing.

- Face structure, hair color/style, eye color, skin tone
- Age range, build/body type
- Permanent features (scars, tattoos, glasses if permanent)

**Used for:** Canonical reference image (one per character).

### Character Wardrobe (Scene-Level)

Stored in `StoryScene.character_wardrobe` (entity_id → description).

- Clothing, accessories, armor, uniforms
- Condition (dirty, bloodstained, pristine)

**Used for:** Per-scene image prompts ("Same character as reference; wearing [wardrobe]").

### Where to Edit

- **Identity Blocks tab:** Character identity (physical only)
- **Scene Content tab → Character Wardrobe:** Per-scene clothing for each character

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

- **character** — Physical identity only; wardrobe in scene
- **vehicle** — Exterior appearance
- **object** — Prop or interactable item
- **environment** — Location/setting; supports extras (MODE B)

### Environment Modes

- **MODE A:** Empty, no people
- **MODE B:** With extras (background figures) — extras_density, extras_activities, extras_depth, foreground_zone

### Reference Image Prompts

- **Characters:** Full body, neutral pose, plain background, "neutral generic clothing; clothing will vary by scene"
- **Vehicles:** 3/4 view, clean background
- **Objects:** Product-shot style
- **Environments:** Wide establishing, with or without extras

---

## 8. Action Rules and SFX Rules

### Action Rules (action_rules.py)

- **Whitelist:** CHARACTER_ACTIONS, OBJECT_ACTIONS, VEHICLE_ACTIONS, ENVIRONMENTAL_ACTIONS, CAMERA_ACTIONS
- **Forbidden:** feel, think, realize, decide, hope, fear, etc. (internal/emotional)
- Used for *asterisk* action markup validation and normalization

### SFX Rules (sfx_rules.py)

- **Whitelist:** HUMAN_SFX, OBJECT_SFX, VEHICLE_SFX, ENVIRONMENTAL_SFX, WEAPON_SFX, ELECTRONIC_SFX
- **Forbidden:** silence, tension, drama, music, mood, etc.
- Format: (lowercase_underscore_separated)
- Used for (parenthetical) sound markup validation

### expand_sfx_markup / fix_sfx_markup

- Expands prose like "the hum of" → "(hum)"
- Validates and normalizes SFX to whitelist

---

## 9. Workflow Profiles

**WorkflowProfileManager** determines wizard steps and prompts by intent:

| Intent                      | Profile      | Story Outline | Characters |
|-----------------------------|--------------|---------------|------------|
| General Story               | NARRATIVE    | Yes           | Yes        |
| Advertisement / Brand Film  | PROMOTIONAL  | Simplified    | Optional   |
| Social Media / Short-form   | NARRATIVE    | Yes           | Yes        |
| Visual Art / Abstract       | EXPERIMENTAL | Simplified    | Optional   |

**Promotional** workflows use brand_context (product_description, core_benefit, etc.).

---

## 10. AI Integration

### Providers

- OpenAI, Together AI, OpenRouter, Hugging Face
- Local: Ollama, LM Studio (configurable base_url)

### Key AI Operations

| Operation              | Purpose                                           |
|------------------------|---------------------------------------------------|
| generate_premise       | Create premise from genre/atmosphere              |
| generate_story_outline | Main storyline, subplots, characters, conclusion  |
| generate_story_framework | Acts, scenes, descriptions                     |
| generate_scene_content | Full scene prose with entity markup               |
| generate_scene_storyboard | Break scene into storyboard items              |
| generate_identity_block_from_notes | Expand user notes to 8-field block         |
| _generate_identity_block_from_scene | Extract identity from scene text            |
| extract_character_appearance_from_scene | Physical traits for user_notes (no clothing) |
| extract_character_wardrobe_from_scene | Clothing/accessories for scene            |
| generate_reference_image_prompt | Higgsfield reference image prompt          |
| regenerate_image_prompt | Regenerate composition prompt for item         |
| regenerate_storyboard_items | Regenerate items based on chat discussion     |

### Threading

- Long operations run in QThread to avoid UI blocking
- Progress dialogs shown during generation

---

## 11. UI Components

### Main Window

- Menu: File (New, Open, Save, Export), View (AI Chat, Framework/Timeline)
- Central: Story Framework View or Storyboard Timeline
- Dock: AI Chat Panel (optional)
- Status bar

### Story Framework View

- **Left:** Tree (Acts → Scenes → Storyboard Items)
- **Right:** Tabbed panel
  - **Framework:** Scene description, content, Character Wardrobe, Approve, Re-extract
  - **Premise:** Premise, genres, atmosphere, story structure
  - **Characters:** Character list and details from story outline
  - **Identity Blocks:** Entity list, identity block editor, approve, reference prompt

### Character Wardrobe (Scene Content Tab)

- Listed by character (from character_focus + existing wardrobe)
- Editable field per character for clothing/accessories in that scene
- Saved when Approve is clicked

### Storyboard Timeline

- Card layout of all storyboard items
- Click to open Storyboard Item Editor
- Drag to reorder

### Storyboard Item Editor

- Duration, storyline, image_prompt, prompt, dialogue, camera_notes
- Regenerate Composition Prompt / Regenerate Motion Prompt
- Scene type, audio intent/notes

### Identity Block Manager

- Entity tree (by type)
- User notes, identity block, status (Placeholder/Approved)
- Generate Identity Block, Approve
- Reference image prompt (generate, save)

### Settings

- AI provider, API key, base URL, model
- Theme (light/dark), font size

---

## 12. Export Formats

### JSON (Higgsfield-optimized)

- title, premise, genre, atmosphere
- total_duration_seconds, item_count
- storyboard: array of { sequence, duration_seconds, image_prompt, prompt, visual_description, scene_type, dialogue, camera_notes, audio_* }

### CSV

- One row per storyboard item
- Columns: Sequence, Duration, Image Prompt, Video Prompt, etc.

### Prompts Only

- Text file: IMAGE: ... / VIDEO: ... per item

### Higgsfield Format

- project_name, metadata, video_segments
- Each segment: segment_number, duration, image_prompt, video_prompt, settings

---

## 13. Configuration

**config.json:**

```json
{
  "ai_provider": "OpenAI" | "Together AI" | "OpenRouter" | "Hugging Face" | "Local",
  "api_key": "...",
  "base_url": "..." (for Local/Custom),
  "model": "...",
  "temperature": 0.7,
  "max_tokens": 4000,
  "ui_settings": {
    "theme": "light" | "dark",
    "font_size": 12
  }
}
```

**Environment:** `OPENAI_API_KEY` can override config.

---

## 14. Higgsfield.ai Integration

MoviePrompterAI outputs prompts tuned for higgsfield.ai:

1. **Image prompts:** Static first-frame descriptions; no action verbs; composition and character wardrobe
2. **Video prompts:** Action descriptions with explicit verbs; same setting as image
3. **Character consistency:** Identity blocks (physical only) + scene wardrobe; reference image per character
4. **Export:** JSON/CSV with sequence, duration, image_prompt, prompt

---

## 15. Known Limitations

- Windows-focused (PyInstaller builds .exe)
- Requires AI API key or local AI server
- Large frameworks (Long tier) can take significant time
- Single-user; no collaboration
- No built-in version control (snapshot manager exists but not fully wired)
- Export formats are fixed; no custom templates

---

*End of Documentation*
