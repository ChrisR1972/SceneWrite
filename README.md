# SceneWrite

A professional desktop application for creating screenplay storyboards with native support for 8 AI video generation platforms. SceneWrite provides a complete workflow from initial premise to platform-ready prompts, using a three-layer prompt architecture (Keyframe, Identity, Video) with automatic platform adaptation.

## Key Features

- **Multi-Platform Video Generation**: Native support for Higgsfield, Runway, Kling, Luma, Pika, OpenAI Sora, Google Veo, and Minimax/Hailuo — with platform-specific prompt adapters that automatically optimize output for each target
- **Three-Layer Prompt Architecture**: Keyframe (static hero frame), Identity (character/entity consistency locks), and Video (camera movement and action) — compiled and adapted per platform
- **AI-Powered Story Development**: Generate premises, outlines, frameworks, scene content, and storyboards with AI assistance from 8 supported providers
- **Episodic Series System**: Create multi-episode stories with a shared Series Bible for persistent characters, world settings, and lore — each episode gets fresh storylines with automatic continuity
- **Custom Story Duration**: Specify a total target time for your story and the AI automatically allocates scene durations; persists across episodes for series
- **Smart Pacing**: Framework generation follows established filmmaking pacing conventions with automatic post-generation validation and correction
- **Environment & Spatial Consistency**: Established environment descriptions are injected into prompts; strict rules prevent the AI from inventing rooms, floors, or areas not in the scene's established location; referenced-only environments detected and handled separately
- **Multi-Shot Clustering**: Group consecutive storyboard items into single video clips with automatic transitions and identity lock reinforcement
- **Identity Block System**: 8-field visual identity schema for characters, groups, vehicles, objects, and environments with approval workflow and reference image management
- **Group Characters**: Collective entities (soldiers, guards) with member count, individuality settings, genre-aware aesthetics, and formation control
- **Character Identity vs Wardrobe**: Global physical identity separated from scene-level wardrobe for visual consistency across costume changes; species-aware extraction for non-human characters
- **Robust Entity Extraction**: Compound character names, acronym filtering, people-group detection, species inference, recurring object detection, and substring filtering
- **Advertisement Mode**: 6-beat commercial template (Hook → Brand Moment) with brand context, escalation validation, and hero shot enforcement
- **Cinematic Grammar Engine**: Real-time token detection, action/SFX whitelist validation, sentence integrity checking, and auto-correction
- **Full Cinematic Controls**: Shot type, camera motion, focal length, aperture style, visual style, mood, lighting — per storyboard item with beat-aware intelligent defaults
- **Post-Generation Quality**: Genre compliance, dialogue deduplication, AI preamble stripping, identity drift detection with synonym-aware color matching, and cross-scene continuity warnings
- **Direct Video Generation**: Submit storyboard items to video platforms directly from the app with progress tracking
- **Export Formats**: JSON, CSV, Higgsfield API, Prompts Only, and platform-specific adapted exports
- **AI Chat Assistant**: Full-featured story assistant with 14 change intents — edit premises, outlines, scenes, storyboard items, character outlines, identity blocks, and Series Bible entries through natural conversation; includes pacing and identity-block analysis, before/after preview, and toast notifications
- **Seamless Updates**: Configuration stored in user AppData survives application updates; Inno Setup installer supports in-place upgrades
- **Auto-Save**: Configurable automatic saving of your work

## Supported AI Providers (Story Generation)

| Provider | Base URL | Notes |
|----------|----------|-------|
| OpenAI | api.openai.com/v1 | GPT-4, GPT-4o, etc. |
| Anthropic | — | Claude models |
| Together AI | api.together.xyz/v1 | Cost-effective alternative |
| OpenRouter | openrouter.ai/api/v1 | Multi-model gateway |
| Hugging Face | api-inference.huggingface.co/v1/ | HF Inference API |
| Ollama Cloud | Custom | Cloud-hosted Ollama |
| Local | localhost:11434/v1 or :1234/v1 | Ollama, LM Studio |
| Custom | User-defined | Any OpenAI-compatible endpoint |

## Supported Video Platforms

| Platform | Models | Max Duration | Special Features |
|----------|--------|-------------|-----------------|
| Higgsfield | Cinema Studio 2.0 | 30s | Multi-shot, identity lock, image gen |
| Runway | Gen-4, Gen-4.5 | 10s | |
| OpenAI Sora | Sora 2, Sora 2 Pro | 12s | Duration presets |
| Kling | O3, Kling 3.0, 2.6 | 10s | |
| Luma | Ray 2, Ray Flash 2 | 10s | Loop mode |
| Google Veo | Veo 3.0, 3.1 | 8s | Duration presets |
| Pika | Pika 2.2, 2.5 | 10s | Motion strength control |
| Minimax | Hailuo 2.3, 02 | 10s | Duration presets |

## Installation

### For End Users (Windows Executable)

1. Download the latest release from the releases page
2. Extract the `SceneWrite` folder
3. Run `SceneWrite.exe`
4. No Python installation required

### For Developers

1. Install Python 3.10 or higher
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the application:
   ```bash
   python main.py
   ```

### Building the Executable

```bash
pip install PyInstaller
build_exe.bat
```

The executable will be in `dist\SceneWrite\`. See `BUILD_INSTRUCTIONS.md` for detailed build and distribution guidance.

## Configuration

### Config File Location

Configuration is stored in your user data directory so it survives updates:

| Platform | Path |
|----------|------|
| Windows  | `%APPDATA%\SceneWrite\config.json` |
| macOS    | `~/Library/Application Support/SceneWrite/config.json` |
| Linux    | `~/.config/SceneWrite/config.json` |

Existing users upgrading from an older version will have their config automatically migrated on first launch.

### AI Provider Setup

Configure in Settings → AI Config, or edit `config.json`:

```json
{
  "ai_provider": "OpenAI",
  "api_key": "your-api-key",
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-4o"
}
```

For local AI servers:

```json
{
  "ai_provider": "Local",
  "base_url": "http://localhost:11434/v1",
  "model": "your-model-name"
}
```

The `OPENAI_API_KEY` environment variable can override the config file.

### Video Platform API Keys

Configure in Settings → AI Config under "Platform API Keys", or add to `config.json`:

```json
{
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
  }
}
```

## Usage

### Recommended Workflow

1. **Configure AI Provider** — Settings → AI Config
2. **Set Up Platform API Keys** — For your target video platform
3. **Create a Story** — File → New Story (AI Generated) for the wizard, or Ctrl+M for a quick micro story
4. **Configure Story Settings** — Story Settings tab: platform, visual style, aspect ratio, cinematic controls
5. **Generate Story Outline & Framework** — Through the wizard or manually
6. **Write Scene Content** — Generate with AI or write manually using cinematic markup
7. **Approve Scenes** — Triggers entity extraction and identity block creation
8. **Manage Identity Blocks** — Generate, review, and approve identity blocks for all entities
9. **Upload Reference Images** — For characters, vehicles, objects, and environments
10. **Generate Storyboards** — AI creates timed items with three-layer prompts
11. **Edit in Storyboard Item Editor** — Fine-tune cinematic controls and prompts
12. **Generate Video** — Use the Generation Panel to submit directly to your video platform
13. **Export** — JSON, CSV, Higgsfield API, Prompts Only, or platform-specific format

### Entity Markup Convention

Scene text uses cinematic markup to identify entities:

| Entity | Markup | Example |
|--------|--------|---------|
| Characters | FULL CAPS | MAYA RIVERA |
| Locations | _underlined_ | _Midnight Falls_ |
| Objects | [brackets] | [console] |
| Vehicles | {{braces}} | {{motorcycle}} |
| Sound FX | (parentheses) | (metal_clang) |
| Actions | *asterisks* | *walks* |

### Three-Layer Prompts

Each storyboard item generates three prompt layers:

- **Keyframe**: Static first-frame composition (no action verbs)
- **Identity**: Auto-generated from approved identity blocks (read-only)
- **Video**: Camera movement, character actions, dialogue

These are automatically combined and adapted for your selected video platform.

## Project Structure

```
core/              Core business logic (data models, AI, prompts, validation, export, series)
ui/                PyQt6 interface components
ui/wizard_steps/   Story Creation Wizard step pages
utils/             Logging utilities
config/            User-extensible whitelists (auto-created)
main.py            Application entry point
config.py          Configuration management (AppData storage with migration)
```

## Storyboard Items

Each storyboard item contains:

- **Duration**: 1–30 seconds (AI-optimized, user-adjustable)
- **Scene Setup**: Shot type, camera motion, focal length, aperture, visual style, mood, lighting
- **Storyline**: 2–4 sentence action description
- **Composition/Blocking**: Scene layout notes
- **Dialogue**: CHARACTER: "text" format
- **Three-Layer Prompts**: Keyframe, Identity, Video, and Platform-adapted output
- **Image Mapping**: Hero frame, end frame, and entity reference slots
- **Audio**: Intent, notes, and source configuration
- **Multi-Shot Info**: Cluster ID, shot number, transition type (when clustering is enabled)

## Export Formats

| Format | Description |
|--------|-------------|
| JSON | Complete story data with three-layer prompts |
| CSV | Spreadsheet-compatible storyboard items |
| Higgsfield API | API-compatible format for Higgsfield Cinema Studio |
| Prompts Only | Plain text with compiled prompt layers |
| Platform-Specific | Adapted prompts for selected video platform |

## License

SceneWrite is a product of Quantum Spark Software. See Help → License for full terms.
