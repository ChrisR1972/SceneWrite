"""
Help dialogs for SceneWrite.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QDialogButtonBox, QLineEdit, QLabel, QWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QTextCharFormat, QColor, QTextCursor, QShortcut, QKeySequence

from config import APP_VERSION


def get_comprehensive_instructions() -> str:
    """Get comprehensive instructions for using the app."""
    return """SCENEWRITE — COMPREHENSIVE USER GUIDE
═══════════════════════════════════════════════════════════════════════════════

OVERVIEW
═══════════════════════════════════════════════════════════════════════════════
SceneWrite is a professional desktop application for creating screenplays and
storyboards optimized for AI video generation. It provides a complete workflow
from initial premise through story development, scene writing, identity
management, and storyboard generation — producing platform-ready prompts for
8 major AI video platforms.

The app uses a three-layer prompt architecture (Keyframe, Identity, Video)
and supports episodic series with shared continuity, custom story durations,
smart pacing based on filmmaking conventions, environment/spatial consistency
enforcement, multi-shot clustering, cinematic grammar enforcement, character
identity locking, and advertisement/brand film workflows.

═══════════════════════════════════════════════════════════════════════════════
PART 1: AI PROVIDER CONFIGURATION
═══════════════════════════════════════════════════════════════════════════════

Before using AI features, configure your AI provider in Settings → AI Config.

SUPPORTED AI PROVIDERS (for story generation):
───────────────────────────────────────────────────────────────────────────────
The app works with ANY provider that implements the OpenAI Chat Completions
API format (/v1/chat/completions endpoint):

• OpenAI — https://api.openai.com/v1 (GPT-4, GPT-4o, etc.)
• Anthropic — Claude models via compatible endpoint
• Together AI — https://api.together.xyz/v1
• OpenRouter — https://openrouter.ai/api/v1 (multi-model gateway)
• Hugging Face — https://api-inference.huggingface.co/v1/
• Ollama Cloud — Cloud-hosted Ollama instances
• Local (Ollama/LM Studio) — http://localhost:11434/v1 or :1234/v1
• Custom — Any OpenAI-compatible endpoint (Groq, DeepInfra, Azure, etc.)

CONFIGURATION STEPS:
───────────────────────────────────────────────────────────────────────────────
1. Go to Settings → AI Config
2. Select your AI provider from the dropdown
3. Enter your API key (if required)
4. Enter or verify the base URL (auto-filled for most providers)
5. Select your model (use "Refresh Models" for Ollama/local)
6. Adjust temperature (0-100%) and max tokens (2000-60000)
7. Click "Test AI Connection" to verify
8. Click "Save" to apply

Each provider remembers its own base URL when switching between them.

═══════════════════════════════════════════════════════════════════════════════
PART 2: VIDEO PLATFORM CONFIGURATION
═══════════════════════════════════════════════════════════════════════════════

SceneWrite generates prompts for 8 AI video generation platforms. Configure
API keys for your platforms in Settings → AI Config under "Platform API Keys."

SUPPORTED VIDEO PLATFORMS:
───────────────────────────────────────────────────────────────────────────────
• Higgsfield — Cinema Studio 2.0 (key + secret required)
  Models: Default Higgsfield models
  Features: Multi-shot clustering, identity lock, image generation

• Runway — Gen-4 / Gen-4.5
  Models: gen4.5, gen4_turbo, gen4_aleph

• OpenAI Sora — Sora 2 / Sora 2 Pro
  Models: sora-2, sora-2-pro
  Duration presets: 4s, 8s, 12s

• Kling — Kling 3.0 / O3 models
  Models: o3-pro, o3-std, kling-3.0-pro, kling-3.0-std, kling-2.6-pro

• Luma — Dream Machine Ray 2
  Models: ray-2, ray-flash-2
  Features: Loop mode for seamless video loops

• Google Veo — Veo 3.0 / 3.1
  Models: veo-3.1-generate, veo-3.0-generate, veo-3.1-fast, veo-3.0-fast
  Duration presets: 4s, 6s, 8s

• Pika — Pika 2.2 / 2.5 (via fal.ai)
  Models: pika-2.5, pika-2.2
  Features: Motion strength control (1-5)

• Minimax / Hailuo — Hailuo 2.3 / 02
  Models: hailuo-2.3, hailuo-02
  Duration presets available

Each platform has its own prompt adapter that automatically converts your
three-layer prompts into the optimal format for that platform.

═══════════════════════════════════════════════════════════════════════════════
PART 3: GETTING STARTED
═══════════════════════════════════════════════════════════════════════════════

CREATING A NEW STORY
───────────────────────────────────────────────────────────────────────────────
There are several ways to start a new project:

METHOD 1: AI-GENERATED STORY (RECOMMENDED)
  File → New Story (AI Generated) or Ctrl+N
  Opens the Story Creation Wizard with full AI assistance.

METHOD 2: MANUAL STORY
  File → New Story (Manual)
  Enter a title and optional premise. Creates a basic structure you fill in.

METHOD 3: QUICK MICRO STORY
  File → Quick Micro Story or Ctrl+M
  Generates a complete micro-length story in one step — great for testing
  or quick concepts.

METHOD 4: EPISODIC SERIES
  File → New Series
  Create a multi-episode series with shared characters, world settings, and
  lore. See Part 20 for full details on the episodic series system.

IMPORTING FROM TEXT
───────────────────────────────────────────────────────────────────────────────
  File → Import Story from Text or Ctrl+I
  Import a novel or script from a text file. The AI analyzes the text and
  builds a screenplay structure from it.

RECENT FILES
───────────────────────────────────────────────────────────────────────────────
  File → Recent Stories
  Quickly re-open your last 10 projects.

═══════════════════════════════════════════════════════════════════════════════
PART 4: STORY CREATION WIZARD
═══════════════════════════════════════════════════════════════════════════════

The wizard guides you through creating a complete story in 3-4 steps.

STEP 1: LENGTH & INTENT
───────────────────────────────────────────────────────────────────────────────
1. Choose story length: Micro, Short, Medium, Long, or Custom
2. Choose story intent:
   - General Story — Standard narrative workflow
   - Advertisement / Brand Film — Promotional workflow with brand context
   - Horror Short, Sci-Fi, etc. — Specialized genre workflows
   - Social Media / Short-form — Quick narrative
   - Visual Art / Abstract — Experimental workflow

CUSTOM DURATION:
  When you select "Custom (specify duration)", a time input appears where
  you enter the total target length of your story in minutes and seconds.
  The AI automatically determines how many acts and scenes to create and
  allocates appropriate durations to each scene. The per-scene duration
  selector is hidden when custom duration is active — the AI handles all
  timing. For episodic series, the custom duration persists across all
  episodes via the Series Bible.

The intent determines which wizard steps appear and how AI prompts are tuned.
Advertisement workflows include brand context fields (product, core benefit,
brand personality) and use a structured 6-beat commercial template.

STEP 2: PREMISE
───────────────────────────────────────────────────────────────────────────────
1. Select one or more genres (16 available, multiple selection)
2. Choose an atmosphere/tone (15 options)
3. Click "Generate Premise" for AI generation, or enter manually
4. Edit the generated premise as needed
5. Click "Next" to proceed

STEP 3: STORY OUTLINE (if required by workflow)
───────────────────────────────────────────────────────────────────────────────
1. Click "Generate Story Outline" to create:
   - Main Storyline (5-8 sentences)
   - Subplots (2-4 secondary storylines)
   - Conclusion (4-6 sentences)
   - Character Profiles (auto-generated after conclusion)
2. Regenerate any section individually
3. Edit text directly in each field
4. Click "Next" when satisfied

STEP 4: FRAMEWORK GENERATION
───────────────────────────────────────────────────────────────────────────────
1. Click "Generate Framework" to create acts and scenes
2. Each scene gets: title, description, duration, character focus, plot point,
   and pacing (Fast, Medium, or Slow)
3. Pacing follows established filmmaking rhythm rules automatically
   (see Part 21 for details)
4. If custom duration is active, scene durations are normalized to sum to
   the specified total
5. Edit scene details by clicking on them
6. Click "Finish" to enter the main editor

═══════════════════════════════════════════════════════════════════════════════
PART 5: STORY SETTINGS (Per-Project)
═══════════════════════════════════════════════════════════════════════════════

Access via the Story Settings tab or Settings → Story Settings. These
settings are saved with each project.

GENERATION PLATFORM
───────────────────────────────────────────────────────────────────────────────
• Platform — Select your target video platform (Higgsfield, Runway, etc.)
• Video Model — Platform-specific model selection
• Image Model — For platforms that support image generation

CINEMATIC CONTROLS
───────────────────────────────────────────────────────────────────────────────
• Multi-Shot Clustering — Group consecutive items into single video clips
  (Higgsfield only)
• Max Clip Duration — 1-30 seconds (capped by platform maximum)
• Aspect Ratio — 16:9, 9:16, 1:1, 4:3, 21:9, 2.35:1 (filtered by platform)
• Visual Style — Photorealistic, Comic Book, Anime, and more
• Default Focal Length — 8-50mm (default 35mm)
• Identity Lock Strength — Relaxed / Standard / Strict (Higgsfield only)
• Cinematic Beat Density — Sparse / Balanced / Dense
• Camera Movement Intensity — Static / Subtle / Dynamic / Frenetic
• Prompt Output Format — Cinematic Script / Shot List / Director Notes

PLATFORM-SPECIFIC OPTIONS
───────────────────────────────────────────────────────────────────────────────
• Sora / Veo / Minimax — Duration presets
• Pika — Motion strength slider (1-5)
• Luma — Loop mode for seamless video loops

AUDIO GENERATION
───────────────────────────────────────────────────────────────────────────────
• Dialogue Mode — Generate / Script Only / Disabled
• SFX Density — Minimal / Cinematic / High-Impact
• Music Strategy — None / Ambient Bed / Thematic Score / Full Cinematic Score

═══════════════════════════════════════════════════════════════════════════════
PART 6: THE MAIN EDITOR
═══════════════════════════════════════════════════════════════════════════════

The main window has five tabs across the top:

TAB 1: STORYBOARD (Main workspace)
───────────────────────────────────────────────────────────────────────────────
Left Panel: Acts and Scenes tree (expandable hierarchy)
Right Panel: Scene editor with title, description, duration, character focus
Bottom Panel: Storyboard items list for the selected scene

Actions:
• Generate Storyboard — AI breaks the scene into timed storyboard items
• Edit Item — Open the full Storyboard Item Editor
• Move Up/Down — Reorder items within a scene
• Select All — Select all items for batch operations

TAB 2: PREMISE
───────────────────────────────────────────────────────────────────────────────
Edit your project's title, premise text, genres, atmosphere, story length,
and intent at any time. Changes here affect the top of the source-of-truth
hierarchy.

TAB 3: CHARACTER DETAILS
───────────────────────────────────────────────────────────────────────────────
View and edit character profiles from the story outline. Each character has:
• Name and physical appearance
• Growth arc and role in the story
• Integration with identity blocks

TAB 4: STORY SETTINGS
───────────────────────────────────────────────────────────────────────────────
All per-project cinematic and platform settings (see Part 5 above).

TAB 5: IDENTITY BLOCKS
───────────────────────────────────────────────────────────────────────────────
Entity management interface (see Part 8 below).

DOCKABLE PANELS
───────────────────────────────────────────────────────────────────────────────
• AI Chat Panel — View → Show AI Chat (14-intent story assistant)
• Higgsfield/Video Generation Panel — View → Show Higgsfield API

═══════════════════════════════════════════════════════════════════════════════
PART 7: WORKING WITH SCENES
═══════════════════════════════════════════════════════════════════════════════

SCENE CONTENT & CINEMATIC MARKUP
───────────────────────────────────────────────────────────────────────────────
Scene text uses cinematic markup to identify entities:

• FULL CAPS — Characters (MAYA RIVERA, ELIAS CROSS)
• _underlined_ — Locations/Environments (_Midnight Falls_, _City Hall_)
• [brackets] — Interactable Objects ([console], [weapon])
• {{braces}} — Vehicles ({{motorcycle}}, {{Starfall Cruiser}})
• (parentheses) — Sound FX ((metal_clang), (footsteps))
• *asterisks* — Actions (*walks*, *reaches for*)

The editor highlights these tokens in real time and detects unmarked tokens
that match the action or SFX whitelists, showing them as suggestions.

GENERATING STORYBOARD ITEMS
───────────────────────────────────────────────────────────────────────────────
1. Select a scene in the Storyboard tab
2. Click "Generate Storyboard for Scene"
3. AI creates items with optimized durations (1-30 seconds each)
4. Each item includes: storyline, three-layer prompts, dialogue, camera notes

EDITING STORYBOARD ITEMS
───────────────────────────────────────────────────────────────────────────────
Click any item to open the Storyboard Item Editor (see Part 9).

CHARACTER WARDROBE & APPEARANCE (Per-Scene)
───────────────────────────────────────────────────────────────────────────────
Character identity is global (physical traits only). Wardrobe is scene-level:
• Each scene stores clothing/accessories per character
• Wardrobe is extracted from scene content during entity extraction
• For non-human characters (species other than Human), the system extracts
  visual appearance instead of clothing (e.g. translucent features, scales,
  wingspan) using species-aware prompts
• Edit wardrobe in the scene editor or Identity Blocks tab
• Wardrobe variants allow multiple looks with reference images
• Character species can be set in the Character Details tab and propagates
  to identity blocks and reference image prompts

RECURRING OBJECTS
───────────────────────────────────────────────────────────────────────────────
After approving scenes, the system detects objects that appear in multiple
scenes (e.g. a medallion, compass, or weapon used throughout the story).
• A notification lists recurring objects that need identity blocks
• Recurring objects are marked with a 🔄 symbol in the entity list
• Generating an identity block for these ensures visual continuity

═══════════════════════════════════════════════════════════════════════════════
PART 8: IDENTITY BLOCKS
═══════════════════════════════════════════════════════════════════════════════

Identity blocks define the visual appearance of entities for consistent
video generation across all scenes.

ENTITY TYPES
───────────────────────────────────────────────────────────────────────────────
• Characters — Physical traits only (no clothing). Wardrobe is per-scene.
• Groups — Multiple characters sharing a visual identity (e.g. IMPERIAL
  SOLDIERS, TEMPLE GUARDS). Groups have:
  - Member count (auto-extracted from scene or set manually)
  - Individuality setting (identical/slight/moderate/high variation)
  - Uniform description (shared outfit/armor/equipment)
  - Formation (how they're arranged in shots)
  Groups appear in FULL CAPS like characters but are tracked separately.
  Genre-aware aesthetics ensure groups match the story's genre (e.g.
  medieval armor for fantasy, tactical gear for sci-fi).
• Vehicles — Exterior appearance
• Objects — Props and interactable items
• Environments — Locations, with optional background extras

IDENTITY BLOCK STRUCTURE (8-Field Schema)
───────────────────────────────────────────────────────────────────────────────
Each identity block is a single flowing paragraph with 8 fields:
1. Identity Lock Phrase — "the same [type] with..."
2. Classification — Type/category
3. Physical Form & Silhouette — Shape, proportions, size
4. Surface & Material Behavior — Color, texture, light reaction
5. Key Identifying Features — Distinct recognition elements
6. Negative Constraints — What is NOT present
7. Condition & State — Clean, worn, pristine, etc.
8. Style/Era/Design Language — Modern, vintage, futuristic, etc.

CREATING AND MANAGING IDENTITY BLOCKS
───────────────────────────────────────────────────────────────────────────────
1. Go to the Identity Blocks tab
2. Left panel: Entity tree organized by type, with status indicators:
   ⚠ Pending | ✓ Approved | ⏳ Generating | 🔗 Linked |
   👁 Referenced | 🔄 Recurring | ◇ Passive
3. Select an entity and enter User Notes (brief description)
4. Click "Generate Identity Block" — AI expands to 8-field schema
5. Review and click "Approve" to lock the identity block

REFERENCED ENVIRONMENTS
───────────────────────────────────────────────────────────────────────────────
Environments that are mentioned in dialogue, visions, carvings, or lore but
never physically visited by characters are automatically detected and marked
with "Referenced" status (👁). These do not get descriptions extracted from
the scene (which would incorrectly use the current location's description).
Referenced environments appear in blue-grey italic in the entity list.

ENVIRONMENT EXTRAS (Environments only)
───────────────────────────────────────────────────────────────────────────────
Environments support two modes:
• MODE A — Empty location, no people
• MODE B — With background extras (crowd, passersby, etc.)
  Configure: Extras density, activities, depth layers, foreground zone

REFERENCE IMAGE PROMPTS
───────────────────────────────────────────────────────────────────────────────
After approving an identity block:
1. Click "Generate Reference Image Prompt"
2. Copy the prompt for use in any image generation tool
3. Upload reference images directly to entity slots

FORMAT BY ENTITY TYPE:
• Characters: Full body, neutral pose, plain background, generic clothing
• Vehicles: 3/4 view, clean background
• Objects: Product-shot style
• Environments: Wide establishing shot, with or without extras

═══════════════════════════════════════════════════════════════════════════════
PART 9: STORYBOARD ITEM EDITOR
═══════════════════════════════════════════════════════════════════════════════

The full-featured editor for individual storyboard items. Open by clicking
any item in the storyboard list.

SCENE SETUP
───────────────────────────────────────────────────────────────────────────────
• Duration — 1-30 seconds
• Scene Type — Action, Dialogue, Transition, etc.
• Shot Type — Wide, Medium, Close-up, Extreme Close-up, Over the Shoulder,
  Two Shot, Bird's Eye, Low Angle, High Angle, Dutch Angle
• Camera Motion — Static, Dolly In/Out, Orbit, Tracking, Handheld, Crash
  Zoom, FPV/Drone, Pan, Tilt, Crane, Push In, Pull Out
• Focal Length — 8-50mm
• Aperture Style — Cinematic Bokeh, Deep Focus, etc.
• Visual Style — Project default or per-item override
• Mood/Tone — Editable selection
• Lighting Description — Editable selection

INTELLIGENT SHOT & CAMERA DEFAULTS
  Shot type and camera motion are automatically chosen per beat based on
  the paragraph's content:
  • Dialogue (1 speaker) → Close-Up, Static
  • Dialogue (2+ characters) → Over the Shoulder, Static
  • Spatial movement (run, dash, flee) → Medium, Tracking
  • Entry/exit (enter, approach) → Wide, Slow Dolly In
  • Tension (aim, draw, crouch) → Low Angle, Push In
  • Intimate actions (whisper, touch) → Extreme Close-Up, Static
  • Environment only (no characters) → Wide, Slow Pan
  • Multiple characters (3+) → Wide, Slow Dolly Out
  • Two characters → Two Shot, Static
  These are defaults — you can override both via the dropdowns.

STORYLINE & DIALOGUE
───────────────────────────────────────────────────────────────────────────────
• Storyline text (2-4 sentences describing the action)
• Composition/Blocking notes
• Dialogue in CHARACTER: "text" format

IMAGE MAPPING
───────────────────────────────────────────────────────────────────────────────
• Hero Frame (required) — Upload or assign the primary reference image
• End Frame (optional) — For shots that transition between states
• Entity Reference Slots (3) — Assign character/object/vehicle images
• Entity tags show which entities are identity-locked (blue) vs markup-only

THREE-LAYER PROMPT SYSTEM (Tabbed View)
───────────────────────────────────────────────────────────────────────────────
• Keyframe Prompt — Layer 1: Static hero frame composition
• Identity Prompt — Layer 2: Auto-generated from approved identity blocks
• Video Prompt — Layer 3: Camera movement, action, dialogue
• Platform Prompt — Read-only adapted output for selected platform
• "Copy All Prompts" copies all layers to clipboard

AUDIO (Optional)
───────────────────────────────────────────────────────────────────────────────
• Audio intent, notes, and source configuration

MULTI-SHOT CLUSTER INFO
───────────────────────────────────────────────────────────────────────────────
If multi-shot clustering is enabled, shows: Cluster ID, Shot number,
Total cluster duration, and Transition type between shots.

═══════════════════════════════════════════════════════════════════════════════
PART 10: THREE-LAYER PROMPT ARCHITECTURE
═══════════════════════════════════════════════════════════════════════════════

SceneWrite uses a three-layer prompt system designed for maximum quality
and consistency across AI video platforms:

LAYER 1: KEYFRAME PROMPT (Hero Frame)
───────────────────────────────────────────────────────────────────────────────
A static first-frame description. No action verbs. Focuses on composition,
character placement, wardrobe, environment, and lighting.

LAYER 2: IDENTITY PROMPT (Soul ID)
───────────────────────────────────────────────────────────────────────────────
Auto-generated from approved identity blocks. Provides character identity
locks so the AI video platform maintains consistent appearances. Read-only.

LAYER 3: VIDEO PROMPT (Motion)
───────────────────────────────────────────────────────────────────────────────
Camera movement, character actions, dialogue delivery, and scene dynamics.
This is where the action happens.

PLATFORM ADAPTATION
───────────────────────────────────────────────────────────────────────────────
The three layers are automatically combined and reformatted for your selected
platform. Each platform adapter optimizes the prompt structure:
• Higgsfield — Native three-layer pass-through
• Runway — Prose-style combined prompt
• Pika — Concise comma-separated tokens
• Kling — Natural-language scene description
• Sora — Cinematic description with shot type and focal length
• Veo — Descriptive prose
• Minimax — Keyword-rich single prompt
• Luma — Scene-focused prompt

═══════════════════════════════════════════════════════════════════════════════
PART 11: MULTI-SHOT CLUSTERING
═══════════════════════════════════════════════════════════════════════════════

Multi-shot clustering groups consecutive storyboard items into single video
clips, reducing cuts and improving visual continuity.

HOW IT WORKS
───────────────────────────────────────────────────────────────────────────────
1. Enable in Story Settings → Multi-Shot Clustering (Higgsfield only)
2. When generating storyboards, compatible adjacent items are grouped
3. The engine checks compatibility: same environment, overlapping characters
4. Transitions between shots are auto-generated (whip pan, match cut, etc.)
5. Identity locks are reinforced across the entire cluster

CLUSTER INFORMATION
───────────────────────────────────────────────────────────────────────────────
Each item in a cluster shows:
• Cluster ID — Shared identifier for grouped items
• Shot number within the cluster
• Total cluster duration
• Transition type to the next shot

═══════════════════════════════════════════════════════════════════════════════
PART 12: ADVERTISEMENT / BRAND FILM MODE
═══════════════════════════════════════════════════════════════════════════════

For promotional content, select "Advertisement / Brand Film" as the story
intent in the wizard.

6-BEAT COMMERCIAL TEMPLATE
───────────────────────────────────────────────────────────────────────────────
Ad mode structures your storyboard around 6 cinematic beats:
1. Hook — Attention-grabbing opening
2. Pain/Desire — Establish the problem or aspiration
3. Product Reveal — Introduce the product/brand
4. Feature Demo — Show the product in action
5. Emotional Payoff — Deliver the emotional resolution
6. Brand Moment — Logo, tagline, call to action

BRAND CONTEXT
───────────────────────────────────────────────────────────────────────────────
Configure in the wizard or Premise tab:
• Product description
• Core benefit
• Brand personality
• Target audience
• Distribution platform presets

VALIDATION
───────────────────────────────────────────────────────────────────────────────
Ad mode enforces: hero shot presence, pacing escalation, narrative complexity
limits, and beat sequence integrity.

═══════════════════════════════════════════════════════════════════════════════
PART 13: VIDEO GENERATION PANEL
═══════════════════════════════════════════════════════════════════════════════

Open via View → Show Higgsfield API. This panel submits your storyboard
items directly to AI video platforms.

USING THE PANEL
───────────────────────────────────────────────────────────────────────────────
1. Platform syncs from your Story Settings (or click "Sync from Settings")
2. Enter API credentials for your selected platform
3. Choose video model and duration
4. The segments table shows all storyboard items with status
5. Click "Generate All" or select specific items and "Generate Selected"
6. Monitor progress in the log area with progress bar
7. Completed items show their image/video URLs

FEATURES
───────────────────────────────────────────────────────────────────────────────
• Background generation with status tracking
• Per-segment status: Queued → Submitting → Polling → Completed/Failed
• Cancel support for in-progress generations
• Result URLs with copy-to-clipboard
• Platform-specific options (motion strength, loop mode, etc.)

═══════════════════════════════════════════════════════════════════════════════
PART 14: AI CHAT ASSISTANT
═══════════════════════════════════════════════════════════════════════════════

Open via View → Show AI Chat. The AI Story Assistant understands your
full story context and can both discuss and directly modify every major
element of a screenplay through natural conversation.

WHAT YOU CAN DO
───────────────────────────────────────────────────────────────────────────────
STORY-LEVEL EDITS
  • Edit the premise — change the story title, premise text, genres,
    or atmosphere (e.g. "Change the genre to sci-fi thriller")
  • Edit the story outline — modify the main storyline, subplots, or
    conclusion (e.g. "Rewrite the conclusion to be more ambiguous")
  • Regenerate the framework — rebuild the entire act/scene structure
    (destructive — requires double confirmation)

SCENE-LEVEL EDITS
  • Regenerate scene content with AI (full or paragraph-level)
  • Edit scene properties: title, description, duration, character focus
  • Add storyboard items to the current scene
  • Remove selected storyboard items
  • Edit or regenerate selected storyboard items

CHARACTER & ENTITY EDITS
  • Modify character outlines and growth arcs from the story outline
  • Edit identity block descriptions for characters, environments,
    vehicles, or objects
  • Approve identity blocks that are ready for use

SERIES FEATURES (episodic series only)
  • Edit the Series Bible — change world setting, time period, lore,
    or tone for all episodes

ANALYSIS & DISCUSSION
  • Discuss story ideas, get feedback, and ask questions
  • Pacing rhythm analysis — detects consecutive runs of 3+ same-paced
    scenes and overall distribution imbalances
  • Identity block status — alerts you to pending blocks that need review
  • Character outline gaps — alerts you to characters missing outlines

WORKFLOW
───────────────────────────────────────────────────────────────────────────────
1. Select a scene or storyboard items for context (optional but
   recommended for scene/item operations)
2. Type your question or request in natural language
3. The AI responds with suggestions and action buttons:
   - "Apply" — Apply the change immediately
   - "Preview" — Review a before/after comparison first
   - "Dismiss" — Ignore the suggestion
4. A green toast notification confirms when changes are applied

TIPS
───────────────────────────────────────────────────────────────────────────────
• Be specific: "Change the premise to a heist in 1920s Paris" works
  better than "change the story"
• For character outlines, mention the character by name: "Extend
  Sarah's backstory with her military career"
• Regenerating the framework is destructive — only use when you want
  to completely redo the structure
• Series Bible edits affect all future episodes

═══════════════════════════════════════════════════════════════════════════════
PART 15: EXPORTING YOUR WORK
═══════════════════════════════════════════════════════════════════════════════

EXPORT FORMATS (File → Export)
───────────────────────────────────────────────────────────────────────────────
1. JSON Export — Complete story data with three-layer prompts
2. CSV Export — Storyboard items in spreadsheet format
3. Higgsfield Export — API-compatible format for Higgsfield Cinema Studio
4. Prompts Only — Plain text with compiled prompt layers
5. Platform-Specific — Adapted prompts for your selected video platform

All exports include: sequence numbers, durations, compiled prompts, dialogue,
camera notes, scene types, and audio metadata.

═══════════════════════════════════════════════════════════════════════════════
PART 16: CINEMATIC MARKUP & WHITELISTS
═══════════════════════════════════════════════════════════════════════════════

ACTION RULES
───────────────────────────────────────────────────────────────────────────────
Actions use *asterisk* markup and must be physical/observable verbs.
Forbidden: internal/emotional verbs (feel, think, realize, hope, fear).
Categories: Character actions, Object actions, Vehicle actions,
Environmental actions, Camera actions.

SFX RULES
───────────────────────────────────────────────────────────────────────────────
Sound effects use (parenthetical) markup in lowercase_underscore format.
Forbidden: abstract concepts (silence, tension, drama, music, mood).
Categories: Human, Object, Vehicle, Environmental, Weapon, Electronic.

CUSTOM WHITELISTS
───────────────────────────────────────────────────────────────────────────────
Add your own action verbs and SFX in Settings → AI Config → Whitelists tab.
Custom entries are saved to config/ActionWhitelist.json and SFXWhitelist.json
and merged with the built-in lists at runtime.

You can also right-click highlighted tokens in the scene editor to add them
to the whitelist directly from context.

═══════════════════════════════════════════════════════════════════════════════
PART 17: UI CUSTOMIZATION
═══════════════════════════════════════════════════════════════════════════════

Go to Settings → UI Config:

• Theme — Light or Dark
• Font Size — 8-24pt (default 12)
• Show Line Numbers — Toggle for text editors
• Auto-Save Interval — 60-3600 seconds (default 300)

All settings apply globally and persist between sessions.

SCROLL GUARD
───────────────────────────────────────────────────────────────────────────────
Dropdown menus and spin boxes throughout the app are protected from accidental
mouse scroll wheel changes. You must click a dropdown to open it — scrolling
over it will not change the selection.

CONFIGURATION STORAGE
───────────────────────────────────────────────────────────────────────────────
Your settings (API keys, model preferences, UI options) are stored in your
user data directory, NOT alongside the application executable:

• Windows:  %APPDATA%/SceneWrite/config.json
• macOS:    ~/Library/Application Support/SceneWrite/config.json
• Linux:    ~/.config/SceneWrite/config.json

This means your configuration survives application updates and reinstalls.
When upgrading from an older version, your existing config is automatically
migrated to the new location on first launch.

═══════════════════════════════════════════════════════════════════════════════
PART 18: KEYBOARD SHORTCUTS
═══════════════════════════════════════════════════════════════════════════════

FILE OPERATIONS:
  Ctrl+N          New Story (AI Generated)
  Ctrl+M          Quick Micro Story
  Ctrl+I          Import Story from Text
  Ctrl+O          Open Story
  Ctrl+S          Save Story
  Ctrl+Shift+S    Save As
  Ctrl+Q          Exit Application

CHAT:
  Ctrl+Enter      Send message in AI Chat

═══════════════════════════════════════════════════════════════════════════════
PART 19: POST-GENERATION CONTENT QUALITY
═══════════════════════════════════════════════════════════════════════════════

SceneWrite applies multiple automated validation and correction passes after
AI generates scene content, ensuring consistency and quality.

AUTOMATED POST-PROCESSING
───────────────────────────────────────────────────────────────────────────────
After scene content is generated, these corrections run automatically:

1. AI Preamble Stripping — Removes meta-text like "Here's the scene..."
   that AI models sometimes prepend to their output
2. Paragraph Tag Cleanup — Fixes doubled tags like [1] [1] and ensures
   sequential numbering
3. Dialogue Deduplication — Detects and removes duplicated dialogue within
   the same line (e.g. "You think your sacrifice changes anything, You
   think your sacrifice changes anything?")
4. Sentence Integrity Repair — Detects and fixes incomplete or broken
   sentences caused by AI word-dropping
5. Genre Compliance — Validates that objects and descriptions match the
   story's genre (e.g. no laser pistols in a fantasy setting)
6. Invented Backstory Detection — Prevents AI from adding lore or history
   through dialogue that contradicts the scene description
7. Invented Abilities Detection — Catches characters displaying powers or
   abilities not established in the story
8. Held-Object Continuity — Tracks what characters are holding and ensures
   they put objects down before picking up new ones
9. Physical Interaction Markup — Auto-wraps unmarked object nouns in
   [brackets] when characters physically interact with them

IDENTITY DRIFT DETECTION
───────────────────────────────────────────────────────────────────────────────
When storyboard items are generated, each prompt is compared against approved
identity blocks to detect visual inconsistencies:

• Hair color changes are detected using synonym groups (auburn/red are
  treated as the same family; grey/silver/white likewise) and only flagged
  when colors appear near hair-related words — preventing false positives
  from phrases like "red light" or "black armor"
• Clothing inconsistencies are noted when identity blocks conflict with
  storyboard prompts

CROSS-SCENE CONTINUITY
───────────────────────────────────────────────────────────────────────────────
The system warns if characters couldn't plausibly be in their current scene
based on where they were last seen — helping catch spatial impossibilities
across the story.

STORYBOARD VALIDATION
───────────────────────────────────────────────────────────────────────────────
Each storyboard item is validated against its source paragraph:
• Missing characters, objects, or vehicles are flagged
• Extra entities not in the source paragraph are flagged
• Wrong environment assignments are detected
• Dialogue paragraphs only require the speaking character (close-up shots
  of a single speaker don't fail for not showing all nearby characters)

PREMISE VARIETY
───────────────────────────────────────────────────────────────────────────────
When regenerating a premise, the system tracks previously generated themes
and instructs the AI to avoid them, ensuring each regeneration produces a
genuinely different story concept rather than variations on the same idea.

PROMPT LENGTH MANAGEMENT
───────────────────────────────────────────────────────────────────────────────
Each video platform has a maximum prompt length. SceneWrite automatically:
• Deduplicates repeated phrases across prompt layers
• Truncates prompts to fit platform limits while preserving key content
• Strips redundant section headers and formatting

═══════════════════════════════════════════════════════════════════════════════
PART 23: BEST PRACTICES & TIPS
═══════════════════════════════════════════════════════════════════════════════

RECOMMENDED WORKFLOW
───────────────────────────────────────────────────────────────────────────────
1. Configure AI provider (Settings → AI Config)
2. Set up platform API keys for your video platform
3. Create a new story with the wizard (or Quick Micro for testing)
4. Configure Story Settings (platform, visual style, aspect ratio)
5. Generate story outline and framework
6. Write or generate scene content with cinematic markup
7. Approve scene content to trigger entity extraction
8. Create and approve identity blocks for all entities
9. Upload or generate reference images
10. Generate storyboards for each scene
11. Review and edit items in the Storyboard Item Editor
12. Fine-tune prompts across all three layers
13. Export or generate video directly from the Generation Panel

STORY DEVELOPMENT TIPS
───────────────────────────────────────────────────────────────────────────────
• Start with a strong premise — it cascades through the entire project
• Let AI generate initial content, then refine manually
• Use the AI Chat Assistant to edit premises, outlines, scenes,
  character outlines, identity blocks, and more through conversation
• Check the suggestions panel for pacing issues and pending blocks
• Keep character identity (physical) separate from wardrobe (clothing)
• Approve identity blocks BEFORE generating storyboards
• For series: build your Series Bible world context thoroughly before
  generating episodes — it ensures strong continuity

PROMPT QUALITY TIPS
───────────────────────────────────────────────────────────────────────────────
• Keyframe prompts should be static descriptions — no action verbs
• Video prompts should focus on movement and dynamics
• Use specific camera terminology (focal length, aperture, motion type)
• Review the Platform Prompt tab to see what your platform receives
• Different platforms work best with different levels of detail

ADVERTISEMENT MODE TIPS
───────────────────────────────────────────────────────────────────────────────
• Follow the 6-beat structure for maximum impact
• Ensure the hero shot (Product Reveal) is strong
• Build escalation across beats — avoid flat pacing
• Keep narrative complexity low for short-form ads

═══════════════════════════════════════════════════════════════════════════════
PART 20: EPISODIC SERIES SYSTEM
═══════════════════════════════════════════════════════════════════════════════

SceneWrite supports multi-episode stories that share persistent characters,
world settings, and lore while allowing each episode to have a fresh,
self-contained storyline.

CREATING A SERIES
───────────────────────────────────────────────────────────────────────────────
  File → New Series
  This creates a series directory and a Series Bible file that stores all
  shared data across episodes.

You can also convert an existing standalone story into a series:
  The first story becomes Episode 1, and a Series Bible is created from
  its characters, locations, and world context.

SERIES BIBLE
───────────────────────────────────────────────────────────────────────────────
The Series Bible is the central data store for everything shared across
episodes:

• World Context — Setting description, rules, lore, world-building notes
• Persistent Characters — Characters that appear across episodes with
  their names, descriptions, and identity blocks
• Recurring Locations — Locations that recur across episodes
• Recurring Props — Objects and vehicles that recur
• Episode Summaries — Per-episode summaries for continuity reference
• Episode Duration — Custom duration setting that persists across episodes
• Continuity Notes — Free-form notes for maintaining consistency

CREATING NEW EPISODES
───────────────────────────────────────────────────────────────────────────────
When creating a new episode for an existing series:
1. The wizard pre-fills the series title, bible path, and characters
2. Custom duration (if set) carries over automatically
3. The AI receives the full Series Bible context during generation
4. "Previously on..." summaries from prior episodes are injected
5. Character identity blocks are reused for visual continuity

SERIES BIBLE EDITOR
───────────────────────────────────────────────────────────────────────────────
A dedicated editor for managing your series data:
• Edit world context (setting, rules, lore)
• Manage persistent characters
• Set episode duration
• View and edit episode summaries and continuity notes

BACKWARD COMPATIBILITY
───────────────────────────────────────────────────────────────────────────────
Existing standalone stories work exactly as before. The series system is
entirely optional — the series_metadata field is empty for non-series
screenplays, and all series-aware features are dormant until activated.

═══════════════════════════════════════════════════════════════════════════════
PART 21: SCENE PACING & RHYTHM
═══════════════════════════════════════════════════════════════════════════════

SceneWrite enforces established filmmaking pacing conventions to create
natural story rhythm and prevent monotonous pacing.

PACING VALUES
───────────────────────────────────────────────────────────────────────────────
Each scene is assigned one of three pacing levels:
• Fast — Action sequences, chases, fights, climaxes
• Medium — Emotional reveals, confrontations, establishing scenes
• Slow — Character reflection, dialogue, world-building, resolution

AUTOMATIC PACING RULES
───────────────────────────────────────────────────────────────────────────────
When the AI generates a story framework, it follows these rules:

Act 1 (Setup):
  Medium → Medium → Fast (build toward the inciting incident)

Act 2 (Confrontation):
  Fast → Medium → Fast → Slow → Medium → Fast (alternation with breathers)

Act 3 (Climax/Resolution):
  Medium → Fast → Fast → Medium/Slow (build, climax, then resolve)

HARD LIMITS:
• Never more than 2 consecutive Fast scenes
• Never more than 2 consecutive Slow scenes
• Target distribution: 30-50% Medium, 25-40% Fast, 15-30% Slow

POST-GENERATION VALIDATION
───────────────────────────────────────────────────────────────────────────────
After framework generation, the app automatically checks and corrects:
• First scene forced to Medium/Slow (setup needs breathing room)
• Last scene forced to Medium/Slow (resolution needs closure)
• Any run of 3+ consecutive same-pacing scenes is broken up

PACING ANALYSIS (AI Chat)
───────────────────────────────────────────────────────────────────────────────
The AI Story Assistant's proactive suggestions panel monitors pacing:
• Consecutive runs of 3+ same-paced scenes (with exact scene numbers)
• Overall distribution imbalances (>60% Fast or >50% Slow)
• Pending identity blocks that need review
• Characters missing outlines
Ask the assistant to fix pacing issues directly via chat.

═══════════════════════════════════════════════════════════════════════════════
PART 22: ENVIRONMENT & SPATIAL CONSISTENCY
═══════════════════════════════════════════════════════════════════════════════

SceneWrite uses multiple layers to ensure environments are correctly detected,
described, and respected during scene generation.

ENVIRONMENT CHANGE DETECTION
───────────────────────────────────────────────────────────────────────────────
The system automatically detects whether the environment has changed between
scenes by comparing environment IDs and cross-checking the _underscored_
locations in scene descriptions. If you edit a scene's description to a
different location and regenerate, the system correctly identifies it as a
new environment — even if the old environment ID was still attached.

ENVIRONMENT DESCRIPTIONS
───────────────────────────────────────────────────────────────────────────────
When a new environment is detected, the system populates its description:
1. Rule-based extraction from scene content (primary)
2. AI-based extraction as fallback if rule-based returns empty
3. Environments matching the scene description are prioritized as primary
4. Outdoor environments (fields, ruins, wastelands) only include terrain
   and landscape features — portable character props (tables, daggers,
   papers) are excluded
5. Environments only mentioned in dialogue, carvings, or visions (never
   visited) are marked as "Referenced" and do not receive descriptions
   from the current scene

SPATIAL CONSISTENCY (How it prevents AI invention)
───────────────────────────────────────────────────────────────────────────────
All environment identity blocks are injected into scene prompts so the AI
knows the full physical description of every established location. Strict
rules prevent the AI from inventing new spaces:

• The AI CANNOT add rooms, floors, levels, balconies, cliffs, rooftops,
  or any other areas not described in the established environment
• Action sequences MUST stay within the described physical boundaries
• Characters cannot crash through walls into non-existent rooms or end
  up on geographical features that were never described
• "Expanding descriptively" means adding sensory detail (textures, sounds,
  smells) to EXISTING spaces — not inventing new architecture

PHYSICAL ACCESS & ZONE LOGIC
───────────────────────────────────────────────────────────────────────────────
Characters are tracked by zone (inside/outside, specific room/area):

• A character can ONLY interact with surfaces and features physically
  reachable from their current zone
• OUTSIDE: can touch exterior walls, ground, vehicles. CANNOT touch
  interior floors, furniture, or indoor fixtures
• INSIDE: can touch interior floors, walls, furniture. CANNOT touch
  outdoor ground or exterior features
• Moving between zones requires an explicit written transition
  (walks through door, steps inside, climbs through window, etc.)
• The AI cannot have a character probe floorboard seams from outside
  a cabin — they must enter first

HELD-OBJECT CONTINUITY
───────────────────────────────────────────────────────────────────────────────
Characters' hand-held objects are tracked throughout each scene:
• A character holding one object must visibly put it down before using
  another hand-held object
• Two-handed objects (rifles, large devices) require both hands
• Objects set down must be picked up again before reuse

═══════════════════════════════════════════════════════════════════════════════
GETTING HELP
═══════════════════════════════════════════════════════════════════════════════

• Help Menu: Instructions, About, and License
• AI Chat: Ask anything — "How do I use this app?", "Change the
  premise to a heist thriller", "Approve all identity blocks", etc.
• Settings: AI Config, UI Config, and Story Settings
• This Guide: Help → Instructions

═══════════════════════════════════════════════════════════════════════════════
END OF GUIDE
═══════════════════════════════════════════════════════════════════════════════
"""


class InstructionsDialog(QDialog):
    """Dialog showing comprehensive app instructions with search."""

    _HIGHLIGHT_FMT = QTextCharFormat()
    _HIGHLIGHT_FMT.setBackground(QColor("#FFEB3B"))
    _HIGHLIGHT_FMT.setForeground(QColor("#000000"))

    _CURRENT_FMT = QTextCharFormat()
    _CURRENT_FMT.setBackground(QColor("#FF9800"))
    _CURRENT_FMT.setForeground(QColor("#000000"))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Instructions")
        self.setMinimumSize(800, 600)
        self._match_positions: list[int] = []
        self._current_match: int = -1
        self.init_ui()

    def init_ui(self):
        """Initialize the dialog UI."""
        layout = QVBoxLayout(self)

        search_bar = QWidget()
        search_layout = QHBoxLayout(search_bar)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(6)

        search_layout.addWidget(QLabel("Search:"))

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Type to search...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_search_changed)
        self.search_input.returnPressed.connect(self._find_next)
        search_layout.addWidget(self.search_input, 1)

        self.match_label = QLabel("")
        self.match_label.setMinimumWidth(80)
        search_layout.addWidget(self.match_label)

        prev_btn = QPushButton("Previous")
        prev_btn.clicked.connect(self._find_previous)
        search_layout.addWidget(prev_btn)

        next_btn = QPushButton("Next")
        next_btn.clicked.connect(self._find_next)
        search_layout.addWidget(next_btn)

        layout.addWidget(search_bar)

        self.instructions_text = QTextEdit()
        self.instructions_text.setReadOnly(True)
        self.instructions_text.setPlainText(get_comprehensive_instructions())
        self.instructions_text.setFont(QFont("Consolas", 9))
        self.instructions_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self.instructions_text)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.accept)
        layout.addWidget(button_box)

        shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        shortcut.activated.connect(self.search_input.setFocus)

    def _clear_highlights(self):
        """Remove all search highlights from the document."""
        cursor = self.instructions_text.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("transparent"))
        fmt.clearForeground()
        cursor.mergeCharFormat(fmt)
        cursor.clearSelection()
        self.instructions_text.setTextCursor(cursor)

    def _on_search_changed(self, text: str):
        """Re-run search when the input text changes."""
        self._clear_highlights()
        self._match_positions.clear()
        self._current_match = -1

        if not text:
            self.match_label.setText("")
            return

        doc = self.instructions_text.document()
        cursor = QTextCursor(doc)
        while True:
            cursor = doc.find(text, cursor)
            if cursor.isNull():
                break
            self._match_positions.append(cursor.selectionStart())
            cursor.mergeCharFormat(self._HIGHLIGHT_FMT)

        total = len(self._match_positions)
        if total == 0:
            self.match_label.setText("No matches")
        else:
            self._current_match = 0
            self._go_to_current_match()

    def _go_to_current_match(self):
        """Scroll to and highlight the current match."""
        if not self._match_positions:
            return
        total = len(self._match_positions)
        idx = self._current_match
        pos = self._match_positions[idx]
        query = self.search_input.text()

        self._clear_highlights()
        doc = self.instructions_text.document()
        cursor = QTextCursor(doc)
        while True:
            cursor = doc.find(query, cursor)
            if cursor.isNull():
                break
            if cursor.selectionStart() == pos:
                cursor.mergeCharFormat(self._CURRENT_FMT)
            else:
                cursor.mergeCharFormat(self._HIGHLIGHT_FMT)

        nav = QTextCursor(doc)
        nav.setPosition(pos)
        self.instructions_text.setTextCursor(nav)
        self.instructions_text.ensureCursorVisible()
        self.match_label.setText(f"{idx + 1} of {total}")

    def _find_next(self):
        """Jump to the next search match."""
        if not self._match_positions:
            return
        self._current_match = (self._current_match + 1) % len(self._match_positions)
        self._go_to_current_match()

    def _find_previous(self):
        """Jump to the previous search match."""
        if not self._match_positions:
            return
        self._current_match = (self._current_match - 1) % len(self._match_positions)
        self._go_to_current_match()


class AboutDialog(QDialog):
    """Dialog showing about information."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About SceneWrite")
        self.setMinimumSize(600, 500)
        self.init_ui()
    
    def init_ui(self):
        """Initialize the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # About text
        about_text = QTextEdit()
        about_text.setReadOnly(True)
        about_text.setPlainText(self.get_about_text())
        about_text.setFont(QFont("Arial", 10))
        about_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        about_text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(about_text)
        
        # Close button
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.accept)
        layout.addWidget(button_box)
    
    def get_about_text(self) -> str:
        """Get the about text content."""
        return f"""SCENEWRITE
═══════════════════════════════════════════════════════════════════════════════

Version {APP_VERSION}

═══════════════════════════════════════════════════════════════════════════════
DESCRIPTION
═══════════════════════════════════════════════════════════════════════════════

A professional screenplay writing application that combines AI-powered story
generation with comprehensive scene and storyboard management. Create complete
screenplays from initial premise to detailed video generation prompts, with
native support for 8 major AI video platforms. Build multi-episode series
with shared continuity, custom story durations, smart pacing, and intelligent
cinematic controls with beat-aware shot composition.

═══════════════════════════════════════════════════════════════════════════════
KEY FEATURES
═══════════════════════════════════════════════════════════════════════════════

• Multi-Platform AI Video Support
  - 8 platforms: Higgsfield, Runway, Kling, Luma, Pika, Sora, Veo, Minimax
  - Platform-specific prompt adapters for optimal output
  - Direct video generation from the app via API integration
  - Per-platform model selection, duration presets, and options

• Three-Layer Prompt Architecture
  - Keyframe Prompt: Static hero frame composition
  - Identity Prompt: Auto-generated character/entity consistency locks
  - Video Prompt: Camera movement, action, and dialogue
  - Automatic platform adaptation for each target

• AI-Powered Story Generation
  - 8 AI providers: OpenAI, Anthropic, Together AI, OpenRouter,
    Hugging Face, Ollama Cloud, Local, and Custom endpoints
  - Story Creation Wizard, Quick Micro Story, and text import
  - Premise, outline, framework, scene content, and storyboard generation

• Episodic Series System
  - Multi-episode stories with shared Series Bible
  - Persistent characters, world settings, lore, and locations
  - AI continuity injection from Series Bible into prompts
  - Convert existing standalone stories to series
  - Series Bible Editor for managing shared data

• Custom Story Duration
  - Specify a total target time for your story
  - AI automatically allocates scene durations
  - Persists across episodes in episodic series

• Smart Pacing & Rhythm
  - Filmmaking-convention pacing rules in framework generation
  - Automatic post-generation validation and correction
  - AI Chat pacing analysis with consecutive-run detection
  - Hard limits: max 2 consecutive Fast or Slow scenes

• Environment & Spatial Consistency
  - Established environment descriptions injected into AI prompts
  - Strict rules prevent AI from inventing rooms, floors, or areas
  - Physical access/zone logic (inside/outside tracking)
  - Held-object continuity within scenes

• Multi-Shot Clustering Engine
  - Group consecutive storyboard items into single video clips
  - Automatic transition generation (whip pan, match cut, etc.)
  - Identity lock reinforcement across clustered shots
  - Render cost estimation

• Advertisement / Brand Film Mode
  - 6-beat commercial template (Hook → Brand Moment)
  - Brand context integration (product, benefit, personality)
  - Distribution platform presets
  - Pacing escalation and hero shot validation

• Identity Block System (8-Field Schema)
  - Characters, vehicles, objects, groups, and environments
  - Character identity (physical) separated from wardrobe (per-scene)
  - Group entities with member count, individuality, and formation
  - Environment extras (MODE A: empty, MODE B: with crowd)
  - Referenced environment detection (mentioned but not visited)
  - Reference image management and prompt generation
  - Approval workflow with status tracking
  - Recurring object detection with 🔄 visual indicator

• Robust Entity Extraction
  - Compound character name splitting
  - Acronym and organization filtering
  - People-group phrase detection (e.g. _Temple Elders_)
  - Species inference with false-positive safeguards
  - Species-aware appearance extraction for non-human characters
  - Substring filtering to prevent environment name fragments
    from being extracted as separate entities

• Post-Generation Content Quality
  - Genre compliance validation
  - Invented backstory and abilities detection
  - Dialogue deduplication
  - AI preamble stripping and paragraph tag cleanup
  - Identity drift detection with synonym-aware color matching
  - Cross-scene character continuity warnings
  - Premise variety (avoids repeating themes on regeneration)
  - Platform-specific prompt length management and deduplication

• Cinematic Grammar Engine
  - Entity markup convention (Characters, Locations, Objects, Vehicles,
    Sound FX, Actions)
  - Real-time token detection and highlighting
  - Action verb and SFX whitelist validation
  - Sentence integrity checking and AI-powered repair
  - Custom whitelists (user-extensible)

• Storyboard Item Editor
  - Full cinematic controls: shot type, camera motion, focal length,
    aperture style, visual style, mood, lighting
  - Beat-aware intelligent defaults for shot type and camera motion
    (dialogue → close-up, action → tracking, tension → low angle, etc.)
  - Image mapping with hero frame, end frame, and entity slots
  - Three-layer prompt editing with platform preview
  - Multi-shot cluster visualization
  - Audio intent and notes

• Export & Generation
  - JSON, CSV, Higgsfield API, Prompts Only, and platform-specific
  - Direct video generation panel with progress tracking
  - Batch generation with cancel support

• AI Story Assistant (Chat Panel)
  - 14 change intents: edit premise, outline, scenes, storyboard items,
    character outlines, identity blocks, Series Bible, and more
  - Before/after preview for every change
  - Proactive analysis: pacing, pending identity blocks, missing outlines
  - Toast notifications on change application
  - Framework regeneration with double confirmation

• User Interface
  - Light and dark themes
  - Adjustable font size (8-24pt), line numbers, auto-save
  - Scroll guard prevents accidental dropdown changes
  - Spell checking throughout

• Seamless Updates
  - Configuration stored in user AppData (survives reinstalls)
  - Automatic config migration from older versions
  - In-place upgrade support via Inno Setup installer

═══════════════════════════════════════════════════════════════════════════════
TECHNOLOGY
═══════════════════════════════════════════════════════════════════════════════

• Built with Python 3.10+ and PyQt6
• OpenAI-compatible API integration
• JSON-based project storage
• Platform: Windows (with PyInstaller distribution)

═══════════════════════════════════════════════════════════════════════════════
AI PROVIDERS (Story Generation)
═══════════════════════════════════════════════════════════════════════════════

• OpenAI, Anthropic (Claude), Together AI, OpenRouter
• Hugging Face, Ollama Cloud, Local (Ollama/LM Studio)
• Custom (any OpenAI-compatible endpoint)

═══════════════════════════════════════════════════════════════════════════════
VIDEO PLATFORMS (Video Generation)
═══════════════════════════════════════════════════════════════════════════════

• Higgsfield Cinema Studio 2.0
• Runway Gen-4 / Gen-4.5
• OpenAI Sora 2
• Kling 3.0 / O3
• Luma Dream Machine Ray 2
• Google Veo 3.0 / 3.1
• Pika 2.2 / 2.5
• Minimax / Hailuo

═══════════════════════════════════════════════════════════════════════════════
VERSION HISTORY
═══════════════════════════════════════════════════════════════════════════════

Version 1.0.0
• Multi-platform video generation (8 platforms)
• Three-layer prompt architecture (Keyframe/Identity/Video)
• Platform-specific prompt adapters and prompt length management
• AI-powered story development: premise, outline, framework, scenes,
  storyboards
• Episodic Series System with Series Bible and Series Manager
• Custom story duration with AI-allocated scene timing
• Smart pacing based on filmmaking conventions with auto-correction
• Environment and spatial consistency enforcement in scene generation
• Physical access/zone logic and held-object continuity
• Multi-shot clustering engine with identity lock reinforcement
• Identity Block System: 8-field visual identity schema with approval
  workflow and reference image management
• Group entity type for collective characters (soldiers, guards, etc.)
  with member count, individuality, formation, and genre-aware aesthetics
• Character identity vs wardrobe separation; species-aware extraction
  for non-human characters
• Robust entity extraction (compound names, acronym filtering,
  people-group detection, species inference, recurring object detection)
• Beat-aware shot type and camera motion defaults per paragraph
• Referenced environment detection for environments mentioned but
  not visited
• Advertisement/Brand Film workflow with 6-beat template
• Cinematic grammar engine with real-time token detection
• Full cinematic controls: shot type, camera motion, focal length,
  aperture style, visual style, mood, lighting
• Post-generation quality: genre compliance, dialogue deduplication,
  AI preamble stripping, identity drift detection, cross-scene
  continuity warnings
• AI Chat Assistant with 14 change intents and targeted help
• Premise variety mechanism for diverse story generation
• Direct video generation with progress tracking
• Export: JSON, CSV, Higgsfield API, Prompts Only, platform-specific
• Novel/text import with AI analysis
• Configuration stored in user AppData (survives updates/reinstalls)
• In-place upgrade support via Inno Setup installer

═══════════════════════════════════════════════════════════════════════════════
COPYRIGHT
═══════════════════════════════════════════════════════════════════════════════

© 2026 SceneWrite
All rights reserved."""


class LicenseDialog(QDialog):
    """Dialog showing license information."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("License")
        self.setMinimumSize(500, 300)
        self.init_ui()
    
    def init_ui(self):
        """Initialize the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # License text
        license_text = QTextEdit()
        license_text.setReadOnly(True)
        license_text.setPlainText(self.get_license_text())
        license_text.setFont(QFont("Arial", 10))
        license_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        license_text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        license_text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(license_text)
        
        # Close button
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.accept)
        layout.addWidget(button_box)
    
    def get_license_text(self) -> str:
        """Get the license text content."""
        return """SOFTWARE LICENSE AGREEMENT
═══════════════════════════════════════════════════════════════════════════════

SceneWrite - Version 1.0.0
Developed by Quantum Spark Software

═══════════════════════════════════════════════════════════════════════════════
IMPORTANT - READ CAREFULLY
═══════════════════════════════════════════════════════════════════════════════

This License Agreement ("Agreement") is a legal agreement between you (either 
an individual or a single entity) and Quantum Spark Software ("Licensor") for 
the SceneWrite software product identified above, which includes 
computer software and may include associated media, printed materials, and 
"online" or electronic documentation ("Software").

By installing, copying, or otherwise using the Software, you agree to be bound 
by the terms of this Agreement. If you do not agree to the terms of this 
Agreement, do not install or use the Software.

═══════════════════════════════════════════════════════════════════════════════
1. GRANT OF LICENSE
═══════════════════════════════════════════════════════════════════════════════

Subject to the terms and conditions of this Agreement, you are granted a 
non-exclusive, non-transferable license to install and use the Software on a 
single computer for your personal or commercial use. This license is granted 
for the lifetime of the Software version you have purchased.

You may:
• Install and use the Software on one computer at a time
• Make one backup copy of the Software for archival purposes
• Transfer the Software to another computer, provided you remove it from the 
  previous computer

You may NOT:
• Install or use the Software on multiple computers simultaneously
• Copy, distribute, or share the Software with others
• Rent, lease, or lend the Software
• Transfer your license to another person or entity without written permission
• Use the Software in any way that violates applicable laws or regulations

═══════════════════════════════════════════════════════════════════════════════
2. INTELLECTUAL PROPERTY RIGHTS
═══════════════════════════════════════════════════════════════════════════════

The Software is protected by copyright laws and international copyright treaties, 
as well as other intellectual property laws and treaties. The Software is 
licensed, not sold. All title and copyrights in and to the Software (including 
but not limited to any images, photographs, animations, video, audio, music, 
text, and "applets" incorporated into the Software), the accompanying printed 
materials, and any copies of the Software are owned by Quantum Spark Software.

You may not:
• Reverse engineer, decompile, or disassemble the Software
• Remove or alter any copyright notices or other proprietary rights notices
• Create derivative works based on the Software
• Use the Software to develop competing products

═══════════════════════════════════════════════════════════════════════════════
3. UPDATES AND SUPPORT
═══════════════════════════════════════════════════════════════════════════════

This license entitles you to:
• Use the Software version you have purchased
• Receive bug fixes and minor updates for the version you purchased
• Access to documentation and user guides

Major version upgrades (e.g., version 2.0) may require a separate purchase. 
Support is provided on a best-effort basis and may be limited to email support 
or community forums.

═══════════════════════════════════════════════════════════════════════════════
4. WARRANTY DISCLAIMER
═══════════════════════════════════════════════════════════════════════════════

THE SOFTWARE IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND, EITHER EXPRESS 
OR IMPLIED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF 
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NONINFRINGEMENT. THE 
ENTIRE RISK AS TO THE QUALITY AND PERFORMANCE OF THE SOFTWARE IS WITH YOU.

Some jurisdictions do not allow the exclusion of implied warranties, so the 
above exclusion may not apply to you. You may have other rights that vary from 
jurisdiction to jurisdiction.

═══════════════════════════════════════════════════════════════════════════════
5. LIMITATION OF LIABILITY
═══════════════════════════════════════════════════════════════════════════════

IN NO EVENT SHALL QUANTUM SPARK SOFTWARE OR ITS SUPPLIERS BE LIABLE FOR ANY 
DAMAGES WHATSOEVER (INCLUDING, WITHOUT LIMITATION, DAMAGES FOR LOSS OF BUSINESS 
PROFITS, BUSINESS INTERRUPTION, LOSS OF BUSINESS INFORMATION, OR ANY OTHER 
PECUNIARY LOSS) ARISING OUT OF THE USE OF OR INABILITY TO USE THE SOFTWARE, 
EVEN IF QUANTUM SPARK SOFTWARE HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH 
DAMAGES.

In no event shall the total liability of Quantum Spark Software exceed the 
amount you paid for the Software.

Some jurisdictions do not allow the limitation or exclusion of liability for 
incidental or consequential damages, so the above limitation may not apply to you.

═══════════════════════════════════════════════════════════════════════════════
6. TERMINATION
═══════════════════════════════════════════════════════════════════════════════

This license is effective until terminated. Your rights under this license will 
terminate automatically without notice if you fail to comply with any term(s) 
of this Agreement. Upon termination of the license, you shall cease all use of 
the Software and destroy all copies, full or partial, of the Software.

═══════════════════════════════════════════════════════════════════════════════
7. REFUND POLICY
═══════════════════════════════════════════════════════════════════════════════

Refund requests must be made within 30 days of purchase. Refunds may be granted 
at the sole discretion of Quantum Spark Software, subject to verification of 
purchase and compliance with refund policy terms. Refunds may be denied if the 
Software has been used extensively or if there is evidence of license violation.

═══════════════════════════════════════════════════════════════════════════════
8. THIRD-PARTY SERVICES
═══════════════════════════════════════════════════════════════════════════════

The Software may integrate with third-party AI services and APIs. Your use of 
such services is subject to the terms and conditions of those third-party 
providers. Quantum Spark Software is not responsible for the availability, 
accuracy, or content of third-party services, nor for any costs associated with 
their use.

═══════════════════════════════════════════════════════════════════════════════
9. EXPORT RESTRICTIONS
═══════════════════════════════════════════════════════════════════════════════

You may not export or re-export the Software or any copy or adaptation of the 
Software in violation of any applicable laws or regulations.

═══════════════════════════════════════════════════════════════════════════════
10. GOVERNING LAW
═══════════════════════════════════════════════════════════════════════════════

This Agreement shall be governed by and construed in accordance with the laws 
of the jurisdiction in which Quantum Spark Software operates, without regard to 
its conflict of law provisions.

═══════════════════════════════════════════════════════════════════════════════
11. ENTIRE AGREEMENT
═══════════════════════════════════════════════════════════════════════════════

This Agreement constitutes the entire agreement between you and Quantum Spark 
Software relating to the Software and supersedes all prior or contemporaneous 
oral or written communications, proposals, and representations with respect to 
the Software or any other subject matter covered by this Agreement.

═══════════════════════════════════════════════════════════════════════════════
12. CONTACT INFORMATION
═══════════════════════════════════════════════════════════════════════════════

For questions about this license or the Software, please contact Quantum Spark 
Software through the appropriate support channels.

═══════════════════════════════════════════════════════════════════════════════
ACKNOWLEDGMENT
═══════════════════════════════════════════════════════════════════════════════

BY INSTALLING OR USING THE SOFTWARE, YOU ACKNOWLEDGE THAT YOU HAVE READ THIS 
AGREEMENT, UNDERSTAND IT, AND AGREE TO BE BOUND BY ITS TERMS AND CONDITIONS.

© 2026 Quantum Spark Software. All rights reserved.
SceneWrite is a product of Quantum Spark Software."""