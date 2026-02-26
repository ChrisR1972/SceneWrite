# MoviePrompterAI

A professional desktop application for creating screenplay storyboards optimized for higgsfield.ai video generation.

## Features

- **Premise Generation**: Create story premises manually or use AI to generate from genre and atmosphere selections
- **AI-Powered Storyboard Generation**: Automatically generate storyboards with AI-optimized per-item durations
- **Timeline View**: Visual timeline displaying all storyboard items as cards
- **Item Editor**: Full-featured editor for individual storyboard items with AI-assisted prompt regeneration
- **Export Formats**: Export to JSON, CSV, or higgsfield.ai-optimized format
- **Auto-Save**: Automatic saving of your work

## Installation

### For End Users (Windows Executable)

1. Download the latest release from the releases page
2. Extract the `MoviePrompterAI` folder
3. Run `MoviePrompterAI.exe`
4. No Python installation required!

### For Developers

1. Install Python 3.10 or higher
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up your OpenAI API key (see Configuration below)

### Building the Executable

To create a standalone Windows executable:

1. Install PyInstaller:
   ```bash
   pip install PyInstaller
   ```

2. Run the build script:
   ```bash
   build_exe.bat
   ```

3. The executable will be in the `dist\MoviePrompterAI\` folder

4. To distribute, zip the entire `MoviePrompterAI` folder and share it

## Configuration

Create a `config.json` file or set the OPENAI_API_KEY environment variable:
```
OPENAI_API_KEY=your_api_key_here
```

For local AI servers (Ollama, LM Studio, etc.), configure in the application or edit `config.json`:
```json
{
  "ai_provider": "Local",
  "base_url": "http://localhost:11434/v1",
  "model": "your-model-name"
}
```

## Usage

Run the application:
```bash
python main.py
```

### Creating a Storyboard

1. **Generate or Enter Premise**:
   - Click "Generate Premise" to use AI generation
   - Select genres and atmosphere, then click "Generate Premise"
   - Or manually enter a premise in the "Manual Entry" tab

2. **Generate Storyboard**:
   - Click "Generate Storyboard" after you have a premise
   - Select the desired length (Micro, Short, Medium, or Long)
   - Wait for AI to generate the storyboard items

3. **Edit Items**:
   - Click on any storyboard item card to edit it
   - Modify duration, prompt, description, dialogue, or camera notes
   - Use "Regenerate with AI" to improve prompts

4. **Export**:
   - Use File → Export to save in various formats
   - "Export for higgsfield.ai" creates an optimized JSON format

## Project Structure

- `core/`: Storyboard engine, AI generation, export functionality
- `ui/`: PyQt6 interface components
- `main.py`: Application entry point
- `config.py`: Configuration management

## Storyboard Items

Each storyboard item contains:
- **Duration**: 1-30 seconds (AI-determined optimal duration, user-adjustable)
- **Prompt**: Video generation prompt optimized for higgsfield.ai
- **Visual Description**: Detailed scene description
- **Dialogue**: Optional dialogue text
- **Scene Type**: Action, dialogue, transition, etc.
- **Camera Notes**: Optional camera/visual direction

## Export Formats

- **JSON**: Standard JSON format with all storyboard data
- **CSV**: Spreadsheet-compatible format
- **higgsfield.ai**: Optimized format for higgsfield.ai video generation
- **Prompts Only**: Simple text file with one prompt per line

## License

MIT License

