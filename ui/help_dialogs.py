"""
Help dialogs for MoviePrompterAI.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QTextEdit, QPushButton, QDialogButtonBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


def get_comprehensive_instructions() -> str:
    """Get comprehensive instructions for using the app."""
    return """FRAMEFORGE - COMPREHENSIVE USER GUIDE
═══════════════════════════════════════════════════════════════════════════════

OVERVIEW
═══════════════════════════════════════════════════════════════════════════════
This application helps you create professional screenplays with AI assistance, 
from initial premise to detailed storyboards optimized for video generation. 
The app supports multiple AI providers and offers a complete workflow for 
story development, character creation, scene management, storyboard generation 
and detailed prompts for AI image & video generation.

═══════════════════════════════════════════════════════════════════════════════
PART 1: AI CONFIGURATION
═══════════════════════════════════════════════════════════════════════════════

CONFIGURING YOUR AI PROVIDER
───────────────────────────────────────────────────────────────────────────────
Before using AI features, you must configure your AI provider in Settings → AI Config.

SUPPORTED AI PROVIDERS:
───────────────────────────────────────────────────────────────────────────────
The app works with ANY provider that implements the OpenAI Chat Completions API 
format and supports the /v1/chat/completions endpoint. This includes:

• OpenAI (Native)
  - Base URL: https://api.openai.com/v1
  - Requires API key from https://platform.openai.com
  - Supports GPT-3.5, GPT-4, and other OpenAI models

• Local (Ollama/LM Studio)
  - Base URL: http://localhost:11434/v1 (Ollama) or http://localhost:1234/v1 (LM Studio)
  - No API key required for most local setups
  - Run Ollama or LM Studio locally, then select this provider
  - Click "Refresh Models" to load available models

• Together AI
  - Base URL: https://api.together.xyz/v1
  - Requires API key from https://together.ai
  - Cost-effective alternative to OpenAI

• OpenRouter
  - Base URL: https://openrouter.ai/api/v1
  - Requires API key from https://openrouter.ai
  - Access to multiple AI models through one API

• Hugging Face
  - Base URL: https://api-inference.huggingface.co/v1/
  - Requires API key (HF_TOKEN) from https://huggingface.co
  - Uses Hugging Face Inference API

• Custom Provider
  - Enter your own base URL and API key
  - Works with any OpenAI-compatible API endpoint
  - Examples: Groq, Anyscale, DeepInfra, Azure OpenAI, etc.

OPENAI COMPATIBILITY REQUIREMENTS:
───────────────────────────────────────────────────────────────────────────────
Your app uses the OpenAI Python library and the Chat Completions API format. 
For a provider to work with this app, it must:

1. Support the /v1/chat/completions endpoint
2. Accept the same request format (messages array with role/content)
3. Return responses in the same JSON format as OpenAI

Most modern AI providers offer OpenAI-compatible APIs, making them compatible 
with this application.

CONFIGURATION STEPS:
───────────────────────────────────────────────────────────────────────────────
1. Go to Settings → AI Config
2. Select your AI provider from the dropdown
3. Enter your API key (if required)
4. Enter or verify the base URL (auto-filled for most providers)
5. Select your model from the dropdown
6. Adjust temperature and max tokens if needed
7. Click "Test AI Connection" to verify setup
8. Click "Save" to apply settings

IMPORTANT NOTES:
───────────────────────────────────────────────────────────────────────────────
• Each provider remembers its own base URL when you switch between them
• For Local providers, use "Refresh Models" to load available models
• The base URL field is automatically filled with defaults but can be customized
• API keys are stored securely in your config.json file

═══════════════════════════════════════════════════════════════════════════════
PART 2: GETTING STARTED
═══════════════════════════════════════════════════════════════════════════════

CREATING A NEW STORY
───────────────────────────────────────────────────────────────────────────────
You can create a new story in two ways:

METHOD 1: AI-GENERATED STORY (RECOMMENDED)
1. Click File → New Story (AI Generated) or press Ctrl+N
2. This opens the Story Creation Wizard with AI assistance

METHOD 2: MANUAL STORY
1. Click File → New Story (Manual)
2. Enter a title (required)
3. Optionally enter a premise
4. Click OK to create a basic story structure

═══════════════════════════════════════════════════════════════════════════════
PART 3: STORY CREATION WIZARD
═══════════════════════════════════════════════════════════════════════════════

The wizard guides you through creating a complete story structure with AI assistance.

WIZARD STEP 1: PREMISE
───────────────────────────────────────────────────────────────────────────────
1. Select one or more genres (multiple selection allowed)
2. Choose an atmosphere/tone from the dropdown
3. Click "Generate Premise"
4. Review and edit the generated premise as needed
5. Click "Next" to proceed

Note: For manual premise entry without AI, use File → New Story (Manual) instead.

WIZARD STEP 2: STORY OUTLINE
───────────────────────────────────────────────────────────────────────────────
1. Click "Generate Story Outline" to create:
   - Main Storyline: Detailed expansion of your premise (5-8 sentences)
   - Subplots: 2-4 secondary storylines (2-3 sentences each)
   - Conclusion: How the story resolves (4-6 sentences)
   - Character Profiles: Automatically generated after conclusion

2. Use "Regenerate" buttons to regenerate any section
3. Edit any text directly in the fields
4. Characters are automatically generated after the conclusion is finalized
5. Click "Next" when complete

WIZARD STEP 3: FRAMEWORK GENERATION
───────────────────────────────────────────────────────────────────────────────
1. Click "Generate Framework" to create:
   - Story Acts: Act 1, Act 2, Act 3 structure
   - Scenes: Multiple scenes within each act
   - Scene Metadata: Titles, descriptions, durations, character focus

2. Edit scene details:
   - Click a scene to select it
   - Edit title, description, duration, and character focus
   - Add or remove scenes as needed

3. Click "Finish" to complete the wizard and start working with your story

═══════════════════════════════════════════════════════════════════════════════
PART 4: WORKING WITH SCENES
═══════════════════════════════════════════════════════════════════════════════

VIEWING SCENES
───────────────────────────────────────────────────────────────────────────────
• Scenes appear in the main Storyboard tab
• Each scene shows its title, description, and metadata
• Click a scene to select and view its details

EDITING SCENES
───────────────────────────────────────────────────────────────────────────────
1. Select a scene in the storyboard view
2. Use the Scene Framework Editor (right panel) to edit:
   - Title: Scene name
   - Description: What happens in the scene
   - Estimated Duration: Scene length in seconds
   - Character Focus: Which characters appear (comma-separated)
3. Changes save automatically

GENERATING STORYBOARD ITEMS
───────────────────────────────────────────────────────────────────────────────
1. Select a scene in the storyboard view
2. Click "Generate Storyboard for Scene" button
3. The AI breaks the scene into storyboard items with AI-optimized durations
4. Each item includes:
   - Sequence number
   - Duration (seconds)
   - Storyline description
   - Video prompt (for video generation)
   - Composition prompt (scene layout)
   - Dialogue (if applicable)
   - Scene type (action, dialogue, transition, etc.)

EDITING STORYBOARD ITEMS
───────────────────────────────────────────────────────────────────────────────
1. Click a storyboard item to select it
2. Use the Storyboard Item Editor to modify:
   - Duration
   - Storyline
   - Video prompt
   - Composition prompt
   - Dialogue
   - Scene type
3. Use "Regenerate Video Prompt" or "Regenerate Composition Prompt" for AI assistance
4. Changes save automatically

MOVING STORYBOARD ITEMS
───────────────────────────────────────────────────────────────────────────────
• Select one or more items
• Use "↑ Move Up" or "↓ Move Down" buttons to reorder
• Use "Select All" to select all items in a scene

═══════════════════════════════════════════════════════════════════════════════
PART 5: IDENTITY BLOCKS
═══════════════════════════════════════════════════════════════════════════════

Identity blocks define the visual appearance of characters, vehicles, objects, 
and environments for consistent video generation.

ACCESSING IDENTITY BLOCKS
───────────────────────────────────────────────────────────────────────────────
1. Go to the "Identity Blocks" tab in the main window
2. View all entities organized by type:
   - Characters
   - Vehicles
   - Objects
   - Environments

CREATING IDENTITY BLOCKS
───────────────────────────────────────────────────────────────────────────────
1. Select an entity from the list (or it will be created automatically)
2. Enter User Notes: A brief description (e.g., "Male captain, 40s, worn uniform")
3. Click "Generate Identity Block"
4. Review the generated detailed description
5. Click "Approve" when satisfied (this locks the identity block)

REFERENCE IMAGE PROMPTS
───────────────────────────────────────────────────────────────────────────────
1. After approving an identity block, click "Generate Reference Image Prompt"
2. Copy the generated prompt
3. Use it in Higgsfield or other image generation tools
4. Create reference images for consistent visual appearance

EDITING IDENTITY BLOCKS
───────────────────────────────────────────────────────────────────────────────
• Before approval: Edit User Notes and regenerate
• After approval: Identity blocks are locked to maintain consistency
• To change an approved block, you'll need to regenerate it

═══════════════════════════════════════════════════════════════════════════════
PART 6: AI CHAT ASSISTANT
═══════════════════════════════════════════════════════════════════════════════

The AI Chat Assistant provides context-aware help and can make changes to your story.

USING THE CHAT
───────────────────────────────────────────────────────────────────────────────
1. Open the AI Chat Panel (View → Show AI Chat, or it may be visible by default)
2. Type questions or requests about your story
3. The AI can:
   - Discuss story elements and provide suggestions
   - Regenerate scenes with modifications
   - Edit scene content based on your feedback
   - Modify character outlines
   - Add or remove storyboard items
   - Change character focus in scenes
   - Answer questions about app usage

CHAT FEATURES
───────────────────────────────────────────────────────────────────────────────
• Context-Aware: Select a scene or storyboard items to give the AI context
• Suggestions: The AI provides actionable suggestions with buttons:
  - "Apply": Apply the change immediately
  - "Preview": Review changes before applying
  - "Dismiss": Ignore the suggestion
• Preview Changes: Review all changes in a before/after comparison dialog

CHAT TIPS
───────────────────────────────────────────────────────────────────────────────
• Be specific in your requests
• Select relevant scenes/items for context before asking questions
• Use "Preview" before applying major changes
• Ask "How do I use this app?" for usage instructions
• The chat works even without AI configured for instruction requests

═══════════════════════════════════════════════════════════════════════════════
PART 7: EXPORTING YOUR WORK
═══════════════════════════════════════════════════════════════════════════════

EXPORT FORMATS
───────────────────────────────────────────────────────────────────────────────
The app supports multiple export formats:

1. JSON Export
   - File → Export → Export as JSON
   - Complete story data in JSON format
   - Useful for backups and data transfer

2. CSV Export
   - File → Export → Export as CSV
   - Storyboard items in spreadsheet format
   - Useful for analysis and external tools

3. Higgsfield Export (RECOMMENDED FOR VIDEO)
   - File → Export → Export for higgsfield.ai
   - Optimized format for Higgsfield video generation
   - Includes all prompts and metadata

4. Prompts Only Export
   - File → Export → Export Prompts Only
   - Just the video prompts without other data
   - Useful for quick prompt extraction

EXPORT OPTIONS
───────────────────────────────────────────────────────────────────────────────
When exporting for Higgsfield, you can choose:
• Include identity blocks
• Include reference images
• Select specific scenes to export

═══════════════════════════════════════════════════════════════════════════════
PART 8: UI CUSTOMIZATION
═══════════════════════════════════════════════════════════════════════════════

APPEARANCE SETTINGS
───────────────────────────────────────────────────────────────────────────────
1. Go to Settings → UI Config
2. Choose Theme:
   - Light: Light color scheme
   - Dark: Dark color scheme
3. Adjust Font Size: Use the slider (10-18px)
4. Click "Save" to apply changes

SETTINGS ARE APPLIED GLOBALLY
───────────────────────────────────────────────────────────────────────────────
• Theme and font size apply to the entire application
• Changes take effect immediately after saving
• Settings persist between sessions

═══════════════════════════════════════════════════════════════════════════════
PART 9: KEYBOARD SHORTCUTS
═══════════════════════════════════════════════════════════════════════════════

FILE OPERATIONS:
───────────────────────────────────────────────────────────────────────────────
• Ctrl+N: New Story (AI Generated)
• Ctrl+O: Open Story
• Ctrl+S: Save Story
• Ctrl+Shift+S: Save As
• Ctrl+Q: Exit Application

CHAT:
───────────────────────────────────────────────────────────────────────────────
• Ctrl+Enter: Send message in AI Chat

═══════════════════════════════════════════════════════════════════════════════
PART 10: BEST PRACTICES & TIPS
═══════════════════════════════════════════════════════════════════════════════

STORY DEVELOPMENT
───────────────────────────────────────────────────────────────────────────────
• Start with a strong premise - it guides everything else
• Let the AI generate initial content, then refine it manually
• Use the chat assistant for iterative improvements
• Regenerate sections that don't fit your vision
• Don't be afraid to edit AI-generated content

CHARACTER DEVELOPMENT
───────────────────────────────────────────────────────────────────────────────
• Create identity blocks early for main characters
• Use detailed user notes for better AI generation
• Review and approve identity blocks before generating scenes
• Update character outlines as your story evolves
• Keep character focus consistent across scenes

SCENE MANAGEMENT
───────────────────────────────────────────────────────────────────────────────
• Set appropriate durations (typically 30-120 seconds per scene)
• Specify character focus to help with image generation
• Generate storyboards after scene content is finalized
• Edit storyboard items to fine-tune video prompts
• Use composition prompts for scene layout, not visual details

STORYBOARD ITEMS
───────────────────────────────────────────────────────────────────────────────
• Durations are AI-optimized per item (1-30 seconds) and can be adjusted manually
• Composition prompts should focus on positioning, not visual details
• Visual details come from identity blocks and reference images
• Use dialogue sparingly and only when necessary
• Regenerate prompts if they don't match your vision

AI CHAT
───────────────────────────────────────────────────────────────────────────────
• Be specific in your requests
• Select relevant scenes/items for context
• Use "Preview" before applying major changes
• Ask for help anytime: "How do I use this app?"
• The AI remembers context from your current selection

WORKFLOW RECOMMENDATION
───────────────────────────────────────────────────────────────────────────────
1. Configure AI provider in Settings → AI Config
2. Create new story with wizard
3. Generate premise (AI or manual)
4. Generate story outline
5. Generate framework (acts and scenes)
6. Create identity blocks for main characters
7. Generate storyboards for each scene
8. Refine using AI chat and manual edits
9. Export for video generation

═══════════════════════════════════════════════════════════════════════════════
GETTING HELP
═══════════════════════════════════════════════════════════════════════════════

• Help Menu: Access Instructions, About, and License from the Help menu
• AI Chat: Ask "How do I use this app?" for usage instructions
• Settings: Check AI Config and UI Config for configuration options
• This Guide: Access via Help → Instructions

═══════════════════════════════════════════════════════════════════════════════
END OF GUIDE
═══════════════════════════════════════════════════════════════════════════════
"""


class InstructionsDialog(QDialog):
    """Dialog showing comprehensive app instructions."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Instructions")
        self.setMinimumSize(800, 600)
        self.init_ui()
    
    def init_ui(self):
        """Initialize the dialog UI."""
        layout = QVBoxLayout(self)
        
        # Instructions text
        instructions_text = QTextEdit()
        instructions_text.setReadOnly(True)
        instructions_text.setPlainText(get_comprehensive_instructions())
        instructions_text.setFont(QFont("Consolas", 9))
        instructions_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(instructions_text)
        
        # Close button
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.accept)
        layout.addWidget(button_box)


class AboutDialog(QDialog):
    """Dialog showing about information."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About MoviePrompterAI")
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
        return """MOVIEPROMPTERAI
═══════════════════════════════════════════════════════════════════════════════

Version 1.4

═══════════════════════════════════════════════════════════════════════════════
DESCRIPTION
═══════════════════════════════════════════════════════════════════════════════

A professional screenplay writing application that combines AI-powered story 
generation with comprehensive scene and storyboard management. Create complete 
screenplays from initial premise to detailed video generation prompts, optimized 
for AI video platforms like Higgsfield.ai.

═══════════════════════════════════════════════════════════════════════════════
KEY FEATURES
═══════════════════════════════════════════════════════════════════════════════

• AI-Powered Story Generation
  - Generate premises, outlines, and story frameworks with AI assistance
  - Support for multiple AI providers (OpenAI, Together AI, OpenRouter, 
    Hugging Face, Local models, and custom providers)
  - OpenAI-compatible API support for maximum flexibility

• Complete Story Development Workflow
  - Story Creation Wizard for guided story development
  - Manual story creation mode for full control
  - Act and scene structure management
  - Character profile generation and management

• Advanced Scene Management
  - Detailed scene editing with metadata
  - Character focus tracking
  - Scene duration estimation
  - Plot point assignment

• Storyboard Generation
  - AI-powered storyboard item generation with optimized per-item durations
  - Detailed video prompts for AI video generation
  - Composition prompts for scene layout
  - Dialogue integration
  - Storyboard item reordering and editing

• Identity Block System
  - Character, vehicle, object, and environment identity blocks
  - Consistent visual appearance across video generation
  - Reference image prompt generation
  - Approval workflow for locked identity blocks

• AI Chat Assistant
  - Context-aware story assistance
  - Interactive story modifications
  - Preview and apply changes workflow

• Export Capabilities
  - JSON export for data backup and transfer
  - CSV export for spreadsheet analysis
  - Higgsfield.ai optimized export format
  - Prompts-only export option

• User Interface
  - Light and dark themes
  - Adjustable font sizes
  - Intuitive tab-based interface

═══════════════════════════════════════════════════════════════════════════════
TECHNOLOGY
═══════════════════════════════════════════════════════════════════════════════

• Built with Python and PyQt6
• OpenAI Python library for AI integration
• JSON-based data storage
• Cross-platform compatibility (Windows, macOS, Linux)

═══════════════════════════════════════════════════════════════════════════════
AI PROVIDER SUPPORT
═══════════════════════════════════════════════════════════════════════════════

Works with any AI provider that supports the OpenAI Chat Completions API format:
• OpenAI (Native)
• Together AI
• OpenRouter
• Hugging Face Inference API
• Local models (Ollama, LM Studio)
• Custom providers (Groq, Anyscale, DeepInfra, Azure OpenAI, etc.)

═══════════════════════════════════════════════════════════════════════════════
VERSION HISTORY
═══════════════════════════════════════════════════════════════════════════════

Version 1.4
• Enhanced premise tab with full editing capabilities
• Improved UI configuration options
• Expanded AI provider support
• Better error handling and debugging
• Enhanced manual story creation workflow
• Improved text wrapping and scrollbar management

═══════════════════════════════════════════════════════════════════════════════
COPYRIGHT
═══════════════════════════════════════════════════════════════════════════════

© 2026 MoviePrompterAI
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

MoviePrompterAI - Version 1.4
Developed by Quantum Spark Software

═══════════════════════════════════════════════════════════════════════════════
IMPORTANT - READ CAREFULLY
═══════════════════════════════════════════════════════════════════════════════

This License Agreement ("Agreement") is a legal agreement between you (either 
an individual or a single entity) and Quantum Spark Software ("Licensor") for 
the MoviePrompterAI software product identified above, which includes 
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
MoviePrompterAI is a product of Quantum Spark Software."""