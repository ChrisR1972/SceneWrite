"""
Step 3: Story Outline Widget for the Story Creation Wizard.
Displays AI-generated outline with editable sections for subplots, characters, and conclusion.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QLabel, QGroupBox, QScrollArea, QMessageBox, QProgressDialog,
    QListWidget, QListWidgetItem, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from typing import Optional, Dict, Any, List
import re
from core.ai_generator import AIGenerator
from core.spell_checker import enable_spell_checking
from core.workflow_profile import WorkflowProfileManager, WorkflowProfile


def _safe_print(*args, **kwargs):
    """Route output through debug_log instead of stdout (hidden in production)."""
    try:
        from debug_log import debug_log as _dl
        _dl(" ".join(str(a) for a in args))
    except Exception:
        pass


def _normalize_character_name(name: str) -> str:
    """Return display name only (no 'Character1: Name' or 'Character 1: Name' prefix)."""
    if not name or not isinstance(name, str):
        return (name or "").strip()
    name = name.strip()
    stripped = re.sub(r"^(?:Character\s*\d+|NewCharacter\d+)\s*:\s*", "", name, flags=re.IGNORECASE)
    return stripped.strip() if stripped else name


def _is_same_character(name_a: str, name_b: str) -> bool:
    """Return True if name_a and name_b refer to the same character (e.g. LYRA vs LYRA DAVIS)."""
    if not name_a or not name_b:
        return False
    a, b = name_a.strip().lower(), name_b.strip().lower()
    if a == b:
        return True
    # One contains the other (e.g. "lyra" in "lyra davis")
    if a in b or b in a:
        return True
    # Same first name (e.g. LYRA DAVIS vs LYRA)
    a_first = a.split()[0] if a else ""
    b_first = b.split()[0] if b else ""
    return a_first == b_first and (len(a.split()) == 1 or len(b.split()) == 1)


class StoryOutlineGenerationThread(QThread):
    """Thread for generating story outline to avoid blocking UI."""
    
    finished = pyqtSignal(dict)  # Emits outline data
    error = pyqtSignal(str)
    
    def __init__(self, ai_generator, premise, title, genres, atmosphere, workflow_profile=None, character_count=None, length="medium", series_context=None):
        super().__init__()
        self.ai_generator = ai_generator
        self.premise = premise
        self.title = title
        self.genres = genres
        self.atmosphere = atmosphere
        self.workflow_profile = workflow_profile
        self.character_count = character_count
        self.length = length
        self.series_context = series_context

    def run(self):
        """Generate outline in background thread."""
        try:
            outline = self.ai_generator.generate_story_outline(
                self.premise, self.genres, self.atmosphere, self.title, self.workflow_profile, self.character_count, self.length,
                series_context=self.series_context,
            )
            # Validate outline structure
            if not isinstance(outline, dict):
                self.error.emit("Generated outline is not in the expected format.")
                return
            
            # Ensure required fields exist
            if "characters" not in outline:
                outline["characters"] = []
            if "main_storyline" not in outline:
                outline["main_storyline"] = ""
            if "subplots" not in outline:
                outline["subplots"] = ""
            if "conclusion" not in outline:
                outline["conclusion"] = ""
            
            # Ensure characters is a list
            if not isinstance(outline["characters"], list):
                outline["characters"] = []
            
            self.finished.emit(outline)
        except Exception as e:
            self.error.emit(str(e))


class SubplotsRegenerationThread(QThread):
    """Thread for regenerating subplots to avoid blocking UI."""
    
    finished = pyqtSignal(str)  # Emits subplots text
    error = pyqtSignal(str)
    
    def __init__(self, ai_generator, premise, title, genres, atmosphere, main_storyline, characters):
        super().__init__()
        self.ai_generator = ai_generator
        self.premise = premise
        self.title = title
        self.genres = genres
        self.atmosphere = atmosphere
        self.main_storyline = main_storyline
        self.characters = characters
    
    def run(self):
        """Regenerate subplots in background thread."""
        try:
            subplots = self.ai_generator.regenerate_subplots(
                self.premise, self.genres, self.atmosphere, self.title,
                self.main_storyline, self.characters
            )
            self.finished.emit(subplots)
        except Exception as e:
            self.error.emit(str(e))


class ConclusionRegenerationThread(QThread):
    """Thread for regenerating conclusion to avoid blocking UI."""
    
    finished = pyqtSignal(str)  # Emits conclusion text
    error = pyqtSignal(str)
    
    def __init__(self, ai_generator, premise, title, genres, atmosphere, main_storyline, subplots, characters):
        super().__init__()
        self.ai_generator = ai_generator
        self.premise = premise
        self.title = title
        self.genres = genres
        self.atmosphere = atmosphere
        self.main_storyline = main_storyline
        self.subplots = subplots
        self.characters = characters
    
    def run(self):
        """Regenerate conclusion in background thread."""
        try:
            conclusion = self.ai_generator.regenerate_conclusion(
                self.premise, self.genres, self.atmosphere, self.title,
                self.main_storyline, self.subplots, self.characters
            )
            self.finished.emit(conclusion)
        except Exception as e:
            self.error.emit(str(e))


class BatchPhysicalAppearanceForOutlineThread(QThread):
    """Thread for generating missing physical appearances in outline characters."""
    
    progress = pyqtSignal(int, int, int, dict)  # (index, done, total, result)
    finished_all = pyqtSignal()
    error = pyqtSignal(str)
    
    def __init__(self, ai_generator, premise, title, genres, atmosphere, main_storyline, characters, indices_to_generate):
        super().__init__()
        self.ai_generator = ai_generator
        self.premise = premise
        self.title = title
        self.genres = genres
        self.atmosphere = atmosphere
        self.main_storyline = main_storyline
        self.characters = characters  # List of char dicts (shared reference)
        self.indices_to_generate = indices_to_generate
    
    def run(self):
        try:
            total = len(self.indices_to_generate)
            max_retries = 2  # Up to 3 attempts per character (1 initial + 2 retries)
            for i, idx in enumerate(self.indices_to_generate):
                if idx < 0 or idx >= len(self.characters):
                    continue
                char = self.characters[idx] if isinstance(self.characters[idx], dict) else {}
                char_name = str(char.get("name", "Unnamed")).strip()
                char_outline = str(char.get("outline", "") or "").strip()
                other_chars = [c for j, c in enumerate(self.characters) if j != idx and isinstance(c, dict)]
                result = None
                for attempt in range(max_retries + 1):
                    result = self.ai_generator.regenerate_character_details(
                        self.premise, self.genres, self.atmosphere, self.title,
                        self.main_storyline, char_name, "physical_appearance",
                        existing_characters=other_chars,
                        character_outline=char_outline
                    )
                    phys = str(result.get("physical_appearance", "") or "").strip()
                    if phys and len(phys) >= 50:
                        break
                    # Empty or too short - retry
                if result:
                    self.progress.emit(idx, i + 1, total, result)
            self.finished_all.emit()
        except Exception as e:
            self.error.emit(str(e))


class StoryOutlineStepWidget(QWidget):
    """Step 3: Story outline with AI generation and editing."""
    
    outline_ready = pyqtSignal()  # Emitted when outline is valid
    
    def __init__(self, ai_generator: Optional[AIGenerator] = None, parent=None):
        super().__init__(parent)
        self.ai_generator = ai_generator
        self.outline_thread: Optional[StoryOutlineGenerationThread] = None
        self.subplots_thread: Optional[SubplotsRegenerationThread] = None
        self.conclusion_thread: Optional[ConclusionRegenerationThread] = None
        self.batch_physical_thread: Optional[BatchPhysicalAppearanceForOutlineThread] = None
        self.progress_dialog: Optional[QProgressDialog] = None
        self.outline_data: Dict[str, Any] = {}
        self.premise: str = ""
        self.title: str = ""
        self.genres: List[str] = []
        self.atmosphere: str = ""
        self.current_character_index: int = -1
        self.workflow_profile: Optional[WorkflowProfile] = None
        self.length: str = "medium"
        self.intent: str = "General Story"
        self.series_context: Optional[Dict[str, Any]] = None
        self._bible_characters: List[Dict[str, Any]] = []
        self._bible_char_names_lower: set = set()
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI."""
        from PyQt6.QtWidgets import QSizePolicy
        # Set size policy to prevent expansion
        size_policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setSizePolicy(size_policy)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)
        
        # No title label to avoid top whitespace
        
        # Scroll area for content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        # Prevent scroll area from expanding beyond parent - use Preferred instead of Expanding
        from PyQt6.QtWidgets import QSizePolicy
        scroll_policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        scroll_area.setSizePolicy(scroll_policy)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(5, 5, 5, 5)
        content_layout.setSpacing(15)
        
        # Main Storyline section
        main_storyline_group = QGroupBox("Main Storyline")
        main_storyline_layout = QVBoxLayout()
        
        # Premise summary (incorporated into Main Storyline section)
        premise_section_label = QLabel("Premise Summary:")
        premise_section_label.setStyleSheet("font-weight: bold; font-size: 11px; margin-top: 5px;")
        main_storyline_layout.addWidget(premise_section_label)
        self.premise_meta_label = QLabel("Title: — | Genres: — | Atmosphere: —")
        self.premise_meta_label.setStyleSheet("color: #666; font-size: 10px;")
        main_storyline_layout.addWidget(self.premise_meta_label)
        self.premise_text = QTextEdit()
        self.premise_text.setMinimumHeight(80)
        # Allow full premise display without truncation
        self.premise_text.setMaximumHeight(400)
        self.premise_text.setPlaceholderText("Your premise from Step 2 will appear here...")
        self.premise_text.textChanged.connect(self.on_premise_changed)
        main_storyline_layout.addWidget(self.premise_text)
        
        # Separator label
        storyline_label = QLabel("Expanded Storyline:")
        storyline_label.setStyleSheet("font-weight: bold; font-size: 11px; margin-top: 10px;")
        main_storyline_layout.addWidget(storyline_label)
        main_storyline_hint = QLabel("The primary narrative arc expanded from the premise:")
        main_storyline_hint.setStyleSheet("color: #666; font-size: 10px;")
        main_storyline_layout.addWidget(main_storyline_hint)
        self.main_storyline_edit = QTextEdit()
        self.main_storyline_edit.setPlaceholderText("Main storyline will be generated here...")
        self.main_storyline_edit.setMinimumHeight(150)
        self.main_storyline_edit.textChanged.connect(self.on_outline_changed)
        main_storyline_layout.addWidget(self.main_storyline_edit)
        
        # Generate button (positioned right below Expanded Storyline section)
        generate_button_layout = QHBoxLayout()
        self.generate_button = QPushButton("Expand Premise")
        self.generate_button.clicked.connect(self.generate_outline)
        generate_button_layout.addWidget(self.generate_button)
        generate_button_layout.addStretch()
        main_storyline_layout.addLayout(generate_button_layout)
        
        main_storyline_group.setLayout(main_storyline_layout)
        content_layout.addWidget(main_storyline_group)
        
        # Subplots section (conditional - hidden for promotional)
        self.subplots_group = QGroupBox("Subplots and Secondary Storylines")
        subplots_layout = QVBoxLayout()
        subplots_hint = QLabel("Secondary storylines that complement the main narrative:")
        subplots_hint.setStyleSheet("color: #666; font-size: 10px;")
        subplots_layout.addWidget(subplots_hint)
        self.subplots_edit = QTextEdit()
        self.subplots_edit.setPlaceholderText("Subplots will be generated here...")
        self.subplots_edit.setMinimumHeight(150)
        self.subplots_edit.textChanged.connect(self.on_outline_changed)
        subplots_layout.addWidget(self.subplots_edit)
        
        # Generate/Regenerate subplots button
        if self.ai_generator:
            regenerate_subplots_layout = QHBoxLayout()
            self.regenerate_subplots_button = QPushButton("Generate Subplots")
            self.regenerate_subplots_button.clicked.connect(self.regenerate_subplots)
            self.regenerate_subplots_button.setEnabled(False)  # Disabled until outline is generated
            regenerate_subplots_layout.addWidget(self.regenerate_subplots_button)
            subplots_layout.addLayout(regenerate_subplots_layout)
        
        self.subplots_group.setLayout(subplots_layout)
        content_layout.addWidget(self.subplots_group)
        
        # Promotional-specific fields (hidden by default, shown for promotional)
        # Core Message
        self.core_message_group = QGroupBox("Core Message")
        core_message_layout = QVBoxLayout()
        core_message_hint = QLabel("The central brand message or value proposition:")
        core_message_hint.setStyleSheet("color: #666; font-size: 10px;")
        core_message_layout.addWidget(core_message_hint)
        self.core_message_edit = QTextEdit()
        self.core_message_edit.setPlaceholderText("Core brand message will be generated here...")
        self.core_message_edit.setMinimumHeight(100)
        self.core_message_edit.textChanged.connect(self.on_outline_changed)
        core_message_layout.addWidget(self.core_message_edit)
        self.core_message_group.setLayout(core_message_layout)
        self.core_message_group.hide()
        content_layout.addWidget(self.core_message_group)
        
        # Emotional Beats
        self.emotional_beats_group = QGroupBox("Emotional Beat Progression")
        emotional_beats_layout = QVBoxLayout()
        emotional_beats_hint = QLabel("3-5 emotional beats that progress the mood and message:")
        emotional_beats_hint.setStyleSheet("color: #666; font-size: 10px;")
        emotional_beats_layout.addWidget(emotional_beats_hint)
        self.emotional_beats_edit = QTextEdit()
        self.emotional_beats_edit.setPlaceholderText("Emotional beats will be generated here...")
        self.emotional_beats_edit.setMinimumHeight(120)
        self.emotional_beats_edit.textChanged.connect(self.on_outline_changed)
        emotional_beats_layout.addWidget(self.emotional_beats_edit)
        self.emotional_beats_group.setLayout(emotional_beats_layout)
        self.emotional_beats_group.hide()
        content_layout.addWidget(self.emotional_beats_group)
        
        # Visual Motifs
        self.visual_motifs_group = QGroupBox("Visual Motifs / Imagery Themes")
        visual_motifs_layout = QVBoxLayout()
        visual_motifs_hint = QLabel("Key visual elements, imagery, and motifs to emphasize:")
        visual_motifs_hint.setStyleSheet("color: #666; font-size: 10px;")
        visual_motifs_layout.addWidget(visual_motifs_hint)
        self.visual_motifs_edit = QTextEdit()
        self.visual_motifs_edit.setPlaceholderText("Visual motifs will be generated here...")
        self.visual_motifs_edit.setMinimumHeight(100)
        self.visual_motifs_edit.textChanged.connect(self.on_outline_changed)
        visual_motifs_layout.addWidget(self.visual_motifs_edit)
        self.visual_motifs_group.setLayout(visual_motifs_layout)
        self.visual_motifs_group.hide()
        content_layout.addWidget(self.visual_motifs_group)
        
        # Call to Action
        self.call_to_action_group = QGroupBox("Call to Action (Optional)")
        call_to_action_layout = QVBoxLayout()
        call_to_action_hint = QLabel("Optional call-to-action or next step for the audience:")
        call_to_action_hint.setStyleSheet("color: #666; font-size: 10px;")
        call_to_action_layout.addWidget(call_to_action_hint)
        self.call_to_action_edit = QTextEdit()
        self.call_to_action_edit.setPlaceholderText("Call to action (optional)...")
        self.call_to_action_edit.setMinimumHeight(80)
        self.call_to_action_edit.textChanged.connect(self.on_outline_changed)
        call_to_action_layout.addWidget(self.call_to_action_edit)
        self.call_to_action_group.setLayout(call_to_action_layout)
        self.call_to_action_group.hide()
        content_layout.addWidget(self.call_to_action_group)
        
        # Conclusion section (conditional - hidden for promotional)
        self.conclusion_group = QGroupBox("Final Conclusion")
        conclusion_layout = QVBoxLayout()
        conclusion_hint = QLabel("How the story resolves, conflicts are resolved, and final themes:")
        conclusion_hint.setStyleSheet("color: #666; font-size: 10px;")
        conclusion_layout.addWidget(conclusion_hint)
        self.conclusion_edit = QTextEdit()
        self.conclusion_edit.setPlaceholderText("Final conclusion will be generated here...")
        self.conclusion_edit.setMinimumHeight(150)
        self.conclusion_edit.textChanged.connect(self.on_outline_changed)
        conclusion_layout.addWidget(self.conclusion_edit)
        
        # Generate/Regenerate conclusion button
        if self.ai_generator:
            regenerate_conclusion_layout = QHBoxLayout()
            self.regenerate_conclusion_button = QPushButton("Generate Conclusion")
            self.regenerate_conclusion_button.clicked.connect(self.regenerate_conclusion)
            self.regenerate_conclusion_button.setEnabled(False)  # Disabled until outline is generated
            regenerate_conclusion_layout.addWidget(self.regenerate_conclusion_button)
            conclusion_layout.addLayout(regenerate_conclusion_layout)
        
        self.conclusion_group.setLayout(conclusion_layout)
        content_layout.addWidget(self.conclusion_group)
        
        # Characters section (conditional - hidden for promotional)
        self.characters_group = QGroupBox("Main Characters (Outline and Growth Arc)")
        characters_layout = QVBoxLayout()
        self._characters_hint = QLabel("Main characters (from Step 2) get outline and growth arc here. They must appear first in the storyline and in Character Details. Minor characters may appear in the storyline/subplots by name and role only—no outline or arc.")
        self._characters_hint.setStyleSheet("color: #666; font-size: 10px; font-weight: bold;")
        self._characters_hint.setWordWrap(True)
        characters_layout.addWidget(self._characters_hint)
        
        # Generate Character Details button (names are filled when conclusion is generated; details on demand)
        if self.ai_generator:
            generate_details_layout = QHBoxLayout()
            self.generate_character_details_button = QPushButton("Generate Character Details")
            self.generate_character_details_button.clicked.connect(self.generate_characters_now)
            self.generate_character_details_button.setToolTip("AI will generate outline, growth arc, and physical appearance for all main characters.")
            generate_details_layout.addWidget(self.generate_character_details_button)
            generate_details_layout.addStretch()
            characters_layout.addLayout(generate_details_layout)
        
        # Character list and editor splitter
        char_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Character list
        self.character_list = QListWidget()
        self.character_list.setMaximumWidth(200)
        self.character_list.currentItemChanged.connect(self.on_character_selected)
        char_splitter.addWidget(self.character_list)
        
        # Character editor
        char_editor_widget = QWidget()
        char_editor_layout = QVBoxLayout(char_editor_widget)
        char_editor_layout.setContentsMargins(0, 0, 0, 0)
        
        char_name_label = QLabel("Character Name:")
        char_editor_layout.addWidget(char_name_label)
        self.char_name_edit = QTextEdit()
        self.char_name_edit.setMaximumHeight(30)
        self.char_name_edit.setPlaceholderText("Character name...")
        self.char_name_edit.textChanged.connect(self.on_character_data_changed)
        char_editor_layout.addWidget(self.char_name_edit)
        
        char_physical_label = QLabel("Physical Appearance (Persistent):")
        char_editor_layout.addWidget(char_physical_label)
        self.char_physical_edit = QTextEdit()
        self.char_physical_edit.setPlaceholderText("Gender, height, face, hair, eyes, skin, age, build, scars. No character name. No clothing.")
        self.char_physical_edit.setMinimumHeight(80)
        self.char_physical_edit.textChanged.connect(self.on_character_data_changed)
        char_editor_layout.addWidget(self.char_physical_edit)
        
        self.char_outline_label = QLabel("Character Outline:")
        char_editor_layout.addWidget(self.char_outline_label)
        self.char_outline_edit = QTextEdit()
        self.char_outline_edit.setPlaceholderText("Character description, role, background, motivation...")
        self.char_outline_edit.setMinimumHeight(100)
        self.char_outline_edit.textChanged.connect(self.on_character_data_changed)
        char_editor_layout.addWidget(self.char_outline_edit)
        
        self.char_growth_label = QLabel("Character Growth Arc:")
        char_editor_layout.addWidget(self.char_growth_label)
        self.char_growth_edit = QTextEdit()
        self.char_growth_edit.setPlaceholderText("Character development: starting point, challenges, changes, ending...")
        self.char_growth_edit.setMinimumHeight(100)
        self.char_growth_edit.textChanged.connect(self.on_character_data_changed)
        char_editor_layout.addWidget(self.char_growth_edit)
        
        char_splitter.addWidget(char_editor_widget)
        char_splitter.setSizes([200, 600])
        characters_layout.addWidget(char_splitter)
        
        self.characters_group.setLayout(characters_layout)
        content_layout.addWidget(self.characters_group)
        
        # Don't add stretch - let scroll area handle scrolling instead of forcing expansion
        # content_layout.addStretch()  # Removed to prevent window expansion
        
        scroll_area.setWidget(content_widget)
        # Set size policy on content widget to prevent expansion
        content_policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        content_widget.setSizePolicy(content_policy)
        self.scroll_area = scroll_area
        layout.addWidget(scroll_area)
        
        # Enable spell checking for editable text widgets
        enable_spell_checking(self.premise_text)
        enable_spell_checking(self.main_storyline_edit)
        enable_spell_checking(self.subplots_edit)
        enable_spell_checking(self.char_name_edit)
        enable_spell_checking(self.char_outline_edit)
        enable_spell_checking(self.char_growth_edit)
        enable_spell_checking(self.char_physical_edit)
        enable_spell_checking(self.conclusion_edit)
        
        # Tab key moves focus (not indentation) in form-style fields
        for w in (self.premise_text, self.main_storyline_edit, self.subplots_edit,
                  self.core_message_edit, self.emotional_beats_edit, self.visual_motifs_edit,
                  self.call_to_action_edit, self.conclusion_edit,
                  self.char_name_edit, self.char_physical_edit, self.char_outline_edit, self.char_growth_edit):
            w.setTabChangesFocus(True)
        
        # Initially disable editing until outline is generated
        self.set_editing_enabled(False)
    
    def is_micro_narrative(self) -> bool:
        """Return True when the story is micro length with a narrative workflow."""
        return (
            self.length == "micro"
            and self.workflow_profile
            and self.workflow_profile == WorkflowProfile.NARRATIVE
        )

    def update_ui_for_profile(self):
        """Update UI based on workflow profile."""
        if not self.workflow_profile:
            return
        
        outline_structure = WorkflowProfileManager.get_outline_structure(self.workflow_profile)
        
        if outline_structure["type"] == "promotional":
            # Hide narrative sections
            self.subplots_group.hide()
            self.conclusion_group.hide()
            self.characters_group.hide()
            
            # Show promotional sections
            self.core_message_group.show()
            self.emotional_beats_group.show()
            self.visual_motifs_group.show()
            self.call_to_action_group.show()
        else:
            is_micro = self.is_micro_narrative()
            
            # Micro narratives skip subplots (too short for secondary storylines)
            self.subplots_group.setVisible(not is_micro)
            self.conclusion_group.show()
            self.characters_group.show()
            
            # Micro narratives: show physical appearance only, hide outline & growth arc
            if is_micro:
                self.characters_group.setTitle("Main Characters (Physical Appearance)")
                self.char_outline_label.hide()
                self.char_outline_edit.hide()
                self.char_growth_label.hide()
                self.char_growth_edit.hide()
                if hasattr(self, 'generate_character_details_button'):
                    self.generate_character_details_button.setToolTip(
                        "AI will generate physical appearance for all main characters."
                    )
            elif self._bible_characters:
                self.characters_group.setTitle("Series Characters (Name & Appearance locked from Bible)")
                self.char_outline_label.show()
                self.char_outline_edit.show()
                self.char_growth_label.show()
                self.char_growth_edit.show()
                if hasattr(self, 'generate_character_details_button'):
                    self.generate_character_details_button.setToolTip(
                        "AI will generate episode-specific outline and growth arc. Name and appearance are locked from the Series Bible."
                    )
            else:
                self.characters_group.setTitle("Main Characters (Outline and Growth Arc)")
                self.char_outline_label.show()
                self.char_outline_edit.show()
                self.char_growth_label.show()
                self.char_growth_edit.show()
                if hasattr(self, 'generate_character_details_button'):
                    self.generate_character_details_button.setToolTip(
                        "AI will generate outline, growth arc, and physical appearance for all main characters."
                    )
            
            # Hide promotional sections
            self.core_message_group.hide()
            self.emotional_beats_group.hide()
            self.visual_motifs_group.hide()
            self.call_to_action_group.hide()
    
    def set_premise(self, premise: str, title: str, genres: List[str], atmosphere: str, character_count: int = 4, length: str = "medium", intent: str = "General Story", series_context=None):
        """Set premise data for outline generation."""
        self.premise = premise
        self.title = title
        self.genres = genres
        self.atmosphere = atmosphere
        self.character_count = character_count
        self.length = length
        self.intent = intent
        self.series_context = series_context
        self.workflow_profile = WorkflowProfileManager.get_profile(length, intent)
        
        # Update UI based on workflow profile
        self.update_ui_for_profile()
        
        # The premise should already be cleaned by premise_step.get_premise_data()
        # Just use it as-is, no further processing needed
        processed_premise = premise.strip() if premise else ""
        
        # Update summary display
        safe_title = title.strip() if title else "—"
        safe_genres = ", ".join(genres) if genres else "—"
        safe_atmosphere = atmosphere.strip() if atmosphere else "—"
        self.premise_meta_label.setText(f"Title: {safe_title} | Genres: {safe_genres} | Atmosphere: {safe_atmosphere}")
        self.premise_text.setPlainText(processed_premise if processed_premise else "")
    
    def set_bible_characters(self, bible_chars: List[Dict[str, Any]]):
        """Store bible main characters for series episodes 2+.

        These characters will be injected into the outline after AI generation,
        and their name + physical_appearance fields will be read-only in the editor.
        """
        from core.series_bible import SeriesBible as _SB
        self._bible_characters = list(bible_chars) if bible_chars else []
        self._bible_char_names_lower = set()
        for c in self._bible_characters:
            name = c.get("name", "")
            if name:
                self._bible_char_names_lower.add(name.strip().lower())
                norm = _SB._normalize_char_name(name)
                if norm:
                    self._bible_char_names_lower.add(norm.lower())
        if self._bible_characters:
            names = [c.get("name", "") for c in self._bible_characters if c.get("name")]
            self._characters_hint.setText(
                f"Series main characters ({', '.join(names)}) are locked from the Series Bible. "
                f"Name and physical appearance cannot be changed. "
                f"The AI will generate episode-specific outline and growth arc for each."
            )
            self.update_ui_for_profile()

    def _is_bible_character(self, name: str) -> bool:
        """Check if a character name matches one from the series bible."""
        if not self._bible_characters or not name:
            return False
        from core.series_bible import SeriesBible as _SB
        name_lower = name.strip().lower()
        norm = _SB._normalize_char_name(name)
        return (name_lower in self._bible_char_names_lower
                or (norm and norm.lower() in self._bible_char_names_lower))

    def generate_outline(self):
        """Generate story outline using AI."""
        if not self.ai_generator:
            QMessageBox.warning(self, "AI Not Available", "AI generator is not configured. Please set up your API key in settings.")
            return
        
        if not self.premise:
            QMessageBox.warning(self, "No Premise", "Please complete Step 2 first.")
            return
        
        # Disable button during generation
        self.generate_button.setEnabled(False)
        self.generate_button.setText("Expanding Premise...")
        
        # Show progress dialog
        self.progress_dialog = QProgressDialog("Generating story outline with AI...", None, 0, 0, self)
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setCancelButton(None)
        self.progress_dialog.setWindowTitle("Generating Story Outline")
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setValue(0)
        self.progress_dialog.show()
        
        # Process events
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        
        # Clean up any existing thread
        if self.outline_thread and self.outline_thread.isRunning():
            self.outline_thread.terminate()
            self.outline_thread.wait()
        
        # Create and start generation thread (pass character_count for exact N character declaration)
        self.outline_thread = StoryOutlineGenerationThread(
            self.ai_generator, self.premise, self.title, self.genres, self.atmosphere, self.workflow_profile, getattr(self, 'character_count', 4), self.length,
            series_context=getattr(self, 'series_context', None),
        )
        self.outline_thread.finished.connect(self.on_outline_generated)
        self.outline_thread.error.connect(self.on_outline_error)
        self.outline_thread.start()
    
    def on_outline_generated(self, outline_data: Dict[str, Any]):
        """Handle successful outline generation."""
        # Close progress dialog
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
        
        # Validate outline_data
        if not isinstance(outline_data, dict):
            QMessageBox.critical(self, "Invalid Data", "Generated outline data is invalid.")
            self.generate_button.setText("Expand Premise")
            self.generate_button.setEnabled(True)
            return
        
        self.outline_data = outline_data.copy() if isinstance(outline_data, dict) else {}
        
        # Ensure main_storyline exists
        if "main_storyline" not in self.outline_data:
            self.outline_data["main_storyline"] = ""
        # Ensure locations list exists (Wizard entity markup: underlined = locations)
        if "locations" not in self.outline_data:
            self.outline_data["locations"] = []
        
        # Populate UI based on workflow profile
        if self.workflow_profile == WorkflowProfile.PROMOTIONAL:
            # Populate promotional fields
            self.main_storyline_edit.setPlainText(str(self.outline_data.get("main_storyline", "")))
            self.core_message_edit.setPlainText(str(self.outline_data.get("core_message", "")))
            self.emotional_beats_edit.setPlainText(str(self.outline_data.get("emotional_beats", "")))
            self.visual_motifs_edit.setPlainText(str(self.outline_data.get("visual_motifs", "")))
            self.call_to_action_edit.setPlainText(str(self.outline_data.get("call_to_action", "")))
        elif self.workflow_profile == WorkflowProfile.EXPERIMENTAL:
            # Populate experimental fields
            self.main_storyline_edit.setPlainText(str(self.outline_data.get("main_storyline", "")))
            self.core_message_edit.setPlainText(str(self.outline_data.get("concept", "")))
            self.visual_motifs_edit.setPlainText(str(self.outline_data.get("visual_themes", "")))
            self.emotional_beats_edit.setPlainText(str(self.outline_data.get("mood_progression", "")))
        else:
            # Populate narrative fields
            main_storyline_text = str(self.outline_data.get("main_storyline", ""))
            self.main_storyline_edit.setPlainText(main_storyline_text)
            self.subplots_edit.setPlainText(str(self.outline_data.get("subplots", "")))
            self.conclusion_edit.setPlainText(str(self.outline_data.get("conclusion", "")))
        
        # Process events to ensure UI is updated
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        
        # Preserve initial AI-returned characters (with physical_appearance) for later matching.
        # They are cleared from the UI but kept for _generate_characters_from_content to reuse.
        chars = self.outline_data.get("characters")
        self._initial_outline_characters = list(chars) if (chars is not None and isinstance(chars, list)) else []
        
        # Populate character names only (no details). User can click "Generate Character Details" when ready.
        self._populate_character_names_only()
        
        # Enable editing
        self.set_editing_enabled(True)
        self.generate_button.setText("Regenerate Premise")
        self.generate_button.setEnabled(True)
        
        # Enable regenerate buttons
        if hasattr(self, 'regenerate_conclusion_button'):
            self.regenerate_conclusion_button.setEnabled(True)
        if hasattr(self, 'regenerate_subplots_button'):
            self.regenerate_subplots_button.setEnabled(True)
        
        # Process events to ensure UI is updated
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        
        # Update outline data from UI and emit signal
        self.on_outline_changed()
    
    def _populate_existing_characters_only(self):
        """Clear character list during initial outline generation.
        
        Characters will be generated only after the conclusion is finalized.
        This ensures they have complete story context for better profiles.
        """
        # Clear character list - no characters should exist yet
        self.character_list.clear()
        self.current_character_index = -1
        
        # Clear character editing fields
        self.char_name_edit.clear()
        self.char_outline_edit.clear()
        self.char_growth_edit.clear()
        self.char_physical_edit.clear()
        
        # Ensure characters list is empty in outline_data
        if self.outline_data:
            self.outline_data["characters"] = []
    
    def _apply_characters_to_ui(self, characters: list):
        """Update outline_data and refresh the character list UI."""
        if not self.outline_data or not isinstance(characters, list):
            return
        self.outline_data["characters"] = characters
        self.character_list.clear()
        self.current_character_index = -1
        try:
            self.character_list.currentItemChanged.disconnect()
        except TypeError:
            pass
        for char in characters:
            if isinstance(char, dict):
                name = _normalize_character_name(str(char.get("name", "Unnamed Character")))
                self.character_list.addItem(QListWidgetItem(name))
        self.character_list.currentItemChanged.connect(self.on_character_selected)
        if self.character_list.count() > 0:
            self.character_list.setCurrentRow(0)
            current_item = self.character_list.currentItem()
            if current_item:
                self.on_character_selected(current_item, None)
    
    def _populate_bible_characters(self):
        """Inject bible main characters into the outline, merging AI-generated episode arcs.

        Bible characters provide the canonical name and physical_appearance (read-only).
        The AI's outline and growth_arc for the episode are preserved if the AI generated
        entries that match the bible characters by name.
        """
        from core.series_bible import SeriesBible as _SB

        # Build a lookup from the AI-generated character list
        ai_chars = self.outline_data.get("characters") or []
        ai_map: dict = {}
        for c in (ai_chars if isinstance(ai_chars, list) else []):
            if isinstance(c, dict) and c.get("name"):
                norm = _SB._normalize_char_name(str(c["name"]).strip())
                if norm:
                    ai_map[norm.lower()] = c

        result = []
        for bc in self._bible_characters:
            name = bc.get("name", "")
            norm = _SB._normalize_char_name(name)
            ai_match = ai_map.get(norm.lower()) if norm else None
            result.append({
                "name": name,
                "outline": (ai_match.get("outline", "") if ai_match else "") or "",
                "growth_arc": (ai_match.get("growth_arc", "") if ai_match else "") or "",
                "physical_appearance": bc.get("physical_appearance", ""),
                "role": bc.get("role", "main"),
                "species": bc.get("species", ""),
            })

        self.outline_data["characters"] = result
        self._apply_characters_to_ui(result)

    def _deduplicate_characters(self, characters: list) -> list:
        """Remove duplicate characters (exact match or same person, e.g. LYRA vs LYRA DAVIS)."""
        if not characters or not isinstance(characters, list):
            return list(characters) if characters else []
        # Use ai_generator's sanitize when available (handles corporations, nickname merges)
        if self.ai_generator:
            return self.ai_generator.sanitize_character_list_for_registry(characters)
        # Fallback: simple dedup by name, prefer longer/full names
        result = []
        seen_lower = set()
        for c in characters:
            if not isinstance(c, dict) or not c.get("name"):
                continue
            name = str(c.get("name", "")).strip()
            key = name.lower()
            if key in seen_lower:
                continue
            # Check if this is a variant of an already-seen character (e.g. LYRA when we have LYRA DAVIS)
            is_dup = False
            for seen in seen_lower:
                if _is_same_character(name, seen):
                    is_dup = True
                    break
            if is_dup:
                continue
            seen_lower.add(key)
            result.append(c)
        return result
    
    def _populate_character_names_only(self):
        """Fill main character names from storyline without generating outline/arc/physical_appearance.
        
        Prefers the ai_generator's processed characters (already extracted and deduplicated).
        Only re-extracts when the incoming character list is empty, has placeholders, or has duplicates.
        For series episodes 2+, bible characters are injected directly with locked identity fields.
        """
        if not self.outline_data:
            return

        # For series episodes 2+, inject bible characters with their locked identity
        if self._bible_characters:
            self._populate_bible_characters()
            return
        
        main_storyline = str(self.outline_data.get("main_storyline", "")).strip()
        target_character_count = getattr(self, 'character_count', 4)
        
        if target_character_count <= 0:
            return
        
        # Prefer ai_generator's already-processed characters (extraction + dedup done in generate_story_outline)
        incoming = self.outline_data.get("characters") or []
        incoming_valid = [
            c for c in incoming
            if isinstance(c, dict) and c.get("name") and
            not re.match(r"^(?:Character\s*\d+|NewCharacter\d+)$", str(c.get("name", "")).strip(), re.IGNORECASE)
        ]
        # Deduplicate incoming: if we have exactly target count with no duplicates, use as-is
        if self.ai_generator and incoming_valid:
            deduped = self._deduplicate_characters(incoming_valid)
            if len(deduped) == target_character_count and len(deduped) == len({str(c.get("name","")).lower() for c in deduped}):
                existing_characters = deduped
                _safe_print(f"Using ai_generator's processed characters (no re-extraction): {[c.get('name') for c in existing_characters]}")
                self._apply_characters_to_ui(existing_characters)
                return
        
        if not main_storyline or not self.ai_generator:
            if incoming_valid:
                existing_characters = self._deduplicate_characters(incoming_valid)
                self._apply_characters_to_ui(existing_characters)
            return
        
        main_storyline_characters = self.ai_generator._extract_first_n_characters_from_main_storyline(
            main_storyline, target_character_count
        )
        _safe_print(f"Populating character names only (extraction): {main_storyline_characters}")
        
        # Fallback: if extraction returns empty, try main+subplots, then use AI's declared list
        if not main_storyline_characters:
            subplots = str(self.outline_data.get("subplots", "")).strip()
            if subplots:
                combined = f"{main_storyline}\n\n{subplots}"
                main_storyline_characters = self.ai_generator._extract_first_n_characters_from_main_storyline(
                    combined, target_character_count
                )
                _safe_print(f"Supplemented from subplots: {main_storyline_characters}")
            if not main_storyline_characters:
                declared = self.outline_data.get("characters") or getattr(self, "_initial_outline_characters", [])
                if declared and isinstance(declared, list):
                    main_storyline_characters = [
                        str(c.get("name", "")).strip() for c in declared[:target_character_count]
                        if isinstance(c, dict) and c.get("name")
                    ]
                    _safe_print(f"Fallback to declared list: {main_storyline_characters}")
            if not main_storyline_characters:
                return
        
        declared_map = {}
        for c in (self.outline_data.get("characters") or getattr(self, "_initial_outline_characters", []) or []):
            if isinstance(c, dict) and c.get("name"):
                nm = _normalize_character_name(str(c.get("name", "")).strip())
                if nm:
                    declared_map[nm.lower()] = c
        
        existing_characters = []
        seen_names = set()
        for name in main_storyline_characters:
            norm = _normalize_character_name(name).strip()
            if not norm or norm.lower() in seen_names:
                continue
            seen_names.add(norm.lower())
            match = declared_map.get(norm.lower())
            existing_characters.append({
                "name": norm or name,
                "outline": (match.get("outline", "") or "") if match else "",
                "growth_arc": (match.get("growth_arc", "") or "") if match else "",
                "physical_appearance": (match.get("physical_appearance", "") or "") if match else ""
            })
        
        # Deduplicate before storing (removes duplicates, merges nickname/surname variants)
        deduped_characters = self._deduplicate_characters(existing_characters)
        self._apply_characters_to_ui(deduped_characters)
    
    def _generate_characters_from_content(self):
        """Generate character outlines from the storyline, subplots, and conclusion.
        
        This is called AFTER storyline, subplots, and conclusion are generated.
        When the outline already has up to N declared characters (from character_count),
        use that list as the canonical Character Registry and only generate outline/arc for each.
        Otherwise extract names from text. character_count is an upper bound, not an exact target.
        """
        if not self.ai_generator or not self.outline_data:
            return
        
        # Get all text content
        main_storyline = str(self.outline_data.get("main_storyline", ""))
        subplots = str(self.outline_data.get("subplots", ""))
        conclusion = str(self.outline_data.get("conclusion", ""))
        
        all_content = f"{main_storyline}\n\n{subplots}\n\n{conclusion}"
        
        target_character_count = getattr(self, 'character_count', 4)
        _safe_print(f"Target character count: {target_character_count}")
        
        # MAIN CHARACTERS = first N mentioned in main storyline only (user requirement)
        # Only those N characters get outline and growth arc. No other characters.
        main_storyline_characters = []
        if target_character_count > 0 and main_storyline.strip():
            main_storyline_characters = self.ai_generator._extract_first_n_characters_from_main_storyline(
                main_storyline, target_character_count
            )
            _safe_print(f"First {target_character_count} characters from main storyline (order of first mention): {main_storyline_characters}")
        
        if target_character_count > 0 and main_storyline_characters:
            # Use ONLY the first N from main storyline - no other characters get outlines
            found_characters = main_storyline_characters
            use_declared_list = False
            # Build existing_characters: reuse AI outline/arc/physical_appearance for names that match.
            # Use initial outline characters (preserved before clear) when outline_data was cleared.
            declared = self.outline_data.get("characters") or getattr(self, "_initial_outline_characters", []) or []
            declared_map = {}
            title_prefixes = ("dr.", "dr ", "judge", "captain", "admiral", "mr.", "mrs.", "ms.", "professor")
            for c in (declared if isinstance(declared, list) else []):
                if isinstance(c, dict) and c.get("name"):
                    raw = _normalize_character_name(str(c.get("name", "")).strip())
                    key = raw.lower()
                    declared_map[key] = c
                    # Also add key without title prefix for matching (e.g. "lila vargas" from "dr. lila vargas")
                    for prefix in title_prefixes:
                        if key.startswith(prefix) and len(key) > len(prefix):
                            rest = key[len(prefix):].strip().lstrip(".")
                            if rest:
                                declared_map[rest] = c
            existing_characters = []
            seen_names = set()
            for name in found_characters:
                norm = _normalize_character_name(name).strip()
                if not norm or norm.lower() in seen_names:
                    continue
                seen_names.add(norm.lower())
                match = declared_map.get(norm.lower()) if norm else None
                if not match and norm:
                    # Try matching declared keys that end with our name (e.g. "judge evelyn rogers" matches "evelyn rogers")
                    norm_lower = norm.lower()
                    for dk, dc in declared_map.items():
                        if dk.endswith(" " + norm_lower) or dk == norm_lower:
                            match = dc
                            break
                existing_characters.append({
                    "name": norm or name,
                    "outline": (match.get("outline", "") or "") if match else "",
                    "growth_arc": (match.get("growth_arc", "") or "") if match else "",
                    "physical_appearance": (match.get("physical_appearance", "") or "") if match else ""
                })
            self.outline_data["characters"] = self._deduplicate_characters(existing_characters)
            characters_from_main_storyline = True
        elif target_character_count > 0 and isinstance(self.outline_data.get("characters"), list):
            declared = self.outline_data.get("characters") or getattr(self, "_initial_outline_characters", [])
            if (len(declared) == target_character_count and all(isinstance(c, dict) and c.get("name") for c in declared)):
                # Fallback: extraction found nothing, use AI's declared list
                # CRITICAL: Filter to only characters that actually appear in storyline/subplots
                content_upper = all_content.upper()
                filtered_declared = []
                for c in declared:
                    name = _normalize_character_name(str(c.get("name", "")).strip())
                    if not name:
                        continue
                    # Character must appear in the expanded storyline/subplots/conclusion
                    name_parts = name.upper().split()
                    appears = name.upper() in content_upper or any(
                        part in content_upper for part in name_parts if len(part) > 2
                    )
                    if appears:
                        filtered_declared.append(c)
                    else:
                        _safe_print(f"Filtered out declared character '{name}' — not in storyline/subplots")
                if len(filtered_declared) >= target_character_count:
                    existing_characters = []
                    seen = set()
                    for c in filtered_declared[:target_character_count]:
                        name = _normalize_character_name(str(c.get("name", "")).strip())
                        if not name or name.lower() in seen:
                            continue
                        seen.add(name.lower())
                        existing_characters.append({
                            "name": name or c.get("name", ""),
                            "outline": c.get("outline", ""),
                            "growth_arc": c.get("growth_arc", ""),
                            "physical_appearance": c.get("physical_appearance", "")
                        })
                    self.outline_data["characters"] = self._deduplicate_characters(existing_characters)
                    found_characters = [c["name"] for c in self.outline_data["characters"]]
                    use_declared_list = True
                    characters_from_main_storyline = False
                else:
                    use_declared_list = False
                    found_characters = []
                    characters_from_main_storyline = False
            else:
                use_declared_list = False
                found_characters = []
                characters_from_main_storyline = False
        else:
            characters_from_main_storyline = False
            use_declared_list = False
            if not all_content.strip():
                return
            found_characters = []
        
        if not use_declared_list and not characters_from_main_storyline:
            sections = [
                ("combined", all_content),
                ("main_storyline", main_storyline),
                ("subplots", subplots),
                ("conclusion", conclusion),
            ]
            seen_lower = set()
            for section_name, section_text in sections:
                if not (section_text and section_text.strip()):
                    continue
                try:
                    max_names = 10
                    ai_characters = self.ai_generator._extract_character_names_from_text(section_text, max_names=max_names)
                    for name in ai_characters:
                        if name and name.lower() not in seen_lower:
                            seen_lower.add(name.lower())
                            found_characters.append(name)
                    if ai_characters:
                        _safe_print(f"AI extraction from {section_name} found: {ai_characters}")
                except Exception as e:
                    _safe_print(f"Warning: AI character extraction from {section_name} failed: {e}")
            
            # Method 2: Pattern-based extraction as backup/supplement
            patterns = [
                r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:said|says|replied|asked|shouted|whispered|thought|decided|realized)',
                r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)'s\b",
                r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*),',
                r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:was|were|is|are|had|has|will|would|could|should)',
                r'(?:Captain|Doctor|Dr|Mr|Mrs|Ms|Miss|Sir|Lord|Lady|General|Colonel|Major|Lieutenant)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
                r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:turned|looked|walked|ran|moved|stepped|approached|left|arrived)'
            ]
            pattern_characters = []
            for pattern in patterns:
                matches = re.findall(pattern, all_content)
                for match in matches:
                    name = match.strip()
                    if name and len(name) > 1 and name not in ['The', 'A', 'An', 'This', 'That', 'He', 'She', 'They', 'It', 'Story', 'World', 'Time']:
                        pattern_characters.append(name)
            all_found = found_characters + pattern_characters
            unique_characters = []
            seen_lower = set()
            for char in all_found:
                if char.lower() not in seen_lower and char.lower() not in ['narrator', 'story', 'character']:
                    unique_characters.append(char)
                    seen_lower.add(char.lower())
            _safe_print(f"All extraction methods found: {unique_characters}")
            filtered_unique = []
            for name in unique_characters:
                if self.ai_generator._is_place_or_region_entity(name) or self.ai_generator._is_event_entity(name):
                    _safe_print(f"Filtered out non-character: '{name}' (place/region or event)")
                    continue
                if self.ai_generator._is_company_or_concept_entity(name):
                    _safe_print(f"Filtered out non-character: '{name}' (company/department/concept)")
                    continue
                if self.ai_generator._is_narrative_transition(name):
                    _safe_print(f"Filtered out non-character: '{name}' (narrative transition)")
                    continue
                if self.ai_generator._is_group_or_team(name):
                    _safe_print(f"Filtered out non-character: '{name}' (group/team)")
                    continue
                if self.ai_generator._is_building_or_location(name):
                    _safe_print(f"Filtered out non-character: '{name}' (building/location)")
                    continue
                if self.ai_generator._is_role_or_title_only(name):
                    _safe_print(f"Filtered out non-character: '{name}' (job title/role; characters must have person names)")
                    continue
                filtered_unique.append(name)
            unique_characters = filtered_unique
            unique_characters = self.ai_generator.canonicalize_character_names_for_registry(unique_characters)
            # CRITICAL: Only keep characters that ACTUALLY appear in storyline/subplots/conclusion — never invent
            content_upper = all_content.upper()
            in_story = []
            for name in unique_characters:
                name_upper = name.upper()
                appears = name_upper in content_upper or any(
                    p in content_upper for p in name_upper.split() if len(p) > 2
                )
                if appears:
                    # Character names must use FULL CAPS markup (Wizard convention)
                    in_story.append(name.upper())
                else:
                    _safe_print(f"Filtered out extracted character '{name}' — not in storyline/subplots/conclusion")
            unique_characters = in_story
            if len(unique_characters) >= target_character_count:
                found_characters = unique_characters[:target_character_count]
                _safe_print(f"Found {len(unique_characters)} characters, using first {target_character_count}")
            else:
                found_characters = unique_characters
                _safe_print(f"Found {len(found_characters)} characters, need {target_character_count - len(found_characters)} more")
        
        # Get existing characters from outline (when use_declared_list we already set outline_data["characters"])
        existing_characters = self.outline_data.get("characters", [])
        if not isinstance(existing_characters, list):
            existing_characters = []
        # Normalize names so we never store "Character1: Name" - just the name
        for char in existing_characters:
            if isinstance(char, dict) and char.get("name"):
                char["name"] = _normalize_character_name(char["name"])
        
        # Build a map of existing characters by name (lowercase) for quick lookup
        existing_char_map = {}
        for char in existing_characters:
            if isinstance(char, dict) and char.get("name"):
                char_name_lower = char.get("name", "").lower()
                existing_char_map[char_name_lower] = char
        
        existing_char_names = set(existing_char_map.keys())
        
        # Combine all story content for context
        full_story_context = f"{main_storyline}\n\nSubplots: {subplots}\n\nConclusion: {conclusion}"
        
        # Check for placeholder text patterns - be very aggressive in detecting placeholders
        placeholder_patterns = [
            "will be developed further",
            "Their role, background, and relationship",
            "contributing to the narrative progression",
            "appears in the story's conclusion",
            "appears in the main storyline",
            "appears in the story",
            "character who appears",
            "will be developed",
            "as the story progresses",
            "is a character who appears"
        ]
        
        def is_placeholder_text(text: str) -> bool:
            """Check if text is a placeholder rather than a full outline."""
            if not text or len(text.strip()) < 150:  # Very short text is likely placeholder
                return True
            text_lower = text.lower()
            # Check for placeholder patterns
            if any(pattern.lower() in text_lower for pattern in placeholder_patterns):
                return True
            # Also check if it's too generic/short
            if len(text.strip()) < 200 and ("character" in text_lower and "appears" in text_lower):
                return True
            return False
        
        # Collect ALL characters that need full profiles generated
        # This includes: existing characters with placeholders AND newly found characters
        characters_to_generate = []
        processed_names = set()  # Track which characters we've already queued
        
        # When derived from main storyline: ALWAYS generate outline/arc for any character with empty or insufficient content
        if characters_from_main_storyline and target_character_count > 0:
            for existing_char in existing_characters:
                if not isinstance(existing_char, dict) or not existing_char.get("name"):
                    continue
                char_name = existing_char.get("name", "").strip()
                if not char_name:
                    continue
                outline = existing_char.get("outline", "") or ""
                growth_arc = existing_char.get("growth_arc", "") or ""
                physical_appearance = existing_char.get("physical_appearance", "") or ""
                # Need generation if outline, growth_arc, or physical_appearance is empty or too short
                # Micro narratives only require physical appearance
                if self.is_micro_narrative():
                    needs_generation = len(physical_appearance.strip()) < 50
                else:
                    needs_generation = (
                        len(outline.strip()) < 80
                        or len(growth_arc.strip()) < 80
                        or len(physical_appearance.strip()) < 50
                    )
                if needs_generation and char_name.lower() not in processed_names:
                    characters_to_generate.append((char_name, existing_char, True))
                    processed_names.add(char_name.lower())
        
        # First, check ALL existing characters for placeholder text and regenerate if needed
        for existing_char in existing_characters:
            if not isinstance(existing_char, dict):
                continue
            
            char_name = existing_char.get("name", "")
            if not char_name or len(char_name.strip()) == 0:
                continue
            
            char_name_lower = char_name.lower()
            if char_name_lower in processed_names:
                continue
            
            outline = existing_char.get("outline", "")
            growth_arc = existing_char.get("growth_arc", "")
            physical_appearance = existing_char.get("physical_appearance", "") or ""
            
            # Check if this character has placeholder text or missing content - be aggressive
            # Micro narratives only require physical appearance
            if self.is_micro_narrative():
                needs_gen = len(physical_appearance.strip()) < 50
            else:
                needs_gen = (
                    is_placeholder_text(outline)
                    or is_placeholder_text(growth_arc)
                    or not outline
                    or not growth_arc
                    or len(physical_appearance.strip()) < 50
                )
            if needs_gen:
                # Has placeholder text or missing content - needs full generation
                characters_to_generate.append((char_name, existing_char, True))
                processed_names.add(char_name_lower)
        
        # Also process newly found characters that aren't in the list yet
        for char_name in found_characters:
            if len(char_name.strip()) > 0:
                char_name_lower = char_name.lower()
                
                if char_name_lower in processed_names:
                    continue
                
                # Check if character already exists
                existing_char = existing_char_map.get(char_name_lower)
                
                if not existing_char:
                    # New character - needs generation
                    characters_to_generate.append((char_name, None, False))
                    processed_names.add(char_name_lower)
                # If it exists but wasn't caught above, it means it has a good outline already
        
        # Generate full outlines for all characters that need it
        _safe_print(f"Generating full profiles for {len(characters_to_generate)} characters...")
        for char_name, existing_char, is_update in characters_to_generate:
            try:
                # Keep extracted name so we only replace with AI name when it was a placeholder
                extracted_char_name = char_name
                _safe_print(f"  Generating profile for: {char_name}")
                # Get all existing characters (excluding the one being generated) to avoid role duplication
                other_characters = [char for char in existing_characters if isinstance(char, dict) and char.get("name", "").lower() != char_name.lower()]
                # Micro narratives only need physical appearance (no outline or growth arc)
                _regen_type = "physical_appearance" if self.is_micro_narrative() else "both"
                char_details = self.ai_generator.regenerate_character_details(
                    premise=self.premise,
                    genres=self.genres,
                    atmosphere=self.atmosphere,
                    title=self.title,
                    main_storyline=full_story_context,  # Include all context
                    character_name=char_name,
                    regenerate_type=_regen_type,
                    existing_characters=other_characters  # Pass existing characters to avoid duplication
                )
                
                outline = char_details.get("outline", "").strip()
                growth_arc = char_details.get("growth_arc", "").strip()
                physical_appearance = char_details.get("physical_appearance", "").strip()
                # Only use AI-returned name when the extracted name was a placeholder (NewCharacter1, Character 1, etc.)
                is_placeholder = bool(re.match(r"^(?:NewCharacter\d+|Character\s*\d+)$", (extracted_char_name or "").strip(), re.IGNORECASE))
                if is_placeholder and char_details.get("name"):
                    ai_name = _normalize_character_name(char_details["name"])
                    existing_lower = {c.get("name", "").lower() for c in existing_characters if isinstance(c, dict)}
                    # CRITICAL: Only accept AI name if it appears in the storyline/subplots — do not use invented names
                    content_upper = full_story_context.upper()
                    ai_appears = ai_name and (
                        ai_name.upper() in content_upper or
                        any(part in content_upper for part in ai_name.upper().split() if len(part) > 2)
                    )
                    if ai_name and ai_name.lower() not in existing_lower and ai_appears:
                        char_name = ai_name
                    else:
                        char_name = extracted_char_name
                else:
                    char_name = extracted_char_name
                
                # Debug: print what was generated (use _safe_print to avoid OSError [Errno 22] on Windows)
                _safe_print(f"    Generated outline ({len(outline)} chars)")
                _safe_print(f"    Generated growth_arc ({len(growth_arc)} chars)")
                
                # Validate generated content - must be substantial (at least 50 chars each)
                # Micro narratives skip outline and growth arc validation
                if self.is_micro_narrative():
                    outline_needs_retry = False
                    growth_arc_needs_retry = False
                else:
                    outline_needs_retry = not outline or len(outline) < 50 or is_placeholder_text(outline)
                    growth_arc_needs_retry = not growth_arc or len(growth_arc) < 50 or is_placeholder_text(growth_arc)
                
                if outline_needs_retry or growth_arc_needs_retry:
                    _safe_print(f"    Warning: Generated content for {char_name} is insufficient, retrying...")
                    _safe_print(f"      Outline issues: {outline_needs_retry} (length: {len(outline) if outline else 0})")
                    _safe_print(f"      Growth arc issues: {growth_arc_needs_retry} (length: {len(growth_arc) if growth_arc else 0})")
                    
                    # Retry with more context and explicit instructions
                    try:
                        # Build more detailed context for retry
                        enhanced_context = f"""
STORY CONTEXT:
{full_story_context}

CHARACTER TO DEVELOP: {char_name}
IMPORTANT: This character appears in the above story content. Please create a detailed profile based on their role and actions in the story.
"""
                        # Get all existing characters to avoid role duplication
                        other_characters = [char for char in existing_characters if isinstance(char, dict) and char.get("name", "").lower() != char_name.lower()]
                        char_details = self.ai_generator.regenerate_character_details(
                            premise=self.premise,
                            genres=self.genres,
                            atmosphere=self.atmosphere,
                            title=self.title,
                            main_storyline=enhanced_context,
                            character_name=char_name,
                            regenerate_type="both",
                            existing_characters=other_characters  # Pass existing characters to avoid duplication
                        )
                        outline = char_details.get("outline", "").strip()
                        growth_arc = char_details.get("growth_arc", "").strip()
                        physical_appearance = char_details.get("physical_appearance", physical_appearance or "").strip()
                        _safe_print(f"    Retry results - outline: {len(outline)} chars, growth_arc: {len(growth_arc)} chars")
                    except Exception as retry_e:
                        _safe_print(f"    Retry failed for {char_name}: {retry_e}")
                        import traceback
                        try:
                            traceback.print_exc()
                        except OSError:
                            pass
                
                # Final validation - if still invalid, try individual generation
                # Skip for micro narratives (no outline needed)
                if not self.is_micro_narrative() and (not outline or len(outline) < 50 or is_placeholder_text(outline)):
                    _safe_print(f"    Trying individual outline generation for {char_name}...")
                    try:
                        # Get all existing characters to avoid role duplication
                        other_characters = [char for char in existing_characters if isinstance(char, dict) and char.get("name", "").lower() != char_name.lower()]
                        outline_result = self.ai_generator.regenerate_character_details(
                            premise=self.premise,
                            genres=self.genres,
                            atmosphere=self.atmosphere,
                            title=self.title,
                            main_storyline=full_story_context,
                            character_name=char_name,
                            regenerate_type="outline",
                            existing_characters=other_characters  # Pass existing characters to avoid duplication
                        )
                        outline = outline_result.get("outline", "").strip()
                        _safe_print(f"    Individual outline result: {len(outline)} chars")
                    except Exception as e:
                        _safe_print(f"    Individual outline generation failed: {e}")
                
                if not self.is_micro_narrative() and (not growth_arc or len(growth_arc) < 50 or is_placeholder_text(growth_arc)):
                    _safe_print(f"    Trying individual growth arc generation for {char_name}...")
                    try:
                        # Get all existing characters to avoid role duplication
                        other_characters = [char for char in existing_characters if isinstance(char, dict) and char.get("name", "").lower() != char_name.lower()]
                        growth_result = self.ai_generator.regenerate_character_details(
                            premise=self.premise,
                            genres=self.genres,
                            atmosphere=self.atmosphere,
                            title=self.title,
                            main_storyline=full_story_context,
                            character_name=char_name,
                            regenerate_type="growth_arc",
                            existing_characters=other_characters  # Pass existing characters to avoid duplication
                        )
                        growth_arc = growth_result.get("growth_arc", "").strip()
                        _safe_print(f"    Individual growth arc result: {len(growth_arc)} chars")
                    except Exception as e:
                        _safe_print(f"    Individual growth arc generation failed: {e}")
                
                # Generate physical_appearance if missing or too short (e.g. from JSON parse fallback)
                if not physical_appearance or len(physical_appearance.strip()) < 50:
                    _safe_print(f"    Trying individual physical appearance generation for {char_name}...")
                    for attempt in range(3):  # Up to 3 attempts with retries
                        try:
                            other_characters = [char for char in existing_characters if isinstance(char, dict) and char.get("name", "").lower() != char_name.lower()]
                            phys_result = self.ai_generator.regenerate_character_details(
                                premise=self.premise,
                                genres=self.genres,
                                atmosphere=self.atmosphere,
                                title=self.title,
                                main_storyline=full_story_context,
                                character_name=char_name,
                                regenerate_type="physical_appearance",
                                existing_characters=other_characters,
                                character_outline=outline
                            )
                            physical_appearance = (phys_result.get("physical_appearance") or "").strip()
                            if physical_appearance and len(physical_appearance) >= 50:
                                _safe_print(f"    Individual physical appearance result: {len(physical_appearance)} chars")
                                break
                        except Exception as e:
                            _safe_print(f"    Physical appearance attempt {attempt + 1} failed: {e}")
                
                # Use fallback only if all attempts failed (skip for micro — no outline/arc needed)
                if not self.is_micro_narrative():
                    if not outline or len(outline) < 30:
                        _safe_print(f"    ERROR: All attempts failed for {char_name} outline, using fallback")
                        outline = f"{char_name} is an important character in this story. Their background, motivations, and relationships with other characters are integral to the narrative's development and resolution."
                    
                    if not growth_arc or len(growth_arc) < 30:
                        _safe_print(f"    ERROR: All attempts failed for {char_name} growth arc, using fallback")
                        growth_arc = f"{char_name} undergoes significant character development throughout the story. Their personal journey, challenges, and evolution contribute meaningfully to the overall narrative arc and thematic resolution."
                
                # Update or add character (store normalized name; use extracted name unless placeholder was replaced by AI)
                display_name = _normalize_character_name(char_name)
                if is_update and existing_char:
                    # Update existing character
                    existing_char["name"] = display_name
                    existing_char["outline"] = outline
                    existing_char["growth_arc"] = growth_arc
                    existing_char["physical_appearance"] = physical_appearance
                    _safe_print(f"    Updated profile for: {display_name}")
                else:
                    # Add new character (store normalized name; display_name already set above)
                    new_char = {
                        "name": display_name,
                        "outline": outline,
                        "growth_arc": growth_arc,
                        "physical_appearance": physical_appearance
                    }
                    existing_characters.append(new_char)
                    existing_char_map[display_name.lower()] = new_char
                    existing_char_names.add(display_name.lower())
                    _safe_print(f"    Added new character: {display_name}")
            except Exception as e:
                # If generation fails completely, log error and apply fallback
                _safe_print(f"    ERROR: Could not generate full outline for {char_name}: {e}")
                import traceback
                try:
                    traceback.print_exc()
                except OSError:
                    pass
                # Apply fallback so character always has outline/growth_arc
                display_name = _normalize_character_name(char_name)
                fallback_outline = f"{display_name} is an important character in this story. Their background, motivations, and relationships with other characters are integral to the narrative's development and resolution."
                fallback_growth_arc = f"{display_name} undergoes significant character development throughout the story. Their personal journey, challenges, and evolution contribute meaningfully to the overall narrative arc and thematic resolution."
                if is_update and existing_char:
                    existing_char["name"] = display_name
                    existing_char["outline"] = fallback_outline
                    existing_char["growth_arc"] = fallback_growth_arc
                    existing_char["physical_appearance"] = ""
                    _safe_print(f"    Applied fallback profile for: {display_name}")
                else:
                    new_char = {
                        "name": display_name,
                        "outline": fallback_outline,
                        "growth_arc": fallback_growth_arc,
                        "physical_appearance": ""
                    }
                    existing_characters.append(new_char)
                    existing_char_map[display_name.lower()] = new_char
                    existing_char_names.add(display_name.lower())
        
        target_character_count = getattr(self, 'character_count', 4)
        if len(existing_characters) > target_character_count:
            existing_characters = existing_characters[:target_character_count]
        current_character_count = len(existing_characters)
        additional_needed = max(0, target_character_count - current_character_count)
        
        _safe_print(f"After processing, have {current_character_count} characters (target {target_character_count}, generating {additional_needed} more)")
        
        # Get names of existing characters to avoid duplicates
        existing_names = {char.get("name", "").lower() for char in existing_characters}
        
        # Generate additional characters using AI with better prompts
        for i in range(additional_needed):
            try:
                # Create a comprehensive context for character generation
                character_context = f"""
STORY CONTEXT:
{full_story_context}

EXISTING CHARACTERS: {', '.join([char.get('name', '') for char in existing_characters])}

TASK: Create a new character that fits naturally into this story. The character should:
- Have a unique name not already used
- Complement the existing characters
- Have a meaningful role in the story
- Fit the genre and atmosphere
"""
                _safe_print(f"  Generating additional character {i+1}...")
                # Get all existing characters to avoid role duplication
                other_characters = [char for char in existing_characters if isinstance(char, dict)]
                char_details = self.ai_generator.regenerate_character_details(
                    premise=self.premise,
                    genres=self.genres,
                    atmosphere=self.atmosphere,
                    title=self.title,
                    main_storyline=character_context,
                    character_name=f"NewCharacter{i+1}",
                    regenerate_type="both",
                    existing_characters=other_characters  # Pass existing characters to avoid duplication
                )
                outline = char_details.get("outline", "").strip()
                growth_arc = char_details.get("growth_arc", "").strip()
                physical_appearance = char_details.get("physical_appearance", "").strip()
                # Use AI-returned name if present (no "Character1:" prefix); otherwise extract from outline
                char_name = _normalize_character_name(char_details.get("name", "") or "")
                if not char_name or char_name.lower() in existing_names or re.match(r"^(?:Character\s*\d+|NewCharacter\d+)$", char_name, re.IGNORECASE):
                    char_name = f"Character{current_character_count + i + 1}"  # Default fallback
                    # Try multiple patterns to extract the name from outline
                    name_patterns = [
                        r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',  # Name at start
                        r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+is\s+',  # "Name is..."
                        r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+serves\s+',  # "Name serves..."
                        r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*),\s+a\s+',  # "Name, a..."
                    ]
                    for pattern in name_patterns:
                        name_match = re.search(pattern, outline)
                        if name_match:
                            potential_name = name_match.group(1).strip()
                            if potential_name.lower() not in existing_names and potential_name not in ('Character', 'NewCharacter'):
                                char_name = potential_name
                                break
                _safe_print(f"    Generated content lengths - outline: {len(outline)}, growth_arc: {len(growth_arc)}")
                # Validate generated content
                if not outline or len(outline) < 50 or is_placeholder_text(outline):
                    _safe_print(f"    Generated outline is insufficient, retrying...")
                    other_characters = [char for char in existing_characters if isinstance(char, dict) and char.get("name", "").lower() != char_name.lower()]
                    retry_details = self.ai_generator.regenerate_character_details(
                        premise=self.premise,
                        genres=self.genres,
                        atmosphere=self.atmosphere,
                        title=self.title,
                        main_storyline=f"{character_context}\n\nIMPORTANT: Generate a detailed character description with specific background, motivations, and personality traits.",
                        character_name=char_name,
                        regenerate_type="outline",
                        existing_characters=other_characters  # Pass existing characters to avoid duplication
                    )
                    outline = retry_details.get("outline", outline)
                if not growth_arc or len(growth_arc) < 50 or is_placeholder_text(growth_arc):
                    _safe_print(f"    Generated growth arc is insufficient, retrying...")
                    other_characters = [char for char in existing_characters if isinstance(char, dict) and char.get("name", "").lower() != char_name.lower()]
                    retry_details = self.ai_generator.regenerate_character_details(
                        premise=self.premise,
                        genres=self.genres,
                        atmosphere=self.atmosphere,
                        title=self.title,
                        main_storyline=f"{character_context}\n\nIMPORTANT: Generate a detailed character growth arc showing their journey and development.",
                        character_name=char_name,
                        regenerate_type="growth_arc",
                        existing_characters=other_characters  # Pass existing characters to avoid duplication
                    )
                    growth_arc = retry_details.get("growth_arc", growth_arc)
                # Final validation and creation (store normalized name only, no "Character1:" prefix)
                if outline and growth_arc and not is_placeholder_text(outline) and not is_placeholder_text(growth_arc):
                    display_name = _normalize_character_name(char_name)
                    new_char = {
                        "name": display_name,
                        "outline": outline,
                        "growth_arc": growth_arc,
                        "physical_appearance": physical_appearance
                    }
                    existing_characters.append(new_char)
                    existing_names.add(display_name.lower())
                    _safe_print(f"    Successfully created character: {display_name}")
                else:
                    _safe_print(f"    Failed to generate valid character {i+1} - using enhanced fallback")
                    display_name = _normalize_character_name(char_name)
                    fallback_char = {
                        "name": display_name,
                        "outline": f"{display_name} is a supporting character in this {', '.join(self.genres)} story. They play an important role in the narrative, bringing unique perspective and skills that help drive the plot forward. Their background and motivations are deeply connected to the main story events, making them integral to the character dynamics and story resolution.",
                        "growth_arc": f"{display_name} begins the story with specific goals and challenges that align with the narrative themes. Throughout the story, they face obstacles that test their resolve and force them to grow. Their character development parallels the main plot, and by the story's end, they have evolved in meaningful ways that contribute to the overall resolution and thematic message.",
                        "physical_appearance": ""
                    }
                    existing_characters.append(fallback_char)
                    existing_names.add(display_name.lower())
                    _safe_print(f"    Created fallback character: {display_name}")
            except Exception as e:
                _safe_print(f"    Error generating additional character {i+1}: {e}")
                import traceback
                try:
                    traceback.print_exc()
                except OSError:
                    pass
        
        # Deduplicate and update outline data
        self.outline_data["characters"] = self._deduplicate_characters(existing_characters)
        existing_characters = self.outline_data["characters"]
        
        # VALIDATION CHECK (REQUIRED): After Wizard generation, number of characters must equal selected
        target_character_count = getattr(self, 'character_count', 4)
        if target_character_count > 0:
            current_count = len(existing_characters)
            if current_count != target_character_count:
                _safe_print(f"Wizard character validation: expected {target_character_count} characters, got {current_count}; enforcing.")
                if current_count > target_character_count:
                    existing_characters = existing_characters[:target_character_count]
                else:
                    # Pad with placeholders (should rarely happen when using declared list)
                    while len(existing_characters) < target_character_count:
                        idx = len(existing_characters) + 1
                        existing_characters.append({
                            "name": f"Character{idx}",
                            "outline": "",
                            "growth_arc": "",
                            "physical_appearance": ""
                        })
                self.outline_data["characters"] = existing_characters
            else:
                _safe_print(f"Wizard character validation: character count == selected ({target_character_count}).")
        
        # Populate character list UI
        self.character_list.clear()
        self.current_character_index = -1
        
        # Temporarily disconnect to prevent signal during population
        try:
            self.character_list.currentItemChanged.disconnect()
        except TypeError:
            pass
        
        for char in existing_characters:
            if not isinstance(char, dict):
                continue
            name = _normalize_character_name(str(char.get("name", "Unnamed Character")))
            item = QListWidgetItem(name)
            self.character_list.addItem(item)
        
        # Reconnect signal
        self.character_list.currentItemChanged.connect(self.on_character_selected)
        
        # Select first character if available
        if self.character_list.count() > 0:
            self.character_list.setCurrentRow(0)
            current_item = self.character_list.currentItem()
            if current_item:
                self.on_character_selected(current_item, None)
        
    def generate_characters_now(self):
        """Manually trigger character generation from current story content.
        
        Fills outline, growth arc, and physical appearance for all main characters via AI.
        """
        if not self.ai_generator or not self.outline_data:
            QMessageBox.warning(self, "Cannot Generate Characters", "Story content is not available. Please generate the outline first.")
            return
        
        # Check if we have enough content
        main_storyline = str(self.outline_data.get("main_storyline", "")).strip()
        subplots = str(self.outline_data.get("subplots", "")).strip()
        conclusion = str(self.outline_data.get("conclusion", "")).strip()
        
        if not main_storyline or not conclusion:
            QMessageBox.warning(self, "Incomplete Story", "Please ensure the storyline and conclusion are generated before creating characters.")
            return
        
        # Disable button during generation
        if hasattr(self, 'generate_character_details_button'):
            self.generate_character_details_button.setEnabled(False)
            self.generate_character_details_button.setText("Generating...")
        
        _safe_print("Manual character generation requested...")
        
        # Show progress dialog for character generation
        char_progress = QProgressDialog(
            "AI is generating character profiles...\n\nThis may take a moment as the AI creates detailed character outlines and growth arcs for all characters.",
            None,  # No cancel button
            0,
            0,
            self
        )
        char_progress.setWindowModality(Qt.WindowModality.ApplicationModal)  # Application modal to ensure visibility
        char_progress.setMinimumDuration(0)  # Show immediately
        char_progress.setWindowTitle("Generating Characters")
        char_progress.setCancelButton(None)  # No cancel for now
        char_progress.setMinimum(0)
        char_progress.setMaximum(0)  # Indeterminate progress
        char_progress.setValue(0)
        
        # Ensure dialog is visible and on top
        char_progress.show()
        char_progress.raise_()
        char_progress.activateWindow()
        
        # Force the dialog to be processed and displayed
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        
        try:
            self._generate_characters_from_content()
        except Exception as e:
            # Close progress dialog on error
            char_progress.close()
            if hasattr(self, 'generate_character_details_button'):
                self.generate_character_details_button.setEnabled(True)
                self.generate_character_details_button.setText("Generate Character Details")
            QMessageBox.critical(self, "Character Generation Error", 
                               f"An error occurred while generating characters:\n\n{str(e)}")
            return
        
        # Close progress dialog after generation completes
        char_progress.close()
        
        # Re-enable button
        if hasattr(self, 'generate_character_details_button'):
            self.generate_character_details_button.setEnabled(True)
            self.generate_character_details_button.setText("Generate Character Details")
    
    def on_outline_error(self, error_message: str):
        """Handle outline generation error."""
        QMessageBox.critical(self, "Generation Failed", f"Failed to generate story outline:\n{error_message}")
        self.generate_button.setText("Expand Premise")
        self.generate_button.setEnabled(True)
        
        # Close progress dialog
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
    
    def regenerate_subplots(self):
        """Regenerate just the subplots using AI."""
        if not self.ai_generator:
            QMessageBox.warning(self, "AI Not Available", "AI generator is not configured.")
            return
        
        if not self.premise:
            QMessageBox.warning(self, "No Premise", "Please complete Step 2 first.")
            return
        
        # Get current outline data
        main_storyline = self.main_storyline_edit.toPlainText().strip()
        characters = self.outline_data.get("characters", [])
        
        # Disable button during generation
        if hasattr(self, 'regenerate_subplots_button'):
            self.regenerate_subplots_button.setEnabled(False)
            self.regenerate_subplots_button.setText("Regenerating...")
        
        # Show progress dialog
        self.progress_dialog = QProgressDialog("Regenerating subplots with AI...", None, 0, 0, self)
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setCancelButton(None)
        self.progress_dialog.setWindowTitle("Regenerating Subplots")
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setValue(0)
        self.progress_dialog.show()
        
        # Process events
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        
        # Clean up any existing thread
        if self.subplots_thread and self.subplots_thread.isRunning():
            self.subplots_thread.terminate()
            self.subplots_thread.wait()
        
        # Create and start generation thread
        self.subplots_thread = SubplotsRegenerationThread(
            self.ai_generator, self.premise, self.title, self.genres, 
            self.atmosphere, main_storyline, characters
        )
        self.subplots_thread.finished.connect(self.on_subplots_regenerated)
        self.subplots_thread.error.connect(self.on_subplots_error)
        self.subplots_thread.start()
    
    def on_subplots_regenerated(self, subplots: str):
        """Handle successful subplots regeneration."""
        # Close progress dialog
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
        
        # Set the subplots
        self.subplots_edit.setPlainText(subplots.strip())
        
        # Update outline_data
        if not isinstance(self.outline_data, dict):
            self.outline_data = {}
        self.outline_data["subplots"] = subplots.strip()
        
        # Re-enable button
        if hasattr(self, 'regenerate_subplots_button'):
            self.regenerate_subplots_button.setText("Regenerate Subplots")
            self.regenerate_subplots_button.setEnabled(True)
        
        self.on_outline_changed()
    
    def on_subplots_error(self, error_message: str):
        """Handle subplots regeneration error."""
        QMessageBox.critical(self, "Generation Failed", f"Failed to regenerate subplots:\n{error_message}")
        
        # Re-enable button
        if hasattr(self, 'regenerate_subplots_button'):
            self.regenerate_subplots_button.setText("Regenerate Subplots")
            self.regenerate_subplots_button.setEnabled(True)
        
        # Close progress dialog
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
    
    def regenerate_conclusion(self):
        """Regenerate just the conclusion using AI."""
        if not self.ai_generator:
            QMessageBox.warning(self, "AI Not Available", "AI generator is not configured.")
            return
        
        if not self.premise:
            QMessageBox.warning(self, "No Premise", "Please complete Step 2 first.")
            return
        
        # Get current outline data
        main_storyline = self.main_storyline_edit.toPlainText().strip()
        subplots = self.subplots_edit.toPlainText().strip()
        characters = self.outline_data.get("characters", [])
        
        # Disable button during generation
        if hasattr(self, 'regenerate_conclusion_button'):
            self.regenerate_conclusion_button.setEnabled(False)
            self.regenerate_conclusion_button.setText("Regenerating...")
        
        # Show progress dialog
        self.progress_dialog = QProgressDialog("Regenerating conclusion with AI...", None, 0, 0, self)
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setCancelButton(None)
        self.progress_dialog.setWindowTitle("Regenerating Conclusion")
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setValue(0)
        self.progress_dialog.show()
        
        # Process events
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        
        # Clean up any existing thread
        if self.conclusion_thread and self.conclusion_thread.isRunning():
            self.conclusion_thread.terminate()
            self.conclusion_thread.wait()
        
        # Create and start generation thread
        self.conclusion_thread = ConclusionRegenerationThread(
            self.ai_generator, self.premise, self.title, self.genres, 
            self.atmosphere, main_storyline, subplots, characters
        )
        self.conclusion_thread.finished.connect(self.on_conclusion_regenerated)
        self.conclusion_thread.error.connect(self.on_conclusion_error)
        self.conclusion_thread.start()
    
    def on_conclusion_regenerated(self, conclusion: str):
        """Handle successful conclusion regeneration."""
        # Close progress dialog
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
        
        # Set the conclusion
        self.conclusion_edit.setPlainText(conclusion.strip())
        
        # Update outline_data
        if not isinstance(self.outline_data, dict):
            self.outline_data = {}
        self.outline_data["conclusion"] = conclusion.strip()
        
        # Populate character names only (no AI generation). User can click "Generate Character Details" when ready.
        self._populate_character_names_only()
        
        # Re-enable button
        if hasattr(self, 'regenerate_conclusion_button'):
            self.regenerate_conclusion_button.setText("Regenerate Conclusion")
            self.regenerate_conclusion_button.setEnabled(True)
        
        # Scroll to conclusion so user sees it (characters are below and would otherwise be visible)
        if hasattr(self, 'scroll_area') and self.scroll_area and hasattr(self, 'conclusion_edit'):
            self.scroll_area.ensureWidgetVisible(self.conclusion_edit)
        
        self.on_outline_changed()
    
    def on_conclusion_error(self, error_message: str):
        """Handle conclusion regeneration error."""
        QMessageBox.critical(self, "Generation Failed", f"Failed to regenerate conclusion:\n{error_message}")
        
        # Re-enable button
        if hasattr(self, 'regenerate_conclusion_button'):
            self.regenerate_conclusion_button.setText("Regenerate Conclusion")
            self.regenerate_conclusion_button.setEnabled(True)
        
        # Close progress dialog
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
    
    def set_editing_enabled(self, enabled: bool):
        """Enable or disable editing of outline sections."""
        self.subplots_edit.setReadOnly(not enabled)
        self.conclusion_edit.setReadOnly(not enabled)
        self.char_name_edit.setReadOnly(not enabled)
        self.char_outline_edit.setReadOnly(not enabled)
        self.char_growth_edit.setReadOnly(not enabled)
        self.char_physical_edit.setReadOnly(not enabled)
        self.character_list.setEnabled(enabled)
        if hasattr(self, 'regenerate_conclusion_button'):
            self.regenerate_conclusion_button.setEnabled(enabled)
        if hasattr(self, 'generate_character_details_button'):
            self.generate_character_details_button.setEnabled(enabled)
    
    def on_character_selected(self, current: QListWidgetItem, previous: QListWidgetItem):
        """Handle character selection change."""
        if not current:
            return
        
        # Save previous character data
        if previous and self.current_character_index >= 0:
            try:
                self.save_current_character()
            except Exception as e:
                # Log error but don't crash
                _safe_print(f"Error saving character: {e}")
        
        # Load new character data
        try:
            index = self.character_list.row(current)
            if index < 0:
                return
            
            self.current_character_index = index
            
            if not isinstance(self.outline_data, dict):
                self.outline_data = {}
            
            characters = self.outline_data.get("characters", [])
            if not isinstance(characters, list):
                characters = []
                self.outline_data["characters"] = characters
            
            if 0 <= index < len(characters):
                char = characters[index]
                if isinstance(char, dict):
                    self.char_name_edit.setPlainText(str(char.get("name", "")))
                    self.char_outline_edit.setPlainText(str(char.get("outline", "")))
                    self.char_growth_edit.setPlainText(str(char.get("growth_arc", "")))
                    self.char_physical_edit.setPlainText(str(char.get("physical_appearance", "")))

                    # Lock name and physical appearance for bible characters
                    is_bible = self._is_bible_character(str(char.get("name", "")))
                    self.char_name_edit.setReadOnly(is_bible)
                    self.char_physical_edit.setReadOnly(is_bible)
                    if is_bible:
                        locked_style = "background-color: #f0f0f0; color: #555;"
                        self.char_name_edit.setStyleSheet(locked_style)
                        self.char_physical_edit.setStyleSheet(locked_style)
                    else:
                        self.char_name_edit.setStyleSheet("")
                        self.char_physical_edit.setStyleSheet("")
                else:
                    self.char_name_edit.clear()
                    self.char_outline_edit.clear()
                    self.char_growth_edit.clear()
                    self.char_physical_edit.clear()
                    self.char_name_edit.setReadOnly(False)
                    self.char_physical_edit.setReadOnly(False)
                    self.char_name_edit.setStyleSheet("")
                    self.char_physical_edit.setStyleSheet("")
            else:
                self.char_name_edit.clear()
                self.char_outline_edit.clear()
                self.char_growth_edit.clear()
                self.char_physical_edit.clear()
                self.char_name_edit.setReadOnly(False)
                self.char_physical_edit.setReadOnly(False)
                self.char_name_edit.setStyleSheet("")
                self.char_physical_edit.setStyleSheet("")
        except Exception as e:
            # Prevent crash on error
            _safe_print(f"Error loading character: {e}")
            self.char_name_edit.clear()
            self.char_outline_edit.clear()
            self.char_growth_edit.clear()
            self.char_physical_edit.clear()
    
    def save_current_character(self):
        """Save current character data to outline_data."""
        if self.current_character_index < 0:
            return
        
        try:
            if not isinstance(self.outline_data, dict):
                self.outline_data = {}
            
            characters = self.outline_data.get("characters", [])
            if not isinstance(characters, list):
                characters = []
                self.outline_data["characters"] = characters
            
            # Ensure list is large enough
            while len(characters) <= self.current_character_index:
                characters.append({"name": "", "outline": "", "growth_arc": "", "physical_appearance": ""})
            
            if 0 <= self.current_character_index < len(characters):
                existing = characters[self.current_character_index] if isinstance(characters[self.current_character_index], dict) else {}
                characters[self.current_character_index] = {
                    "name": self.char_name_edit.toPlainText().strip(),
                    "outline": self.char_outline_edit.toPlainText().strip(),
                    "growth_arc": self.char_growth_edit.toPlainText().strip(),
                    "physical_appearance": self.char_physical_edit.toPlainText().strip()
                }
                # Update list item name
                item = self.character_list.item(self.current_character_index)
                if item:
                    name = characters[self.current_character_index]["name"] or "Unnamed Character"
                    item.setText(name)
        except Exception as e:
            _safe_print(f"Error saving character: {e}")
    
    def on_character_data_changed(self):
        """Handle character data changes."""
        if self.current_character_index >= 0:
            self.save_current_character()
            self.on_outline_changed()
    
    def on_outline_changed(self):
        """Handle outline data changes."""
        # Ensure outline_data is a dict
        if not isinstance(self.outline_data, dict):
            self.outline_data = {}
        
        # Update outline_data with current UI values
        self.outline_data["main_storyline"] = self.main_storyline_edit.toPlainText().strip()
        self.outline_data["subplots"] = self.subplots_edit.toPlainText().strip()
        self.outline_data["conclusion"] = self.conclusion_edit.toPlainText().strip()
    
    def on_premise_changed(self):
        """Handle premise text changes - allows user to edit the premise in Step 3."""
        # Update the stored premise with the edited text
        self.premise = self.premise_text.toPlainText().strip()
        
        # Save current character before emitting
        if self.current_character_index >= 0:
            self.save_current_character()
        
        self.outline_ready.emit()
    
    def is_valid(self) -> bool:
        """Check if outline step is valid based on workflow profile."""
        # Get current values from UI (user may have edited them)
        main_storyline = self.main_storyline_edit.toPlainText().strip()
        
        # Main storyline is always required
        if not main_storyline:
            return False
        
        if self.workflow_profile == WorkflowProfile.PROMOTIONAL:
            # For promotional, core message is required
            core_message = self.core_message_edit.toPlainText().strip()
            return bool(core_message)
        elif self.workflow_profile == WorkflowProfile.EXPERIMENTAL:
            # For experimental, concept is required
            concept = self.core_message_edit.toPlainText().strip()
            return bool(concept)
        else:
            # For narrative, conclusion and characters are required
            conclusion = self.conclusion_edit.toPlainText().strip()
            if not conclusion:
                return False
            
            # Check if at least one character exists
            characters = self.outline_data.get("characters", [])
            if not isinstance(characters, list) or len(characters) == 0:
                return False
            
            return True
    
    def get_outline_data(self) -> Dict[str, Any]:
        """Get outline data from this step based on workflow profile."""
        # Ensure outline_data is a dict
        if not isinstance(self.outline_data, dict):
            self.outline_data = {}
        
        # Ensure current character is saved (only for narrative)
        if self.current_character_index >= 0 and self.workflow_profile == WorkflowProfile.NARRATIVE:
            self.save_current_character()
        
        # Update from UI based on workflow profile
        if self.workflow_profile == WorkflowProfile.PROMOTIONAL:
            # Return promotional structure
            return {
                "main_storyline": self.main_storyline_edit.toPlainText().strip(),
                "core_message": self.core_message_edit.toPlainText().strip(),
                "emotional_beats": self.emotional_beats_edit.toPlainText().strip(),
                "visual_motifs": self.visual_motifs_edit.toPlainText().strip(),
                "call_to_action": self.call_to_action_edit.toPlainText().strip(),
                "subplots": "",
                "conclusion": "",
                "characters": [],
                "locations": []
            }
        elif self.workflow_profile == WorkflowProfile.EXPERIMENTAL:
            # Return experimental structure
            return {
                "main_storyline": self.main_storyline_edit.toPlainText().strip(),
                "concept": self.core_message_edit.toPlainText().strip(),
                "visual_themes": self.visual_motifs_edit.toPlainText().strip(),
                "mood_progression": self.emotional_beats_edit.toPlainText().strip(),
                "subplots": "",
                "conclusion": "",
                "characters": [],
                "locations": []
            }
        else:
            # Return narrative structure
            self.outline_data["main_storyline"] = self.main_storyline_edit.toPlainText().strip()
            self.outline_data["subplots"] = self.subplots_edit.toPlainText().strip()
            self.outline_data["conclusion"] = self.conclusion_edit.toPlainText().strip()
            # Location registry: re-extract underlined locations from current narrative (Wizard entity markup)
            if getattr(self, "ai_generator", None):
                combined = "\n\n".join([
                    self.outline_data.get("main_storyline", ""),
                    self.outline_data.get("subplots", ""),
                    self.outline_data.get("conclusion", ""),
                ])
                self.outline_data["locations"] = self.ai_generator._extract_locations_from_text(combined, max_locations=50)
                passed, issues = self.ai_generator._validate_entity_markup(combined)
                if not passed and issues:
                    _safe_print("Wizard entity markup validation:", "; ".join(issues))
            return self.outline_data

    def has_characters_missing_physical_appearance(self) -> bool:
        """Return True if any narrative character has empty or too-short physical appearance."""
        if self.workflow_profile != WorkflowProfile.NARRATIVE:
            return False
        characters = self.outline_data.get("characters", []) or []
        for c in characters:
            if isinstance(c, dict):
                phys = str(c.get("physical_appearance", "") or "").strip()
                if not phys or len(phys) < 50:
                    return True
        return False

    def ensure_missing_physical_appearances(self, on_done, on_error):
        """Generate physical appearance for characters that are missing it. Calls on_done() when finished, on_error(msg) on failure."""
        if not self.ai_generator or self.workflow_profile != WorkflowProfile.NARRATIVE:
            on_done()
            return
        characters = self.outline_data.get("characters", []) or []
        indices_needing = []
        for i, c in enumerate(characters):
            if isinstance(c, dict):
                phys = str(c.get("physical_appearance", "") or "").strip()
                if not phys or len(phys) < 50:
                    indices_needing.append(i)
        if not indices_needing:
            on_done()
            return
        if self.batch_physical_thread and self.batch_physical_thread.isRunning():
            on_error("A batch generation is already in progress.")
            return

        main_storyline = str(self.outline_data.get("main_storyline", ""))
        progress = QProgressDialog(
            f"Generating physical appearance for {len(indices_needing)} character(s)...",
            None, 0, len(indices_needing), self
        )
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)
        progress.setValue(0)
        progress.show()

        def on_progress(idx, done, total, result):
            progress.setValue(done)
            progress.setLabelText(f"Generating physical appearance ({done} of {total})...")
            if 0 <= idx < len(characters) and "physical_appearance" in result and result.get("physical_appearance") is not None:
                characters[idx]["physical_appearance"] = result["physical_appearance"]
            if self.character_list.currentRow() == idx and hasattr(self, "char_physical_edit"):
                if result.get("physical_appearance"):
                    self.char_physical_edit.setPlainText(result["physical_appearance"])

        def on_finished():
            progress.close()
            self.batch_physical_thread = None
            on_done()

        def on_err(msg):
            progress.close()
            self.batch_physical_thread = None
            on_error(msg)

        self.batch_physical_thread = BatchPhysicalAppearanceForOutlineThread(
            self.ai_generator, self.premise, self.title, self.genres, self.atmosphere,
            main_storyline, characters, indices_needing
        )
        self.batch_physical_thread.progress.connect(on_progress)
        self.batch_physical_thread.finished_all.connect(on_finished)
        self.batch_physical_thread.error.connect(on_err)
        self.batch_physical_thread.start()

